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


def _make_scalar(db: Session, result: ExperimentalResults, gross_nh4: float,
                 h2_ppm: float | None = None) -> ScalarResults:
    sr = ScalarResults(
        result_id=result.id,
        gross_ammonium_concentration_mM=gross_nh4,
        background_ammonium_concentration_mM=0.2,
        h2_concentration=h2_ppm,
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


class TestRollupOutlierExclusion:
    def test_flagged_replicate_excluded_from_stats_and_n(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_OUT_001a", 7)
        exp_b = _make_experiment(view_db, "ROLL_OUT_001b", 8)
        exp_c = _make_experiment(view_db, "ROLL_OUT_001c", 9)
        for exp, nh4 in ((exp_a, 1.0), (exp_b, 2.0), (exp_c, 30.0)):
            er = _make_result(view_db, exp, bucket_days=7.0)
            _make_scalar(view_db, er, gross_nh4=nh4)
        exp_c.is_outlier = True
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_replicates, "mean_gross_ammonium_mM", "median_gross_ammonium_mM", "sd_gross_ammonium_mM"
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_OUT_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["n_replicates"] == 2
        assert mapping["mean_gross_ammonium_mM"] == pytest.approx(1.5)
        assert mapping["median_gross_ammonium_mM"] == pytest.approx(1.5)
        assert mapping["sd_gross_ammonium_mM"] == pytest.approx(0.70710678, abs=1e-6)

    def test_flagged_replicate_remains_in_per_row_view(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_OUT_002a", 10)
        exp_b = _make_experiment(view_db, "ROLL_OUT_002b", 11)
        for exp, nh4 in ((exp_a, 1.0), (exp_b, 50.0)):
            er = _make_result(view_db, exp, bucket_days=3.0)
            _make_scalar(view_db, er, gross_nh4=nh4)
        exp_b.is_outlier = True
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT experiment_id FROM v_results_scalar
                WHERE experiment_id IN ('ROLL_OUT_002a', 'ROLL_OUT_002b')
            """)
        ).fetchall()
        assert {r._mapping["experiment_id"] for r in rows} == {"ROLL_OUT_002a", "ROLL_OUT_002b"}

    def test_group_with_all_members_flagged_has_no_rollup_row(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_OUT_003a", 12)
        exp_b = _make_experiment(view_db, "ROLL_OUT_003b", 13)
        for exp in (exp_a, exp_b):
            er = _make_result(view_db, exp, bucket_days=7.0)
            _make_scalar(view_db, er, gross_nh4=2.0)
            exp.is_outlier = True
        view_db.commit()

        rows = view_db.execute(
            text("SELECT 1 FROM v_results_scalar_rollup WHERE base_experiment_id = 'ROLL_OUT_003'")
        ).fetchall()
        assert rows == []


class TestRollupH2Ppm:
    """Issue #90: mean_h2_ppm / sd_h2_ppm aggregate scalar_results.h2_concentration."""

    def test_mean_and_sd_across_three_replicates(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_H2_001a", 610)
        exp_b = _make_experiment(view_db, "ROLL_H2_001b", 611)
        exp_c = _make_experiment(view_db, "ROLL_H2_001c", 612)
        for exp, h2 in ((exp_a, 100.0), (exp_b, 200.0), (exp_c, 300.0)):
            er = _make_result(view_db, exp, bucket_days=7.0)
            _make_scalar(view_db, er, gross_nh4=1.0, h2_ppm=h2)
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_replicates, mean_h2_ppm, sd_h2_ppm
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_H2_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()
        assert row is not None
        mapping = row._mapping
        assert mapping["n_replicates"] == 3
        assert mapping["mean_h2_ppm"] == pytest.approx(200.0)
        assert mapping["sd_h2_ppm"] == pytest.approx(100.0)

    def test_lone_experiment_null_sd(self, view_db):
        exp = _make_experiment(view_db, "ROLL_H2_LONE_001", 613)
        er = _make_result(view_db, exp, bucket_days=7.0)
        _make_scalar(view_db, er, gross_nh4=1.0, h2_ppm=420.0)
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_replicates, mean_h2_ppm, sd_h2_ppm
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_H2_LONE_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()
        assert row is not None
        mapping = row._mapping
        assert mapping["n_replicates"] == 1
        assert mapping["mean_h2_ppm"] == pytest.approx(420.0)
        assert mapping["sd_h2_ppm"] is None

    def test_outlier_excluded_from_mean_h2_ppm(self, view_db):
        exp_a = _make_experiment(view_db, "ROLL_H2_OUT_001a", 614)
        exp_b = _make_experiment(view_db, "ROLL_H2_OUT_001b", 615)
        exp_c = _make_experiment(view_db, "ROLL_H2_OUT_001c", 616)
        for exp, h2 in ((exp_a, 100.0), (exp_b, 200.0), (exp_c, 9000.0)):
            er = _make_result(view_db, exp, bucket_days=7.0)
            _make_scalar(view_db, er, gross_nh4=1.0, h2_ppm=h2)
        exp_c.is_outlier = True
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_replicates, mean_h2_ppm
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_H2_OUT_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()
        assert row is not None
        mapping = row._mapping
        assert mapping["n_replicates"] == 2
        assert mapping["mean_h2_ppm"] == pytest.approx(150.0)


class TestRollupTimepointVials:
    """Issue #81: '-t<days>' vials aggregate under the shared base per day
    bucket with NO view change (reuses base + time_post_reaction_bucket_days)."""

    def test_three_vials_roll_up_at_their_day(self, view_db):
        for i, (exp_id, nh4) in enumerate([
            ("SERUM_050a-t7", 1.0), ("SERUM_050b-t7", 2.0), ("SERUM_050c-t7", 3.0),
        ]):
            exp = _make_experiment(view_db, exp_id, 5000 + i)
            result = _make_result(view_db, exp, bucket_days=7.0)
            _make_scalar(view_db, result, gross_nh4=nh4)
        view_db.commit()
        row = view_db.execute(text(
            'SELECT n_replicates, "mean_gross_ammonium_mM", "median_gross_ammonium_mM", '
            '"sd_gross_ammonium_mM" FROM v_results_scalar_rollup '
            "WHERE base_experiment_id = 'SERUM_050' "
            "AND time_post_reaction_bucket_days = 7.0"
        )).fetchone()
        assert row is not None
        assert row[0] == 3
        assert row[1] == 2.0
        assert row[2] == 2.0
        assert abs(row[3] - 1.0) < 1e-9

    def test_t0_set_forms_separate_bucket(self, view_db):
        for i, exp_id in enumerate(["SERUM_051a-t0", "SERUM_051b-t0"]):
            exp = _make_experiment(view_db, exp_id, 5100 + i)
            result = _make_result(view_db, exp, bucket_days=0.0)
            _make_scalar(view_db, result, gross_nh4=1.5)
        exp7 = _make_experiment(view_db, "SERUM_051a-t7", 5102)
        result7 = _make_result(view_db, exp7, bucket_days=7.0)
        _make_scalar(view_db, result7, gross_nh4=4.0)
        view_db.commit()
        buckets = view_db.execute(text(
            "SELECT time_post_reaction_bucket_days, n_replicates "
            "FROM v_results_scalar_rollup WHERE base_experiment_id = 'SERUM_051' "
            "ORDER BY time_post_reaction_bucket_days"
        )).fetchall()
        assert [(b[0], b[1]) for b in buckets] == [(0.0, 2), (7.0, 1)]

    def test_lone_vial_n1_sd_null(self, view_db):
        exp = _make_experiment(view_db, "SERUM_052a-t14", 5200)
        result = _make_result(view_db, exp, bucket_days=14.0)
        _make_scalar(view_db, result, gross_nh4=2.5)
        view_db.commit()
        row = view_db.execute(text(
            'SELECT n_replicates, "sd_gross_ammonium_mM" FROM v_results_scalar_rollup '
            "WHERE base_experiment_id = 'SERUM_052'"
        )).fetchone()
        assert row[0] == 1
        assert row[1] is None
