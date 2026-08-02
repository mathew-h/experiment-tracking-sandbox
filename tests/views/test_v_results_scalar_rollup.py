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
    def test_mean_median_stddev_and_n_vials(self, view_db):
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
                SELECT n_vials, "mean_gross_ammonium_mM", "median_gross_ammonium_mM", "sd_gross_ammonium_mM"
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["n_vials"] == 3
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
                SELECT n_vials, "mean_gross_ammonium_mM", "sd_gross_ammonium_mM"
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_LONE_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["n_vials"] == 1
        assert mapping["mean_gross_ammonium_mM"] == pytest.approx(5.0)
        assert mapping["sd_gross_ammonium_mM"] is None


class TestRollupCountsAreNotRowCounts:
    """The counts must describe experiments and letters, not scalar rows.

    Root cause A of the 2026-08-01 rollup investigation: the view counted
    ``sr.result_id`` over a LEFT JOIN, which is neither a replicate count nor a
    vial count. See docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md
    """

    def test_icp_only_timepoint_does_not_appear_in_scalar_rollup(self, view_db):
        """A primary result with no scalar row must not produce a phantom group.

        Previously this rendered a row with n_replicates = 0 and NULL statistics;
        335 such groups existed in production (all ICP-only).
        """
        exp = _make_experiment(view_db, "ROLL_ICPONLY_001", 5)
        _make_result(view_db, exp, bucket_days=7.0)  # no scalar row at all
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_vials FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_ICPONLY_001'
            """)
        ).fetchone()

        assert row is None, "an ICP-only timepoint must be absent from the scalar rollup"

    def test_counts_distinguish_vials_letters_and_values(self, view_db):
        """Three letters, one vial each -> 3 vials, 3 letters, 3 values."""
        for idx, letter in enumerate("abc"):
            exp = _make_experiment(view_db, f"ROLL_CNT_001{letter}", 10 + idx)
            er = _make_result(view_db, exp, bucket_days=7.0)
            _make_scalar(view_db, er, gross_nh4=float(idx + 1))
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_vials, n_replicate_letters, n_values
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_CNT_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["n_vials"] == 3
        assert mapping["n_replicate_letters"] == 3
        assert mapping["n_values"] == 3

    def test_one_vial_with_two_primary_rows_counts_as_one_vial(self, view_db):
        """A vial contributing two rows to a bucket is one vial, two values.

        Constructed on the NULL bucket because that is the only place the
        partial unique index permits it -- which is exactly how the 397 excess
        primary rows in production arose (root cause C).
        """
        exp = _make_experiment(view_db, "ROLL_DUP_001", 20)
        for gross in (1.0, 3.0):
            er = ExperimentalResults(
                experiment_fk=exp.id,
                time_post_reaction_days=None,
                time_post_reaction_bucket_days=None,
                is_primary_timepoint_result=True,
                description="duplicate primary on the NULL bucket",
            )
            view_db.add(er)
            view_db.flush()
            _make_scalar(view_db, er, gross_nh4=gross)
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_vials, n_values, "mean_gross_ammonium_mM"
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_DUP_001'
                  AND time_post_reaction_bucket_days IS NULL
            """)
        ).fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["n_vials"] == 1, "two rows from one vial is still one vial"
        assert mapping["n_values"] == 2, "both rows still feed the mean"
        assert mapping["mean_gross_ammonium_mM"] == pytest.approx(2.0)

    def test_unlettered_group_reports_zero_letters(self, view_db):
        """Sequential re-runs share a base but have no replicate letters."""
        exp = _make_experiment(view_db, "ROLL_SEQ_001", 30)
        er = _make_result(view_db, exp, bucket_days=7.0)
        _make_scalar(view_db, er, gross_nh4=4.0)
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_vials, n_replicate_letters
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_SEQ_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()

        assert row is not None
        assert row._mapping["n_vials"] == 1
        assert row._mapping["n_replicate_letters"] == 0


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
                SELECT time_post_reaction_bucket_days, n_vials
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_BKT_001'
                ORDER BY time_post_reaction_bucket_days
            """)
        ).fetchall()

        assert len(rows) == 2
        assert rows[0]._mapping["time_post_reaction_bucket_days"] == pytest.approx(1.0)
        assert rows[0]._mapping["n_vials"] == 2
        assert rows[1]._mapping["time_post_reaction_bucket_days"] == pytest.approx(7.0)
        assert rows[1]._mapping["n_vials"] == 1


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
                SELECT n_vials, "mean_gross_ammonium_mM", "median_gross_ammonium_mM", "sd_gross_ammonium_mM"
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_OUT_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["n_vials"] == 2
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
                SELECT n_vials, mean_h2_ppm, sd_h2_ppm
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_H2_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()
        assert row is not None
        mapping = row._mapping
        assert mapping["n_vials"] == 3
        assert mapping["mean_h2_ppm"] == pytest.approx(200.0)
        assert mapping["sd_h2_ppm"] == pytest.approx(100.0)

    def test_lone_experiment_null_sd(self, view_db):
        exp = _make_experiment(view_db, "ROLL_H2_LONE_001", 613)
        er = _make_result(view_db, exp, bucket_days=7.0)
        _make_scalar(view_db, er, gross_nh4=1.0, h2_ppm=420.0)
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_vials, mean_h2_ppm, sd_h2_ppm
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_H2_LONE_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()
        assert row is not None
        mapping = row._mapping
        assert mapping["n_vials"] == 1
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
                SELECT n_vials, mean_h2_ppm
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_H2_OUT_001' AND time_post_reaction_bucket_days = 7.0
            """)
        ).fetchone()
        assert row is not None
        mapping = row._mapping
        assert mapping["n_vials"] == 2
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
            'SELECT n_vials, "mean_gross_ammonium_mM", "median_gross_ammonium_mM", '
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
            "SELECT time_post_reaction_bucket_days, n_vials "
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
            'SELECT n_vials, "sd_gross_ammonium_mM" FROM v_results_scalar_rollup '
            "WHERE base_experiment_id = 'SERUM_052'"
        )).fetchone()
        assert row[0] == 1
        assert row[1] is None


