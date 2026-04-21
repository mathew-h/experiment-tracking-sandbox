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


def test_list_users():
    cli = _import_cli()
    runner = CliRunner()
    users_data = [
        {"uid": "uid1", "email": "alice@addisenergy.com", "display_name": "Alice", "disabled": False},
        {"uid": "uid2", "email": "bob@addisenergy.com", "display_name": "Bob", "disabled": True},
    ]
    with patch("scripts.manage_users.list_users", return_value=users_data):
        result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "uid1" in result.output
    assert "alice@addisenergy.com" in result.output
    assert "uid2" in result.output
    assert "disabled" in result.output


def test_list_users_empty():
    cli = _import_cli()
    runner = CliRunner()
    with patch("scripts.manage_users.list_users", return_value=[]):
        result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "No users" in result.output


def test_create_user():
    cli = _import_cli()
    runner = CliRunner()
    new_user = {"uid": "uid_new", "email": "carol@addisenergy.com"}
    with patch("scripts.manage_users.create_user", return_value=new_user):
        result = runner.invoke(cli, ["create", "carol@addisenergy.com", "pass123", "Carol"])
    assert result.exit_code == 0
    assert "carol@addisenergy.com" in result.output


def test_create_user_domain_error():
    cli = _import_cli()
    runner = CliRunner(mix_stderr=True)
    with patch("scripts.manage_users.create_user", side_effect=ValueError("Email must end with @addisenergy.com")):
        result = runner.invoke(cli, ["create", "carol@gmail.com", "pass123", "Carol"])
    assert result.exit_code != 0
    assert "addisenergy.com" in result.output


def test_delete_user():
    cli = _import_cli()
    runner = CliRunner()
    with patch("scripts.manage_users.delete_user", return_value=True):
        result = runner.invoke(cli, ["delete", "uid_abc"])
    assert result.exit_code == 0
    assert "uid_abc" in result.output


def test_update_user_name():
    cli = _import_cli()
    runner = CliRunner()
    updated = {"uid": "uid1", "email": "alice@addisenergy.com"}
    with patch("scripts.manage_users.update_user", return_value=updated):
        result = runner.invoke(cli, ["update", "uid1", "--name", "Alicia"])
    assert result.exit_code == 0
    assert "alice@addisenergy.com" in result.output


def test_set_claims():
    cli = _import_cli()
    runner = CliRunner()
    claimed = {"uid": "uid1", "email": "alice@addisenergy.com", "custom_claims": {"approved": True, "role": "admin"}}
    with patch("scripts.manage_users.set_user_claims", return_value=claimed):
        result = runner.invoke(cli, ["set-claims", "uid1", "admin"])
    assert result.exit_code == 0
    assert "admin" in result.output


def test_reset_password():
    cli = _import_cli()
    runner = CliRunner()
    with patch("scripts.manage_users.reset_user_password", return_value="https://reset.link/token"):
        result = runner.invoke(cli, ["reset-password", "alice@addisenergy.com"])
    assert result.exit_code == 0
    assert "https://reset.link/token" in result.output


def test_delete_request_found():
    cli = _import_cli()
    runner = CliRunner()
    with patch("scripts.manage_users.delete_request_by_email", return_value=True):
        result = runner.invoke(cli, ["delete-request", "alice@addisenergy.com"])
    assert result.exit_code == 0
    assert "Deleted" in result.output


def test_delete_request_not_found():
    cli = _import_cli()
    runner = CliRunner()
    with patch("scripts.manage_users.delete_request_by_email", return_value=False):
        result = runner.invoke(cli, ["delete-request", "nobody@addisenergy.com"])
    assert result.exit_code == 0
    assert "No pending request" in result.output
