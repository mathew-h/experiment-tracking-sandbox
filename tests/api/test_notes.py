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
