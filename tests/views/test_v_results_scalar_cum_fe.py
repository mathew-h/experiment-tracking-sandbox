"""Tests for cumulative_ferrous_iron_yield_h2_pct column in v_results_scalar."""
import datetime
import pytest
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session

from database import Base
from database.models import (
    Experiment, ExperimentalConditions, ExperimentalResults, ScalarResults
)

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def view_engine():
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def view_db(view_engine):
    connection = view_engine.connect()
    transaction = connection.begin()

    from database.event_listeners import _VIEWS
    for view_name, view_sql in _VIEWS:
        try:
            connection.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
            connection.execute(text(view_sql))
        except Exception:
            pass

    TestSession = sessionmaker(bind=connection)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def _make_experiment(db: Session, exp_id: str, number: int, base_id: str = None) -> Experiment:
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
        base_experiment_id=base_id,
    )
    cond = ExperimentalConditions(
        experiment_id=exp_id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    exp.conditions = cond
    db.add(exp)
    db.flush()
    cond.experiment_fk = exp.id
    return exp


def _make_result(
    db: Session,
    experiment: Experiment,
    cumulative_days: float,
    is_primary: bool = True,
) -> ExperimentalResults:
    er = ExperimentalResults(
        experiment_fk=experiment.id,
        time_post_reaction_days=cumulative_days,
        time_post_reaction_bucket_days=cumulative_days,
        cumulative_time_post_reaction_days=cumulative_days,
        is_primary_timepoint_result=is_primary,
        description=f"Result at {cumulative_days}d",
    )
    db.add(er)
    db.flush()
    return er


def _make_scalar(db: Session, result: ExperimentalResults, fe_h2_pct: float = None) -> ScalarResults:
    sr = ScalarResults(result_id=result.id, ferrous_iron_yield_h2_pct=fe_h2_pct)
    db.add(sr)
    db.flush()
    return sr


class TestColumnExists:
    def test_cumulative_column_present(self, view_db):
        """v_results_scalar exposes cumulative_ferrous_iron_yield_h2_pct."""
        result = view_db.execute(
            text("SELECT cumulative_ferrous_iron_yield_h2_pct FROM v_results_scalar")
        )
        assert result.fetchall() == []


class TestCumulativeSum:
    def test_single_experiment_running_total(self, view_db):
        """Cumulative sum accumulates across timepoints within one experiment."""
        exp = _make_experiment(view_db, "CUM001", 1)
        er1 = _make_result(view_db, exp, cumulative_days=1.0)
        er2 = _make_result(view_db, exp, cumulative_days=7.0)
        er3 = _make_result(view_db, exp, cumulative_days=14.0)
        _make_scalar(view_db, er1, fe_h2_pct=10.0)
        _make_scalar(view_db, er2, fe_h2_pct=5.0)
        _make_scalar(view_db, er3, fe_h2_pct=3.0)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT cumulative_ferrous_iron_yield_h2_pct
                FROM v_results_scalar
                WHERE experiment_id = 'CUM001'
                ORDER BY cumulative_time_post_reaction_days
            """)
        ).fetchall()

        assert len(rows) == 3
        assert rows[0][0] == pytest.approx(10.0)
        assert rows[1][0] == pytest.approx(15.0)
        assert rows[2][0] == pytest.approx(18.0)

    def test_null_h2_contributes_zero(self, view_db):
        """Timepoints with NULL ferrous_iron_yield_h2_pct contribute 0 to running sum."""
        exp = _make_experiment(view_db, "CUM002", 2)
        er1 = _make_result(view_db, exp, cumulative_days=1.0)
        er2 = _make_result(view_db, exp, cumulative_days=7.0)
        er3 = _make_result(view_db, exp, cumulative_days=14.0)
        _make_scalar(view_db, er1, fe_h2_pct=8.0)
        _make_scalar(view_db, er2, fe_h2_pct=None)   # NULL — should contribute 0
        _make_scalar(view_db, er3, fe_h2_pct=4.0)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT cumulative_ferrous_iron_yield_h2_pct
                FROM v_results_scalar
                WHERE experiment_id = 'CUM002'
                ORDER BY cumulative_time_post_reaction_days
            """)
        ).fetchall()

        assert len(rows) == 3
        assert rows[0][0] == pytest.approx(8.0)
        assert rows[1][0] == pytest.approx(8.0)   # NULL added 0
        assert rows[2][0] == pytest.approx(12.0)

    def test_no_scalar_row_contributes_zero(self, view_db):
        """Timepoints with no scalar_results row (LEFT JOIN miss) also contribute 0."""
        exp = _make_experiment(view_db, "CUM003", 3)
        er1 = _make_result(view_db, exp, cumulative_days=1.0)
        er2 = _make_result(view_db, exp, cumulative_days=7.0)   # no ScalarResults row
        _make_scalar(view_db, er1, fe_h2_pct=6.0)
        # er2 intentionally has no _make_scalar call
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT cumulative_ferrous_iron_yield_h2_pct
                FROM v_results_scalar
                WHERE experiment_id = 'CUM003'
                ORDER BY cumulative_time_post_reaction_days
            """)
        ).fetchall()

        assert len(rows) == 2
        assert rows[0][0] == pytest.approx(6.0)
        assert rows[1][0] == pytest.approx(6.0)   # no scalar row → contributed 0

    def test_two_independent_experiments_do_not_share_sums(self, view_db):
        """Partition by experiment chain — unrelated experiments accumulate independently."""
        expA = _make_experiment(view_db, "IND_A", 10)
        expB = _make_experiment(view_db, "IND_B", 11)
        erA = _make_result(view_db, expA, cumulative_days=1.0)
        erB = _make_result(view_db, expB, cumulative_days=1.0)
        _make_scalar(view_db, erA, fe_h2_pct=20.0)
        _make_scalar(view_db, erB, fe_h2_pct=5.0)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT experiment_id, cumulative_ferrous_iron_yield_h2_pct
                FROM v_results_scalar
                WHERE experiment_id IN ('IND_A', 'IND_B')
                ORDER BY experiment_id
            """)
        ).fetchall()

        by_exp = {r[0]: r[1] for r in rows}
        assert by_exp["IND_A"] == pytest.approx(20.0)
        assert by_exp["IND_B"] == pytest.approx(5.0)


