"""Tests for ExperimentStatusService.

Key logic:
- to_ongoing: experiments listed in the file that exist in DB (reactor_number optional).
- to_completed: ONGOING experiments with HPHT ExperimentalConditions NOT listed in the file.
- missing_ids: listed experiment IDs not found in DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Experiment
from database.models import ExperimentalConditions
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.experiment_status import ExperimentStatusService

from .excel_helpers import make_excel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_experiment(
    db: Session,
    experiment_id: str,
    exp_num: int,
    status: ExperimentStatus = ExperimentStatus.ONGOING,
    experiment_type: str | None = None,
) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=status,
    )
    db.add(exp)
    db.flush()

    if experiment_type:
        cond = ExperimentalConditions(
            experiment_fk=exp.id,
            experiment_id=experiment_id,
            experiment_type=experiment_type,
        )
        db.add(cond)
        db.flush()

    return exp


# ---------------------------------------------------------------------------
# Preview tests
# ---------------------------------------------------------------------------

def test_preview_places_listed_experiment_in_to_ongoing(db_session: Session):
    """Any experiment listed in the file goes to to_ongoing (with or without reactor_number)."""
    _seed_experiment(db_session, "HPHT_ST001", 6601, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "reactor_number"],
        [["HPHT_ST001", 3]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    ongoing_ids = [r["experiment_id"] for r in preview.to_ongoing]
    assert "HPHT_ST001" in ongoing_ids


def test_preview_ongoing_hpht_not_in_file_goes_to_completed(db_session: Session):
    """ONGOING HPHT experiment NOT in the file is auto-queued for COMPLETED."""
    _seed_experiment(db_session, "HPHT_ST002", 6602, ExperimentStatus.ONGOING, "HPHT")
    # Seed a different experiment in the file to trigger the completed-detection query
    _seed_experiment(db_session, "HPHT_ST003", 6603, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "reactor_number"],
        [["HPHT_ST003", 2]],  # ST002 is NOT in the file
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    completed_ids = [r["experiment_id"] for r in preview.to_completed]
    assert "HPHT_ST002" in completed_ids


def test_preview_records_missing_experiment_ids(db_session: Session):
    """IDs not in the DB are captured in missing_ids."""
    xlsx = make_excel(
        ["experiment_id", "reactor_number"],
        [["NONEXISTENT_ST", 2]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert "NONEXISTENT_ST" in preview.missing_ids


def test_preview_missing_experiment_id_column_returns_error(db_session: Session):
    """File without 'experiment_id' column returns an error."""
    xlsx = make_excel(
        ["exp", "reactor"],
        [["HPHT_ST001", 3]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert len(preview.errors) > 0


# ---------------------------------------------------------------------------
# Apply tests
# ---------------------------------------------------------------------------

def test_apply_marks_experiment_ongoing_with_reactor(db_session: Session):
    """apply_status_changes transitions experiment to ONGOING."""
    exp = _seed_experiment(db_session, "HPHT_ST004", 6604, ExperimentStatus.COMPLETED, "HPHT")

    marked_ongoing, marked_completed, _reactor_updates, errors = (
        ExperimentStatusService.apply_status_changes(
            db_session, ["HPHT_ST004"], {}
        )
    )

    assert errors == []
    assert marked_ongoing == 1
    db_session.refresh(exp)
    assert exp.status == ExperimentStatus.ONGOING


def test_apply_auto_completes_unlisted_ongoing_hpht(db_session: Session):
    """apply_status_changes marks ONGOING HPHT experiments not in to_ongoing list as COMPLETED."""
    exp_ongoing = _seed_experiment(
        db_session, "HPHT_ST005", 6605, ExperimentStatus.ONGOING, "HPHT"
    )
    exp_listed = _seed_experiment(
        db_session, "HPHT_ST006", 6606, ExperimentStatus.COMPLETED, "HPHT"
    )

    # Only ST006 is in to_ongoing; ST005 is ONGOING+HPHT and NOT listed → COMPLETED
    marked_ongoing, marked_completed, _ru, errors = (
        ExperimentStatusService.apply_status_changes(
            db_session, ["HPHT_ST006"], {}
        )
    )

    assert errors == []
    assert marked_completed >= 1
    db_session.flush()
    db_session.refresh(exp_ongoing)
    assert exp_ongoing.status == ExperimentStatus.COMPLETED


def test_apply_empty_inputs_zero_changes(db_session: Session):
    """apply_status_changes with empty to_ongoing and no ONGOING HPHT → zero changes."""
    marked_ongoing, marked_completed, _ru, errors = (
        ExperimentStatusService.apply_status_changes(db_session, [], {})
    )
    assert errors == []
    assert marked_ongoing == 0


def test_full_round_trip_file_to_db_state(db_session: Session):
    """Full round-trip: file → preview → apply → DB state correct."""
    exp_a = _seed_experiment(db_session, "HPHT_ST007", 6607, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "reactor_number"],
        [["HPHT_ST007", 5]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert preview.errors == []

    to_ongoing = [item["experiment_id"] for item in preview.to_ongoing]
    reactor_map = {
        item["experiment_id"]: item["new_reactor_number"]
        for item in preview.to_ongoing
        if item.get("new_reactor_number") is not None
    }
    marked_ongoing, _mc, _ru, errors = ExperimentStatusService.apply_status_changes(
        db_session, to_ongoing, reactor_map
    )

    assert errors == []
    assert marked_ongoing == 1
    db_session.refresh(exp_a)
    assert exp_a.status == ExperimentStatus.ONGOING
