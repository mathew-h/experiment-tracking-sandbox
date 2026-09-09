"""Reporting views over the typed notes model (issue #118, PR3).

v_experiments.description reads the note typed 'description' (not the first
note by created_at); v_dim_timepoints.modification_note reads the result's
'modification' notes; v_results_scalar no longer exposes sampling_description;
v_notes is the per-note view.
"""
import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from database import Base
from database.models import Experiment, ExperimentNotes, ExperimentalResults
from database.models.enums import ExperimentStatus, NoteType

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"


@pytest.fixture(scope="module")
def view_engine():
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    yield engine


@pytest.fixture
def view_db(view_engine):
    connection = view_engine.connect()
    transaction = connection.begin()
    from database.event_listeners import _VIEWS
    for view_name, view_sql in _VIEWS:
        connection.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
        connection.execute(text(view_sql))
    db = sessionmaker(bind=connection)()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def _exp(db: Session, eid: str, num: int) -> Experiment:
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _note(db, exp, text_, **kw) -> ExperimentNotes:
    n = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text=text_, **kw)
    db.add(n)
    db.flush()
    return n


def _result(db, exp, day) -> ExperimentalResults:
    r = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=day,
                            time_post_reaction_bucket_days=day, description="legacy", is_primary_timepoint_result=True)
    db.add(r)
    db.flush()
    return r


class TestVExperimentsDescription:
    def test_reads_the_typed_description_not_the_earliest_created_at(self, view_db):
        """The defect: an observation with an EARLIER created_at but a later id
        used to win the LIMIT 1. Now the type decides."""
        exp = _exp(view_db, "VN_001", 63001)
        _note(view_db, exp, "the real description", note_type=NoteType.description,
              created_at=datetime.datetime(2026, 2, 1, tzinfo=datetime.timezone.utc))
        _note(view_db, exp, "ICP Analysis - VN_001_Day1_5x",
              created_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc))
        view_db.flush()
        row = view_db.execute(
            text("SELECT description FROM v_experiments WHERE experiment_id = 'VN_001'")
        ).fetchone()
        assert row[0] == "the real description"

    def test_null_when_no_description_note(self, view_db):
        exp = _exp(view_db, "VN_002", 63002)
        _note(view_db, exp, "just an observation")
        row = view_db.execute(
            text("SELECT description FROM v_experiments WHERE experiment_id = 'VN_002'")
        ).fetchone()
        assert row[0] is None


class TestVDimTimepointsModificationNote:
    def test_columns(self, view_db):
        cols = {r[0] for r in view_db.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'v_dim_timepoints'"
        ))}
        assert "modification_note" in cols
        assert "brine_modification_description" not in cols

    def test_reads_modification_notes_joined_in_id_order(self, view_db):
        exp = _exp(view_db, "VN_003", 63003)
        r = _result(view_db, exp, 7.0)
        _note(view_db, exp, "added KOH", note_type=NoteType.modification, result_id=r.id, created_by="master_bulk_upload")
        _note(view_db, exp, "then filtered", note_type=NoteType.modification, result_id=r.id, created_by="someone@addisenergy.com")
        _note(view_db, exp, "not a modification", note_type=NoteType.observation, result_id=r.id)
        row = view_db.execute(
            text("SELECT modification_note FROM v_dim_timepoints WHERE result_id = :rid"), {"rid": r.id}
        ).fetchone()
        assert row[0] == "added KOH; then filtered"

    def test_null_when_no_modification_note(self, view_db):
        exp = _exp(view_db, "VN_004", 63004)
        r = _result(view_db, exp, 7.0)
        row = view_db.execute(
            text("SELECT modification_note FROM v_dim_timepoints WHERE result_id = :rid"), {"rid": r.id}
        ).fetchone()
        assert row[0] is None


class TestVResultsScalar:
    def test_sampling_description_is_gone(self, view_db):
        cols = {r[0] for r in view_db.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'v_results_scalar'"
        ))}
        assert "sampling_description" not in cols
        assert {"result_id", "experiment_id", "experiment_fk", "net_ammonium_concentration"} <= cols


class TestVNotes:
    def test_columns_match_spec(self, view_db):
        cols = [r[0] for r in view_db.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'v_notes' ORDER BY ordinal_position"
        ))]
        assert cols == ["note_id", "experiment_id", "result_id", "note_type", "note_text",
                        "created_at", "created_by", "needs_review"]

    def test_one_row_per_note_with_type_as_text(self, view_db):
        exp = _exp(view_db, "VN_005", 63005)
        r = _result(view_db, exp, 1.0)
        _note(view_db, exp, "desc", note_type=NoteType.description, created_by="new_experiments")
        _note(view_db, exp, "mod", note_type=NoteType.modification, result_id=r.id, needs_review=False)
        _note(view_db, exp, "queued", note_type=NoteType.observation, result_id=r.id, needs_review=True,
              created_by="reclassify_notes_020")
        rows = view_db.execute(text(
            "SELECT note_type, note_text, result_id, created_by, needs_review FROM v_notes"
            " WHERE experiment_id = 'VN_005' ORDER BY note_id"
        )).fetchall()
        assert [tuple(x) for x in rows] == [
            ("description", "desc", None, "new_experiments", False),
            ("modification", "mod", r.id, None, False),
            ("observation", "queued", r.id, "reclassify_notes_020", True),
        ]

    def test_review_queue_is_a_filter_on_the_view(self, view_db):
        exp = _exp(view_db, "VN_006", 63006)
        _note(view_db, exp, "fine")
        _note(view_db, exp, "check me", needs_review=True)
        n = view_db.execute(text(
            "SELECT count(*) FROM v_notes WHERE experiment_id = 'VN_006' AND needs_review"
        )).scalar()
        assert n == 1
