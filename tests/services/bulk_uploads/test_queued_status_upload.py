"""Bulk status upload must not auto-complete QUEUED experiments (issue #33)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Experiment
from database.models import ExperimentalConditions
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.experiment_status import ExperimentStatusService

from .excel_helpers import make_excel


def _seed(db: Session, exp_id: str, num: int, status: ExperimentStatus, exp_type: str) -> Experiment:
    exp = Experiment(experiment_id=exp_id, experiment_number=num, status=status)
    db.add(exp)
    db.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp_id, experiment_type=exp_type,
    )
    db.add(cond)
    db.flush()
    return exp


def test_bulk_status_upload_does_not_complete_queued(db_session: Session):
    """A QUEUED HPHT experiment absent from the upload file must remain QUEUED."""
    queued_exp = _seed(db_session, "HPHT_QUEUED_001", 33010, ExperimentStatus.QUEUED, "HPHT")
    _seed(db_session, "HPHT_ACTIVE_001", 33011, ExperimentStatus.ONGOING, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "reactor_number"],
        [["HPHT_ACTIVE_001", 1]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert preview.errors == []
    completed_ids = [r["experiment_id"] for r in preview.to_completed]
    assert "HPHT_QUEUED_001" not in completed_ids

    _ongoing, _completed, _ru, errors = ExperimentStatusService.apply_status_changes(
        db_session, ["HPHT_ACTIVE_001"], {}
    )
    assert errors == []
    db_session.refresh(queued_exp)
    assert queued_exp.status == ExperimentStatus.QUEUED, (
        "QUEUED experiment must not be auto-completed by bulk status upload"
    )
