"""API tests for POST /api/admin/notion-sync/trigger."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser


@pytest.fixture()
def unauth_client(db_session):
    def override_get_db():
        yield db_session

    async def no_auth():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_firebase_token] = no_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_trigger_requires_auth(unauth_client) -> None:
    """POST /api/admin/notion-sync/trigger without token returns 401."""
    resp = unauth_client.post("/api/admin/notion-sync/trigger")
    assert resp.status_code == 401


def test_trigger_notion_token_not_configured(client: TestClient) -> None:
    """Returns 503 when NOTION_TOKEN is not set."""
    from backend.config.settings import get_settings, Settings
    from unittest.mock import patch

    no_token_settings = Settings(notion_token="", notion_database_id="")

    with patch("backend.api.routers.notion_sync.get_settings", return_value=no_token_settings):
        resp = client.post("/api/admin/notion-sync/trigger")

    assert resp.status_code == 503
    assert "NOTION_TOKEN" in resp.json()["detail"]


def test_trigger_success(client: TestClient) -> None:
    """With valid auth and mocked sync, returns 200 with summary payload."""
    from backend.config.settings import Settings
    from backend.services.notion_sync.sync import SyncResult
    from unittest.mock import patch

    configured_settings = Settings(
        notion_token="secret_test_token",
        notion_database_id="testdbid",
    )
    mock_result = SyncResult(imported=2, exported=3, carried_forward=1, errors=[])

    with (
        patch("backend.api.routers.notion_sync.get_settings", return_value=configured_settings),
        patch("backend.api.routers.notion_sync.run_sync", return_value=mock_result),
    ):
        resp = client.post("/api/admin/notion-sync/trigger")

    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 2
    assert body["exported"] == 3
    assert body["carried_forward"] == 1
    assert body["errors"] == []


def test_trigger_returns_errors_in_payload(client: TestClient) -> None:
    """Sync errors are returned in the payload (not as HTTP 500) so the client can inspect them."""
    from backend.config.settings import Settings
    from backend.services.notion_sync.sync import SyncResult

    configured_settings = Settings(
        notion_token="secret_test_token",
        notion_database_id="testdbid",
    )
    mock_result = SyncResult(imported=0, exported=0, errors=["R01: DB error — timeout"])

    with (
        patch("backend.api.routers.notion_sync.get_settings", return_value=configured_settings),
        patch("backend.api.routers.notion_sync.run_sync", return_value=mock_result),
    ):
        resp = client.post("/api/admin/notion-sync/trigger")

    assert resp.status_code == 200
    assert resp.json()["errors"] == ["R01: DB error — timeout"]
