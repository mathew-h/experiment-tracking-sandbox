"""Tests for TimepointModificationsService."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Experiment, ExperimentalResults, ExperimentNotes, ModificationsLog
from database.models.enums import ExperimentStatus, NoteType
from backend.services.notes import add_note
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
    )
    db.add(result)
    db.flush()
    return exp, result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_valid_upload_sets_modification(db_session: Session):
    """Valid file writes a modification note on the matched result row."""
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
    notes = db_session.query(ExperimentNotes).filter(ExperimentNotes.result_id == result.id).all()
    assert [(n.note_type, n.note_text, n.created_by) for n in notes] == [
        (NoteType.modification, "Added Mg(OH)2 after sampling", "bulk_upload")
    ]


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
    add_note(db_session, exp, "Original note", note_type=NoteType.modification,
             result_id=result.id, created_by="someone@addisenergy.com")

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

    notes = db_session.query(ExperimentNotes).filter(ExperimentNotes.result_id == result.id).all()
    assert [(n.note_text, n.created_by) for n in notes] == [("Original note", "someone@addisenergy.com")]


def test_overwrite_true_replaces_existing_modification(db_session: Session):
    """Existing modification IS replaced when overwrite_existing=True."""
    exp, result = _seed_experiment_with_result(db_session, "HPHT_MOD004", 5.0, 9904)
    add_note(db_session, exp, "Old note", note_type=NoteType.modification,
             result_id=result.id, created_by="bulk_upload")

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
    notes = db_session.query(ExperimentNotes).filter(ExperimentNotes.result_id == result.id).all()
    assert [(n.note_text, n.created_by) for n in notes] == [("Replaced note", "bulk_upload")]


def test_overwrite_true_writes_own_slot_and_leaves_another_authors_note(db_session: Session):
    """The guard trips on anyone's note; overwrite writes only the caller's slot."""
    exp, result = _seed_experiment_with_result(db_session, "HPHT_MOD006", 9.0, 9906)
    add_note(db_session, exp, "Hand-written by a researcher", note_type=NoteType.modification,
             result_id=result.id, created_by="researcher@addisenergy.com")
    xlsx = make_excel(
        ["experiment_id", "time_point", "modification_description"],
        [["HPHT_MOD006", 9.0, "Upload note"]],
    )
    updated, skipped, errors, feedbacks = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx, overwrite_existing=False, modified_by="uploader@addisenergy.com",
    )
    assert (updated, skipped, errors) == (0, 1, [])
    assert "modification note already exists" in feedbacks[0]["reason"]

    updated, skipped, errors, _ = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx, overwrite_existing=True, modified_by="uploader@addisenergy.com",
    )
    assert (updated, skipped, errors) == (1, 0, [])
    notes = sorted(
        (n.created_by, n.note_text)
        for n in db_session.query(ExperimentNotes).filter(ExperimentNotes.result_id == result.id)
    )
    assert notes == [
        ("researcher@addisenergy.com", "Hand-written by a researcher"),
        ("uploader@addisenergy.com", "Upload note"),
    ]


def test_audit_log_entry_written(db_session: Session):
    """A ModificationsLog row is written for each updated result."""
    _exp, seeded = _seed_experiment_with_result(db_session, "HPHT_MOD005", 21.0, 9905)
    log_result_id = seeded.id

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
    assert log.modified_table == "experiment_notes"
    assert log.modification_type == "update"
    assert log.new_values == {"result_id": log_result_id, "note_text": "Audit test note"}
    assert log.old_values == {"result_id": log_result_id, "note_text": None}


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


def test_ambiguous_experiment_id_reports_candidates(db_session: Session):
    """An ambiguous ID must name both candidates, not just say 'not found'.

    AMBTPM_1 and AMBTPM_001 share the normalized key ambtpm_1, so .first() used
    to attach the modification to whichever row came back.
    """
    db_session.add_all([
        Experiment(experiment_id="AMBTPM_1", experiment_number=8806001,
                   status=ExperimentStatus.ONGOING),
        Experiment(experiment_id="AMBTPM_001", experiment_number=8806002,
                   status=ExperimentStatus.ONGOING),
    ])
    db_session.flush()

    xlsx = make_excel(
        ["experiment_id", "time_point", "modification_description"],
        [["ambtpm-01", 7.0, "swapped brine"]],
    )
    updated, skipped, errors, _ = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx
    )

    assert updated == 0
    assert any("ambiguous" in e.lower() for e in errors), errors
    assert any("AMBTPM_1" in e and "AMBTPM_001" in e for e in errors), errors
