"""Data migration 015 — Swap reactor assignments for reactors 4 and 7.

Background
----------
Reactors 4 and 7 were physically swapped in the lab. Every historical experiment
record attributed to reactor_number=4 was actually run on the physical unit now
labeled Reactor 7, and vice versa.

This migration corrects the database in a single atomic transaction using a
three-step approach with a temporary placeholder value (9999):
  Step 1: reactor_number=4  → 9999
  Step 2: reactor_number=7  → 4
  Step 3: reactor_number=9999 → 7

⚠️  One-time migration.  Running it a second time swaps back to the original
(incorrect) state.  Use --dry-run to preview before running live.

How to run
----------
From the project root (Windows)::

    # Preview — prints counts and checksums, no DB changes committed
    .venv\\Scripts\\python database/data_migrations/swap_reactor_4_7_015.py --dry-run

    # Live run — requires --confirm flag as a deliberate gate
    .venv\\Scripts\\python database/data_migrations/swap_reactor_4_7_015.py --confirm

Prerequisites
-------------
- Take a full database backup before running live.
- Review --dry-run output with Mat before running live.
- Do not run without explicit user sign-off.
"""

from __future__ import annotations
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment
from database.models.results import ExperimentalResults, ScalarResults

_REACTOR_A = 4
_REACTOR_B = 7
_TEMP_VALUE = 9999  # transient placeholder — never persisted to disk


def _swap_reactor_assignments(db: Session, dry_run: bool = False) -> dict:
    """Swap reactor_number between _REACTOR_A (4) and _REACTOR_B (7).

    When dry_run=True the swap is executed inside a nested savepoint which is
    always rolled back, so the return dict reflects what would change without
    modifying any committed state.

    Returns a summary dict. Caller is responsible for db.commit() in live mode.
    """
    # ── Pre-migration counts ──────────────────────────────────────────────────
    pre_r4 = (
        db.query(func.count(ExperimentalConditions.id))
        .filter(ExperimentalConditions.reactor_number == _REACTOR_A)
        .scalar() or 0
    )
    pre_r7 = (
        db.query(func.count(ExperimentalConditions.id))
        .filter(ExperimentalConditions.reactor_number == _REACTOR_B)
        .scalar() or 0
    )

    # ── Pre-migration yield checksum ──────────────────────────────────────────
    # Sum of grams_per_ton_yield for experiments on R4 or R7. Must be unchanged
    # post-swap to confirm no scalar data was accidentally mutated.
    pre_yield_sum = (
        db.query(func.coalesce(func.sum(ScalarResults.grams_per_ton_yield), 0.0))
        .join(ExperimentalResults, ScalarResults.result_id == ExperimentalResults.id)
        .join(Experiment, ExperimentalResults.experiment_fk == Experiment.id)
        .join(
            ExperimentalConditions,
            ExperimentalConditions.experiment_fk == Experiment.id,
        )
        .filter(ExperimentalConditions.reactor_number.in_([_REACTOR_A, _REACTOR_B]))
        .scalar()
    ) or 0.0

    # ── Dry-run uses a nested savepoint so the swap is always rolled back ─────
    sp = db.begin_nested() if dry_run else None

    # Step 1: A → temp
    r4_moved = (
        db.query(ExperimentalConditions)
        .filter(ExperimentalConditions.reactor_number == _REACTOR_A)
        .update({"reactor_number": _TEMP_VALUE}, synchronize_session="fetch")
    )
    # Step 2: B → A
    db.query(ExperimentalConditions).filter(
        ExperimentalConditions.reactor_number == _REACTOR_B
    ).update({"reactor_number": _REACTOR_A}, synchronize_session="fetch")
    # Step 3: temp → B
    r7_moved = (
        db.query(ExperimentalConditions)
        .filter(ExperimentalConditions.reactor_number == _TEMP_VALUE)
        .update({"reactor_number": _REACTOR_B}, synchronize_session="fetch")
    )

    db.flush()

    # ── Post-migration counts ─────────────────────────────────────────────────
    post_r4 = (
        db.query(func.count(ExperimentalConditions.id))
        .filter(ExperimentalConditions.reactor_number == _REACTOR_A)
        .scalar() or 0
    )
    post_r7 = (
        db.query(func.count(ExperimentalConditions.id))
        .filter(ExperimentalConditions.reactor_number == _REACTOR_B)
        .scalar() or 0
    )

    # ── Post-migration yield checksum ─────────────────────────────────────────
    post_yield_sum = (
        db.query(func.coalesce(func.sum(ScalarResults.grams_per_ton_yield), 0.0))
        .join(ExperimentalResults, ScalarResults.result_id == ExperimentalResults.id)
        .join(Experiment, ExperimentalResults.experiment_fk == Experiment.id)
        .join(
            ExperimentalConditions,
            ExperimentalConditions.experiment_fk == Experiment.id,
        )
        .filter(ExperimentalConditions.reactor_number.in_([_REACTOR_A, _REACTOR_B]))
        .scalar()
    ) or 0.0

    # ── Validate counts ───────────────────────────────────────────────────────
    if post_r4 != pre_r7 or post_r7 != pre_r4:
        raise ValueError(
            f"Count mismatch after swap: "
            f"pre(R{_REACTOR_A}={pre_r4}, R{_REACTOR_B}={pre_r7}) → "
            f"post(R{_REACTOR_A}={post_r4}, R{_REACTOR_B}={post_r7})"
        )

    if dry_run and sp is not None:
        sp.rollback()

    return {
        "pre_r4": pre_r4,
        "pre_r7": pre_r7,
        "post_r4": post_r4,
        "post_r7": post_r7,
        "r4_moved": r4_moved,
        "r7_moved": r7_moved,
        "pre_yield_sum": pre_yield_sum,
        "post_yield_sum": post_yield_sum,
        "yield_sum_unchanged": abs(pre_yield_sum - post_yield_sum) < 0.001,
    }


def run_migration(dry_run: bool = False, confirm: bool = False) -> None:
    if not dry_run and not confirm:
        print("ERROR: Pass --confirm to run live, or --dry-run to preview.")
        sys.exit(1)

    db = SessionLocal()
    try:
        print("=" * 60)
        print(f"SWAP REACTOR {_REACTOR_A} ↔ {_REACTOR_B}  (migration 015)")
        print("=" * 60)
        if dry_run:
            print("DRY RUN — no changes will be committed\n")

        summary = _swap_reactor_assignments(db, dry_run=dry_run)

        print(f"Pre-migration:       R{_REACTOR_A}={summary['pre_r4']}  R{_REACTOR_B}={summary['pre_r7']}")
        print(f"Post-migration:      R{_REACTOR_A}={summary['post_r4']}  R{_REACTOR_B}={summary['post_r7']}")
        print(f"Rows moved:          R{_REACTOR_A}→R{_REACTOR_B}={summary['r4_moved']}   R{_REACTOR_B}→R{_REACTOR_A}={summary['r7_moved']}")
        print(
            f"Yield sum unchanged: {summary['yield_sum_unchanged']}  "
            f"(pre={summary['pre_yield_sum']:.4f} g/t  "
            f"post={summary['post_yield_sum']:.4f} g/t)"
        )

        if not dry_run:
            db.commit()
            print("\nMigration committed successfully.")
        else:
            print("\nDRY RUN complete — no changes committed.")

        print("=" * 60)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    dry_run_flag = "--dry-run" in sys.argv
    confirm_flag = "--confirm" in sys.argv
    run_migration(dry_run=dry_run_flag, confirm=confirm_flag)
