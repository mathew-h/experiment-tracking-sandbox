from database.models.experiments import Experiment
from database.models.results import ExperimentalResults
from database.models.enums import ExperimentStatus


def _seed(db):
    exp = Experiment(experiment_id="RES_EXP_001", experiment_number=6001, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    result = ExperimentalResults(
        experiment_fk=exp.id,
        description="T0",
        is_primary_timepoint_result=True,
        time_post_reaction_days=0.0,
        time_post_reaction_bucket_days=0.0,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return exp, result


def test_list_results_by_experiment(client, db_session):
    exp, _ = _seed(db_session)
    resp = client.get(f"/api/results/{exp.experiment_id}")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_create_result(client, db_session):
    exp, _ = _seed(db_session)
    payload = {
        "experiment_fk": exp.id,
        "description": "Day 7",
        "time_post_reaction_days": 7.0,
        "time_post_reaction_bucket_days": 7.0,
        "is_primary_timepoint_result": False,
    }
    resp = client.post("/api/results", json=payload)
    assert resp.status_code == 201
    assert resp.json()["description"] == "Day 7"


def test_create_scalar_triggers_calculation(client, db_session):
    exp, result = _seed(db_session)
    payload = {
        "result_id": result.id,
        "gross_ammonium_concentration_mM": 1.0,
        "h2_concentration": 500.0,
        "gas_sampling_volume_ml": 10.0,
        "gas_sampling_pressure_MPa": 0.1,
    }
    resp = client.post("/api/results/scalar", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    # H2 calc should have run
    assert data["h2_micromoles"] is not None
    assert data["h2_micromoles"] > 0
