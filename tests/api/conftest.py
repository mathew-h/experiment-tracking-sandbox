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
