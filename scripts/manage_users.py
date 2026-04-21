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
