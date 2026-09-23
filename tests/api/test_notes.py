from __future__ import annotations
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.enums import ExperimentStatus
from sqlalchemy import select


def _make_experiment_with_note(db, exp_id="NOTE_001", number=7001, text="Initial note text"):
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    note = ExperimentNotes(experiment_id=exp_id, experiment_fk=exp.id, note_text=text)
    db.add(note)
    db.commit()
    db.refresh(exp)
    db.refresh(note)
    return exp, note


def test_patch_note_happy_path(client, db_session):
    exp, note = _make_experiment_with_note(db_session)
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
        json={"note_text": "Corrected note text"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["note_text"] == "Corrected note text"
    assert body["id"] == note.id
    assert body["updated_at"] is not None


def test_patch_note_wrong_experiment_returns_404(client, db_session):
    exp, note = _make_experiment_with_note(db_session, "NOTE_002", 7002)
    resp = client.patch(
        f"/api/experiments/DOES_NOT_EXIST/notes/{note.id}",
        json={"note_text": "x"},
    )
    assert resp.status_code == 404


def test_patch_note_wrong_note_id_returns_404(client, db_session):
    exp, _ = _make_experiment_with_note(db_session, "NOTE_003", 7003)
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/99999",
        json={"note_text": "x"},
    )
    assert resp.status_code == 404


def test_patch_note_empty_text_returns_422(client, db_session):
    exp, note = _make_experiment_with_note(db_session, "NOTE_004", 7004)
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
        json={"note_text": ""},
    )
    assert resp.status_code == 422


def test_patch_condition_note_is_editable(client, db_session):
    """First note (condition note) must be editable — no special read-only treatment."""
    exp, note = _make_experiment_with_note(db_session, "NOTE_005", 7005, text="Original condition note")
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
        json={"note_text": "Fixed condition note"},
    )
    assert resp.status_code == 200
    assert resp.json()["note_text"] == "Fixed condition note"


def test_patch_note_writes_modifications_log(client, db_session):
    exp, note = _make_experiment_with_note(db_session, "NOTE_006", 7006, text="Before")
    client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
        json={"note_text": "After"},
    )
    log_entry = db_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id,
            ModificationsLog.modified_table == "experiment_notes",
        )
    ).scalar_one_or_none()
    assert log_entry is not None
    assert log_entry.modification_type == "update"
    assert log_entry.old_values == {"note_text": "Before"}
    assert log_entry.new_values == {"note_text": "After"}


def test_patch_note_noop_when_text_unchanged(client, db_session):
    """If text matches the stored value exactly, no DB write and no ModificationsLog entry."""
    exp, note = _make_experiment_with_note(db_session, "NOTE_007", 7007, text="Same text")
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/notes/{note.id}",
        json={"note_text": "Same text"},
    )
    assert resp.status_code == 200
    assert resp.json()["note_text"] == "Same text"
    log_count = db_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id,
            ModificationsLog.modified_table == "experiment_notes",
        )
    ).scalars().all()
    assert len(log_count) == 0


# ---------------------------------------------------------------------------
# Typed notes on POST /experiments/{id}/notes (issue #118, PR1)
# ---------------------------------------------------------------------------
from database.models.enums import NoteType  # noqa: E402
from database.models.results import ExperimentalResults  # noqa: E402


def _make_result(db, exp, day=1.0):
    r = ExperimentalResults(
        experiment_fk=exp.id, description="seed",
        time_post_reaction_days=day, time_post_reaction_bucket_days=day,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_post_note_defaults_to_observation_and_records_author(client, db_session):
    exp, _ = _make_experiment_with_note(db_session, "NOTE_T_001", 7101)
    resp = client.post(f"/api/experiments/{exp.experiment_id}/notes", json={"note_text": "free text"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["note_type"] == "observation"
    assert body["result_id"] is None
    assert body["created_by"] == "test@addisenergy.com"
    assert body["needs_review"] is False


def test_post_modification_note_scoped_to_own_result(client, db_session):
    exp, _ = _make_experiment_with_note(db_session, "NOTE_T_002", 7102)
    r = _make_result(db_session, exp)
    resp = client.post(
        f"/api/experiments/{exp.experiment_id}/notes",
        json={"note_text": "brine replaced", "note_type": "modification", "result_id": r.id},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["note_type"], body["result_id"]) == ("modification", r.id)
    stored = db_session.get(ExperimentNotes, body["id"])
    assert stored.note_type is NoteType.modification and stored.result_id == r.id


def test_post_note_rejects_result_of_another_experiment(client, db_session):
    exp, _ = _make_experiment_with_note(db_session, "NOTE_T_003", 7103)
    other, _ = _make_experiment_with_note(db_session, "NOTE_T_004", 7104)
    r_other = _make_result(db_session, other)
    resp = client.post(
        f"/api/experiments/{exp.experiment_id}/notes",
        json={"note_text": "x", "note_type": "result_note", "result_id": r_other.id},
    )
    assert resp.status_code == 422
    assert "does not belong" in resp.json()["detail"]


def test_post_note_rejects_description_with_result(client, db_session):
    exp, _ = _make_experiment_with_note(db_session, "NOTE_T_005", 7105)
    r = _make_result(db_session, exp)
    resp = client.post(
        f"/api/experiments/{exp.experiment_id}/notes",
        json={"note_text": "x", "note_type": "description", "result_id": r.id},
    )
    assert resp.status_code == 422


def test_post_note_rejects_modification_without_result(client, db_session):
    exp, _ = _make_experiment_with_note(db_session, "NOTE_T_006", 7106)
    resp = client.post(
        f"/api/experiments/{exp.experiment_id}/notes",
        json={"note_text": "x", "note_type": "modification"},
    )
    assert resp.status_code == 422


def test_post_second_description_returns_409(client, db_session):
    exp, _ = _make_experiment_with_note(db_session, "NOTE_T_007", 7107)
    first = client.post(
        f"/api/experiments/{exp.experiment_id}/notes",
        json={"note_text": "summary", "note_type": "description"},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/experiments/{exp.experiment_id}/notes",
        json={"note_text": "another summary", "note_type": "description"},
    )
    assert second.status_code == 409
    assert "description" in second.json()["detail"]


def test_post_note_unknown_type_is_422(client, db_session):
    exp, _ = _make_experiment_with_note(db_session, "NOTE_T_008", 7108)
    resp = client.post(
        f"/api/experiments/{exp.experiment_id}/notes",
        json={"note_text": "x", "note_type": "gossip"},
    )
    assert resp.status_code == 422
