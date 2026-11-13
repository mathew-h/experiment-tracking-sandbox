"""Issue #122 PR-D: the Solution Chemistry parser's Description column is a
'result_note' (an 'observation' until 2026-11-09) signed by the parser (one slot
per result); a blank cell writes nothing and leaves an earlier note in place.

The quick-upload and long-format parsers this file also covered were deleted in
issue #189 (no route; legacy Streamlit only)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Experiment, ExperimentNotes, ExperimentalResults
from database.models.enums import ExperimentStatus, NoteType
from backend.services.bulk_uploads.scalar_results import ScalarResultsUploadService

from .excel_helpers import make_excel


def _seed(db: Session, exp_id: str, num: int) -> Experiment:
    exp = Experiment(experiment_id=exp_id, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _notes(db: Session, exp: Experiment):
    return db.execute(
        select(ExperimentNotes).where(ExperimentNotes.experiment_fk == exp.id).order_by(ExperimentNotes.id)
    ).scalars().all()


def _result_ids(db: Session, exp: Experiment):
    return db.execute(
        select(ExperimentalResults.id).where(ExperimentalResults.experiment_fk == exp.id)
    ).scalars().all()


_SCALAR_HEADERS = ["Experiment ID", "Time (days)", "Description", "Gross Ammonium (mM)"]


def test_scalar_description_becomes_a_result_note_signed_by_the_parser(db_session: Session):
    exp = _seed(db_session, "PON_001", 9122401)
    created, updated, skipped, errors, _fb = ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_001", 7.0, "Liquid clear, no gas", 1.2]]),
    )
    assert errors == [] and created == 1
    (rid,) = _result_ids(db_session, exp)
    assert [(n.note_type, n.result_id, n.note_text, n.created_by) for n in _notes(db_session, exp)] == [
        (NoteType.result_note, rid, "Liquid clear, no gas", "scalar_results"),
    ]


def test_scalar_reupload_updates_the_slot_and_a_blank_cell_leaves_it(db_session: Session):
    exp = _seed(db_session, "PON_002", 9122402)
    ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_002", 7.0, "first text", 1.2]]),
    )
    first = _notes(db_session, exp)
    assert len(first) == 1
    ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_002", 7.0, "second text", 1.3]]),
    )
    second = _notes(db_session, exp)
    assert [(n.id, n.note_text) for n in second] == [(first[0].id, "second text")]
    ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_002", 7.0, None, 1.4]]),
    )
    assert [(n.id, n.note_text) for n in _notes(db_session, exp)] == [(first[0].id, "second text")]


def test_scalar_blank_description_writes_no_note(db_session: Session):
    exp = _seed(db_session, "PON_003", 9122403)
    created, _u, _s, errors, _fb = ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_003", 7.0, None, 1.2]]),
    )
    assert errors == [] and created == 1
    assert _notes(db_session, exp) == []


def test_scalar_numeric_description_cell_becomes_a_result_note(db_session: Session):
    exp = _seed(db_session, "PON_007", 9122407)
    created, updated, skipped, errors, _fb = ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_007", 7.0, 5, 1.2]]),
    )
    assert errors == [] and created == 1
    assert [(n.note_type, n.note_text, n.created_by) for n in _notes(db_session, exp)] == [
        (NoteType.result_note, "5", "scalar_results"),
    ]
