from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Import Base via database package (triggers model registration)
from database import Base  # noqa: F401 — side-effect: registers all models
from backend.api.main import app
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
_test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """Create all tables once per test session, drop after."""
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def db_session(create_test_tables) -> Session:
    """Per-test DB session wrapped in a savepoint; rolls back after each test."""
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = _TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def reporting_views(db_session: Session):
    """Create the reporting views inside the test transaction.

    experiments_test is built by create_all, which makes tables only; the views
    (database/event_listeners.py::_VIEWS) are created at app import on the dev
    engine. DDL here is rolled back with the test. Some test files define their
    own copy of this fixture, which takes precedence.
    """
    from sqlalchemy import text
    from database.event_listeners import _VIEWS
    for view_name, _ in _VIEWS:
        db_session.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
    for _, view_sql in _VIEWS:
        db_session.execute(text(view_sql))
    db_session.flush()
    yield


_FAKE_USER = FirebaseUser(uid="test-uid", email="test@addisenergy.com", display_name="Test User")


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    """TestClient with DB and auth overrides applied."""

    def override_get_db():
        yield db_session

    def override_verify_token():
        return _FAKE_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_firebase_token] = override_verify_token
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