class TestRollupVialLevelIds:
    """Issue #111: the Dashboard moved to one row per unique experiment ID, so
    replicate spread must come from the rollup rather than from avg/SD columns
    on the sheet.

    ID form matters here. A replicate letter only binds to a NUMERIC index —
    `_REPLICATE_LETTER_RE = r'^(\\d+)([a-z])$'` in
    database/experiment_id_parser.py matches the final underscore-separated
    segment. 'ROLL_910a' parses to base 'ROLL_910' + label 'a', but an
    alphanumeric index like 'ROLL_R10a' does not parse as a replicate at all
    and each vial would become its own base — silently producing n=1 groups and
    a vacuous test.
    """

    def test_three_vials_at_one_timepoint_give_mean_and_sd(self, view_db):
        """ROLL_910a/b/c-t1 aggregate to n=3 with an n-1 SD.

        The -t token is stripped before lineage grouping, so all three land on
        base 'ROLL_910' at bucket 1.0.
        """
        exp_a = _make_experiment(view_db, "ROLL_910a-t1", 9101)
        exp_b = _make_experiment(view_db, "ROLL_910b-t1", 9102)
        exp_c = _make_experiment(view_db, "ROLL_910c-t1", 9103)

        for exp, h2 in ((exp_a, 10.0), (exp_b, 20.0), (exp_c, 30.0)):
            er = _make_result(view_db, exp, bucket_days=1.0)
            _make_scalar(view_db, er, gross_nh4=1.0, h2_ppm=h2)
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_vials, mean_h2_ppm, sd_h2_ppm
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_910'
                  AND time_post_reaction_bucket_days = 1.0
            """)
        ).fetchone()

        assert row is not None, "vial-level IDs must group under their base"
        mapping = row._mapping
        assert mapping["n_vials"] == 3
        assert mapping["mean_h2_ppm"] == pytest.approx(20.0)
        assert mapping["sd_h2_ppm"] == pytest.approx(10.0)

    def test_timepoints_stay_in_separate_buckets(self, view_db):
        """3 letters x 2 timepoints is 6 vials but two independent buckets."""
        for letter, num, h2_t1, h2_t3 in (
            ("a", 9111, 10.0, 100.0),
            ("b", 9112, 20.0, 200.0),
            ("c", 9113, 30.0, 300.0),
        ):
            exp_t1 = _make_experiment(view_db, f"ROLL_920{letter}-t1", num)
            _make_scalar(view_db, _make_result(view_db, exp_t1, bucket_days=1.0),
                         gross_nh4=1.0, h2_ppm=h2_t1)
            exp_t3 = _make_experiment(view_db, f"ROLL_920{letter}-t3", num + 100)
            _make_scalar(view_db, _make_result(view_db, exp_t3, bucket_days=3.0),
                         gross_nh4=1.0, h2_ppm=h2_t3)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT time_post_reaction_bucket_days, n_vials, mean_h2_ppm
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_920'
                ORDER BY time_post_reaction_bucket_days
            """)
        ).fetchall()

        assert len(rows) == 2, "each timepoint is its own bucket"
        assert rows[0]._mapping["n_vials"] == 3
        assert rows[0]._mapping["mean_h2_ppm"] == pytest.approx(20.0)
        assert rows[1]._mapping["n_vials"] == 3
        assert rows[1]._mapping["mean_h2_ppm"] == pytest.approx(200.0)
