from database.models.experiments import Experiment
from database.models.enums import ExperimentStatus


def _make_experiment(db, experiment_id="TEST_001", number=9001):
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def test_list_experiments_empty(client):
    resp = client.get("/api/experiments")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_experiments_returns_items(client, db_session):
    _make_experiment(db_session)
    resp = client.get("/api/experiments")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_get_experiment_not_found(client):
    resp = client.get("/api/experiments/DOES_NOT_EXIST")
    assert resp.status_code == 404


def test_get_experiment_by_id(client, db_session):
    exp = _make_experiment(db_session, "READABLE_001", 9002)
    resp = client.get(f"/api/experiments/{exp.experiment_id}")
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == "READABLE_001"
