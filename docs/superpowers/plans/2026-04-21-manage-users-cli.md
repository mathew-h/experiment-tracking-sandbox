# manage_users CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `scripts/manage_users.py`, a Click-based CLI that wraps `auth/user_management.py` for Firebase user administration without needing Streamlit.

**Architecture:** Single CLI script that initializes Firebase via `backend/config/settings.py` (the same Pydantic-settings path the FastAPI backend uses — no Streamlit dependency). All business logic lives in the existing `auth/user_management.py`; the CLI is a thin dispatch layer only. Tests use `click.testing.CliRunner` with all Firebase calls mocked.

**Tech Stack:** Python 3, Click 8 (already in requirements.txt), firebase-admin 6.7, unittest.mock

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `scripts/manage_users.py` | CLI entry point — Firebase init, Click group + all subcommands |
| Create | `tests/test_manage_users_cli.py` | CliRunner tests, all commands mocked |

No changes to `auth/user_management.py` or `backend/` — this is additive only.

---

## Context You Need Before Starting

- `auth/user_management.py` — contains all functions the CLI calls; **do not modify it**
- `backend/config/settings.py` — `get_settings()` returns a `Settings` instance with `.firebase_cred_dict` property; used for Firebase init
- `backend/auth/firebase_auth.py` — reference implementation for how to initialize Firebase from settings (the `_ensure_firebase_initialized()` pattern)
- Existing scripts (e.g. `scripts/migrate-sqlite-to-postgres.py`) use `sys.path.insert(0, ...)` to make project-root imports work — follow the same pattern

---

### Task 1: Scaffold + `pending` command

**Files:**
- Create: `scripts/manage_users.py`
- Create: `tests/test_manage_users_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_manage_users_cli.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /c/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox
.venv/Scripts/python -m pytest tests/test_manage_users_cli.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.manage_users'`

- [ ] **Step 3: Create the script scaffold with `pending` command**

Create `scripts/manage_users.py`:

```python
#!/usr/bin/env python3
"""Firebase user management CLI for the Experiment Tracking System.

Usage (run from project root):
  python scripts/manage_users.py pending
  python scripts/manage_users.py approve <request_id>
  python scripts/manage_users.py reject <request_id>
  python scripts/manage_users.py list
  python scripts/manage_users.py create <email> <password> <display_name>
  python scripts/manage_users.py delete <uid>
  python scripts/manage_users.py update <uid> [--name NAME] [--email EMAIL]
  python scripts/manage_users.py set-claims <uid> <role>
  python scripts/manage_users.py reset-password <email>
  python scripts/manage_users.py delete-request <email>
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import click
import firebase_admin
from firebase_admin import credentials

from backend.config.settings import get_settings
from auth.user_management import (
    list_pending_users,
    approve_user,
    reject_user,
    list_users,
    create_user,
    delete_user,
    update_user,
    set_user_claims,
    reset_user_password,
    delete_request_by_email,
)


def _init_firebase() -> None:
    """Initialize Firebase Admin SDK from .env settings. No-op if already done."""
    if firebase_admin._apps:
        return
    settings = get_settings()
    if not settings.firebase_project_id:
        click.echo(
            "Error: Firebase credentials not configured. "
            "Set FIREBASE_PROJECT_ID / FIREBASE_PRIVATE_KEY / FIREBASE_CLIENT_EMAIL in .env",
            err=True,
        )
        sys.exit(1)
    cred = credentials.Certificate(settings.firebase_cred_dict)
    firebase_admin.initialize_app(cred)


@click.group()
def cli() -> None:
    """Firebase user management for Experiment Tracking System."""
    _init_firebase()


@cli.command()
def pending() -> None:
    """List all pending registration requests."""
    users = list_pending_users()
    if not users:
        click.echo("No pending requests.")
        return
    for u in users:
        click.echo(
            f"ID: {u['id']}\n"
            f"  Email:   {u['email']}\n"
            f"  Name:    {u.get('display_name', 'N/A')}\n"
            f"  Role:    {u.get('role', 'N/A')}\n"
            f"  Created: {u.get('created_at', 'N/A')}\n"
        )


if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/Scripts/python -m pytest tests/test_manage_users_cli.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/manage_users.py tests/test_manage_users_cli.py
git commit -m "$(cat <<'EOF'
[fix] add manage_users CLI scaffold with pending command

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 2: `approve` and `reject` commands

**Files:**
- Modify: `scripts/manage_users.py`
- Modify: `tests/test_manage_users_cli.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_manage_users_cli.py`:

```python
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
    runner = CliRunner()
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
    runner = CliRunner()
    with patch("scripts.manage_users.reject_user", side_effect=ValueError("Request not found.")):
        result = runner.invoke(cli, ["reject", "bad_id"])
    assert result.exit_code != 0
    assert "Request not found" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python -m pytest tests/test_manage_users_cli.py -v -k "approve or reject"
```

Expected: `4 failed` — commands don't exist yet

- [ ] **Step 3: Add `approve` and `reject` commands to the script**

In `scripts/manage_users.py`, after the `pending` command and before `if __name__ == "__main__":`, add:

```python
@cli.command()
@click.argument("request_id")
def approve(request_id: str) -> None:
    """Approve a pending user request and create their Firebase account."""
    try:
        user = approve_user(request_id)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Approved: {user['email']} (uid: {user['uid']})")


