# Backfill Cumulative Times — Data Migration 014

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write and run a one-time data migration that recalculates `cumulative_time_post_reaction_days` for every `ExperimentalResults` row after the lineage assignment was corrected.

**Architecture:** `cumulative_time_post_reaction_days` is a stored field written by `update_cumulative_times_for_chain()` in `result_merge_utils.py`. That function is only called on result insert/update — not when `parent_experiment_fk` / `base_experiment_id` change. This migration calls it once per unique lineage chain for all existing rows. No schema changes; no Alembic migration needed.

**Tech Stack:** Python 3.11, SQLAlchemy ORM, pytest, PostgreSQL test DB (via `migration_session` fixture)

---

## Files

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `database/data_migrations/recalculate_cumulative_times_014.py` | Backfill function + dry-run + `__main__` runner |
| Create | `tests/data_migrations/test_recalculate_cumulative_times_014.py` | Pytest coverage of the backfill function |

No other files are touched.

---

### Task 1: Write failing tests

**Files:**
- Create: `tests/data_migrations/test_recalculate_cumulative_times_014.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for database/data_migrations/recalculate_cumulative_times_014.py

Uses the PostgreSQL migration_session fixture (savepoints) so that
db.commit() calls inside the migration only release the savepoint —
the outer transaction is rolled back on teardown.
"""
import pytest
from sqlalchemy.orm import Session

from database.models import Experiment, ExperimentalResults
from database.data_migrations.recalculate_cumulative_times_014 import (
    _backfill_cumulative_times,
)


def _make_experiment(db: Session, experiment_id: str, number: int, base_id: str | None = None) -> Experiment:
    exp = Experiment(experiment_id=experiment_id, experiment_number=number, base_experiment_id=base_id)
    db.add(exp)
    db.flush()
    return exp


def _make_result(db: Session, exp: Experiment, time: float) -> ExperimentalResults:
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=time,
        time_post_reaction_bucket_days=int(time),
        description=f"t={time}d",
        is_primary_timepoint_result=True,
        cumulative_time_post_reaction_days=None,  # simulate stale/null
    )
    db.add(result)
    db.flush()
    return result


class TestBaseExperiment:
    def test_standalone_experiment_sets_cumulative_equal_to_time(self, migration_session: Session):
        """A base experiment with no parent: cumulative == time_post_reaction."""
        exp = _make_experiment(migration_session, "CUMUL_BASE_001", 9001, base_id="CUMUL_BASE_001")
        result = _make_result(migration_session, exp, 7.0)

        _backfill_cumulative_times(migration_session)

        migration_session.refresh(result)
        assert result.cumulative_time_post_reaction_days == pytest.approx(7.0)


class TestSingleDerivation:
    def test_child_cumulative_equals_parent_max_plus_own_time(self, migration_session: Session):
        """One derivation: child cumulative = parent max + child time."""
        base = _make_experiment(migration_session, "CUMUL_002", 9002, base_id="CUMUL_002")
        child = _make_experiment(migration_session, "CUMUL_002-2", 9003, base_id="CUMUL_002")
        child.parent_experiment_fk = base.id
        migration_session.flush()

        base_result = _make_result(migration_session, base, 5.0)
        child_result = _make_result(migration_session, child, 3.0)

        _backfill_cumulative_times(migration_session)

        migration_session.refresh(base_result)
        migration_session.refresh(child_result)
        assert base_result.cumulative_time_post_reaction_days == pytest.approx(5.0)
        assert child_result.cumulative_time_post_reaction_days == pytest.approx(8.0)

    def test_parent_with_multiple_results_uses_max_as_offset(self, migration_session: Session):
        """Offset from parent chain uses max(time_post_reaction_days) of the parent."""
        base = _make_experiment(migration_session, "CUMUL_003", 9004, base_id="CUMUL_003")
        child = _make_experiment(migration_session, "CUMUL_003-2", 9005, base_id="CUMUL_003")
        child.parent_experiment_fk = base.id
        migration_session.flush()

        _make_result(migration_session, base, 3.0)
        _make_result(migration_session, base, 7.0)  # max = 7
        child_result = _make_result(migration_session, child, 2.0)

        _backfill_cumulative_times(migration_session)

        migration_session.refresh(child_result)
        assert child_result.cumulative_time_post_reaction_days == pytest.approx(9.0)


class TestTwoDeepChain:
    def test_grandchild_cumulative_sums_both_ancestor_maxes(self, migration_session: Session):
        """Two-deep chain: grandchild cumulative = grandparent max + parent max + own time."""
        gp = _make_experiment(migration_session, "CUMUL_004", 9006, base_id="CUMUL_004")
        parent = _make_experiment(migration_session, "CUMUL_004-2", 9007, base_id="CUMUL_004")
        child = _make_experiment(migration_session, "CUMUL_004-3", 9008, base_id="CUMUL_004")
        parent.parent_experiment_fk = gp.id
        child.parent_experiment_fk = parent.id
        migration_session.flush()

        gp_result = _make_result(migration_session, gp, 5.0)
        parent_result = _make_result(migration_session, parent, 3.0)
        child_result = _make_result(migration_session, child, 2.0)

        _backfill_cumulative_times(migration_session)

        migration_session.refresh(gp_result)
        migration_session.refresh(parent_result)
        migration_session.refresh(child_result)
        assert gp_result.cumulative_time_post_reaction_days == pytest.approx(5.0)
        assert parent_result.cumulative_time_post_reaction_days == pytest.approx(8.0)
        assert child_result.cumulative_time_post_reaction_days == pytest.approx(10.0)


class TestEdgeCases:
    def test_null_time_post_reaction_stays_null(self, migration_session: Session):
        """Results with NULL time_post_reaction_days get NULL cumulative (not an error)."""
        exp = _make_experiment(migration_session, "CUMUL_005", 9009, base_id="CUMUL_005")
        result = ExperimentalResults(
            experiment_fk=exp.id,
            time_post_reaction_days=None,
            time_post_reaction_bucket_days=None,
            description="no time",
            is_primary_timepoint_result=True,
            cumulative_time_post_reaction_days=None,
        )
        migration_session.add(result)
        migration_session.flush()

        _backfill_cumulative_times(migration_session)

        migration_session.refresh(result)
        assert result.cumulative_time_post_reaction_days is None

    def test_experiment_with_no_results_does_not_error(self, migration_session: Session):
        """Chain member with zero results should not raise."""
        exp = _make_experiment(migration_session, "CUMUL_006", 9010, base_id="CUMUL_006")
        _backfill_cumulative_times(migration_session)  # must not raise

    def test_experiment_with_null_base_experiment_id_is_skipped(self, migration_session: Session):
        """Experiments with NULL base_experiment_id (pre-lineage-migration) are skipped safely."""
        exp = Experiment(experiment_id="CUMUL_007", experiment_number=9011, base_experiment_id=None)
        migration_session.add(exp)
        result = ExperimentalResults(
            experiment_fk=exp.id,
            time_post_reaction_days=4.0,
            time_post_reaction_bucket_days=4,
            description="t=4d",
            is_primary_timepoint_result=True,
            cumulative_time_post_reaction_days=None,
        )
        migration_session.add(result)
        migration_session.flush()

        _backfill_cumulative_times(migration_session)  # must not raise

        # cumulative is still None (not touched — NULL base_experiment_id excluded)
        migration_session.refresh(result)
        assert result.cumulative_time_post_reaction_days is None
```

