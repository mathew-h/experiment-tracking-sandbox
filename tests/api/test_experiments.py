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


# --- B4: results-with-flags ---

def test_get_experiment_results_empty(client, db_session):
    _make_experiment(db_session, "RESULTS_EXP_001", 9300)
    resp = client.get("/api/experiments/RESULTS_EXP_001/results")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_experiment_results_with_flags(client, db_session):
    from database.models.results import ExperimentalResults, ScalarResults
    exp = _make_experiment(db_session, "RESULTS_EXP_002", 9301)
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=7.0,
        time_post_reaction_bucket_days=7.0,
        cumulative_time_post_reaction_days=7.0,
        is_primary_timepoint_result=True,
        description="T7",
    )
    db_session.add(result)
    db_session.flush()
    scalar = ScalarResults(result_id=result.id, final_ph=7.2, grams_per_ton_yield=55.0)
    db_session.add(scalar)
    db_session.commit()

    resp = client.get("/api/experiments/RESULTS_EXP_002/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["has_scalar"] is True
    assert data[0]["has_icp"] is False
    assert data[0]["final_ph"] == 7.2
    assert data[0]["grams_per_ton_yield"] == 55.0


def test_next_ids_no_auth_required(client):
    """next-ids must be accessible without authentication."""
    from fastapi.testclient import TestClient
    from backend.api.main import app
    from backend.auth.firebase_auth import verify_firebase_token

    original = app.dependency_overrides.copy()
    if verify_firebase_token in app.dependency_overrides:
        del app.dependency_overrides[verify_firebase_token]

    try:
        with TestClient(app) as c:
            r = c.get('/api/experiments/next-ids')
            assert r.status_code == 200
    finally:
        app.dependency_overrides.update(original)


def test_next_ids_includes_autoclave(client):
    """next-ids response includes Autoclave type."""
    r = client.get('/api/experiments/next-ids')
    assert r.status_code == 200
    data = r.json()
    assert 'Autoclave' in data
    assert isinstance(data['Autoclave'], int)
    assert data['Autoclave'] >= 1


# ============================================================
# Additive endpoints (Issue #7)
# ============================================================
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.conditions import ExperimentalConditions as _EC


def _make_exp_with_conditions(db, exp_id="TEST_001"):
    """Create experiment + conditions row, return (experiment, conditions)."""
    from database.models.experiments import Experiment
    from database.models.enums import ExperimentStatus
    from sqlalchemy import select, func as sqlfunc
    max_num = db.execute(select(sqlfunc.max(Experiment.experiment_number))).scalar() or 0
    exp = Experiment(experiment_id=exp_id, experiment_number=max_num + 1, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    cond = _EC(experiment_fk=exp.id, experiment_id=exp_id)
    db.add(cond)
    db.commit()
    db.refresh(exp)
    db.refresh(cond)
    return exp, cond


def _make_compound_for_additives(db, name="TestChem"):
    c = Compound(name=name, formula="TC", molecular_weight_g_mol=50.0)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_list_experiment_additives_empty(client, db_session):
    _make_exp_with_conditions(db_session, "ADDTEST_001")
    resp = client.get("/api/experiments/ADDTEST_001/additives")
    assert resp.status_code == 200
    assert resp.json() == []


def test_upsert_additive_creates(client, db_session):
    exp, _ = _make_exp_with_conditions(db_session, "ADDTEST_002")
    compound = _make_compound_for_additives(db_session, "MgOH2")
    resp = client.put(
        f"/api/experiments/{exp.experiment_id}/additives/{compound.id}",
        json={"amount": 5.0, "unit": "g"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["compound_id"] == compound.id
    assert data["amount"] == 5.0


def test_upsert_additive_updates_existing(client, db_session):
    exp, _ = _make_exp_with_conditions(db_session, "ADDTEST_003")
    compound = _make_compound_for_additives(db_session, "NaCl")
    # Create first
    client.put(
        f"/api/experiments/{exp.experiment_id}/additives/{compound.id}",
        json={"amount": 1.0, "unit": "g"}
    )
    # Update
    resp = client.put(
        f"/api/experiments/{exp.experiment_id}/additives/{compound.id}",
        json={"amount": 99.0, "unit": "mg"}
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == 99.0
    assert resp.json()["unit"] == "mg"


def test_upsert_additive_experiment_not_found(client, db_session):
    compound = _make_compound_for_additives(db_session, "Orphan")
    resp = client.put(
        f"/api/experiments/NONEXISTENT/additives/{compound.id}",
        json={"amount": 1.0, "unit": "g"}
    )
    assert resp.status_code == 404


def test_upsert_additive_no_conditions(client, db_session):
    """Experiment exists but has no conditions row — should 404."""
    from database.models.experiments import Experiment
    from database.models.enums import ExperimentStatus
    from sqlalchemy import select, func as sqlfunc
    max_num = db_session.execute(select(sqlfunc.max(Experiment.experiment_number))).scalar() or 0
    exp = Experiment(experiment_id="NOCOND_001", experiment_number=max_num + 1, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.commit()
    compound = _make_compound_for_additives(db_session, "NoCond")
    resp = client.put(
        f"/api/experiments/NOCOND_001/additives/{compound.id}",
        json={"amount": 1.0, "unit": "g"}
    )
    assert resp.status_code == 404


def test_upsert_additive_compound_not_found(client, db_session):
    """Upsert with a compound_id that doesn't exist should 404."""
    _make_exp_with_conditions(db_session, "ADDTEST_006")
    resp = client.put(
        "/api/experiments/ADDTEST_006/additives/99999",
        json={"amount": 1.0, "unit": "g"}
    )
    assert resp.status_code == 404


def test_delete_additive(client, db_session):
    exp, _ = _make_exp_with_conditions(db_session, "ADDTEST_004")
    compound = _make_compound_for_additives(db_session, "ToDelete")
    # Create additive first
    client.put(
        f"/api/experiments/{exp.experiment_id}/additives/{compound.id}",
        json={"amount": 2.0, "unit": "g"}
    )
    # Delete it
    resp = client.delete(f"/api/experiments/{exp.experiment_id}/additives/{compound.id}")
    assert resp.status_code == 204
    # Verify gone
    list_resp = client.get(f"/api/experiments/{exp.experiment_id}/additives")
    assert list_resp.json() == []


def test_delete_additive_not_found(client, db_session):
    _make_exp_with_conditions(db_session, "ADDTEST_005")
    resp = client.delete("/api/experiments/ADDTEST_005/additives/99999")
    assert resp.status_code == 404