@cli.command()
@click.argument("request_id")
def reject(request_id: str) -> None:
    """Reject and remove a pending user request."""
    try:
        reject_user(request_id)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Request {request_id} rejected and removed.")
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
.venv/Scripts/python -m pytest tests/test_manage_users_cli.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/manage_users.py tests/test_manage_users_cli.py
git commit -m "$(cat <<'EOF'
[fix] add approve and reject commands to manage_users CLI

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 3: Remaining commands (`list`, `create`, `delete`, `update`, `set-claims`, `reset-password`, `delete-request`)

**Files:**
- Modify: `scripts/manage_users.py`
- Modify: `tests/test_manage_users_cli.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_manage_users_cli.py`:

```python
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
    runner = CliRunner()
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python -m pytest tests/test_manage_users_cli.py -v -k "list or create or delete or update or set or reset"
```

Expected: all new tests `FAILED` — commands not yet defined

- [ ] **Step 3: Add remaining commands to the script**

In `scripts/manage_users.py`, after the `reject` command and before `if __name__ == "__main__":`, add:

```python
@cli.command("list")
def list_cmd() -> None:
    """List all Firebase Auth users."""
    users = list_users()
    if not users:
        click.echo("No users found.")
        return
    for u in users:
        status = "disabled" if u.get("disabled") else "active"
        click.echo(f"{u['uid']}  {u['email']}  {u.get('display_name', '')}  [{status}]")


@cli.command()
@click.argument("email")
@click.argument("password")
@click.argument("display_name")
def create(email: str, password: str, display_name: str) -> None:
    """Create a new Firebase Auth user directly (bypasses approval flow)."""
    try:
        user = create_user(email, password, display_name)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Created: {user['email']} (uid: {user['uid']})")


@cli.command()
@click.argument("uid")
def delete(uid: str) -> None:
    """Delete a Firebase Auth user by UID."""
    try:
        delete_user(uid)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Deleted user {uid}.")


@cli.command()
@click.argument("uid")
@click.option("--name", default=None, help="New display name")
@click.option("--email", default=None, help="New email (must be @addisenergy.com)")
def update(uid: str, name: str, email: str) -> None:
    """Update a user's display name or email."""
    try:
        user = update_user(uid, display_name=name, email=email)
    except (ValueError, Exception) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Updated: {user['email']} (uid: {user['uid']})")


@cli.command("set-claims")
@click.argument("uid")
@click.argument("role")
def set_claims(uid: str, role: str) -> None:
    """Set approved=True and role claim for an existing Firebase user."""
    try:
        user = set_user_claims(uid, role=role)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Claims set: uid={user['uid']} claims={user['custom_claims']}")


@cli.command("reset-password")
@click.argument("email")
def reset_password(email: str) -> None:
    """Generate a password reset link for a user."""
    try:
        link = reset_user_password(email)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Reset link: {link}")


@cli.command("delete-request")
@click.argument("email")
def delete_request(email: str) -> None:
    """Delete any pending Firestore registration requests for an email."""
    deleted = delete_request_by_email(email)
    if deleted:
        click.echo(f"Deleted pending request(s) for {email}.")
    else:
        click.echo(f"No pending request found for {email}.")
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
.venv/Scripts/python -m pytest tests/test_manage_users_cli.py -v
```

Expected: all tests `PASSED` (16 total)

- [ ] **Step 5: Smoke test the help output (no Firebase needed)**

```bash
.venv/Scripts/python scripts/manage_users.py --help
```

Expected: list of all subcommands printed.

```bash
.venv/Scripts/python scripts/manage_users.py pending --help
```

Expected: description of `pending` command.

- [ ] **Step 6: Commit**

```bash
git add scripts/manage_users.py tests/test_manage_users_cli.py
git commit -m "$(cat <<'EOF'
[fix] complete manage_users CLI with all subcommands

- Tests added: yes
- Docs updated: no
EOF
)"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|-------------|------|
| `pending` — list pending requests | Task 1 |
| `approve <request_id>` | Task 2 |
| `reject <request_id>` | Task 2 |
| `list` — all Firebase Auth users | Task 3 |
| `create <email> <password> <display_name>` | Task 3 |
| `delete <uid>` | Task 3 |
| `update <uid> [--name] [--email]` | Task 3 |
| `set-claims <uid> <role>` | Task 3 |
| `reset-password <email>` | Task 3 |
| `delete-request <email>` | Task 3 |
| No Streamlit dependency in CLI | `_init_firebase()` uses `backend/config/settings.py` |
| Error cases exit non-zero | `sys.exit(1)` after `click.echo(..., err=True)` |

### Type + Name Consistency

- `list_pending_users`, `approve_user`, `reject_user`, `list_users`, `create_user`, `delete_user`, `update_user`, `set_user_claims`, `reset_user_password`, `delete_request_by_email` — all match `auth/user_management.py` exactly
- `_import_cli()` used in all tests for consistent lazy import
- `no_firebase_init` fixture is `autouse=True` — covers all tests automatically

### No Placeholders

Scanned — all steps have complete code. No TBD/TODO/similar patterns found.
