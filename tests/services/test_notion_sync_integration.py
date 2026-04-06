"""Integration tests for the full Notion sync cycle.

Uses the PostgreSQL test DB and a fully mocked NotionSyncClient.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from backend.services.notion_sync.sync import run_sync
from backend.services.notion_sync.client import NotionSyncClient
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment
from database.models.notion_sync import ReactorChangeRequest


def _notion_page(page_id: str, reactor_label: str, change_request: str = "", status: str = "Pending") -> dict:
    return {
        "id": page_id,
        "properties": {
            "Name": {"title": [{"plain_text": reactor_label}]},
            "Change Request": {
                "rich_text": [{"plain_text": change_request}] if change_request.strip() else []
            },
            "Change Request Status": {"select": {"name": status}},
        },
    }


def _seed(db: Session, experiment_id: str, number: int, reactor: int, etype: str = "Serum") -> None:
    exp = Experiment(
        experiment_id=experiment_id, experiment_number=number,
        status=ExperimentStatus.ONGOING, date=datetime(2026, 1, 1),
    )
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=experiment_id,
        reactor_number=reactor, experiment_type=etype,
    ))
    db.flush()


def test_full_sync_cycle(db_session: Session) -> None:
    """Full sync: 2 ONGOING experiments, 1 non-empty Change Request → 1 import + 2 exports."""
    client = MagicMock(spec=NotionSyncClient)
    client.query_all_rows.return_value = [
        _notion_page("page-r01-0000-0000-0000-000000000000", "R01", "Sample today", "Pending"),
        _notion_page("page-r03-0000-0000-0000-000000000000", "R03", "", "Pending"),
    ]

    _seed(db_session, "SERUM_A", 2001, reactor=1)
    _seed(db_session, "SERUM_B", 2002, reactor=3)

    result = run_sync(client, db_session)

    # Import: R01 has content, R03 is empty → 1 imported, 1 skipped
    assert result.imported == 1
    # Export: 2 ONGOING experiments → 2 Notion writes
    assert result.exported == 2
    assert result.errors == []

    # DB should have one ReactorChangeRequest row for R01
    assert db_session.query(ReactorChangeRequest).count() == 1
    # Notion write calls: one per occupied slot
    assert client.write_experiment_info.call_count == 2
    # R01 had its Change Request cleared → status was reset to Pending in export
    client.set_status_pending.assert_called_once_with(
        "page-r01-0000-0000-0000-000000000000"
    )


def test_sync_survives_notion_outage(db_session: Session) -> None:
    """If Notion API raises on query_all_rows, sync logs error and returns without crashing."""
    import httpx
    client = MagicMock(spec=NotionSyncClient)
    client.query_all_rows.side_effect = httpx.ConnectError("connection refused")

    result = run_sync(client, db_session)

    assert len(result.errors) == 1
    assert "connection refused" in result.errors[0]
    assert result.imported == 0
    assert result.exported == 0


def test_sync_result_to_dict(db_session: Session) -> None:
    """SyncResult.to_dict() returns the summary payload for the API response."""
    client = MagicMock(spec=NotionSyncClient)
    client.query_all_rows.return_value = []

    result = run_sync(client, db_session)

    d = result.to_dict()
    assert set(d.keys()) == {"imported", "exported", "carried_forward", "errors"}
