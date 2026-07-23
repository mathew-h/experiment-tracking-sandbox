"""Tests for the Experiment.replicate_label column (issue #69)."""
import datetime
import pytest
from sqlalchemy import create_engine
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


def test_replicate_label_defaults_to_null(db):
    exp = Experiment(
        experiment_id="RLBL_COL_001",
        experiment_number=900001,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
    )
    db.add(exp)
    db.flush()
    assert exp.replicate_label is None


def test_replicate_label_accepts_single_letter(db):
    exp = Experiment(
        experiment_id="RLBL_COL_002a",
        experiment_number=900002,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
        replicate_label="a",
    )
    db.add(exp)
    db.flush()
    assert exp.replicate_label == "a"
