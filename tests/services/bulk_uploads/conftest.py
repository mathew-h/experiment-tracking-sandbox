from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from database import Base  # noqa: F401 — registers all models

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
_test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=_test_engine)


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """Create all tables once for this test session. No teardown — API suite may share the DB."""
    Base.metadata.create_all(bind=_test_engine)
    yield


@pytest.fixture()
def db_session(create_test_tables) -> Session:
    """Per-test DB session wrapped in a transaction; rolls back after each test."""
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = _TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()
