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
