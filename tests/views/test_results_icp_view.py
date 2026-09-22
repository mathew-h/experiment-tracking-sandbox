"""Tests for the v_results_icp reporting view (Titanium column, 2026-09-22)."""
import datetime

import pytest
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from database.models import Experiment, ExperimentalResults, ICPResults

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def view_engine():
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def view_db(view_engine):
    """Per-test transaction; creates the views from the source of truth, then rolls back."""
    connection = view_engine.connect()
    transaction = connection.begin()
    from database.event_listeners import _VIEWS

    for view_name, view_sql in _VIEWS:
        try:
            connection.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
            connection.execute(text(view_sql))
        except Exception:
            pass  # views over tables outside this test's scope
    db = sessionmaker(bind=connection)()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def test_v_results_icp_exposes_ti_ppm(view_db):
    exp = Experiment(
        experiment_id="TI_VIEW_001",
        experiment_number=930001,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
    )
    view_db.add(exp)
    view_db.flush()
    er = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=7.0,
        time_post_reaction_bucket_days=7.0,
        is_primary_timepoint_result=True,
        description="Day 7 results",
    )
    view_db.add(er)
    view_db.flush()
    view_db.add(ICPResults(result_id=er.id, fe=10.0, ti=0.42))
    view_db.flush()

    row = view_db.execute(text(
        "SELECT fe_ppm, ti_ppm FROM v_results_icp WHERE experiment_id = 'TI_VIEW_001'"
    )).one()
    assert row.fe_ppm == 10.0
    assert row.ti_ppm == 0.42


def test_v_results_icp_ti_ppm_null_when_unset(view_db):
    exp = Experiment(
        experiment_id="TI_VIEW_002",
        experiment_number=930002,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
    )
    view_db.add(exp)
    view_db.flush()
    er = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=7.0,
        time_post_reaction_bucket_days=7.0,
        is_primary_timepoint_result=True,
        description="Day 7 results",
    )
    view_db.add(er)
    view_db.flush()
    view_db.add(ICPResults(result_id=er.id, fe=10.0))
    view_db.flush()

    ti = view_db.execute(text(
        "SELECT ti_ppm FROM v_results_icp WHERE experiment_id = 'TI_VIEW_002'"
    )).scalar_one()
    assert ti is None
