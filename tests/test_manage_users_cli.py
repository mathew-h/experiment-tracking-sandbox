import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner


# Patch _init_firebase for the entire module so no real Firebase call is made.
@pytest.fixture(autouse=True)
def no_firebase_init():
    with patch("scripts.manage_users._init_firebase"):
        yield


def _import_cli():
    """Import cli lazily so the sys.path insert in manage_users.py runs first."""
    from scripts.manage_users import cli
    return cli


def test_pending_lists_requests():
    cli = _import_cli()
    runner = CliRunner()
    pending_data = [
        {
            "id": "abc123",
            "email": "alice@addisenergy.com",
            "display_name": "Alice",
            "role": "researcher",
            "created_at": "2026-01-01",
        }
    ]
    with patch("scripts.manage_users.list_pending_users", return_value=pending_data):
        result = runner.invoke(cli, ["pending"])
    assert result.exit_code == 0
    assert "abc123" in result.output
    assert "alice@addisenergy.com" in result.output


def test_pending_empty():
    cli = _import_cli()
    runner = CliRunner()
    with patch("scripts.manage_users.list_pending_users", return_value=[]):
        result = runner.invoke(cli, ["pending"])
    assert result.exit_code == 0
    assert "No pending" in result.output


def test_approve_request():
    cli = _import_cli()
    runner = CliRunner()
    approved_user = {"uid": "uid999", "email": "bob@addisenergy.com"}
    with patch("scripts.manage_users.approve_user", return_value=approved_user):
        result = runner.invoke(cli, ["approve", "req_abc"])
    assert result.exit_code == 0
    assert "bob@addisenergy.com" in result.output
    assert "uid999" in result.output


def test_approve_not_found():
    cli = _import_cli()
    runner = CliRunner(mix_stderr=True)
    with patch("scripts.manage_users.approve_user", side_effect=ValueError("Request not found.")):
        result = runner.invoke(cli, ["approve", "bad_id"])
    assert result.exit_code != 0
    assert "Request not found" in result.output


def test_reject_request():
    cli = _import_cli()
    runner = CliRunner()
    with patch("scripts.manage_users.reject_user", return_value=True):
        result = runner.invoke(cli, ["reject", "req_abc"])
    assert result.exit_code == 0
    assert "req_abc" in result.output


def test_reject_not_found():
    cli = _import_cli()
    runner = CliRunner(mix_stderr=True)
    with patch("scripts.manage_users.reject_user", side_effect=ValueError("Request not found.")):
        result = runner.invoke(cli, ["reject", "bad_id"])
    assert result.exit_code != 0
    assert "Request not found" in result.output


def test_approve_firebase_error():
    cli = _import_cli()
    runner = CliRunner(mix_stderr=True)
    with patch("scripts.manage_users.approve_user", side_effect=RuntimeError("Firebase unavailable")):
        result = runner.invoke(cli, ["approve", "req_abc"])
    assert result.exit_code != 0
    assert "Firebase unavailable" in result.output
