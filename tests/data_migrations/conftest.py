"""Fixtures for data migration tests.

Data migration functions call db.commit() internally (after each chunk). The standard
db_session fixture from tests/api/conftest.py wraps the test in a plain transaction and
rolls it back on teardown — but an internal db.commit() commits that outer transaction,
defeating the rollback isolation.

The migration_session fixture below uses begin_nested() (savepoints) so that when the
migration calls db.commit() it only releases the savepoint, not the outer transaction.
The outer transaction is rolled back on teardown, keeping the test DB clean.
"""
import pytest
from sqlalchemy.orm import sessionmaker

# Re-export create_test_tables so pytest discovers it as a fixture for this package.
from tests.api.conftest import create_test_tables  # noqa: F401
from tests.api.conftest import _test_engine


@pytest.fixture
def migration_session(create_test_tables):
    """Per-test DB session with savepoint isolation for migration tests.

    Uses begin_nested() so that when the migration calls db.commit() it only
    releases the savepoint, not the outer transaction. The outer transaction is
    rolled back on teardown, keeping the test DB clean.
    """
    connection = _test_engine.connect()
    outer_transaction = connection.begin()

    TestSession = sessionmaker(bind=connection)
    session = TestSession()

    # Start a savepoint so that migration db.commit() only releases the savepoint.
    session.begin_nested()

    yield session

    session.close()
    outer_transaction.rollback()
    connection.close()
