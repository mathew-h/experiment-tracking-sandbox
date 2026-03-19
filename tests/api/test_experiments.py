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
    assert resp.json()["items"] == []


def test_list_experiments_returns_items(client, db_session):
    _make_experiment(db_session)
    resp = client.get("/api/experiments")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) >= 1


def test_get_experiment_not_found(client):
    resp = client.get("/api/experiments/DOES_NOT_EXIST")
    assert resp.status_code == 404


def test_get_experiment_by_id(client, db_session):
    exp = _make_experiment(db_session, "READABLE_001", 9002)
    resp = client.get(f"/api/experiments/{exp.experiment_id}")
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == "READABLE_001"


def test_create_experiment(client):
    payload = {
        "experiment_id": "CREATE_TEST_001",
        "experiment_number": 8001,
        "status": "ONGOING",
    }
    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 201
    assert resp.json()["experiment_id"] == "CREATE_TEST_001"


def test_create_experiment_duplicate_id_fails(client, db_session):
    _make_experiment(db_session, "DUP_001", 8002)
    payload = {"experiment_id": "DUP_001", "experiment_number": 8003}
    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 409


def test_patch_experiment(client, db_session):
    _make_experiment(db_session, "PATCH_ME_001", 8004)
    resp = client.patch("/api/experiments/PATCH_ME_001", json={"status": "COMPLETED"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"


def test_delete_experiment(client, db_session):
    _make_experiment(db_session, "DELETE_ME_001", 8005)
    resp = client.delete("/api/experiments/DELETE_ME_001")
    assert resp.status_code == 204
    assert client.get("/api/experiments/DELETE_ME_001").status_code == 404


# --- B2: next-id and auto-numbering ---

def test_next_id_first_ever(client):
    """No existing experiments of type → returns PREFIX_001."""
    resp = client.get("/api/experiments/next-id?type=HPHT")
    assert resp.status_code == 200
    assert resp.json()["next_id"] == "HPHT_001"


def test_next_id_increments(client, db_session):
    """Existing HPHT_002 → next is HPHT_003."""
    db_session.add(Experiment(experiment_id="HPHT_002", experiment_number=9010, status=ExperimentStatus.ONGOING))
    db_session.commit()
    resp = client.get("/api/experiments/next-id?type=HPHT")
    assert resp.json()["next_id"] == "HPHT_003"


def test_next_id_serum_prefix(client):
    resp = client.get("/api/experiments/next-id?type=Serum")
    assert resp.json()["next_id"] == "SERUM_001"


def test_next_id_core_flood_prefix(client):
    resp = client.get("/api/experiments/next-id?type=Core Flood")
    assert resp.json()["next_id"] == "CF_001"


def test_create_experiment_auto_number(client, db_session):
    """experiment_number omitted → auto-assigned."""
    resp = client.post("/api/experiments", json={"experiment_id": "AUTONUMBER_001", "status": "ONGOING"})
    assert resp.status_code == 201
    assert resp.json()["experiment_number"] >= 1


# --- B3: status-patch and list pagination ---

def test_patch_status(client, db_session):
    _make_experiment(db_session, "STATUS_TEST_001", 9020)
    resp = client.patch("/api/experiments/STATUS_TEST_001/status", json={"status": "COMPLETED"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"


def test_patch_status_invalid(client, db_session):
    _make_experiment(db_session, "STATUS_TEST_002", 9021)
    resp = client.patch("/api/experiments/STATUS_TEST_002/status", json={"status": "INVALID"})
    assert resp.status_code == 422


def test_list_experiments_pagination(client, db_session):
    for i in range(5):
        db_session.add(Experiment(experiment_id=f"PAGE_{i:03d}", experiment_number=9100 + i, status=ExperimentStatus.ONGOING))
    db_session.commit()
    resp = client.get("/api/experiments?skip=0&limit=3")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) <= 3


def test_list_experiments_filter_by_status(client, db_session):
    db_session.add(Experiment(experiment_id="COMP_001", experiment_number=9200, status=ExperimentStatus.COMPLETED))
    db_session.commit()
    resp = client.get("/api/experiments?status=COMPLETED")
    data = resp.json()
    assert all(e["status"] == "COMPLETED" for e in data["items"])
