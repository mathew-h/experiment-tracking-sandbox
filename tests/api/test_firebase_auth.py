import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from unittest.mock import patch
from backend.auth.firebase_auth import FirebaseUser, _decode_token, verify_firebase_token


def test_decode_token_returns_firebase_user():
    mock_decoded = {
        "uid": "abc123",
        "email": "user@addisenergy.com",
        "name": "Test User",
        "approved": True,
    }
    with patch("backend.auth.firebase_auth._verify_id_token", return_value=mock_decoded):
        user = _decode_token("fake-token")
    assert isinstance(user, FirebaseUser)
    assert user.uid == "abc123"
    assert user.email == "user@addisenergy.com"


def test_decode_token_raises_401_on_invalid():
    with patch("backend.auth.firebase_auth._verify_id_token", side_effect=Exception("bad")):
        with pytest.raises(HTTPException) as exc:
            _decode_token("bad-token")
    assert exc.value.status_code == 401


def _assert_403(decoded: dict) -> None:
    with patch("backend.auth.firebase_auth._verify_id_token", return_value=decoded):
        with pytest.raises(HTTPException) as exc:
            _decode_token("t")
    assert exc.value.status_code == 403
    assert exc.value.detail == "Account not approved"


@pytest.mark.parametrize("claims", [{}, {"approved": False}])
def test_decode_token_rejects_unapproved(claims):
    _assert_403({"uid": "u1", "email": "x@addisenergy.com", **claims})


@pytest.mark.parametrize("value", ["true", 1])
def test_decode_token_rejects_non_boolean_approved(value):
    _assert_403({"uid": "u1", "email": "x@addisenergy.com", "approved": value})


def test_verify_dependency_rejects_unapproved():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="t")
    with patch(
        "backend.auth.firebase_auth._verify_id_token",
        return_value={"uid": "u1", "email": "x@addisenergy.com"},
    ):
        with pytest.raises(HTTPException) as exc:
            verify_firebase_token(creds)
    assert exc.value.status_code == 403
