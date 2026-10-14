"""Issue #122 PR-D: the Solution Chemistry and quick-upload parsers' Description
column is an 'observation' note signed by the parser (one slot per result);
a blank cell writes nothing and leaves an earlier note in place; long-format
has no text column and writes no note."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Experiment, ExperimentNotes, ExperimentalResults
from database.models.enums import ExperimentStatus, NoteType
from backend.services.bulk_uploads.quick_upload import quick_upload_from_excel
from backend.services.bulk_uploads.long_format import long_format_upload_from_excel
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


def test_scalar_description_becomes_an_observation_note_signed_by_the_parser(db_session: Session):
    exp = _seed(db_session, "PON_001", 9122401)
    created, updated, skipped, errors, _fb = ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db_session, make_excel(_SCALAR_HEADERS, [["PON_001", 7.0, "Liquid clear, no gas", 1.2]]),
    )
    assert errors == [] and created == 1
    (rid,) = _result_ids(db_session, exp)
    assert [(n.note_type, n.result_id, n.note_text, n.created_by) for n in _notes(db_session, exp)] == [
        (NoteType.observation, rid, "Liquid clear, no gas", "scalar_results"),
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


_QUICK_HEADERS = ["Experiment ID*", "Time (days)*", "H2 Conc (ppm)*", "Description"]


def test_quick_upload_description_becomes_an_observation_note(db_session: Session):
    exp = _seed(db_session, "PON_004", 9122404)
    created, updated, skipped, errors, _fb = quick_upload_from_excel(
        db_session, make_excel(_QUICK_HEADERS, [["PON_004", 7.0, 120.0, "Headspace sampled twice"]], sheet_name="Data"),
        "hydrogen",
    )
    assert errors == [], errors
    # quick_upload's created/updated split is a heuristic on result.updated_at
    # (pre-existing, out of scope here); only the row count matters to this test.
    assert created + updated == 1
    (rid,) = _result_ids(db_session, exp)
    assert [(n.note_type, n.result_id, n.note_text, n.created_by) for n in _notes(db_session, exp)] == [
        (NoteType.observation, rid, "Headspace sampled twice", "quick_upload"),
    ]


def test_quick_upload_blank_description_writes_no_note(db_session: Session):
    exp = _seed(db_session, "PON_005", 9122405)
    created, updated, _s, errors, _fb = quick_upload_from_excel(
        db_session, make_excel(_QUICK_HEADERS, [["PON_005", 7.0, 120.0, None]], sheet_name="Data"),
        "hydrogen",
    )
    assert errors == [], errors
    # quick_upload's created/updated split is a heuristic on result.updated_at
    # (pre-existing, out of scope here); only the row count matters to this test.
    assert created + updated == 1
    assert _notes(db_session, exp) == []


def test_long_format_writes_no_note(db_session: Session):
    """Long format has no free-text column; the 'Day N results' filler is gone."""
    exp = _seed(db_session, "PON_006", 9122406)
    headers = ["Experiment ID", "Time (days)", "Metric", "Value", "Unit"]
    created, updated, skipped, errors, _fb = long_format_upload_from_excel(
        db_session, make_excel(headers, [["PON_006", 7.0, "final_ph", 7.1, None]], sheet_name="Data"),
    )
    assert errors == [], errors
    assert _result_ids(db_session, exp) != []
    assert _notes(db_session, exp) == []
