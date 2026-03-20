"""Tests for TimepointModificationsService."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Experiment, ExperimentalResults, ModificationsLog
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.timepoint_modifications import TimepointModificationsService

from .excel_helpers import make_excel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_experiment_with_result(
    db: Session,
    experiment_id: str = "HPHT_MOD001",
    time_days: float = 7.0,
    exp_num: int = 9901,
) -> tuple[Experiment, ExperimentalResults]:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()

    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=time_days,
        description=f"Day {time_days}",
    )
    db.add(result)
    db.flush()
    return exp, result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_valid_upload_sets_modification(db_session: Session):
    """Valid file sets brine_modification_description on the matched result row."""
    _seed_experiment_with_result(db_session, "HPHT_MOD001", 7.0, 9901)

    xlsx = make_excel(
        ["experiment_id", "time_point", "modification_description"],
        [["HPHT_MOD001", 7.0, "Added Mg(OH)2 after sampling"]],
    )
    updated, skipped, errors, feedbacks = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1
    assert skipped == 0
    assert feedbacks[0]["status"] == "updated"

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_MOD001")
        .first()
    )
    assert result is not None
    assert result.brine_modification_description == "Added Mg(OH)2 after sampling"
    assert result.has_brine_modification is True


def test_missing_required_columns_returns_error(db_session: Session):
    """File missing required column names returns an error, zero updates."""
    xlsx = make_excel(
        ["experiment_id", "days"],  # 'modification_description' missing; wrong alias for time
        [["HPHT_MOD001", 7.0]],
    )
    updated, skipped, errors, _ = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx
    )

    assert updated == 0
    assert any("modification_description" in e for e in errors)


def test_duplicate_pairs_in_file_rejected(db_session: Session):
    """File with duplicate (experiment_id, time_point) is rejected entirely, zero updates."""
    _seed_experiment_with_result(db_session, "HPHT_MOD002", 14.0, 9902)

    xlsx = make_excel(
        ["experiment_id", "time_point", "modification_description"],
        [
            ["HPHT_MOD002", 14.0, "First note"],
            ["HPHT_MOD002", 14.0, "Duplicate note"],
        ],
    )
    updated, skipped, errors, _ = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx
    )

    assert updated == 0
    assert any("duplicate" in e.lower() for e in errors)


def test_overwrite_false_skips_existing_modification(db_session: Session):
    """Existing modification is not overwritten when overwrite_existing=False."""
    exp, result = _seed_experiment_with_result(db_session, "HPHT_MOD003", 3.0, 9903)
    result.brine_modification_description = "Original note"
    db_session.flush()

    xlsx = make_excel(
        ["experiment_id", "time_point", "modification_description"],
        [["HPHT_MOD003", 3.0, "New note"]],
    )
    updated, skipped, errors, feedbacks = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx, overwrite_existing=False
    )

    assert errors == []
    assert updated == 0
    assert skipped == 1
    assert feedbacks[0]["status"] == "skipped"

    db_session.refresh(result)
    assert result.brine_modification_description == "Original note"


def test_overwrite_true_replaces_existing_modification(db_session: Session):
    """Existing modification IS replaced when overwrite_existing=True."""
    exp, result = _seed_experiment_with_result(db_session, "HPHT_MOD004", 5.0, 9904)
    result.brine_modification_description = "Old note"
    db_session.flush()

    xlsx = make_excel(
        ["experiment_id", "time_point", "modification_description"],
        [["HPHT_MOD004", 5.0, "Replaced note"]],
    )
    updated, skipped, errors, _ = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx, overwrite_existing=True
    )

    assert errors == []
    assert updated == 1
    assert skipped == 0

    db_session.flush()
    db_session.refresh(result)
    assert result.brine_modification_description == "Replaced note"


def test_audit_log_entry_written(db_session: Session):
    """A ModificationsLog row is written for each updated result."""
    _seed_experiment_with_result(db_session, "HPHT_MOD005", 21.0, 9905)

    xlsx = make_excel(
        ["experiment_id", "time_point", "modification_description"],
        [["HPHT_MOD005", 21.0, "Audit test note"]],
    )
    TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx, modified_by="testuser@addisenergy.com"
    )

    log = (
        db_session.query(ModificationsLog)
        .filter(ModificationsLog.experiment_id == "HPHT_MOD005")
        .first()
    )
    assert log is not None
    assert log.modified_by == "testuser@addisenergy.com"
    assert log.modified_table == "experimental_results"
    assert log.modification_type == "update"


def test_unknown_experiment_id_recorded_as_error(db_session: Session):
    """A row referencing a non-existent experiment is recorded as an error."""
    xlsx = make_excel(
        ["experiment_id", "time_point", "modification_description"],
        [["NONEXISTENT_EXP", 1.0, "Should fail"]],
    )
    updated, skipped, errors, _ = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx
    )

    assert updated == 0
    assert any("NONEXISTENT_EXP" in e for e in errors)