class TestChainPartitioning:
    def test_derived_experiment_shares_cumulative_with_root(self, view_db):
        """Root and derived experiments in the same chain accumulate into one running sum."""
        # Root experiment: base_experiment_id is NULL (COALESCE resolves to 'CHAIN_ROOT')
        root = _make_experiment(view_db, "CHAIN_ROOT", 20)
        # Derived experiment: base_experiment_id = 'CHAIN_ROOT' (COALESCE resolves to 'CHAIN_ROOT')
        derived = _make_experiment(view_db, "CHAIN_ROOT-2", 21, base_id="CHAIN_ROOT")

        er_root = _make_result(view_db, root, cumulative_days=1.0)
        er_derived = _make_result(view_db, derived, cumulative_days=30.0)

        _make_scalar(view_db, er_root, fe_h2_pct=10.0)
        _make_scalar(view_db, er_derived, fe_h2_pct=5.0)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT experiment_id, cumulative_ferrous_iron_yield_h2_pct
                FROM v_results_scalar
                WHERE experiment_id IN ('CHAIN_ROOT', 'CHAIN_ROOT-2')
                ORDER BY cumulative_time_post_reaction_days
            """)
        ).fetchall()

        assert len(rows) == 2
        # Root timepoint: cumulative = 10.0 (first in partition)
        assert rows[0][0] == "CHAIN_ROOT"
        assert rows[0][1] == pytest.approx(10.0)
        # Derived timepoint: cumulative = 10.0 + 5.0 = 15.0 (same partition)
        assert rows[1][0] == "CHAIN_ROOT-2"
        assert rows[1][1] == pytest.approx(15.0)
