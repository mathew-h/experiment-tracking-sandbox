"""Unit tests for the Firestore pending-user flow in auth/user_management.py.

Firestore and Firebase Auth are mocked at the module boundary; no network calls.
"""
from unittest.mock import MagicMock, patch

import pytest

import auth.user_management as um


@pytest.fixture()
def fs():
    """Mock the firestore module used by user_management; yields (module_mock, db_mock)."""
    with patch.object(um, "firestore") as firestore_mock:
        db = MagicMock()
        firestore_mock.client.return_value = db
        yield firestore_mock, db


@pytest.fixture()
def fb_auth():
    with patch.object(um, "auth") as auth_mock:
        auth_mock.generate_password_reset_link.return_value = "https://reset.example/link"
        yield auth_mock


def _pending_doc(db: MagicMock, data: dict) -> MagicMock:
    request_ref = MagicMock()
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = data
    request_ref.get.return_value = snapshot
    db.collection.return_value.document.return_value = request_ref
    return request_ref


def test_create_pending_request_stores_no_password(fs):
    _, db = fs
    db.collection.return_value.where.return_value.get.return_value = []
    um.create_pending_user_request(
        email="new@addisenergy.com", display_name="New", role="researcher"
    )
    stored = db.collection.return_value.add.call_args.args[0]
    assert "password" not in stored
    assert stored["email"] == "new@addisenergy.com"
    assert stored["status"] == "pending"


def test_approve_user_ignores_and_deletes_legacy_password(fs, fb_auth):
    firestore_mock, db = fs
    request_ref = _pending_doc(db, {
        "email": "old@addisenergy.com",
        "password": "hunter22",
        "display_name": "Old",
        "role": "researcher",
    })
    with patch.object(um, "create_user", return_value={"uid": "u1", "email": "old@addisenergy.com"}) as cu:
        result = um.approve_user("req1")

    used_password = cu.call_args.kwargs["password"]
    assert used_password != "hunter22"
    assert len(used_password) >= 32
    fb_auth.set_custom_user_claims.assert_called_once_with("u1", {"approved": True, "role": "researcher"})
    update = request_ref.update.call_args.args[0]
    assert update["password"] is firestore_mock.DELETE_FIELD
    assert update["status"] == "approved"
    assert result["password_setup_link"] == "https://reset.example/link"
    assert result["role"] == "researcher"


def test_approve_user_link_failure_returns_none(fs, fb_auth):
    _, db = fs
    _pending_doc(db, {"email": "a@addisenergy.com", "display_name": "A", "role": "admin"})
    fb_auth.generate_password_reset_link.side_effect = Exception("quota")
    with patch.object(um, "create_user", return_value={"uid": "u2", "email": "a@addisenergy.com"}):
        result = um.approve_user("req2")
    assert result["password_setup_link"] is None
    fb_auth.set_custom_user_claims.assert_called_once_with("u2", {"approved": True, "role": "admin"})


def test_purge_pending_passwords_counts_only_docs_with_password(fs):
    firestore_mock, db = fs
    docs = []
    for data in ({"email": "a", "password": "x"}, {"email": "b"}, {"email": "c", "password": "y"}):
        d = MagicMock()
        d.to_dict.return_value = data
        docs.append(d)
    db.collection.return_value.stream.return_value = docs

    assert um.purge_pending_passwords() == 2
    for d, touched in zip(docs, (True, False, True)):
        if touched:
            d.reference.update.assert_called_once_with({"password": firestore_mock.DELETE_FIELD})
        else:
            d.reference.update.assert_not_called()


def test_list_users_includes_custom_claims(fb_auth):
    u1, u2 = MagicMock(), MagicMock()
    u1.custom_claims = {"approved": True}
    u2.custom_claims = None
    fb_auth.list_users.return_value.users = [u1, u2]
    users = um.list_users()
    assert users[0]["custom_claims"] == {"approved": True}
    assert users[1]["custom_claims"] == {}
