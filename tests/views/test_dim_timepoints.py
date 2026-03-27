"""Tests for the v_dim_timepoints reporting view."""
import datetime
import pytest
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session

from database import Base
from database.models import Experiment, ExperimentalConditions, ExperimentalResults, ScalarResults, ICPResults

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def view_engine():
    """Create test tables once per module."""
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def view_db(view_engine):
    """Per-test session wrapped in a savepoint; creates views then rolls back."""
    connection = view_engine.connect()
    transaction = connection.begin()

    # Create the view under test — must match event_listeners.py exactly.
    # Import the SQL from the source of truth.
    from database.event_listeners import _VIEWS

    for view_name, view_sql in _VIEWS:
        try:
            connection.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
            connection.execute(text(view_sql))
        except Exception:
            pass  # Some views may reference tables not in test scope; skip

    TestSession = sessionmaker(bind=connection)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def _make_experiment(db: Session, exp_id: str, number: int) -> Experiment:
    """Helper: create an experiment with conditions."""
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


def _make_result(
    db: Session,
    experiment: Experiment,
    time_days: float,
    bucket_days: float,
    cumulative_days: float,
    is_primary: bool = True,
) -> ExperimentalResults:
    """Helper: create an experimental result row."""
    er = ExperimentalResults(
        experiment_fk=experiment.id,
        time_post_reaction_days=time_days,
        time_post_reaction_bucket_days=bucket_days,
        cumulative_time_post_reaction_days=cumulative_days,
        is_primary_timepoint_result=is_primary,
        description=f"Result at {time_days}d",
    )
    db.add(er)
    db.flush()
    return er


class TestDimTimepointsViewExists:
    """v_dim_timepoints is queryable after view creation."""

    def test_view_is_queryable(self, view_db):
        """View exists and returns zero rows on empty DB."""
        rows = view_db.execute(text("SELECT * FROM v_dim_timepoints")).fetchall()
        assert rows == []


class TestDimTimepointsOnlyPrimaryRows:
    """View contains only rows where is_primary_timepoint_result = TRUE."""

    def test_primary_rows_included(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        _make_result(view_db, exp, 1.0, 1.0, 1.0, is_primary=True)
        _make_result(view_db, exp, 1.0, 1.0, 1.0, is_primary=False)  # non-primary
        view_db.commit()

        rows = view_db.execute(text("SELECT * FROM v_dim_timepoints")).fetchall()
        assert len(rows) == 1

    def test_multiple_timepoints_multiple_experiments(self, view_db):
        exp1 = _make_experiment(view_db, "EXP_001", 1)
        exp2 = _make_experiment(view_db, "EXP_002", 2)
        _make_result(view_db, exp1, 1.0, 1.0, 1.0, is_primary=True)
        _make_result(view_db, exp1, 7.0, 7.0, 7.0, is_primary=True)
        _make_result(view_db, exp2, 1.0, 1.0, 1.0, is_primary=True)
        view_db.commit()

        rows = view_db.execute(text("SELECT * FROM v_dim_timepoints")).fetchall()
        assert len(rows) == 3


class TestDimTimepointsColumns:
    """View exposes the correct columns with correct values."""

    def test_columns_match_spec(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        er = _make_result(view_db, exp, 3.5, 4.0, 10.5, is_primary=True)
        view_db.commit()

        row = view_db.execute(text("SELECT * FROM v_dim_timepoints")).fetchone()
        # Access by key name
        assert row._mapping["result_id"] == er.id
        assert row._mapping["experiment_id"] == "EXP_001"
        assert row._mapping["time_post_reaction_days"] == 3.5
        assert row._mapping["time_post_reaction_bucket_days"] == 4.0
        assert row._mapping["cumulative_time_post_reaction_days"] == 10.5


class TestDimTimepointsResultIdAlignment:
    """result_id values match those in v_results_scalar, v_results_h2, v_results_icp."""

    def test_result_id_matches_scalar_view(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        er = _make_result(view_db, exp, 1.0, 1.0, 1.0, is_primary=True)
        sr = ScalarResults(result_id=er.id, final_ph=7.0)
        view_db.add(sr)
        view_db.commit()

        dim_ids = {
            r._mapping["result_id"]
            for r in view_db.execute(text("SELECT result_id FROM v_dim_timepoints"))
        }
        scalar_ids = {
            r._mapping["result_id"]
            for r in view_db.execute(text("SELECT result_id FROM v_results_scalar"))
        }
        assert dim_ids & scalar_ids == dim_ids  # all dim IDs are in scalar

    def test_result_id_matches_icp_view(self, view_db):
        exp = _make_experiment(view_db, "EXP_001", 1)
        er = _make_result(view_db, exp, 1.0, 1.0, 1.0, is_primary=True)
        icp = ICPResults(result_id=er.id, fe=10.0)
        view_db.add(icp)
        view_db.commit()

        dim_ids = {
            r._mapping["result_id"]
            for r in view_db.execute(text("SELECT result_id FROM v_dim_timepoints"))
        }
        icp_ids = {
            r._mapping["result_id"]
            for r in view_db.execute(text("SELECT result_id FROM v_results_icp"))
        }
        assert dim_ids & icp_ids == icp_ids  # all ICP IDs are in dim
