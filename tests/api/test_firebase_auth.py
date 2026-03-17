import pytest
from fastapi import HTTPException
from unittest.mock import patch
from backend.auth.firebase_auth import FirebaseUser, _decode_token


def test_decode_token_returns_firebase_user():
    mock_decoded = {"uid": "abc123", "email": "user@addisenergy.com", "name": "Test User"}
    with patch("backend.auth.firebase_auth._verify_id_token", return_value=mock_decoded):
        user = _decode_token("fake-token")
    assert user.uid == "abc123"
    assert user.email == "user@addisenergy.com"


def test_decode_token_raises_401_on_invalid():
    with patch("backend.auth.firebase_auth._verify_id_token", side_effect=Exception("bad")):
        with pytest.raises(HTTPException) as exc:
            _decode_token("bad-token")
    assert exc.value.status_code == 401
