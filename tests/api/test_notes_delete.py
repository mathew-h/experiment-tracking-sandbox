"""Tests for DELETE /experiments/{experiment_id}/notes/{note_id}."""
from __future__ import annotations
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.enums import ExperimentStatus
from sqlalchemy import select


def _make_experiment_with_note(db, exp_id="DEL_NOTE_001", number=8001, text="Note to delete"):
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


def test_delete_note_returns_204(client, db_session):
    """DELETE /experiments/{id}/notes/{note_id} returns 204 on success."""
    exp, note = _make_experiment_with_note(db_session)
    response = client.delete(f"/api/experiments/{exp.experiment_id}/notes/{note.id}")
    assert response.status_code == 204


def test_delete_note_removes_row(client, db_session):
    """Note row is removed from the database after DELETE."""
    exp, note = _make_experiment_with_note(db_session, "DEL_NOTE_002", 8002)
    note_id = note.id
    client.delete(f"/api/experiments/{exp.experiment_id}/notes/{note_id}")
    remaining = db_session.execute(
        select(ExperimentNotes).where(ExperimentNotes.id == note_id)
    ).scalar_one_or_none()
    assert remaining is None


def test_delete_note_writes_modifications_log(client, db_session):
    """DELETE writes a ModificationsLog entry with modification_type='delete'."""
    exp, note = _make_experiment_with_note(db_session, "DEL_NOTE_003", 8003, text="Log me")
    client.delete(f"/api/experiments/{exp.experiment_id}/notes/{note.id}")
    log_entry = db_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id,
            ModificationsLog.modified_table == "experiment_notes",
        )
    ).scalar_one_or_none()
    assert log_entry is not None
    assert log_entry.modification_type == "delete"
    assert log_entry.old_values == {"note_text": "Log me"}
    assert log_entry.new_values is None


def test_delete_note_404_when_experiment_missing(client, db_session):
    """Returns 404 if the experiment does not exist."""
    response = client.delete("/api/experiments/DOES_NOT_EXIST/notes/1")
    assert response.status_code == 404


def test_delete_note_404_when_note_missing(client, db_session):
    """Returns 404 if the note does not exist or belongs to a different experiment."""
    exp, _ = _make_experiment_with_note(db_session, "DEL_NOTE_004", 8004)
    response = client.delete(f"/api/experiments/{exp.experiment_id}/notes/99999")
    assert response.status_code == 404
