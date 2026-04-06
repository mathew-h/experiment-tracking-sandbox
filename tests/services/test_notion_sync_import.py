"""Unit tests for the Notion import step.

Uses the PostgreSQL test DB (db_session fixture from tests/services/conftest.py).
All Notion API calls are mocked via MagicMock — no real Notion calls are made.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from backend.services.notion_sync.import_ import run_import
from database.models.notion_sync import ReactorChangeRequest

SYNC_DATE = date(2026, 4, 1)
_PAGE_ID = "abc12345-1234-1234-1234-abc123456789"


def _page(
    page_id: str,
    reactor_label: str,
    change_request: str,
    status: str = "Pending",
) -> dict:
    """Build a minimal mock Notion page matching the extract_* function expectations."""
    return {
        "id": page_id,
        "properties": {
            "Name": {"title": [{"plain_text": reactor_label}]},
            "Change Request": {
                "rich_text": [{"plain_text": change_request}] if change_request else []
            },
            "Change Request Status": {"select": {"name": status}},
        },
    }


def _empty_page(page_id: str, reactor_label: str) -> dict:
    return {
        "id": page_id,
        "properties": {
            "Name": {"title": [{"plain_text": reactor_label}]},
            "Change Request": {"rich_text": []},
            "Change Request Status": {"select": {"name": "Pending"}},
        },
    }


def test_import_skips_empty_rows(db_session: Session) -> None:
    """Rows with blank Change Request produce zero DB writes and zero Notion calls."""
    client = MagicMock()
    pages = [_empty_page(_PAGE_ID, "R01")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.skipped == 1
    assert result.imported == 0
    client.clear_change_request.assert_not_called()
    assert db_session.query(ReactorChangeRequest).count() == 0


def test_import_skips_whitespace_only_change_request(db_session: Session) -> None:
    """Change Request with only whitespace is treated as empty."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R02", "   ", "Pending")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.skipped == 1
    assert result.imported == 0


def test_import_preserves_in_progress(db_session: Session) -> None:
    """In Progress row is written to DB; Notion clear is NOT called."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R05", "Run test today", "In Progress")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.imported == 1
    assert result.carried_forward == 0
    client.clear_change_request.assert_not_called()

    row = db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R05", sync_date=SYNC_DATE
    ).one()
    assert row.carried_forward is False
    assert row.notion_status == "In Progress"


def test_import_preserves_carried_forward(db_session: Session) -> None:
    """Carried Forward row is written with carried_forward=True; Notion clear NOT called."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R07", "Continue reaction", "Carried Forward")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.imported == 1
    assert result.carried_forward == 1
    client.clear_change_request.assert_not_called()

    row = db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R07", sync_date=SYNC_DATE
    ).one()
    assert row.carried_forward is True
    assert row.notion_status == "Carried Forward"


def test_import_clears_completed_after_write(db_session: Session) -> None:
    """Completed row: DB upsert first, THEN Notion clear."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R03", "Sample and clean", "Completed")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.imported == 1
    assert _PAGE_ID in result.cleared_page_ids
    client.clear_change_request.assert_called_once_with(_PAGE_ID)
    assert db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R03", sync_date=SYNC_DATE
    ).count() == 1


def test_import_clears_pending_with_content(db_session: Session) -> None:
    """Pending row with non-empty content is imported and cleared."""
    client = MagicMock()
    page_id = "deadbeef-dead-beef-dead-beefdeadbeef"
    pages = [_page(page_id, "R02", "Check pH and repressurize", "Pending")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.imported == 1
    assert page_id in result.cleared_page_ids
    client.clear_change_request.assert_called_once_with(page_id)


def test_import_db_committed_before_notion_clear(db_session: Session) -> None:
    """If Notion clear raises, the DB row must already be committed."""
    client = MagicMock()
    client.clear_change_request.side_effect = Exception("Network timeout")
    pages = [_page(_PAGE_ID, "R08", "Take a sample", "Completed")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    # DB row persists despite Notion error
    assert db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R08", sync_date=SYNC_DATE
    ).count() == 1
    # Error was captured, not raised
    assert len(result.errors) == 1


def test_import_upsert_idempotent(db_session: Session) -> None:
    """Two runs with same reactor_label + sync_date produce exactly one DB row."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R01", "Sample reactor", "Pending")]

    run_import(client, db_session, pages, SYNC_DATE)
    result = run_import(client, db_session, pages, SYNC_DATE)

    assert db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R01", sync_date=SYNC_DATE
    ).count() == 1
    assert result.imported == 1


def test_carried_forward_accumulates_across_dates(db_session: Session) -> None:
    """Same Carried Forward row on two different sync dates produces two DB rows."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R04", "Ongoing reaction", "Carried Forward")]
    date1 = date(2026, 4, 1)
    date2 = date(2026, 4, 2)

    run_import(client, db_session, pages, date1)
    run_import(client, db_session, pages, date2)

    assert db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R04"
    ).count() == 2
