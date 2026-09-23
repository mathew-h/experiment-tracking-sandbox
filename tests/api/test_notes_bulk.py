"""Issue #122 PR-A: bulk review-queue actions.

PATCH /api/experiments/notes/bulk and DELETE /api/experiments/notes/bulk act on
a list of note ids atomically: every id is validated first, then all rows change
in one transaction, with one ModificationsLog row per note.
"""
from __future__ import annotations

from sqlalchemy import select

from database.models.enums import ExperimentStatus, NoteType
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.results import ExperimentalResults


def _exp(db, eid, num, researcher=None):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING, researcher=researcher)
    db.add(exp)
    db.flush()
    return exp


def _result(db, exp, day=7.0):
    r = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=day,
                            time_post_reaction_bucket_days=day, description="legacy")
    db.add(r)
    db.flush()
    return r


def _note(db, exp, text_, **kw):
    n = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text=text_, **kw)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _logs(db, exp):
    return db.execute(
        select(ModificationsLog).where(ModificationsLog.experiment_fk == exp.id,
                                       ModificationsLog.modified_table == "experiment_notes")
    ).scalars().all()


# ---------------------------------------------------------------- PATCH ----

def test_bulk_patch_marks_reviewed_and_logs_one_row_per_note(client, db_session):
    exp = _exp(db_session, "BULK_001", 7301)
    a = _note(db_session, exp, "t=0", needs_review=True)
    b = _note(db_session, exp, "Day 7", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [a.id, b.id], "needs_review": False})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"count": 2, "ids": sorted([a.id, b.id])}
    db_session.expire_all()
    assert db_session.get(ExperimentNotes, a.id).needs_review is False
    assert db_session.get(ExperimentNotes, b.id).needs_review is False
    logs = _logs(db_session, exp)
    assert len(logs) == 2
    assert all(l.modification_type == "update" for l in logs)
    assert all(l.old_values == {"needs_review": True} and l.new_values == {"needs_review": False} for l in logs)
    assert all(l.modified_by == "test@addisenergy.com" for l in logs)


def test_bulk_patch_duplicate_ids_are_counted_once(client, db_session):
    exp = _exp(db_session, "BULK_002", 7302)
    a = _note(db_session, exp, "x", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [a.id, a.id, a.id], "needs_review": False})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"count": 1, "ids": [a.id]}
    assert len(_logs(db_session, exp)) == 1


def test_bulk_patch_already_in_state_is_a_no_op(client, db_session):
    exp = _exp(db_session, "BULK_003", 7303)
    a = _note(db_session, exp, "x", needs_review=False)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [a.id], "needs_review": False})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"count": 0, "ids": []}
    assert _logs(db_session, exp) == []


def test_bulk_patch_retypes_result_scoped_notes_and_clears_review(client, db_session):
    exp = _exp(db_session, "BULK_004", 7304)
    r = _result(db_session, exp)
    a = _note(db_session, exp, "swapped brine", result_id=r.id, needs_review=True)
    b = _note(db_session, exp, "added Cu", result_id=r.id, needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk",
                        json={"ids": [a.id, b.id], "note_type": "modification", "needs_review": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 2
    db_session.expire_all()
    assert db_session.get(ExperimentNotes, a.id).note_type is NoteType.modification
    logs = _logs(db_session, exp)
    assert len(logs) == 2
    assert logs[0].new_values == {"note_type": "modification", "needs_review": False}


def test_bulk_patch_scope_violation_is_422_naming_ids_and_changes_nothing(client, db_session):
    exp = _exp(db_session, "BULK_005", 7305)
    r = _result(db_session, exp)
    ok = _note(db_session, exp, "on result", result_id=r.id, needs_review=True)
    bad = _note(db_session, exp, "experiment-level", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk",
                        json={"ids": [ok.id, bad.id], "note_type": "modification", "needs_review": False})
    assert resp.status_code == 422, resp.text
    assert str(bad.id) in resp.json()["detail"]
    assert str(ok.id) not in resp.json()["detail"]
    db_session.expire_all()
    # Atomic: the valid one did not change either.
    assert db_session.get(ExperimentNotes, ok.id).note_type is NoteType.observation
    assert db_session.get(ExperimentNotes, ok.id).needs_review is True
    assert _logs(db_session, exp) == []


def test_bulk_patch_description_on_result_scoped_note_is_422(client, db_session):
    exp = _exp(db_session, "BULK_006", 7306)
    r = _result(db_session, exp)
    n = _note(db_session, exp, "x", result_id=r.id)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [n.id], "note_type": "description"})
    assert resp.status_code == 422
    assert str(n.id) in resp.json()["detail"]


def test_bulk_patch_second_description_is_409_when_experiment_has_one(client, db_session):
    exp = _exp(db_session, "BULK_007", 7307)
    _note(db_session, exp, "the description", note_type=NoteType.description)
    other = _note(db_session, exp, "an observation", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [other.id], "note_type": "description"})
    assert resp.status_code == 409, resp.text
    assert "BULK_007" in resp.json()["detail"]
    db_session.expire_all()
    assert db_session.get(ExperimentNotes, other.id).note_type is NoteType.observation


def test_bulk_patch_two_selected_on_same_experiment_to_description_is_409(client, db_session):
    exp = _exp(db_session, "BULK_008", 7308)
    a = _note(db_session, exp, "one", needs_review=True)
    b = _note(db_session, exp, "two", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [a.id, b.id], "note_type": "description"})
    assert resp.status_code == 409, resp.text
    assert "BULK_008" in resp.json()["detail"]
    assert _logs(db_session, exp) == []


def test_bulk_patch_unknown_id_is_404_naming_it(client, db_session):
    exp = _exp(db_session, "BULK_009", 7309)
    a = _note(db_session, exp, "x", needs_review=True)
    resp = client.patch("/api/experiments/notes/bulk", json={"ids": [a.id, 999999], "needs_review": False})
    assert resp.status_code == 404, resp.text
    assert "999999" in resp.json()["detail"]
    db_session.expire_all()
    assert db_session.get(ExperimentNotes, a.id).needs_review is True


def test_bulk_patch_body_validation(client, db_session):
    # No action field.
    assert client.patch("/api/experiments/notes/bulk", json={"ids": [1]}).status_code == 422
    # Empty ids.
    assert client.patch("/api/experiments/notes/bulk", json={"ids": [], "needs_review": False}).status_code == 422
    # Over the cap.
    too_many = list(range(1, 502))
    assert client.patch("/api/experiments/notes/bulk", json={"ids": too_many, "needs_review": False}).status_code == 422


def test_bulk_path_is_not_captured_as_an_experiment_id(client, db_session):
    """/notes/bulk must hit the bulk route (422 on a bad body), not /{experiment_id}/... (404)."""
    resp = client.patch("/api/experiments/notes/bulk", json={})
    assert resp.status_code == 422