- [ ] **Step 2: Run the tests to confirm they fail (module not yet importable)**

```bash
.venv/Scripts/pytest tests/data_migrations/test_recalculate_cumulative_times_014.py -v
```

Expected: `ImportError: cannot import name '_backfill_cumulative_times'`

---

### Task 2: Implement the backfill migration

**Files:**
- Create: `database/data_migrations/recalculate_cumulative_times_014.py`

- [ ] **Step 3: Write the migration file**

```python
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
            .filter(Experiment.base_experiment_id == base_id)
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


def run_migration(dry_run: bool = False) -> bool:
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
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run_migration(dry_run=dry_run)
```

- [ ] **Step 4: Run the tests — all should pass**

```bash
.venv/Scripts/pytest tests/data_migrations/test_recalculate_cumulative_times_014.py -v
```

Expected output (7 tests):
```
PASSED tests/data_migrations/test_recalculate_cumulative_times_014.py::TestBaseExperiment::test_standalone_experiment_sets_cumulative_equal_to_time
PASSED tests/data_migrations/test_recalculate_cumulative_times_014.py::TestSingleDerivation::test_child_cumulative_equals_parent_max_plus_own_time
PASSED tests/data_migrations/test_recalculate_cumulative_times_014.py::TestSingleDerivation::test_parent_with_multiple_results_uses_max_as_offset
PASSED tests/data_migrations/test_recalculate_cumulative_times_014.py::TestTwoDeepChain::test_grandchild_cumulative_sums_both_ancestor_maxes
PASSED tests/data_migrations/test_recalculate_cumulative_times_014.py::TestEdgeCases::test_null_time_post_reaction_stays_null
PASSED tests/data_migrations/test_recalculate_cumulative_times_014.py::TestEdgeCases::test_experiment_with_no_results_does_not_error
PASSED tests/data_migrations/test_recalculate_cumulative_times_014.py::TestEdgeCases::test_experiment_with_null_base_experiment_id_is_skipped
```

- [ ] **Step 5: Commit**

```bash
git add database/data_migrations/recalculate_cumulative_times_014.py tests/data_migrations/test_recalculate_cumulative_times_014.py
git commit -m "[fix] add migration 014 to backfill cumulative times after lineage fix

- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Run the migration against the dev database

- [ ] **Step 6: Dry run first — verify the counts look reasonable**

```bash
.venv/Scripts/python database/data_migrations/recalculate_cumulative_times_014.py --dry-run
```

Review the printed `Chains processed` count. It should match the number of distinct `base_experiment_id` values in your DB. If it prints 0, check that `establish_experiment_lineage_006.py` was run and `base_experiment_id` is populated.

- [ ] **Step 7: Run for real**

```bash
.venv/Scripts/python database/data_migrations/recalculate_cumulative_times_014.py
```

Expected: completes without errors, prints chain counts, exits cleanly.

- [ ] **Step 8: Spot-check one chain in the DB (optional but recommended)**

```bash
.venv/Scripts/python -c "
from database import SessionLocal
from database.models import Experiment, ExperimentalResults
db = SessionLocal()
# Replace 'YOUR_BASE_ID' with a known base experiment ID that has derivations
exps = db.query(Experiment).filter(Experiment.base_experiment_id == 'YOUR_BASE_ID').all()
for e in exps:
    for r in db.query(ExperimentalResults).filter(ExperimentalResults.experiment_fk == e.id).all():
        print(e.experiment_id, r.time_post_reaction_days, '->', r.cumulative_time_post_reaction_days)
db.close()
"
```

Expected: `cumulative_time_post_reaction_days` values increase monotonically across the chain.
