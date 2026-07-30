"""Shared fixtures for tests/models/.

`db_session` follows the same module-scoped-engine + per-test-transaction
pattern already used locally in test_addition_method_column.py and
test_replicate_label_column.py, just promoted to a shared fixture so multiple
files in this directory (e.g. test_reactor_slot_column.py) can use it without
each redefining its own engine/db pair.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def _models_engine():
    eng = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(eng)
    yield eng
    # No teardown — API/services suite may share the DB


@pytest.fixture
def db_session(_models_engine):
    connection = _models_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
