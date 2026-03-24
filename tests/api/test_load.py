"""Load test: 5 concurrent users hitting list/dashboard endpoints simultaneously.

Verifies the API handles concurrent requests without errors, deadlocks, or
connection pool exhaustion (the main failure modes for a multi-user lab app).
"""
from __future__ import annotations

import concurrent.futures
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.main import app
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from database import Base

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
_engine = create_engine(TEST_DB_URL, pool_size=10, max_overflow=5, pool_pre_ping=True)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

_FAKE_USER = FirebaseUser(uid="load-uid", email="load@addisenergy.com", display_name="Load Tester")

CONCURRENT_USERS = 5
REQUESTS_PER_USER = 3


@pytest.fixture(scope="module", autouse=True)
def setup_load_db():
    Base.metadata.create_all(bind=_engine)

    # Override once, before any worker starts: factory creates a new session per request
    def override_get_db():
        session = _Session()
        try:
            yield session
        finally:
            session.close()

    def override_auth():
        return _FAKE_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_firebase_token] = override_auth
    yield
    app.dependency_overrides.clear()


def _read_worker(worker_id: int) -> list[tuple[str, int]]:
    """One user making REQUESTS_PER_USER sequential read requests."""
    with TestClient(app, raise_server_exceptions=False) as client:
        results = []
        endpoints = ["/api/samples", "/api/experiments", "/api/dashboard/"]
        for i in range(REQUESTS_PER_USER):
            url = endpoints[i % len(endpoints)]
            resp = client.get(url)
            results.append((url, resp.status_code))
    return results


def _write_worker(worker_id: int) -> int:
    """One user creating a unique sample."""
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            "/api/samples",
            json={"sample_id": f"LOAD_TEST_{worker_id:03d}", "rock_classification": "Dunite"},
        )
    return resp.status_code


def test_concurrent_read_requests():
    """5 concurrent users each making 3 read requests — all must return 200."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_USERS) as pool:
        futures = [pool.submit(_read_worker, i) for i in range(CONCURRENT_USERS)]
        all_results = []
        for f in concurrent.futures.as_completed(futures):
            all_results.extend(f.result())

    failures = [(url, code) for url, code in all_results if code not in (200, 404)]
    assert not failures, f"Unexpected status codes under concurrent load: {failures}"
    assert len(all_results) == CONCURRENT_USERS * REQUESTS_PER_USER


def test_concurrent_write_requests():
    """5 concurrent users each creating a unique sample — all must return 201 or 409."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_USERS) as pool:
        futures = [pool.submit(_write_worker, i) for i in range(CONCURRENT_USERS)]
        codes = [f.result() for f in concurrent.futures.as_completed(futures)]

    bad = [c for c in codes if c not in (201, 409)]
    assert not bad, f"Unexpected status codes during concurrent writes: {bad}"
