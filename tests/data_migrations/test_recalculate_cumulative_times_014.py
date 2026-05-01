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
