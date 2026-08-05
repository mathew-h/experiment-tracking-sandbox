"""Issue #109 follow-up: the bulk rename path must sync every denormalized
experiment_id copy, not just notes and modifications_log.

This is the mechanism that produced all 187 stale experimental_conditions
strings (of 1013 rows) measured against the 2026-08-05 production dump. With
the string unsynced, migration 018's backfill decays with every rename
workbook.

Uses an autoflush=False session, mirroring production SessionLocal — the same
reason test_new_experiments_rename_lineage.py does.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database import (
    Experiment,
    ExperimentNotes,
    ExperimentalConditions,
    ExternalAnalysis,
    ModificationsLog,
    XRDPhase,
)
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService

from .excel_helpers import make_excel

_TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
_engine = create_engine(_TEST_DB_URL, pool_pre_ping=True)
_SessionAutoflushOff = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

_EXP_HEADERS = [
    "experiment_id",
    "old_experiment_id",
    "sample_id",
    "researcher",
    "date",
    "status",
    "initial_note",
    "overwrite",
]


@pytest.fixture()
def pg_session(create_test_tables) -> Session:
    """Per-test autoflush=False session, wrapped in a transaction that rolls back."""
    connection = _engine.connect()
    transaction = connection.begin()
    session = _SessionAutoflushOff(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _seed_with_children(db: Session, exp_id: str, number: int) -> Experiment:
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    db.add_all([
        ExperimentalConditions(experiment_id=exp_id, experiment_fk=exp.id, temperature_c=250.0),
        ExperimentNotes(experiment_id=exp_id, experiment_fk=exp.id, note_text="seed"),
        ModificationsLog(
            experiment_id=exp_id, experiment_fk=exp.id,
            modified_by="t", modification_type="create", modified_table="experiments",
        ),
        ExternalAnalysis(experiment_id=exp_id, experiment_fk=exp.id, analysis_type="XRD"),
        XRDPhase(
            experiment_id=exp_id, experiment_fk=exp.id,
            mineral_name="Magnetite", amount=11.0, time_post_reaction_days=7.0,
        ),
    ])
    db.flush()
    return exp


def test_bulk_rename_syncs_conditions_string(pg_session: Session):
    """The regression this task exists for."""
    exp = _seed_with_children(pg_session, "BULKSYNC_001", 8803001)
    exp_pk = exp.id

    xlsx = make_excel(
        _EXP_HEADERS,
        [["BULKSYNC_001a-t7", "BULKSYNC_001", None, None, None, None, None, True]],
        sheet_name="experiments",
    )
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(pg_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1

    cond = (
        pg_session.query(ExperimentalConditions)
        .filter(ExperimentalConditions.experiment_fk == exp_pk)
        .one()
    )
    assert cond.experiment_id == "BULKSYNC_001a-t7", (
        "conditions string still stale — this is the 187-row mechanism"
    )


def test_bulk_rename_syncs_all_five_tables(pg_session: Session):
    """Full parity with PATCH /api/experiments/{id}.

    `ExperimentNotes` is asserted separately below, NOT in the loop, because on
    the `overwrite=True` branch a passing loop assertion would prove nothing:

    1. The parser deletes *every* note for the experiment (`new_experiments.py`,
       "clearing existing notes for overwrite") — and it does so AFTER the sync
       has run, so the seeded row is gone by assertion time.
    2. A blank `initial_note` cell does not parse to `None`: `pd.read_excel`
       yields `float('nan')` and the parser stringifies it, so it inserts a
       *fresh* note reading `"nan"` carrying `experiment.experiment_id` — the
       new ID by construction, whatever the sync did.

    So the loop would have been green even with the notes sync deleted. The
    notes sync is genuinely covered by
    `tests/services/test_denormalized_ids.py::test_syncs_all_five_tables` and by
    `tests/api/test_experiments_rename_sync.py`, neither of which runs the
    overwrite branch. The `"nan"` insert is a separate live bug in the locked
    parser: `docs/issues/issue-blank-initial-note-parses-to-nan.md`.
    """
    exp = _seed_with_children(pg_session, "BULKSYNC_002", 8803002)
    exp_pk = exp.id
    seeded_note_pk = (
        pg_session.query(ExperimentNotes.id)
        .filter(ExperimentNotes.experiment_fk == exp_pk)
        .scalar()
    )
    assert seeded_note_pk is not None

    xlsx = make_excel(
        _EXP_HEADERS,
        [["BULKSYNC_002b-t3", "BULKSYNC_002", None, None, None, None, None, True]],
        sheet_name="experiments",
    )
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(pg_session, xlsx)
    )
    assert errors == [], f"Unexpected errors: {errors}"

    for model in (ExperimentalConditions, ModificationsLog,
                  ExternalAnalysis, XRDPhase):
        rows = pg_session.query(model).filter(model.experiment_fk == exp_pk).all()
        assert rows, f"{model.__name__} row vanished"
        for row in rows:
            assert row.experiment_id == "BULKSYNC_002b-t3", (
                f"{model.__name__} not synced: {row.experiment_id!r}"
            )

    # Notes: assert what actually happens, so this cannot read as a sync check.
    assert pg_session.get(ExperimentNotes, seeded_note_pk) is None, (
        "expected the overwrite branch to have deleted the seeded note"
    )
    remaining = (
        pg_session.query(ExperimentNotes)
        .filter(ExperimentNotes.experiment_fk == exp_pk)
        .all()
    )
    assert [n.note_text for n in remaining] == ["nan"], (
        "expected the blank initial_note cell to have inserted a literal 'nan' "
        "note — see docs/issues/issue-blank-initial-note-parses-to-nan.md"
    )


def test_conditions_sheet_after_rename_sees_new_string(pg_session: Session):
    """The conditions sheet is processed after the rename block and resolves its
    row by experiment_fk into the same session. A sync that left the identity
    map stale would hand it the old string."""
    exp = _seed_with_children(pg_session, "BULKSYNC_003", 8803003)
    exp_pk = exp.id

    import io
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "experiments"
    ws.append(_EXP_HEADERS)
    ws.append(["BULKSYNC_003c", "BULKSYNC_003", None, None, None, None, None, True])
    ws2 = wb.create_sheet("conditions")
    ws2.append(["experiment_id", "temperature_c"])
    ws2.append(["BULKSYNC_003c", 275.0])
    buf = io.BytesIO()
    wb.save(buf)

    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(pg_session, buf.getvalue())
    )
    assert errors == [], f"Unexpected errors: {errors}"

    cond = (
        pg_session.query(ExperimentalConditions)
        .filter(ExperimentalConditions.experiment_fk == exp_pk)
        .one()
    )
    assert cond.experiment_id == "BULKSYNC_003c"
    assert cond.temperature_c == 275.0, "conditions sheet did not apply"
