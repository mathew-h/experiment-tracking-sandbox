"""Tests for database/data_migrations/swap_reactor_4_7_015.py

Uses migration_session (savepoint isolation) from tests/data_migrations/conftest.py.
All tests seed their own data with experiment_number values in the 9000s to avoid
production ID collisions.
"""
import pytest
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models.experiments import Experiment
from database.models.conditions import ExperimentalConditions
from database.data_migrations.swap_reactor_4_7_015 import _swap_reactor_assignments


# ── Helpers ───────────────────────────────────────────────────────────────────

def _seed(db: Session, exp_id: str, exp_num: int, reactor: int | None) -> ExperimentalConditions:
    """Seed one Experiment + ExperimentalConditions row."""
    exp = Experiment(experiment_id=exp_id, experiment_number=exp_num)
    db.add(exp)
    db.flush()
    cond = ExperimentalConditions(
        experiment_id=exp_id,
        experiment_fk=exp.id,
        reactor_number=reactor,
    )
    db.add(cond)
    db.flush()
    return cond


def _count(db: Session, reactor_number: int) -> int:
    return (
        db.query(func.count(ExperimentalConditions.id))
        .filter(ExperimentalConditions.reactor_number == reactor_number)
        .scalar()
        or 0
    )


# ── Swap correctness ──────────────────────────────────────────────────────────

class TestSwapCorrectness:
    def test_reactor4_rows_become_reactor7(self, migration_session: Session):
        """All conditions with reactor_number=4 are reassigned to 7."""
        cond = _seed(migration_session, "SWAP_001", 9001, reactor=4)
        _swap_reactor_assignments(migration_session)
        migration_session.refresh(cond)
        assert cond.reactor_number == 7

    def test_reactor7_rows_become_reactor4(self, migration_session: Session):
        """All conditions with reactor_number=7 are reassigned to 4."""
        cond = _seed(migration_session, "SWAP_002", 9002, reactor=7)
        _swap_reactor_assignments(migration_session)
        migration_session.refresh(cond)
        assert cond.reactor_number == 4

    def test_counts_swap_correctly(self, migration_session: Session):
        """3 R4 rows + 2 R7 rows become 2 R4 rows + 3 R7 rows."""
        specs = [
            (4, 9010, "SWAP_CNT_000"), (4, 9011, "SWAP_CNT_001"), (4, 9012, "SWAP_CNT_002"),
            (7, 9013, "SWAP_CNT_003"), (7, 9014, "SWAP_CNT_004"),
        ]
        for rn, en, eid in specs:
            _seed(migration_session, eid, en, reactor=rn)

        result = _swap_reactor_assignments(migration_session)

        assert result["post_r4"] == 2
        assert result["post_r7"] == 3

    def test_total_count_unchanged(self, migration_session: Session):
        """Total experiment count across R4 + R7 is the same before and after."""
        for rn, en, eid in [(4, 9020, "SWAP_TOT_000"), (7, 9021, "SWAP_TOT_001"), (7, 9022, "SWAP_TOT_002")]:
            _seed(migration_session, eid, en, reactor=rn)

        result = _swap_reactor_assignments(migration_session)

        assert result["pre_r4"] + result["pre_r7"] == result["post_r4"] + result["post_r7"]

    def test_other_reactors_unaffected(self, migration_session: Session):
        """Reactors 1, 3, and 8 are untouched by the swap."""
        for rn, en, eid in [(1, 9030, "SWAP_OTH_001"), (3, 9031, "SWAP_OTH_003"), (8, 9032, "SWAP_OTH_008")]:
            _seed(migration_session, eid, en, reactor=rn)

        pre_r1 = _count(migration_session, 1)
        pre_r3 = _count(migration_session, 3)
        pre_r8 = _count(migration_session, 8)

        _swap_reactor_assignments(migration_session)

        assert _count(migration_session, 1) == pre_r1
        assert _count(migration_session, 3) == pre_r3
        assert _count(migration_session, 8) == pre_r8

    def test_null_reactor_unaffected(self, migration_session: Session):
        """Conditions with reactor_number=NULL are not affected."""
        cond = _seed(migration_session, "SWAP_NULL_001", 9040, reactor=None)
        _swap_reactor_assignments(migration_session)
        migration_session.refresh(cond)
        assert cond.reactor_number is None

    def test_summary_counts_are_correct(self, migration_session: Session):
        """Return dict accurately reports pre/post counts and moved-row counts."""
        _seed(migration_session, "SWAP_SUM_004", 9050, reactor=4)
        _seed(migration_session, "SWAP_SUM_007", 9051, reactor=7)

        result = _swap_reactor_assignments(migration_session)

        assert result["pre_r4"] == 1
        assert result["pre_r7"] == 1
        assert result["post_r4"] == 1
        assert result["post_r7"] == 1
        assert result["r4_moved"] == 1
        assert result["r7_moved"] == 1


# ── Dry-run and rollback ──────────────────────────────────────────────────────

class TestDryRunAndRollback:
    def test_dry_run_does_not_persist(self, migration_session: Session):
        """dry_run=True rolls back the swap via a nested savepoint; reactor_number stays 4."""
        cond = _seed(migration_session, "SWAP_DRY_001", 9060, reactor=4)

        result = _swap_reactor_assignments(migration_session, dry_run=True)

        migration_session.expire_all()
        fresh = migration_session.query(ExperimentalConditions).filter_by(
            experiment_id="SWAP_DRY_001"
        ).one()
        assert fresh.reactor_number == 4           # unchanged in DB
        assert result["r4_moved"] == 1             # but summary shows what would have moved

    def test_partial_migration_rolls_back_cleanly(self, migration_session: Session):
        """After a mid-migration rollback, no rows are stranded at the temp value (9999)."""
        cond = _seed(migration_session, "SWAP_RB_001", 9070, reactor=4)

        # Simulate step 1 only (partial migration — crash before steps 2 and 3)
        migration_session.query(ExperimentalConditions).filter(
            ExperimentalConditions.reactor_number == 4
        ).update({"reactor_number": 9999}, synchronize_session="fetch")

        # Explicit rollback (what run_migration's except block does)
        migration_session.rollback()
        migration_session.begin_nested()  # restart savepoint for test cleanup

        assert _count(migration_session, 9999) == 0
        fresh = migration_session.query(ExperimentalConditions).filter_by(
            experiment_id="SWAP_RB_001"
        ).first()
        assert fresh is not None
        assert fresh.reactor_number == 4
