from database.models.experiments import Experiment
from database.models.enums import ExperimentStatus


def _make_experiment(db, eid="COND_EXP_001", num=7001):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def test_create_conditions_triggers_calculation(client, db_session):
    exp = _make_experiment(db_session)
    payload = {
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "rock_mass_g": 10.0,
        "water_volume_mL": 50.0,
    }
    resp = client.post("/api/conditions", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    # water_to_rock_ratio is a persisted Float column (conditions.py line 33)
    # The calc engine writes it directly; it is NOT a @hybrid_property.
    assert data["water_to_rock_ratio"] == 5.0  # 50/10


def test_get_conditions(client, db_session):
    exp = _make_experiment(db_session, "COND_EXP_002", 7002)
    payload = {"experiment_fk": exp.id, "experiment_id": exp.experiment_id, "temperature_c": 180.0}
    created = client.post("/api/conditions", json=payload).json()
    resp = client.get(f"/api/conditions/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["temperature_c"] == 180.0
