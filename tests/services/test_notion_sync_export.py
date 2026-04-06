"""Unit tests for the Notion export step.

Uses the PostgreSQL test DB (db_session fixture) and mocked NotionSyncClient.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from backend.services.notion_sync.export import run_export
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment, ExperimentNotes


def _notion_page(page_id: str, reactor_label: str, status: str = "Pending") -> dict:
    return {
        "id": page_id,
        "properties": {
            "Name": {"title": [{"plain_text": reactor_label}]},
            "Change Request": {"rich_text": []},
            "Change Request Status": {"select": {"name": status}},
        },
    }


def _seed_experiment(
    db: Session,
    experiment_id: str,
    experiment_number: int,
    reactor_number: int,
    experiment_type: str = "Serum",
    start_date: datetime | None = None,
    description: str = "",
    status: ExperimentStatus = ExperimentStatus.ONGOING,
) -> Experiment:
    """Seed an experiment with conditions into the test DB."""
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=experiment_number,
        status=status,
        date=start_date or datetime(2026, 1, 1),
    )
    db.add(exp)
    db.flush()
    if description:
        note = ExperimentNotes(
            experiment_fk=exp.id,
            experiment_id=experiment_id,
            note_text=description,
        )
        db.add(note)
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=experiment_id,
        reactor_number=reactor_number,
        experiment_type=experiment_type,
    )
    db.add(cond)
    db.flush()
    return exp


def test_export_skips_idle_slots(db_session: Session) -> None:
    """write_experiment_info is only called for occupied (ONGOING) reactor slots."""
    client = MagicMock()
    pages = [
        _notion_page("aaa", "R01"),
        _notion_page("bbb", "R02"),  # no experiment in R02
    ]
    _seed_experiment(db_session, "SERUM_001", 1001, reactor_number=1)

    result = run_export(client, db_session, pages, cleared_page_ids=set())

    assert result.exported == 1
    client.write_experiment_info.assert_called_once()
    assert client.write_experiment_info.call_args[1]["page_id"] == "aaa"


def test_export_writes_correct_properties(db_session: Session) -> None:
    """write_experiment_info is called with correct experiment_id, description, date_started."""
    client = MagicMock()
    pages = [_notion_page("ccc", "R03")]
    _seed_experiment(
        db_session, "HPHT_001", 1002,
        reactor_number=3, experiment_type="HPHT",
        start_date=datetime(2026, 3, 15),
        description="Rock dissolution test",
    )

    run_export(client, db_session, pages, cleared_page_ids=set())

    client.write_experiment_info.assert_called_once_with(
        page_id="ccc",
        experiment_id="HPHT_001",
        description="Rock dissolution test",
        date_started="2026-03-15",
    )


def test_export_sets_pending_after_clear(db_session: Session) -> None:
    """set_status_pending is called for a page that was cleared in this cycle."""
    client = MagicMock()
    pages = [_notion_page("ddd", "R05")]
    _seed_experiment(db_session, "SERUM_002", 1003, reactor_number=5)

    run_export(client, db_session, pages, cleared_page_ids={"ddd"})

    client.set_status_pending.assert_called_once_with("ddd")


def test_export_preserves_in_progress_status(db_session: Session) -> None:
    """set_status_pending is NOT called for a page that was not cleared (In Progress)."""
    client = MagicMock()
    pages = [_notion_page("eee", "R06", status="In Progress")]
    _seed_experiment(db_session, "SERUM_003", 1004, reactor_number=6)

    run_export(client, db_session, pages, cleared_page_ids=set())

    client.set_status_pending.assert_not_called()


def test_export_preserves_carried_forward_status(db_session: Session) -> None:
    """set_status_pending is NOT called for a Carried Forward page that was not cleared."""
    client = MagicMock()
    pages = [_notion_page("fff", "R07", status="Carried Forward")]
    _seed_experiment(db_session, "SERUM_004", 1005, reactor_number=7)

    run_export(client, db_session, pages, cleared_page_ids=set())

    client.set_status_pending.assert_not_called()


def test_export_cf_slots_mapped_correctly(db_session: Session) -> None:
    """Core Flood experiments map to CF01/CF02 Notion labels."""
    client = MagicMock()
    pages = [_notion_page("ggg", "CF01")]
    _seed_experiment(
        db_session, "CF_001", 1006,
        reactor_number=1, experiment_type="Core Flood",
    )

    result = run_export(client, db_session, pages, cleared_page_ids=set())

    assert result.exported == 1
    assert client.write_experiment_info.call_args[1]["page_id"] == "ggg"


def test_export_skips_completed_experiments(db_session: Session) -> None:
    """COMPLETED experiments are not exported (only ONGOING)."""
    client = MagicMock()
    pages = [_notion_page("hhh", "R08")]
    _seed_experiment(
        db_session, "SERUM_005", 1007,
        reactor_number=8, status=ExperimentStatus.COMPLETED,
    )

    result = run_export(client, db_session, pages, cleared_page_ids=set())

    assert result.exported == 0
    client.write_experiment_info.assert_not_called()


def test_export_no_description_writes_empty_string(db_session: Session) -> None:
    """Experiment with no notes exports description as empty string (not None)."""
    client = MagicMock()
    pages = [_notion_page("iii", "R09")]
    _seed_experiment(db_session, "SERUM_006", 1008, reactor_number=9, description="")

    run_export(client, db_session, pages, cleared_page_ids=set())

    call_kwargs = client.write_experiment_info.call_args[1]
    assert call_kwargs["description"] == ""


def test_export_captures_write_error(db_session: Session) -> None:
    """If write_experiment_info raises, error is captured and processing continues."""
    client = MagicMock()
    client.write_experiment_info.side_effect = Exception("Notion API down")
    pages = [_notion_page("jjj", "R10")]
    _seed_experiment(db_session, "SERUM_007", 1009, reactor_number=10)

    result = run_export(client, db_session, pages, cleared_page_ids=set())

    assert result.exported == 0
    assert len(result.errors) == 1
    assert "R10" in result.errors[0]
