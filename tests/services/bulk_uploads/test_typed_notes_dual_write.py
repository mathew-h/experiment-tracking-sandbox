"""Issue #118 PR1: the three bulk parsers mirror their free-text columns into
typed experiment_notes rows, and the New Experiments parser no longer turns a
blank initial_note into the literal text "nan".

Master Results is also checked for v3/v4 header parity: the v4 Dashboard
template renamed 'Description' -> 'Observation Note' and 'Modification' ->
'Modification Note'; both spellings must produce identical result rows AND
identical note rows for the same data.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from database import Experiment, ExperimentNotes, ExperimentalResults, ModificationsLog
from database.models.enums import ExperimentStatus, NoteType
from backend.services.bulk_uploads.master_bulk_upload import MasterBulkUploadService
from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService
from backend.services.bulk_uploads.timepoint_modifications import TimepointModificationsService

from .excel_helpers import make_excel, make_excel_multisheet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_experiment(db: Session, experiment_id: str, exp_num: int) -> Experiment:
    exp = Experiment(experiment_id=experiment_id, experiment_number=exp_num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _notes(db: Session, exp: Experiment) -> list[ExperimentNotes]:
    return db.execute(
        select(ExperimentNotes).where(ExperimentNotes.experiment_fk == exp.id).order_by(ExperimentNotes.id)
    ).scalars().all()


def _note_shape(notes: list[ExperimentNotes], result_id_of: dict[int, float]) -> list[tuple]:
    """(day, note_type, text, created_by) -- comparable across two uploads whose
    result ids differ."""
    return sorted(
        (result_id_of[n.result_id], n.note_type.value, n.note_text, n.created_by) for n in notes
    )


def _results_by_day(db: Session, exp: Experiment) -> dict[int, float]:
    rows = db.execute(
        select(ExperimentalResults.id, ExperimentalResults.time_post_reaction_days)
        .where(ExperimentalResults.experiment_fk == exp.id)
    ).all()
    return {rid: day for rid, day in rows}


_V3_HEADERS = [
    "Experiment ID", "Duration (Days)", "Description", "Sample Date",
    "NMR Run Date", "ICP Run Date", "GC Run Date",
    "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
    "Sample pH", "Sample Conductivity (mS/cm)", "Modification", "Overwrite",
]
_V4_HEADERS = [
    "Experiment ID", "Duration (Days)", "Observation Note", "Sample Collection Date",
    "NMR Run Date", "ICP Run Date", "GC Run Date",
    "NH4 (mM)", "FL H2 (ppm)", "FL Gas Volume (mL)", "FL Gas Pressure (psi)",
    "Sample pH", "Sample Conductivity (mS/cm)", "Modification Note", "OVERWRITE",
]


def _dashboard(headers: list[str], rows: list[list]) -> bytes:
    return make_excel_multisheet({"Dashboard": (headers, rows)})


def _rows(exp_id: str) -> list[list]:
    return [
        [exp_id, 7.0, "Liquid sample, slightly cloudy", None, None, None, None,
         5.2, None, None, None, 7.1, 12.5, "Replaced 5 mL brine with DI", "FALSE"],
        [exp_id, 14.0, None, None, None, None, None,
         6.0, None, None, None, 7.3, 12.9, None, "FALSE"],
    ]


# ---------------------------------------------------------------------------
# Master Results
# ---------------------------------------------------------------------------

def test_master_upload_mirrors_both_text_columns_into_notes(db_session: Session):
    exp = _seed_experiment(db_session, "TNM_001", 9118201)
    r = MasterBulkUploadService.from_bytes_ex(db_session, _dashboard(_V3_HEADERS, _rows("TNM_001")))
    assert r.errors == [], r.errors
    assert r.created == 2

    by_day = _results_by_day(db_session, exp)
    shape = _note_shape(_notes(db_session, exp), by_day)
    assert shape == [
        (7.0, "modification", "Replaced 5 mL brine with DI", "master_bulk_upload"),
        (7.0, "observation", "Liquid sample, slightly cloudy", "master_bulk_upload"),
    ]
    # Legacy columns still written -- Power BI reads them until PR3.
    day7 = db_session.execute(
        select(ExperimentalResults).where(
            ExperimentalResults.experiment_fk == exp.id, ExperimentalResults.time_post_reaction_days == 7.0,
        )
    ).scalar_one()
    assert day7.description == "Liquid sample, slightly cloudy"
    assert day7.brine_modification_description == "Replaced 5 mL brine with DI"
    assert day7.has_brine_modification is True


def test_master_blank_description_writes_no_note(db_session: Session):
    """A blank Observation Note writes NO note row. The legacy NOT NULL column
    keeps its generated fallback until PR3 (readers are unchanged in PR1), and
    that generated text must never leak into the notes model."""
    exp = _seed_experiment(db_session, "TNM_002", 9118202)
    r = MasterBulkUploadService.from_bytes_ex(db_session, _dashboard(_V3_HEADERS, _rows("TNM_002")))
    assert r.errors == [], r.errors
    day14 = db_session.execute(
        select(ExperimentalResults).where(
            ExperimentalResults.experiment_fk == exp.id, ExperimentalResults.time_post_reaction_days == 14.0,
        )
    ).scalar_one()
    assert day14.description.startswith("Master upload"), "legacy fallback still owns the column in PR1"
    assert day14.brine_modification_description is None
    assert [n for n in _notes(db_session, exp) if n.result_id == day14.id] == []


def test_master_v3_and_v4_headers_produce_identical_notes(db_session: Session):
    a = _seed_experiment(db_session, "TNM_V3", 9118203)
    b = _seed_experiment(db_session, "TNM_V4", 9118204)
    r3 = MasterBulkUploadService.from_bytes_ex(db_session, _dashboard(_V3_HEADERS, _rows("TNM_V3")))
    r4 = MasterBulkUploadService.from_bytes_ex(db_session, _dashboard(_V4_HEADERS, _rows("TNM_V4")))
    assert r3.errors == [] and r4.errors == [], (r3.errors, r4.errors)
    assert (r3.created, r3.updated) == (r4.created, r4.updated) == (2, 0)

    shape3 = _note_shape(_notes(db_session, a), _results_by_day(db_session, a))
    shape4 = _note_shape(_notes(db_session, b), _results_by_day(db_session, b))
    assert shape3 == shape4
    assert len(shape3) == 2

    def legacy(exp):
        return sorted(
            (row.time_post_reaction_days, row.description, row.brine_modification_description)
            for row in db_session.execute(
                select(ExperimentalResults).where(ExperimentalResults.experiment_fk == exp.id)
            ).scalars()
        )
    assert legacy(a) == legacy(b)


def test_master_reupload_updates_note_slot_instead_of_appending(db_session: Session):
    exp = _seed_experiment(db_session, "TNM_003", 9118205)
    first = MasterBulkUploadService.from_bytes_ex(db_session, _dashboard(_V4_HEADERS, _rows("TNM_003")))
    assert first.errors == []
    before = {n.note_type: n.id for n in _notes(db_session, exp)}

    edited = _rows("TNM_003")
    edited[0][2] = "Liquid sample, now clear"
    edited[0][13] = "Replaced 10 mL brine with DI"
    second = MasterBulkUploadService.from_bytes_ex(db_session, _dashboard(_V4_HEADERS, edited))
    assert second.errors == []
    assert second.updated == 2

    notes = _notes(db_session, exp)
    assert len(notes) == 2, "re-upload must not append duplicate notes"
    after = {n.note_type: (n.id, n.note_text) for n in notes}
    assert after[NoteType.observation] == (before[NoteType.observation], "Liquid sample, now clear")
    assert after[NoteType.modification] == (before[NoteType.modification], "Replaced 10 mL brine with DI")


# ---------------------------------------------------------------------------
# Timepoint modifications
# ---------------------------------------------------------------------------

def _seed_result(db: Session, exp: Experiment, day: float) -> ExperimentalResults:
    r = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=day,
                            time_post_reaction_bucket_days=day, description=f"Day {day}")
    db.add(r)
    db.flush()
    return r


_TP_HEADERS = ["experiment_id", "time_point", "modification_description", "overwrite_existing"]


def test_timepoint_modifications_mirror_into_modification_note(db_session: Session):
    exp = _seed_experiment(db_session, "TNT_001", 9118301)
    r = _seed_result(db_session, exp, 7.0)
    xlsx = make_excel(_TP_HEADERS, [["TNT_001", 7.0, "Added 5 g Mg(OH)2", "FALSE"]])
    updated, skipped, errors, _fb = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx, modified_by="tester@addisenergy.com",
    )
    assert errors == [] and updated == 1
    db_session.refresh(r)
    assert r.brine_modification_description == "Added 5 g Mg(OH)2"
    notes = _notes(db_session, exp)
    assert [(n.note_type, n.result_id, n.note_text, n.created_by) for n in notes] == [
        (NoteType.modification, r.id, "Added 5 g Mg(OH)2", "tester@addisenergy.com"),
    ]


def test_timepoint_modifications_v4_header_is_accepted(db_session: Session):
    exp = _seed_experiment(db_session, "TNT_002", 9118302)
    _seed_result(db_session, exp, 7.0)
    xlsx = make_excel(["experiment_id", "time_point", "Modification Note"], [["TNT_002", 7.0, "swapped brine"]])
    updated, skipped, errors, _fb = TimepointModificationsService.bulk_set_from_bytes(db_session, xlsx)
    assert errors == [] and updated == 1
    assert [n.note_text for n in _notes(db_session, exp)] == ["swapped brine"]


def test_timepoint_modifications_overwrite_blank_clears_column_and_note(db_session: Session):
    exp = _seed_experiment(db_session, "TNT_003", 9118303)
    r = _seed_result(db_session, exp, 7.0)
    set_xlsx = make_excel(_TP_HEADERS, [["TNT_003", 7.0, "first", "FALSE"]])
    TimepointModificationsService.bulk_set_from_bytes(db_session, set_xlsx, modified_by="u")
    assert len(_notes(db_session, exp)) == 1

    clear_xlsx = make_excel(_TP_HEADERS, [["TNT_003", 7.0, None, "TRUE"]])
    updated, skipped, errors, _fb = TimepointModificationsService.bulk_set_from_bytes(
        db_session, clear_xlsx, modified_by="u",
    )
    assert errors == [] and updated == 1
    db_session.refresh(r)
    assert r.brine_modification_description is None
    assert r.has_brine_modification is False
    assert _notes(db_session, exp) == []


# ---------------------------------------------------------------------------
# New Experiments (autoflush=False, mirroring production SessionLocal)
# ---------------------------------------------------------------------------

_TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
_engine = create_engine(_TEST_DB_URL, pool_pre_ping=True)
_SessionAutoflushOff = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

_EXP_HEADERS = ["experiment_id", "old_experiment_id", "sample_id", "researcher", "date", "status",
                "initial_note", "overwrite"]


@pytest.fixture()
def pg_session(create_test_tables) -> Session:
    connection = _engine.connect()
    transaction = connection.begin()
    session = _SessionAutoflushOff(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _upsert(db: Session, rows: list[list]):
    created, updated, skipped, errors, warnings, info = NewExperimentsUploadService.bulk_upsert_from_excel(
        db, make_excel(_EXP_HEADERS, rows, sheet_name="experiments"),
    )
    assert errors == [], errors
    return created, updated


def _notes_by_id(db: Session, exp_id: str) -> list[ExperimentNotes]:
    return db.execute(
        select(ExperimentNotes).where(ExperimentNotes.experiment_id == exp_id).order_by(ExperimentNotes.id)
    ).scalars().all()


def test_new_experiment_initial_note_is_the_description(pg_session: Session):
    created, _ = _upsert(pg_session, [["TNN_001", None, None, None, None, None, "Serum baseline, no catalyst", False]])
    assert created == 1
    notes = _notes_by_id(pg_session, "TNN_001")
    assert [(n.note_type, n.note_text, n.created_by, n.result_id) for n in notes] == [
        (NoteType.description, "Serum baseline, no catalyst", "new_experiments", None),
    ]


def test_blank_initial_note_creates_no_note_at_all(pg_session: Session):
    """The 'nan' bug: a blank cell used to insert a note reading 'nan'."""
    created, _ = _upsert(pg_session, [["TNN_002", None, None, None, None, None, None, False]])
    assert created == 1
    assert _notes_by_id(pg_session, "TNN_002") == []


def test_initial_note_on_existing_experiment_without_overwrite_is_skipped(pg_session: Session):
    """Without overwrite the parser skips an existing experiment entirely
    ("already exists; set overwrite=True"), so no note of any type is added and
    the legacy note is untouched. This is what keeps `initial_note -> description`
    safe: the parser only writes a description for a brand-new experiment or
    after an overwrite row has cleared the old notes."""
    exp = _seed_experiment(pg_session, "TNN_003", 9118403)
    pg_session.add(ExperimentNotes(experiment_id="TNN_003", experiment_fk=exp.id, note_text="legacy first note"))
    pg_session.flush()
    created, updated, skipped, errors, warnings, info = NewExperimentsUploadService.bulk_upsert_from_excel(
        pg_session, make_excel(_EXP_HEADERS, [["TNN_003", None, None, None, None, None, "later remark", False]],
                               sheet_name="experiments"),
    )
    assert errors == [] and (created, updated) == (0, 0)
    assert any("already exists" in w for w in warnings)
    notes = _notes_by_id(pg_session, "TNN_003")
    assert [(n.note_type, n.note_text) for n in notes] == [(NoteType.observation, "legacy first note")]


def test_blank_initial_note_with_overwrite_leaves_notes_alone(pg_session: Session):
    exp = _seed_experiment(pg_session, "TNN_004", 9118404)
    pg_session.add(ExperimentNotes(experiment_id="TNN_004", experiment_fk=exp.id, note_text="keep me"))
    pg_session.flush()
    _created, updated = _upsert(pg_session, [["TNN_004", None, None, "Someone", None, None, None, True]])
    assert updated == 1
    pg_session.expire_all()
    assert [n.note_text for n in _notes_by_id(pg_session, "TNN_004")] == ["keep me"]
    audit = pg_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id, ModificationsLog.modified_table == "experiment_notes",
        )
    ).scalars().all()
    assert audit == [], "nothing was deleted, so nothing should be logged"


def test_initial_note_with_overwrite_replaces_notes_and_audits_the_deletion(pg_session: Session):
    exp = _seed_experiment(pg_session, "TNN_005", 9118405)
    pg_session.add_all([
        ExperimentNotes(experiment_id="TNN_005", experiment_fk=exp.id, note_text="old one"),
        ExperimentNotes(experiment_id="TNN_005", experiment_fk=exp.id, note_text="old two"),
    ])
    pg_session.flush()
    _created, updated = _upsert(pg_session, [["TNN_005", None, None, None, None, None, "fresh summary", True]])
    assert updated == 1
    pg_session.expire_all()
    notes = _notes_by_id(pg_session, "TNN_005")
    assert [(n.note_type, n.note_text) for n in notes] == [(NoteType.description, "fresh summary")]
    audit = pg_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id, ModificationsLog.modified_table == "experiment_notes",
        )
    ).scalars().all()
    assert len(audit) == 1
    assert audit[0].modification_type == "delete"
    assert audit[0].old_values == {"note_texts": ["old one", "old two"]}
