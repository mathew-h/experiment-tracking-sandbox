"""Tests for the Experiment.is_outlier column (issue #70 P4)."""
import datetime
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import Base
from database.models import Experiment

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_is_outlier_defaults_to_false(db):
    exp = Experiment(
        experiment_id="OUTL_COL_001",
        experiment_number=910001,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
    )
    db.add(exp)
    db.flush()
    assert exp.is_outlier is False


def test_is_outlier_server_default_false_for_raw_insert(db):
    # Raw insert omitting the column exercises the server_default that
    # backfills pre-existing rows during migration.
    db.execute(text(
        "INSERT INTO experiments (experiment_id, experiment_number) "
        "VALUES ('OUTL_COL_002', 910002)"
    ))
    val = db.execute(text(
        "SELECT is_outlier FROM experiments WHERE experiment_id = 'OUTL_COL_002'"
    )).scalar_one()
    assert val is False


def test_is_outlier_settable_true(db):
    exp = Experiment(
        experiment_id="OUTL_COL_003c",
        experiment_number=910003,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
        is_outlier=True,
    )
    db.add(exp)
    db.flush()
    assert exp.is_outlier is True
