"""PATCH /api/experiments/{id} must sync every denormalized experiment_id copy."""
from __future__ import annotations

from database import (
    Experiment,
    ExperimentNotes,
    ExperimentalConditions,
    ExternalAnalysis,
    ModificationsLog,
    XRDPhase,
)
from database.models.enums import ExperimentStatus


def test_patch_rename_syncs_all_denormalized_ids(client, db_session):
    exp = Experiment(
        experiment_id="RENAME_API_001",
        experiment_number=8802001,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add_all([
        ExperimentalConditions(
            experiment_id="RENAME_API_001", experiment_fk=exp.id, temperature_c=200.0
        ),
        ExperimentNotes(
            experiment_id="RENAME_API_001", experiment_fk=exp.id, note_text="n"
        ),
        ModificationsLog(
            experiment_id="RENAME_API_001", experiment_fk=exp.id,
            modified_by="t", modification_type="create", modified_table="experiments",
        ),
        ExternalAnalysis(
            experiment_id="RENAME_API_001", experiment_fk=exp.id, analysis_type="XRD"
        ),
        XRDPhase(
            experiment_id="RENAME_API_001", experiment_fk=exp.id,
            mineral_name="Olivine", amount=4.0, time_post_reaction_days=1.0,
        ),
    ])
    db_session.commit()
    exp_pk = exp.id

    resp = client.patch(
        "/api/experiments/RENAME_API_001",
        json={"experiment_id": "RENAME_API_001a-t1"},
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    for model in (ExperimentalConditions, ExperimentNotes, ExternalAnalysis, XRDPhase):
        for row in db_session.query(model).filter(model.experiment_fk == exp_pk).all():
            assert row.experiment_id == "RENAME_API_001a-t1", (
                f"{model.__name__} not synced: {row.experiment_id!r}"
            )
    # Every modifications_log row for this experiment now names the new id,
    # including the pre-existing one and the row the rename itself wrote.
    mods = db_session.query(ModificationsLog).filter(
        ModificationsLog.experiment_fk == exp_pk
    ).all()
    assert mods
    assert {m.experiment_id for m in mods} == {"RENAME_API_001a-t1"}
