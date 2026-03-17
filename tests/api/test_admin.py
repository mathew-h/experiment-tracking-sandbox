from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment
from database.models.enums import ExperimentStatus


def test_recalculate_conditions(client, db_session):
    exp = Experiment(experiment_id="ADMIN_EXP_001", experiment_number=4001, status=ExperimentStatus.ONGOING)
    db_session.add(exp); db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp.experiment_id,
        rock_mass_g=20.0, water_volume_mL=100.0, water_to_rock_ratio=None,
    )
    db_session.add(cond); db_session.commit(); db_session.refresh(cond)
    # water_to_rock_ratio is None; trigger recalculate via admin endpoint
    resp = client.post(f"/api/admin/recalculate/conditions/{cond.id}")
    assert resp.status_code == 200
    assert resp.json()["water_to_rock_ratio"] == 5.0


def test_recalculate_unknown_model(client):
    resp = client.post("/api/admin/recalculate/unknown_model/1")
    assert resp.status_code == 422
