"""DB-level guarantees on experiment_notes (issue #118, PR1).

Every assertion here is about what PostgreSQL rejects, not what app code
checks -- the spec requires the partial unique index, the composite FK and the
scope CHECK to be enforced by the database. The test DB is built with
Base.metadata.create_all, so the model's __table_args__ must carry them; if
one of these tests goes red after a model edit, the migration in
alembic/versions/b7e2c9a41d05_typed_experiment_notes.py has drifted from the
model too.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import Experiment, ExperimentNotes, ExperimentalResults
from database.models.enums import ExperimentStatus, NoteType


def _exp(db, exp_id, number):
    exp = Experiment(experiment_id=exp_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _result(db, exp, day):
    r = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=day,
        time_post_reaction_bucket_days=day,
        description="seed",
    )
    db.add(r)
    db.flush()
    return r


def _note(db, exp, **kw):
    n = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, **kw)
    db.add(n)
    db.flush()
    return n


def test_defaults_are_observation_not_reviewed(db_session):
    exp = _exp(db_session, "TN_DEF_001", 9118001)
    n = _note(db_session, exp, note_text="plain")
    db_session.refresh(n)
    assert n.note_type is NoteType.observation
    assert n.result_id is None
    assert n.created_by is None
    assert n.needs_review is False


def test_enum_labels_are_the_lowercase_values(db_session):
    """The Postgres enum labels must be the spec's lowercase strings, so raw SQL
    in the views and the PR2 backfill can compare against 'description' etc."""
    exp = _exp(db_session, "TN_LBL_001", 9118012)
    _note(db_session, exp, note_text="d", note_type=NoteType.description)
    raw = db_session.execute(
        select(ExperimentNotes.__table__.c.note_type.cast(__import__("sqlalchemy").String))
        .where(ExperimentNotes.experiment_fk == exp.id)
    ).scalar_one()
    assert raw == "description"


@pytest.mark.parametrize("note_type", [NoteType.modification, NoteType.result_note])
def test_scope_check_rejects_result_scoped_type_without_result(db_session, note_type):
    exp = _exp(db_session, "TN_CK_001", 9118002)
    with pytest.raises(IntegrityError, match="ck_note_scope"):
        _note(db_session, exp, note_text="x", note_type=note_type)


def test_scope_check_rejects_description_with_result(db_session):
    exp = _exp(db_session, "TN_CK_002", 9118003)
    r = _result(db_session, exp, 1.0)
    with pytest.raises(IntegrityError, match="ck_note_scope"):
        _note(db_session, exp, note_text="x", note_type=NoteType.description, result_id=r.id)


def test_observation_is_valid_with_and_without_result(db_session):
    """'observation' is deliberately scope-free (spec). Do not narrow it."""
    exp = _exp(db_session, "TN_OBS_001", 9118004)
    r = _result(db_session, exp, 1.0)
    _note(db_session, exp, note_text="free", note_type=NoteType.observation)
    _note(db_session, exp, note_text="scoped", note_type=NoteType.observation, result_id=r.id)
    rows = db_session.execute(
        select(ExperimentNotes).where(ExperimentNotes.experiment_fk == exp.id)
    ).scalars().all()
    assert len(rows) == 2
    assert sorted(n.result_id for n in rows if n.result_id) == [r.id]


def test_partial_unique_index_rejects_second_description(db_session):
    exp = _exp(db_session, "TN_UQ_001", 9118005)
    _note(db_session, exp, note_text="first", note_type=NoteType.description)
    with pytest.raises(IntegrityError, match="uq_one_description_per_experiment"):
        _note(db_session, exp, note_text="second", note_type=NoteType.description)


def test_two_experiments_may_each_have_a_description(db_session):
    a = _exp(db_session, "TN_UQ_002", 9118006)
    b = _exp(db_session, "TN_UQ_003", 9118007)
    _note(db_session, a, note_text="a", note_type=NoteType.description)
    _note(db_session, b, note_text="b", note_type=NoteType.description)


def test_many_observations_per_experiment_are_fine(db_session):
    """The unique index is partial: it must not bite non-description notes."""
    exp = _exp(db_session, "TN_UQ_004", 9118013)
    for i in range(3):
        _note(db_session, exp, note_text=f"obs {i}")


def test_composite_fk_rejects_result_from_another_experiment(db_session):
    a = _exp(db_session, "TN_FK_001", 9118008)
    b = _exp(db_session, "TN_FK_002", 9118009)
    rb = _result(db_session, b, 1.0)
    with pytest.raises(IntegrityError, match="fk_note_result_same_experiment"):
        _note(db_session, a, note_text="x", note_type=NoteType.modification, result_id=rb.id)


def test_composite_fk_accepts_result_from_same_experiment(db_session):
    a = _exp(db_session, "TN_FK_003", 9118010)
    ra = _result(db_session, a, 1.0)
    n = _note(db_session, a, note_text="x", note_type=NoteType.modification, result_id=ra.id)
    db_session.refresh(n)
    assert n.result.id == ra.id
    db_session.refresh(ra)
    assert [x.id for x in ra.notes] == [n.id]


def test_deleting_result_cascades_to_its_notes_but_not_experiment_notes(db_session):
    a = _exp(db_session, "TN_CAS_001", 9118011)
    ra = _result(db_session, a, 1.0)
    scoped = _note(db_session, a, note_text="scoped", note_type=NoteType.result_note, result_id=ra.id)
    free = _note(db_session, a, note_text="free")
    scoped_id, free_id, exp_pk = scoped.id, free.id, a.id
    db_session.execute(
        ExperimentalResults.__table__.delete().where(ExperimentalResults.id == ra.id)
    )
    db_session.expire_all()
    ids = set(
        db_session.execute(
            select(ExperimentNotes.id).where(ExperimentNotes.experiment_fk == exp_pk)
        ).scalars()
    )
    assert ids == {free_id}
    assert scoped_id not in ids


def test_orm_delete_of_experiment_removes_scoped_and_free_notes(db_session):
    """Experiment.notes cascades via the ORM while result-scoped notes also sit
    behind the composite FK; the unit of work must order the deletes so
    neither path raises."""
    a = _exp(db_session, "TN_CAS_002", 9118014)
    ra = _result(db_session, a, 1.0)
    _note(db_session, a, note_text="scoped", note_type=NoteType.modification, result_id=ra.id)
    _note(db_session, a, note_text="free", note_type=NoteType.description)
    db_session.delete(a)
    db_session.flush()
    remaining = db_session.execute(
        select(ExperimentNotes.id).where(ExperimentNotes.experiment_id == "TN_CAS_002")
    ).scalars().all()
    assert remaining == []
