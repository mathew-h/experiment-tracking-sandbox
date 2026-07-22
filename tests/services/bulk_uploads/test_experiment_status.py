"""Tests for ExperimentStatusService.

Per-row model:
- Each row sets its own `status` (ONGOING / COMPLETED / CANCELLED / QUEUED).
- `reactor_number` and `date` are optional; `date` is the experiment start date.
- Setting an HPHT or Core Flood row to ONGOING with a reactor_number schedules
  demotion of an older ONGOING occupant in the same reactor (see Task 2 tests).
- A missing `experiment_id` or `status` column hard-errors the whole upload.
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
    reactor_number: int | None = None,
    date=None,
) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=status,
        date=date,
    )
    db.add(exp)
    db.flush()

    if experiment_type is not None or reactor_number is not None:
        cond = ExperimentalConditions(
            experiment_fk=exp.id,
            experiment_id=experiment_id,
            experiment_type=experiment_type,
            reactor_number=reactor_number,
        )
        db.add(cond)
        db.flush()

    return exp


# ---------------------------------------------------------------------------
# Column / row validation
# ---------------------------------------------------------------------------

def test_preview_missing_experiment_id_column_returns_error(db_session: Session):
    xlsx = make_excel(["status", "reactor_number"], [["ONGOING", 3]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "experiment_id" in preview.errors[0]
    assert preview.changes == []


def test_preview_missing_status_column_returns_error(db_session: Session):
    xlsx = make_excel(["experiment_id", "reactor_number"], [["HPHT_ST001", 3]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "status" in preview.errors[0]
    assert preview.changes == []


def test_preview_builds_planned_change_per_row(db_session: Session):
    """A valid row produces one PlannedChange with the parsed status/reactor/date."""
    _seed_experiment(db_session, "HPHT_ST001", 6601, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST001", "ongoing", 3, "2026-07-15"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert len(preview.changes) == 1
    change = preview.changes[0]
    assert change.experiment_id == "HPHT_ST001"
    assert change.new_status == "ONGOING"
    assert change.new_reactor_number == 3
    assert change.new_date is not None
    assert change.new_date.date().isoformat() == "2026-07-15"


def test_preview_records_missing_experiment_ids(db_session: Session):
    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["NONEXISTENT_ST", "ONGOING", 2]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert "NONEXISTENT_ST" in preview.missing_ids
    assert preview.changes == []
    assert preview.errors == []


def test_preview_invalid_status_produces_row_error(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST002", 6602, ExperimentStatus.ONGOING, "HPHT")
    xlsx = make_excel(
        ["experiment_id", "status"],
        [["HPHT_ST002", "IN_PROGRESS"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "Invalid status" in preview.errors[0]


def test_preview_invalid_reactor_number_produces_row_error(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST003", 6603, ExperimentStatus.ONGOING, "HPHT")
    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["HPHT_ST003", "ONGOING", "not-a-number"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "Invalid reactor_number" in preview.errors[0]


def test_preview_invalid_date_produces_row_error(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST004", 6604, ExperimentStatus.ONGOING, "HPHT")
    xlsx = make_excel(
        ["experiment_id", "status", "date"],
        [["HPHT_ST004", "ONGOING", "not-a-date"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "Invalid date" in preview.errors[0]


# ---------------------------------------------------------------------------
# Same-reactor-in-file conflict (Open Item #3: error, don't let apply order decide)
# ---------------------------------------------------------------------------

def test_preview_same_reactor_multiple_rows_errors(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST005", 6605, ExperimentStatus.COMPLETED, "HPHT")
    _seed_experiment(db_session, "HPHT_ST006", 6606, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["HPHT_ST005", "ONGOING", 4], ["HPHT_ST006", "ONGOING", 4]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert len(preview.errors) == 1
    assert "Reactor 4" in preview.errors[0]
    assert "HPHT_ST005" in preview.errors[0]
    assert "HPHT_ST006" in preview.errors[0]
    assert preview.changes == []


def test_preview_serum_rows_same_reactor_do_not_conflict(db_session: Session):
    """The same-reactor conflict check only applies to HPHT/Core Flood rows."""
    _seed_experiment(db_session, "Serum_ST001", 6607, ExperimentStatus.COMPLETED, "Serum")
    _seed_experiment(db_session, "Serum_ST002", 6608, ExperimentStatus.COMPLETED, "Serum")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["Serum_ST001", "ONGOING", 4], ["Serum_ST002", "ONGOING", 4]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert len(preview.changes) == 2
