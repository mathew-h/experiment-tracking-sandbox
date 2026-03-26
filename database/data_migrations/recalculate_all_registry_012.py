"""Data migration 012 — Backfill all calculated fields using the M3 registry.

What it does
------------
Iterates every ExperimentalConditions row and every ChemicalAdditive row in the
database and recomputes all derived fields by calling the M3 calculation registry
(``backend.services.calculations.registry.recalculate``).

Execution order
---------------
1. **Conditions pass** — ``_backfill_conditions`` calls ``recalculate(conditions, db)``
   for every ExperimentalConditions row.  The conditions calculator internally
   propagates to all linked ScalarResults (``conditions_calcs.py`` calls
   ``recalculate_scalar`` for every result attached to the experiment), so scalar
   fields such as ``grams_per_ton_yield`` and ``ferrous_iron_yield`` are refreshed
   as a side-effect.

2. **Additives sub-pass** — still inside ``_backfill_conditions``, each
   ChemicalAdditive attached to the conditions row is recalculated independently
   (``recalculate(additive, db)``), writing ``mass_in_grams``, ``moles_added``,
   catalyst fields, etc.

3. **Scalar safety-net pass** (implemented in Task 2, ``_backfill_scalars``) — an
   explicit pass over every ScalarResults row ensures any row whose parent
   conditions had no results at the time of the conditions pass is still updated.

Independent ferrous-iron columns
---------------------------------
``ExperimentalConditions.total_ferrous_iron_g`` and
``ExperimentalConditions.total_ferrous_iron`` are **independent**.
- ``total_ferrous_iron_g`` is written by the conditions calculator from rock
  elemental data (FeO wt% lookup).
- ``total_ferrous_iron`` (old column) is read by the scalar calculator for the
  ferrous iron yield % — it is NOT touched by this migration.

How to run
----------
From the project root (Windows)::

    .venv\\Scripts\\python database/data_migrations/recalculate_all_registry_012.py

Dry-run (reads and recalculates in memory but does not commit)::

    .venv\\Scripts\\python database/data_migrations/recalculate_all_registry_012.py --dry-run
"""

import sys
import os

# ---------------------------------------------------------------------------
# sys.path bootstrap — make project root importable regardless of cwd
# ---------------------------------------------------------------------------
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ---------------------------------------------------------------------------
# Register all calculators by importing the calculations package
# ---------------------------------------------------------------------------
import backend.services.calculations as _calcs  # noqa: F401 — registers all calculators
from backend.services.calculations.registry import recalculate

from sqlalchemy.orm import Session, joinedload
from database import SessionLocal
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment
from database.models.results import ExperimentalResults

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHUNK_SIZE = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunked(lst: list, size: int):
    """Yield successive chunks of *size* from *lst*."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _backfill_conditions(db: Session, dry_run: bool = False) -> tuple[int, int]:
    """Recalculate all ExperimentalConditions and their ChemicalAdditives.

    For each conditions row:
    - Calls ``recalculate(conditions, db)``, which writes ``water_to_rock_ratio``,
      ``total_ferrous_iron_g``, and propagates to linked ScalarResults.
    - Calls ``recalculate(additive, db)`` for every linked ChemicalAdditive.

    Uses broad joinedload to prevent N+1 queries when the conditions calculator
    walks the experiment → results → scalar_data chain internally.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    dry_run:
        When True, recalculations are performed in memory but the session is
        never committed (changes are discarded at the end of each chunk).

    Returns
    -------
    tuple[int, int]
        ``(cond_ok, add_ok)`` — counts of successfully recalculated conditions
        rows and additive rows respectively.
    """
    all_conditions: list[ExperimentalConditions] = (
        db.query(ExperimentalConditions)
        .options(
            joinedload(ExperimentalConditions.chemical_additives),
            joinedload(ExperimentalConditions.experiment)
            .joinedload(Experiment.results)
            .joinedload(ExperimentalResults.scalar_data),
        )
        .all()
    )

    cond_ok = 0
    cond_err = 0
    add_ok = 0
    add_err = 0

    for chunk_idx, chunk in enumerate(_chunked(all_conditions, CHUNK_SIZE), start=1):
        chunk_cond_ok = 0
        chunk_cond_err = 0
        chunk_add_ok = 0
        chunk_add_err = 0

        for conditions in chunk:
            # --- recalculate conditions row ---
            try:
                recalculate(conditions, db)
                chunk_cond_ok += 1
            except Exception as exc:
                print(f"[WARN] conditions id={conditions.id} ({conditions.experiment_id}): {exc}")
                chunk_cond_err += 1

            # --- recalculate each linked additive ---
            for additive in getattr(conditions, 'chemical_additives', None) or []:
                try:
                    recalculate(additive, db)
                    chunk_add_ok += 1
                except Exception as exc:
                    print(f"[WARN] additive id={additive.id} on conditions id={conditions.id}: {exc}")
                    chunk_add_err += 1

        # commit or rollback after each chunk
        if dry_run:
            db.rollback()
        else:
            db.commit()

        cond_ok += chunk_cond_ok
        cond_err += chunk_cond_err
        add_ok += chunk_add_ok
        add_err += chunk_add_err

        print(
            f"[INFO] Chunk {chunk_idx}: "
            f"conditions ok={chunk_cond_ok} err={chunk_cond_err} | "
            f"additives ok={chunk_add_ok} err={chunk_add_err}"
        )

    print(
        f"[INFO] _backfill_conditions complete — "
        f"conditions ok={cond_ok} err={cond_err} | "
        f"additives ok={add_ok} err={add_err}"
        + (" (DRY RUN — nothing committed)" if dry_run else "")
    )
    return cond_ok, add_ok


# ---------------------------------------------------------------------------
# Script entrypoint (Task 2 adds run_migration and _backfill_scalars)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Migration 012: backfill all calculated fields via M3 registry."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Recalculate in memory only; do not commit changes.",
    )
    args = parser.parse_args()

    db: Session = SessionLocal()
    try:
        print("=== Migration 012: recalculate_all_registry ===")
        if args.dry_run:
            print("[INFO] DRY RUN mode — no changes will be committed.")
        _backfill_conditions(db, dry_run=args.dry_run)
    except Exception as exc:
        print(f"[ERROR] Migration aborted: {exc}")
        db.rollback()
    finally:
        db.close()
        print("=== Migration 012 finished ===")
