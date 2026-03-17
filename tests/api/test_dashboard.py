from database.models.experiments import Experiment
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus


def _seed_reactor(db, reactor_num=1, exp_id="DASH_EXP_001", num=5001):
    exp = Experiment(experiment_id=exp_id, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp); db.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp_id, reactor_number=reactor_num
    )
    db.add(cond); db.commit(); db.refresh(exp)
    return exp


def test_reactor_status_empty(client):
    resp = client.get("/api/dashboard/reactor-status")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_reactor_status_returns_ongoing(client, db_session):
    _seed_reactor(db_session, reactor_num=3, exp_id="DASH_R3_001", num=5002)
    resp = client.get("/api/dashboard/reactor-status")
    assert resp.status_code == 200
    reactor_nums = [r["reactor_number"] for r in resp.json()]
    assert 3 in reactor_nums


def test_experiment_timeline(client, db_session):
    exp = _seed_reactor(db_session, reactor_num=4, exp_id="DASH_TL_001", num=5003)
    resp = client.get(f"/api/dashboard/timeline/{exp.experiment_id}")
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == exp.experiment_id
