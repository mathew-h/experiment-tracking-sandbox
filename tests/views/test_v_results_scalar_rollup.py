"""Tests for the v_results_scalar_rollup reporting view (issue #69)."""
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


def _make_experiment(db: Session, exp_id: str, number: int) -> Experiment:
    """Creates a bare Experiment row. The before_flush lineage listener sets
    base_experiment_id/replicate_label automatically from exp_id on flush."""
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
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


def _make_result(db: Session, experiment: Experiment, bucket_days: float) -> ExperimentalResults:
    er = ExperimentalResults(
        experiment_fk=experiment.id,
        time_post_reaction_days=bucket_days,
        time_post_reaction_bucket_days=bucket_days,
        cumulative_time_post_reaction_days=bucket_days,
        is_primary_timepoint_result=True,
        description=f"Result at {bucket_days}d",
    )
    db.add(er)
    db.flush()
    return er


def _make_scalar(db: Session, result: ExperimentalResults, gross_nh4: float) -> ScalarResults:
    sr = ScalarResults(
        result_id=result.id,
        gross_ammonium_concentration_mM=gross_nh4,
        background_ammonium_concentration_mM=0.2,
    )
    db.add(sr)
    db.flush()
    return sr


class TestRollupThreeReplicates:
    def test_mean_median_stddev_and_n_replicates(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_001a", 1)
        exp_b = _make_experiment(view_db, "ROLL_001b", 2)
        exp_c = _make_experiment(view_db, "ROLL_001c", 3)

        er_a = _make_result(view_db, exp_a, bucket_days=7.0)
        er_b = _make_result(view_db, exp_b, bucket_days=7.0)
        er_c = _make_result(view_db, exp_c, bucket_days=7.0)

        _make_scalar(view_db, er_a, gross_nh4=1.0)
        _make_scalar(view_db, er_b, gross_nh4=2.0)
        _make_scalar(view_db, er_c, gross_nh4=3.0)
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_replicates, "mean_gross_ammonium_mM", "median_gross_ammonium_mM", "sd_gross_ammonium_mM"
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["n_replicates"] == 3
        assert mapping["mean_gross_ammonium_mM"] == pytest.approx(2.0)
        assert mapping["median_gross_ammonium_mM"] == pytest.approx(2.0)
        assert mapping["sd_gross_ammonium_mM"] == pytest.approx(1.0)


class TestRollupLoneExperiment:
    def test_lone_experiment_gives_n_1_and_null_sd(self, view_db):
        exp = _make_experiment(view_db, "ROLL_LONE_001", 4)
        er = _make_result(view_db, exp, bucket_days=7.0)
        _make_scalar(view_db, er, gross_nh4=5.0)
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_replicates, "mean_gross_ammonium_mM", "sd_gross_ammonium_mM"
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_LONE_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["n_replicates"] == 1
        assert mapping["mean_gross_ammonium_mM"] == pytest.approx(5.0)
        assert mapping["sd_gross_ammonium_mM"] is None


class TestRollupOneRowPerBaseAndBucket:
    def test_two_buckets_produce_two_rows(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_BKT_001a", 5)
        exp_b = _make_experiment(view_db, "ROLL_BKT_001b", 6)

        er_a1 = _make_result(view_db, exp_a, bucket_days=1.0)
        er_b1 = _make_result(view_db, exp_b, bucket_days=1.0)
        er_a2 = _make_result(view_db, exp_a, bucket_days=7.0)

        _make_scalar(view_db, er_a1, gross_nh4=1.0)
        _make_scalar(view_db, er_b1, gross_nh4=3.0)
        _make_scalar(view_db, er_a2, gross_nh4=9.0)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT time_post_reaction_bucket_days, n_replicates
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_BKT_001'
                ORDER BY time_post_reaction_bucket_days
            """)
        ).fetchall()

        assert len(rows) == 2
        assert rows[0]._mapping["time_post_reaction_bucket_days"] == pytest.approx(1.0)
        assert rows[0]._mapping["n_replicates"] == 2
        assert rows[1]._mapping["time_post_reaction_bucket_days"] == pytest.approx(7.0)
        assert rows[1]._mapping["n_replicates"] == 1
