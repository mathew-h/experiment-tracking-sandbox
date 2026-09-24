"""ck_note_scope after issue #122 PR-B: a 'modification' note is anchored to a
result OR an event_date (design decision 1). Every (note_type, result_id,
event_date) combination the spec names is pinned here against PostgreSQL --
the test DB is built with create_all, so the model's CheckConstraint must carry
the new rule; if a row here goes red the migration e5b2d9c7a1f4 has drifted too.
"""
import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from database import Experiment, ExperimentNotes, ExperimentalResults
from database.models.enums import ExperimentStatus, NoteType

DAY = datetime.date(2026, 9, 24)


def _exp(db, exp_id, number):
    exp = Experiment(experiment_id=exp_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _result(db, exp, day=7.0):
    r = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=day,
                            time_post_reaction_bucket_days=day, description="seed")
    db.add(r)
    db.flush()
    return r


def _note(db, exp, **kw):
    n = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text="t", **kw)
    db.add(n)
    db.flush()
    return n


def test_event_date_column_round_trips_and_is_nullable(db_session):
    exp = _exp(db_session, "EVD_001", 91001)
    dated = _note(db_session, exp, note_type=NoteType.observation, event_date=DAY)
    undated = _note(db_session, exp, note_type=NoteType.observation)
    db_session.refresh(dated)
    assert dated.event_date == DAY
    assert undated.event_date is None


# --- the nine combinations the spec names -----------------------------------

def test_description_without_result_is_valid(db_session):
    exp = _exp(db_session, "EVD_002", 91002)
    _note(db_session, exp, note_type=NoteType.description)


def test_description_with_result_is_rejected(db_session):
    exp = _exp(db_session, "EVD_003", 91003)
    r = _result(db_session, exp)
    with pytest.raises(IntegrityError, match="ck_note_scope"):
        _note(db_session, exp, note_type=NoteType.description, result_id=r.id)


def test_modification_with_result_only_is_valid(db_session):
    exp = _exp(db_session, "EVD_004", 91004)
    r = _result(db_session, exp)
    _note(db_session, exp, note_type=NoteType.modification, result_id=r.id)


def test_modification_with_date_only_is_valid(db_session):
    exp = _exp(db_session, "EVD_005", 91005)
    _note(db_session, exp, note_type=NoteType.modification, event_date=DAY)


def test_modification_with_result_and_date_is_valid(db_session):
    exp = _exp(db_session, "EVD_006", 91006)
    r = _result(db_session, exp)
    _note(db_session, exp, note_type=NoteType.modification, result_id=r.id, event_date=DAY)


def test_modification_with_neither_anchor_is_rejected(db_session):
    exp = _exp(db_session, "EVD_007", 91007)
    with pytest.raises(IntegrityError, match="ck_note_scope"):
        _note(db_session, exp, note_type=NoteType.modification)


def test_result_note_with_result_is_valid(db_session):
    exp = _exp(db_session, "EVD_008", 91008)
    r = _result(db_session, exp)
    _note(db_session, exp, note_type=NoteType.result_note, result_id=r.id)


def test_result_note_with_date_only_is_rejected(db_session):
    # A date does not anchor a result_note; only a result does.
    exp = _exp(db_session, "EVD_009", 91009)
    with pytest.raises(IntegrityError, match="ck_note_scope"):
        _note(db_session, exp, note_type=NoteType.result_note, event_date=DAY)


def test_observation_with_date_only_is_valid(db_session):
    exp = _exp(db_session, "EVD_010", 91010)
    _note(db_session, exp, note_type=NoteType.observation, event_date=DAY)
