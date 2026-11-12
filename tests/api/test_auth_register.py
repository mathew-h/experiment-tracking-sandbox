"""POST /api/auth/register — passwordless access requests (issue #170)."""
from unittest.mock import patch

import pytest

_BODY = {"email": "new@addisenergy.com", "display_name": "New Person", "role": "researcher"}


@pytest.fixture()
def pending_mock():
    with patch("backend.api.routers.auth._ensure_firebase_initialized"), \
         patch("auth.user_management.create_pending_user_request") as m:
        yield m


def test_register_without_password_returns_201(client, pending_mock):
    resp = client.post("/api/auth/register", json=_BODY)
    assert resp.status_code == 201
    pending_mock.assert_called_once_with(
        email="new@addisenergy.com", display_name="New Person", role="researcher"
    )
    assert "link to set your password" in resp.json()["message"]


def test_register_ignores_legacy_password_field(client, pending_mock):
    resp = client.post("/api/auth/register", json={**_BODY, "password": "x"})
    assert resp.status_code == 201
    assert "password" not in pending_mock.call_args.kwargs


def test_register_rejects_non_addis_domain(client, pending_mock):
    resp = client.post("/api/auth/register", json={**_BODY, "email": "x@gmail.com"})
    assert resp.status_code == 422
    pending_mock.assert_not_called()
