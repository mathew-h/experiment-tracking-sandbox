"""Issue #118 PR3: the results list reads the notes model.

has_modification_note is EXISTS over 'modification' notes on the result;
every result-scoped note is returned; the experiment detail's notes carry
their type; POST /api/results no longer requires a description.
"""
from __future__ import annotations

from database.models.enums import ExperimentStatus, NoteType
from database.models.experiments import Experiment, ExperimentNotes
from database.models.results import ExperimentalResults


def _exp(db, eid, num):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _result(db, exp, day, **kw):
    r = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=day,
                            time_post_reaction_bucket_days=day, description="legacy", **kw)
    db.add(r)
    db.flush()
    return r


def _note(db, exp, text_, **kw):
    n = ExperimentNotes(experiment_id=exp.experiment_id, experiment_fk=exp.id, note_text=text_, **kw)
    db.add(n)
    db.flush()
    return n


def test_results_list_flags_modification_from_notes_not_legacy_column(client, db_session):
    exp = _exp(db_session, "RTN_001", 7301)
    with_note = _result(db_session, exp, 1.0)
    legacy_only = _result(db_session, exp, 2.0, brine_modification_description="legacy text, no note")
    neither = _result(db_session, exp, 3.0)
    _note(db_session, exp, "swapped brine", note_type=NoteType.modification, result_id=with_note.id)
    _note(db_session, exp, "cloudy", note_type=NoteType.observation, result_id=with_note.id)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200, resp.text
    by_id = {r["id"]: r for r in resp.json()}
    assert by_id[with_note.id]["has_modification_note"] is True
    assert by_id[legacy_only.id]["has_modification_note"] is False, "the badge no longer reads the legacy column"
    assert by_id[neither.id]["has_modification_note"] is False
    assert "has_brine_modification" not in by_id[with_note.id]
    notes = by_id[with_note.id]["notes"]
    assert [(n["note_type"], n["note_text"]) for n in notes] == [
        ("modification", "swapped brine"), ("observation", "cloudy"),
    ]
    assert by_id[neither.id]["notes"] == []


def test_experiment_detail_notes_carry_their_type(client, db_session):
    exp = _exp(db_session, "RTN_002", 7302)
    r = _result(db_session, exp, 1.0)
    _note(db_session, exp, "the description", note_type=NoteType.description, created_by="new_experiments")
    _note(db_session, exp, "queued", result_id=r.id, needs_review=True)
    db_session.commit()
    resp = client.get(f"/api/experiments/{exp.experiment_id}")
    assert resp.status_code == 200
    notes = resp.json()["notes"]
    assert [(n["note_type"], n["result_id"], n["needs_review"], n["created_by"]) for n in notes] == [
        ("description", None, False, "new_experiments"),
        ("observation", r.id, True, None),
    ]


def test_create_result_without_description_uses_placeholder_and_writes_no_note(client, db_session):
    exp = _exp(db_session, "RTN_003", 7303)
    db_session.commit()
    resp = client.post("/api/results", json={"experiment_fk": exp.id, "time_post_reaction_days": 7.0})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["description"] == "Day 7.0 results"
    listed = client.get(f"/api/experiments/{exp.experiment_id}/results").json()
    assert listed[0]["notes"] == []


def test_list_item_condition_note_is_the_typed_description(client, db_session):
    exp = _exp(db_session, "RTN_004", 7304)
    _note(db_session, exp, "an older observation")
    _note(db_session, exp, "the description", note_type=NoteType.description)
    db_session.commit()
    resp = client.get("/api/experiments?search=RTN_004")
    assert resp.status_code == 200
    item = next(i for i in resp.json()["items"] if i["experiment_id"] == "RTN_004")
    assert item["condition_note"] == "the description"
