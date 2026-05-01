"""Data migration 014 — Backfill cumulative_time_post_reaction_days.

What it does
------------
After the experiment lineage assignment was corrected (parent_experiment_fk /
base_experiment_id), cumulative_time_post_reaction_days on existing
ExperimentalResults rows was not recalculated — that field is only written
when results are inserted or updated, not when lineage changes.

This migration calls update_cumulative_times_for_chain() once per unique
lineage chain, which recalculates the field for every result row across
the entire chain. Experiments with NULL base_experiment_id are skipped
(they have no lineage and will be corrected when a result is next saved).

No schema changes. No Alembic migration required.

How to run
----------
From the project root (Windows)::

    .venv\\Scripts\\python database/data_migrations/recalculate_cumulative_times_014.py

Dry-run (recalculates in memory, does not commit)::

    .venv\\Scripts\\python database/data_migrations/recalculate_cumulative_times_014.py --dry-run
"""

import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy.orm import Session

from database import SessionLocal
from database.models.experiments import Experiment
from backend.services.result_merge_utils import update_cumulative_times_for_chain


def _backfill_cumulative_times(db: Session, dry_run: bool = False) -> dict:
    """Recalculate cumulative_time_post_reaction_days for all lineage chains.

    Queries distinct base_experiment_id values, then calls
    update_cumulative_times_for_chain() once per chain (which flushes
    all rows in that chain). Commits once at the end.

    Experiments with NULL base_experiment_id are excluded — they have no
    established lineage and their cumulative times will be set correctly
    the next time a result is saved via the API.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    dry_run:
        When True, flushes but does not commit.

    Returns
    -------
    dict with keys ``chains_processed``, ``chains_skipped``.
    """
    base_ids = (
        db.query(Experiment.base_experiment_id)
        .filter(Experiment.base_experiment_id.isnot(None))
        .distinct()
        .all()
    )

    chains_processed = 0
    chains_skipped = 0

    for (base_id,) in base_ids:
        anchor = (
            db.query(Experiment)
            .filter(Experiment.experiment_id == base_id)
            .first()
        )
        if anchor is None:
            chains_skipped += 1
            continue

        update_cumulative_times_for_chain(db, anchor.id)
        chains_processed += 1

    if not dry_run:
        db.commit()
    else:
        db.flush()

    return {"chains_processed": chains_processed, "chains_skipped": chains_skipped}


def run_migration(dry_run: bool = False) -> None:
    db = SessionLocal()
    try:
        print("=" * 60)
        print("BACKFILL CUMULATIVE TIMES (migration 014)")
        print("=" * 60)
        if dry_run:
            print("DRY RUN — no changes will be committed\n")

        summary = _backfill_cumulative_times(db, dry_run=dry_run)

        print(f"Chains processed:  {summary['chains_processed']}")
        print(f"Chains skipped:    {summary['chains_skipped']}")
        print("=" * 60)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run_migration(dry_run=dry_run)
