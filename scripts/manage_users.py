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


@cli.command()
@click.argument("request_id")
def approve(request_id: str) -> None:
    """Approve a pending user request and create their Firebase account."""
    try:
        user = approve_user(request_id)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Approved: {user['email']} (uid: {user['uid']})")


@cli.command()
@click.argument("request_id")
def reject(request_id: str) -> None:
    """Reject and remove a pending user request."""
    try:
        reject_user(request_id)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Request {request_id} rejected and removed.")


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
    except Exception as exc:
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
    except Exception as exc:
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


if __name__ == "__main__":
    cli()
