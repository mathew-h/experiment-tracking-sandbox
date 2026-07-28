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


def test_patch_rename_success(client, db_session):
    _make_experiment(db_session, "RENAME_SRC_001", 9010)
    resp = client.patch("/api/experiments/RENAME_SRC_001", json={"experiment_id": "RENAME_DST_001"})
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == "RENAME_DST_001"


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


# ============================================================
# Type/reactor filter + description search regression (Issue #64)
# ============================================================

def test_list_experiments_type_reactor_filter_pagination_regression(client, db_session):
    """Type/reactor filters must be applied in SQL before pagination. Matches are given
    the LOWEST experiment_numbers in the batch (i.e. NOT among the "newest" page), which
    reproduces the original bug: filtering in Python after offset/limit returned an empty
    page 1 even though matches existed further down."""
    from sqlalchemy import select, func as sqlfunc
    base_num = (db_session.execute(select(sqlfunc.max(Experiment.experiment_number))).scalar() or 0) + 1000

    match_count = 3
    total_count = 30
    for i in range(total_count):
        exp = Experiment(experiment_id=f"FILTREG_{i:03d}", experiment_number=base_num + i, status=ExperimentStatus.ONGOING)
        db_session.add(exp)
        db_session.flush()
        is_match = i < match_count
        db_session.add(_EC(
            experiment_fk=exp.id,
            experiment_id=exp.experiment_id,
            experiment_type="HPHT" if is_match else "Serum",
            reactor_number=3 if is_match else 7,
        ))
    db_session.commit()

    resp = client.get("/api/experiments?experiment_type=HPHT&reactor_number=3&skip=0&limit=25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == match_count
    assert len(data["items"]) == match_count
    returned_ids = {item["experiment_id"] for item in data["items"]}
    assert returned_ids == {f"FILTREG_{i:03d}" for i in range(match_count)}


def test_list_experiments_total_stable_across_pages(client, db_session):
    """total must be identical across skip=0 and skip=limit for the same filter."""
    from sqlalchemy import select, func as sqlfunc
    base_num = (db_session.execute(select(sqlfunc.max(Experiment.experiment_number))).scalar() or 0) + 2000

    for i in range(10):
        exp = Experiment(experiment_id=f"TOTSTABLE_{i:03d}", experiment_number=base_num + i, status=ExperimentStatus.ONGOING)
        db_session.add(exp)
        db_session.flush()
        db_session.add(_EC(
            experiment_fk=exp.id, experiment_id=exp.experiment_id,
            experiment_type="Autoclave", reactor_number=5,
        ))
    db_session.commit()

    resp1 = client.get("/api/experiments?experiment_type=Autoclave&reactor_number=5&skip=0&limit=4")
    resp2 = client.get("/api/experiments?experiment_type=Autoclave&reactor_number=5&skip=4&limit=4")
    assert resp1.status_code == 200 and resp2.status_code == 200
    assert resp1.json()["total"] == resp2.json()["total"] == 10


def test_list_experiments_description_search(client, db_session):
    """description filters on the experiment's first note (initial_note)."""
    from database.models.experiments import ExperimentNotes
    from sqlalchemy import select, func as sqlfunc
    base_num = (db_session.execute(select(sqlfunc.max(Experiment.experiment_number))).scalar() or 0) + 3000

    exp_match = Experiment(experiment_id="DESC_MATCH_001", experiment_number=base_num, status=ExperimentStatus.ONGOING)
    exp_other = Experiment(experiment_id="DESC_OTHER_001", experiment_number=base_num + 1, status=ExperimentStatus.ONGOING)
    db_session.add_all([exp_match, exp_other])
    db_session.flush()
    db_session.add(ExperimentNotes(experiment_id=exp_match.experiment_id, experiment_fk=exp_match.id, note_text="unique magnetite pulse test"))
    db_session.add(ExperimentNotes(experiment_id=exp_other.experiment_id, experiment_fk=exp_other.id, note_text="unrelated note text"))
    db_session.commit()

    resp = client.get("/api/experiments?description=magnetite")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["experiment_id"] == "DESC_MATCH_001"

    resp2 = client.get("/api/experiments?description=magnetite&skip=0&limit=1")
    assert resp2.json()["total"] == 1
    assert len(resp2.json()["items"]) == 1


def test_upsert_additive_no_conditions(client, db_session):
    """Experiment exists but has no conditions row — should 404."""
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


# --- #27: /exists endpoint ---

def test_exists_returns_true_for_known_id(client, db_session):
    _make_experiment(db_session, "EXISTS_001", 9020)
    resp = client.get("/api/experiments/EXISTS_001/exists")
    assert resp.status_code == 200
    assert resp.json() == {"exists": True}


def test_exists_returns_false_for_unknown_id(client):
    resp = client.get("/api/experiments/DOES_NOT_EXIST_XYZ/exists")
    assert resp.status_code == 200
    assert resp.json() == {"exists": False}


# --- #27: rename via PATCH ---

def test_patch_rename_conflict(client, db_session):
    _make_experiment(db_session, "CONFLICT_SRC_001", 9030)
    _make_experiment(db_session, "CONFLICT_DST_001", 9031)
    resp = client.patch(
        "/api/experiments/CONFLICT_SRC_001",
        json={"experiment_id": "CONFLICT_DST_001"},
    )
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_patch_rename_same_id_is_noop(client, db_session):
    _make_experiment(db_session, "SAME_ID_001", 9032)
    resp = client.patch("/api/experiments/SAME_ID_001", json={"experiment_id": "SAME_ID_001"})
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == "SAME_ID_001"


def test_patch_rename_logs_modification(client, db_session):
    from database.models.experiments import ModificationsLog
    from sqlalchemy import select as sa_select
    _make_experiment(db_session, "LOG_SRC_001", 9033)
    client.patch("/api/experiments/LOG_SRC_001", json={"experiment_id": "LOG_DST_001"})
    log = db_session.execute(
        sa_select(ModificationsLog)
        .where(ModificationsLog.modified_table == "experiments")
        .order_by(ModificationsLog.id.desc())
    ).scalar_one_or_none()
    assert log is not None
    assert log.old_values == {"experiment_id": "LOG_SRC_001"}
    assert log.new_values == {"experiment_id": "LOG_DST_001"}


def test_patch_rename_strips_whitespace(client, db_session):
    _make_experiment(db_session, "STRIP_SRC_001", 9034)
    resp = client.patch("/api/experiments/STRIP_SRC_001", json={"experiment_id": "  STRIP_DST_001  "})
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == "STRIP_DST_001"


# --- #81 C1: rename must re-sync id_timepoint_days ---

def test_patch_rename_resyncs_id_timepoint_days(client, db_session):
    _make_experiment(db_session, "SERUM_020a-t7", 9041)
    resp = client.patch(
        "/api/experiments/SERUM_020a-t7",
        json={"experiment_id": "SERUM_020a-t14"},
    )
    assert resp.status_code == 200
    assert resp.json()["id_timepoint_days"] == 14.0
    db_session.expire_all()
    exp = db_session.query(Experiment).filter(
        Experiment.experiment_id == "SERUM_020a-t14"
    ).one()
    assert exp.id_timepoint_days == 14.0


def test_patch_rename_clears_id_timepoint_days_when_token_dropped(client, db_session):
    _make_experiment(db_session, "SERUM_021a-t7", 9042)
    resp = client.patch(
        "/api/experiments/SERUM_021a-t7",
        json={"experiment_id": "SERUM_021a"},
    )
    assert resp.status_code == 200
    assert resp.json()["id_timepoint_days"] is None
    db_session.expire_all()
    exp = db_session.query(Experiment).filter(
        Experiment.experiment_id == "SERUM_021a"
    ).one()
    assert exp.id_timepoint_days is None


def test_patch_rename_syncs_external_analysis(client, db_session):
    from database.models.analysis import ExternalAnalysis

    exp = _make_experiment(db_session, "ANALYSIS_SYNC_SRC_001", 9040)
    analysis = ExternalAnalysis(
        experiment_id="ANALYSIS_SYNC_SRC_001",
        experiment_fk=exp.id,
        analysis_type="XRD",
    )
    db_session.add(analysis)
    db_session.commit()
    db_session.refresh(analysis)

    resp = client.patch(
        "/api/experiments/ANALYSIS_SYNC_SRC_001",
        json={"experiment_id": "ANALYSIS_SYNC_DST_001"},
    )
    assert resp.status_code == 200

    db_session.refresh(analysis)
    assert analysis.experiment_id == "ANALYSIS_SYNC_DST_001"


# --- #87 Phase 4 (D3): rename recomputes replicate lineage ---

def test_patch_rename_same_stem_sets_replicate_lineage(client, db_session):
    """Renaming a plain experiment into a lettered spelling of an EXISTING
    stem's parent must set replicate_label and link parent_experiment_fk,
    and the vial must then show up in its replicate group."""
    parent = _make_experiment(db_session, "SERUM_020", 9050)
    _make_experiment(db_session, "RENAME_INTO_REPL_SRC", 9051)

    resp = client.patch(
        "/api/experiments/RENAME_INTO_REPL_SRC",
        json={"experiment_id": "SERUM_020b"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["replicate_label"] == "b"
    assert body["base_experiment_id"] == "SERUM_020"
    assert body["parent_experiment_fk"] == parent.id

    group_resp = client.get("/api/experiments/SERUM_020b/replicate-group")
    assert group_resp.status_code == 200
    group = group_resp.json()
    assert group["parent"]["experiment_id"] == "SERUM_020"
    labels = [m["replicate_label"] for m in group["members"]]
    assert "b" in labels


def test_patch_rename_across_stems_rewrites_base_experiment_id(client, db_session):
    """Renaming a lettered replicate of one stem into a lettered spelling of
    a DIFFERENT stem must rewrite base_experiment_id to the new stem."""
    _make_experiment(db_session, "SERUM_020", 9052)
    _make_experiment(db_session, "SERUM_020c", 9053)

    resp = client.patch(
        "/api/experiments/SERUM_020c",
        json={"experiment_id": "SERUM_030c"},
    )
    assert resp.status_code == 200
    assert resp.json()["base_experiment_id"] == "SERUM_030"
    assert resp.json()["replicate_label"] == "c"


def test_patch_rename_group_parent_with_replicates_returns_409(client, db_session):
    """Renaming a group parent that has lettered members is blocked, and
    nothing about the parent or its members is mutated."""
    parent = _make_experiment(db_session, "SERUM_040", 9054)
    member = _make_experiment(db_session, "SERUM_040a", 9055)
    db_session.expire_all()
    member = db_session.query(Experiment).filter_by(id=member.id).one()
    assert member.parent_experiment_fk == parent.id  # sanity: lineage set on create

    resp = client.patch("/api/experiments/SERUM_040", json={"experiment_id": "SERUM_050"})
    assert resp.status_code == 409
    assert "SERUM_040a" in resp.json()["detail"]

    db_session.expire_all()
    unchanged_parent = db_session.query(Experiment).filter_by(id=parent.id).one()
    assert unchanged_parent.experiment_id == "SERUM_040"
    unchanged_member = db_session.query(Experiment).filter_by(id=member.id).one()
    assert unchanged_member.parent_experiment_fk == parent.id
    assert unchanged_member.experiment_id == "SERUM_040a"


def test_patch_rename_dash0_parent_with_replicates_returns_409(client, db_session):
    """Regression (review gap): a group parent spelled '-0' shares its lettered
    members' base_experiment_id via the BARE STEM, not its own literal id
    string. The guard must resolve the canonical stem before querying members
    so this spelling is blocked too, not just the bare-stem parent case."""
    parent = _make_experiment(db_session, "SERUM_040-0", 9059)
    member_a = _make_experiment(db_session, "SERUM_040a", 9060)
    member_b = _make_experiment(db_session, "SERUM_040b", 9061)
    db_session.expire_all()
    member_a = db_session.query(Experiment).filter_by(id=member_a.id).one()
    member_b = db_session.query(Experiment).filter_by(id=member_b.id).one()
    assert member_a.parent_experiment_fk == parent.id  # sanity: lineage set on create
    assert member_b.parent_experiment_fk == parent.id

    resp = client.patch("/api/experiments/SERUM_040-0", json={"experiment_id": "SERUM_050"})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "SERUM_040a" in detail
    assert "SERUM_040b" in detail

    db_session.expire_all()
    unchanged_parent = db_session.query(Experiment).filter_by(id=parent.id).one()
    assert unchanged_parent.experiment_id == "SERUM_040-0"
    unchanged_a = db_session.query(Experiment).filter_by(id=member_a.id).one()
    assert unchanged_a.parent_experiment_fk == parent.id
    assert unchanged_a.experiment_id == "SERUM_040a"


def test_patch_rename_lettered_member_not_blocked_by_parent_guard(client, db_session):
    """Regression: renaming a LETTERED MEMBER (not the parent) must never be
    blocked by the group-parent guard, even though its base_experiment_id
    equals the parent's stem — the guard must gate on the OLD id itself being
    a parent spelling, not merely on shared base_experiment_id."""
    parent = _make_experiment(db_session, "SERUM_070", 9062)
    _make_experiment(db_session, "SERUM_070b", 9063)
    _make_experiment(db_session, "SERUM_070c", 9064)

    resp = client.patch("/api/experiments/SERUM_070b", json={"experiment_id": "SERUM_070z"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["replicate_label"] == "z"
    assert body["base_experiment_id"] == "SERUM_070"
    assert body["parent_experiment_fk"] == parent.id


def test_patch_rename_sequential_derivation_not_blocked_by_parent_guard(client, db_session):
    """Regression: renaming a SEQUENTIAL re-run (e.g. SERUM_070-2) of a stem
    that has lettered members must never be blocked — it is not a group
    parent and the guard must not treat it as one."""
    _make_experiment(db_session, "SERUM_080", 9065)
    _make_experiment(db_session, "SERUM_080a", 9066)
    _make_experiment(db_session, "SERUM_080-2", 9067)

    resp = client.patch("/api/experiments/SERUM_080-2", json={"experiment_id": "SERUM_080-3"})
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == "SERUM_080-3"


def test_patch_rename_to_parent_spelling_backlinks_orphans(client, db_session):
    """Renaming an unrelated experiment INTO a group-parent spelling must
    back-link any pre-existing orphaned lettered derivations of that stem."""
    orphan_a = _make_experiment(db_session, "SERUM_060a", 9056)
    orphan_b = _make_experiment(db_session, "SERUM_060b", 9057)
    db_session.expire_all()
    orphan_a = db_session.query(Experiment).filter_by(id=orphan_a.id).one()
    orphan_b = db_session.query(Experiment).filter_by(id=orphan_b.id).one()
    assert orphan_a.parent_experiment_fk is None
    assert orphan_b.parent_experiment_fk is None

    _make_experiment(db_session, "STAGE_060", 9058)
    resp = client.patch("/api/experiments/STAGE_060", json={"experiment_id": "SERUM_060"})
    assert resp.status_code == 200

    db_session.expire_all()
    new_parent = db_session.query(Experiment).filter_by(experiment_id="SERUM_060").one()
    a = db_session.query(Experiment).filter_by(id=orphan_a.id).one()
    b = db_session.query(Experiment).filter_by(id=orphan_b.id).one()
    assert a.parent_experiment_fk == new_parent.id
    assert b.parent_experiment_fk == new_parent.id


def test_patch_experiment_date(client, db_session):
    """PATCH with a valid ISO date string updates the experiment's date field."""
    _make_experiment(db_session, "DATE_PATCH_001", 9020)
    resp = client.patch(
        "/api/experiments/DATE_PATCH_001",
        json={"date": "2026-03-15T00:00:00"},
    )
    assert resp.status_code == 200
    assert resp.json()["date"] is not None
    assert "2026-03-15" in resp.json()["date"]


def test_patch_experiment_date_invalid(client, db_session):
    """PATCH with a non-datetime string returns 422."""
    _make_experiment(db_session, "DATE_INVALID_001", 9021)
    resp = client.patch(
        "/api/experiments/DATE_INVALID_001",
        json={"date": "not-a-date"},
    )
    assert resp.status_code == 422


def test_patch_date_logs_modification(client, db_session):
    """Patching date writes a ModificationsLog row with old and new values."""
    from database.models.experiments import ModificationsLog
    exp = _make_experiment(db_session, "DATE_LOG_001", 9022)
    old_date = "2026-01-01T00:00:00"
    new_date = "2026-03-15T00:00:00"

    # Set an initial date so old_values is non-null
    client.patch(f"/api/experiments/{exp.experiment_id}", json={"date": old_date})
    db_session.expire_all()

    client.patch(f"/api/experiments/{exp.experiment_id}", json={"date": new_date})
    db_session.expire_all()

    log_entry = (
        db_session.query(ModificationsLog)
        .filter(
            ModificationsLog.experiment_id == "DATE_LOG_001",
            ModificationsLog.modified_table == "experiments",
        )
        .order_by(ModificationsLog.id.desc())
        .first()
    )
    assert log_entry is not None
    assert log_entry.modification_type == "update"
    assert log_entry.new_values is not None
    assert "date" in log_entry.new_values
    assert "2026-03-15" in log_entry.new_values["date"]


# --- Change Requests endpoint tests ---

def _make_change_request(db_session, experiment_id, reactor_label, sync_date, notion_status="Pending", carried_forward=False):
    from database.models.notion_sync import ReactorChangeRequest
    row = ReactorChangeRequest(
        reactor_label=reactor_label,
        experiment_id=experiment_id,
        requested_change=f"Check {reactor_label}",
        notion_status=notion_status,
        carried_forward=carried_forward,
        sync_date=sync_date,
        notion_page_id="a" * 32,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_get_change_requests_returns_list(client, db_session):
    from datetime import date
    _make_experiment(db_session, "CR_TEST_001", 9801)
    _make_change_request(db_session, "CR_TEST_001", "R05", date(2026, 4, 1))
    _make_change_request(db_session, "CR_TEST_001", "R05", date(2026, 4, 2))
    db_session.commit()

    resp = client.get("/api/experiments/CR_TEST_001/change-requests")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["sync_date"] == "2026-04-02"
    assert data[1]["sync_date"] == "2026-04-01"
    assert "reactor_label" in data[0]
    assert "requested_change" in data[0]
    assert "notion_status" in data[0]
    assert "carried_forward" in data[0]
    assert "notion_page_id" not in data[0]


def test_get_change_requests_returns_empty_list(client, db_session):
    _make_experiment(db_session, "CR_EMPTY_001", 9802)
    db_session.commit()
    resp = client.get("/api/experiments/CR_EMPTY_001/change-requests")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_change_requests_requires_auth(db_session):
    """Unauthenticated request returns 401."""
    from fastapi.testclient import TestClient
    from backend.api.main import app as _app
    from backend.api.dependencies.db import get_db
    _app.dependency_overrides.clear()
    def override_get_db():
        yield db_session
    _app.dependency_overrides[get_db] = override_get_db
    with TestClient(_app) as unauthed:
        resp = unauthed.get("/api/experiments/ANY_001/change-requests")
    assert resp.status_code == 401
    _app.dependency_overrides.clear()


def test_get_change_requests_experiment_not_found(client):
    """Nonexistent experiment returns 404, not 200 []."""
    resp = client.get("/api/experiments/NONEXISTENT_999/change-requests")
    assert resp.status_code == 404


# ============================================================
# Issue #57: Change sample_id on existing experiment
# ============================================================

def _make_sample(db, sample_id: str):
    """Create a minimal SampleInfo row."""
    from database.models.samples import SampleInfo
    s = SampleInfo(sample_id=sample_id)
    db.add(s)
    db.flush()
    return s


def test_patch_sample_id_to_valid_sample(client, db_session):
    """PATCH with a valid sample_id updates the field and returns 200."""
    _make_sample(db_session, "SAMPLE_VALID_001")
    _make_experiment(db_session, "SAMPLETEST_001", 9700)
    db_session.commit()

    resp = client.patch(
        "/api/experiments/SAMPLETEST_001",
        json={"sample_id": "SAMPLE_VALID_001"},
    )
    assert resp.status_code == 200
    assert resp.json()["sample_id"] == "SAMPLE_VALID_001"


def test_patch_sample_id_nonexistent_returns_404(client, db_session):
    """PATCH with a sample_id that does not exist in SampleInfo returns 404."""
    _make_experiment(db_session, "SAMPLETEST_002", 9701)
    db_session.commit()

    resp = client.patch(
        "/api/experiments/SAMPLETEST_002",
        json={"sample_id": "GHOST_SAMPLE_XYZ"},
    )
    assert resp.status_code == 404
    assert "GHOST_SAMPLE_XYZ" in resp.json()["detail"]


def test_patch_sample_id_no_conditions_no_crash(client, db_session):
    """Experiment with no conditions row: PATCH sample_id succeeds, no crash."""
    _make_sample(db_session, "SAMPLE_NOCOND_001")
    _make_experiment(db_session, "SAMPLETEST_003", 9702)
    db_session.commit()

    resp = client.patch(
        "/api/experiments/SAMPLETEST_003",
        json={"sample_id": "SAMPLE_NOCOND_001"},
    )
    assert resp.status_code == 200
    assert resp.json()["sample_id"] == "SAMPLE_NOCOND_001"


def test_patch_sample_id_calls_recalculate_on_conditions(client, db_session):
    """recalculate is called with the ExperimentalConditions instance."""
    from unittest.mock import patch as mock_patch
    from database.models.conditions import ExperimentalConditions

    _make_sample(db_session, "SAMPLE_COND_001")
    exp = _make_experiment(db_session, "SAMPLETEST_004", 9703)
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=exp.experiment_id,
        rock_mass_g=100.0,
    )
    db_session.add(cond)
    db_session.commit()

    with mock_patch("backend.api.routers.experiments.recalculate") as mock_recalc:
        resp = client.patch(
            "/api/experiments/SAMPLETEST_004",
            json={"sample_id": "SAMPLE_COND_001"},
        )

    assert resp.status_code == 200
    called_types = [type(call_args[0][0]) for call_args in mock_recalc.call_args_list]
    assert ExperimentalConditions in called_types


def test_patch_sample_id_calls_recalculate_on_scalars(client, db_session):
    """recalculate is called with each ScalarResults instance."""
    from unittest.mock import patch as mock_patch
    from database.models.conditions import ExperimentalConditions
    from database.models.results import ExperimentalResults, ScalarResults

    _make_sample(db_session, "SAMPLE_SCALAR_001")
    exp = _make_experiment(db_session, "SAMPLETEST_005", 9704)
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=exp.experiment_id,
    )
    db_session.add(cond)
    db_session.flush()
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=1.0,
        time_post_reaction_bucket_days=1.0,
        cumulative_time_post_reaction_days=1.0,
        is_primary_timepoint_result=True,
        description="T1",
    )
    db_session.add(result)
    db_session.flush()
    scalar = ScalarResults(result_id=result.id)
    db_session.add(scalar)
    db_session.commit()

    with mock_patch("backend.api.routers.experiments.recalculate") as mock_recalc:
        resp = client.patch(
            "/api/experiments/SAMPLETEST_005",
            json={"sample_id": "SAMPLE_SCALAR_001"},
        )

    assert resp.status_code == 200
    called_types = [type(call_args[0][0]) for call_args in mock_recalc.call_args_list]
    assert ScalarResults in called_types


def test_patch_sample_id_logs_modification(client, db_session):
    """Changing sample_id writes a ModificationsLog entry."""
    from database.models.experiments import ModificationsLog
    from sqlalchemy import select as sa_select

    _make_sample(db_session, "OLD_SAMPLE")
    _make_sample(db_session, "SAMPLE_LOG_001")
    exp = _make_experiment(db_session, "SAMPLETEST_006", 9705)
    exp.sample_id = "OLD_SAMPLE"
    db_session.commit()

    client.patch(
        "/api/experiments/SAMPLETEST_006",
        json={"sample_id": "SAMPLE_LOG_001"},
    )

    log = db_session.execute(
        sa_select(ModificationsLog)
        .where(ModificationsLog.experiment_id == "SAMPLETEST_006")
        .where(ModificationsLog.modified_table == "experiments")
        .order_by(ModificationsLog.id.desc())
    ).scalar_one_or_none()
    assert log is not None
    assert log.old_values == {"sample_id": "OLD_SAMPLE"}
    assert log.new_values == {"sample_id": "SAMPLE_LOG_001"}


def test_create_experiment_duplicate_replicate_id_fails(client, db_session):
    _make_experiment(db_session, "DUP_REP_001a", 8100)
    payload = {"experiment_id": "DUP_REP_001a", "experiment_number": 8101}
    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 409


def test_create_replicate_experiment_sets_lineage(client, db_session):
    _make_experiment(db_session, "LINE_REP_001", 8102)
    payload = {"experiment_id": "LINE_REP_001a", "experiment_number": 8103}
    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 201

    created = db_session.query(Experiment).filter_by(experiment_id="LINE_REP_001a").first()
    parent = db_session.query(Experiment).filter_by(experiment_id="LINE_REP_001").first()
    assert created.base_experiment_id == "LINE_REP_001"
    assert created.replicate_label == "a"
    assert created.parent_experiment_fk == parent.id


class TestReplicateFieldsExposed:
    def test_list_items_include_replicate_lineage_fields(self, client, db_session):
        parent = _make_experiment(db_session, experiment_id="RFLD_001", number=9700)
        db_session.add(Experiment(experiment_id="RFLD_001a", experiment_number=9701,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?search=RFLD_001")
        assert resp.status_code == 200
        by_id = {i["experiment_id"]: i for i in resp.json()["items"]}
        member = by_id["RFLD_001a"]
        assert member["replicate_label"] == "a"
        assert member["base_experiment_id"] == "RFLD_001"
        assert member["parent_experiment_fk"] == parent.id
        assert by_id["RFLD_001"]["replicate_label"] is None

    def test_detail_includes_replicate_label(self, client, db_session):
        _make_experiment(db_session, experiment_id="RFLD_002", number=9702)
        db_session.add(Experiment(experiment_id="RFLD_002a", experiment_number=9703,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments/RFLD_002a")
        assert resp.status_code == 200
        assert resp.json()["replicate_label"] == "a"


class TestGroupedListMode:
    def _make_set(self, db):
        parent = _make_experiment(db, experiment_id="GRP_001", number=9710)
        for i, letter in enumerate("abc"):
            db.add(Experiment(experiment_id=f"GRP_001{letter}", experiment_number=9711 + i,
                              status=ExperimentStatus.ONGOING))
        db.commit()
        return parent

    def test_grouped_collapses_lettered_set(self, client, db_session):
        self._make_set(db_session)
        resp = client.get("/api/experiments?group_replicates=true&search=GRP_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        (item,) = data["items"]
        assert item["experiment_id"] == "GRP_001"
        assert [r["replicate_label"] for r in item["replicates"]] == ["a", "b", "c"]

    def test_flat_mode_unchanged(self, client, db_session):
        self._make_set(db_session)
        resp = client.get("/api/experiments?search=GRP_001")
        assert resp.json()["total"] == 4
        assert all(i.get("replicates") is None for i in resp.json()["items"])

    def test_filter_matching_only_member_pulls_group(self, client, db_session):
        self._make_set(db_session)
        resp = client.get("/api/experiments?group_replicates=true&search=GRP_001b")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["experiment_id"] == "GRP_001"
        assert len(data["items"][0]["replicates"]) == 3

    def test_orphan_member_stays_top_level(self, client, db_session):
        db_session.add(Experiment(experiment_id="GRP_ORPH_001a", experiment_number=9720,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=GRP_ORPH_001a")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["experiment_id"] == "GRP_ORPH_001a"
        assert data["items"][0]["replicates"] is None

    def test_sequential_derivation_stays_flat_in_grouped_mode(self, client, db_session):
        _make_experiment(db_session, experiment_id="GRPSEQ_001", number=9730)
        db_session.add(Experiment(experiment_id="GRPSEQ_001-2", experiment_number=9731,
                                  status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=GRPSEQ_001")
        assert resp.json()["total"] == 2  # base and -2 are separate top-level rows

    def test_grouped_pagination_counts_groups(self, client, db_session):
        self._make_set(db_session)                                    # 1 group
        _make_experiment(db_session, experiment_id="GRP_SOLO_001", number=9740)  # 1 flat
        resp = client.get("/api/experiments?group_replicates=true&search=GRP_&limit=1")
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 1

    def test_orphan_lettered_set_collapses_to_one_row(self, client, db_session):
        """No parent row exists for GRP_ORPHSET_001 -- a/b/c must still
        collapse into one bucket (issue #87 D2 core fix), represented by the
        lowest-ordered member ("a"), with the remaining members ("b", "c")
        attached as replicates."""
        for i, letter in enumerate("abc"):
            db_session.add(Experiment(
                experiment_id=f"GRP_ORPHSET_001{letter}", experiment_number=9721 + i,
                status=ExperimentStatus.ONGOING,
            ))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=GRP_ORPHSET_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        (item,) = data["items"]
        assert item["experiment_id"] == "GRP_ORPHSET_001a"
        assert [r["replicate_label"] for r in item["replicates"]] == ["b", "c"]

    def test_timepoint_variant_shares_letter_no_dedupe(self, client, db_session):
        """A '-t<days>' vial shares its letter with its parent vial. Grouping
        must not dedupe by replicate_label -- both rows attach as separate
        replicates, identified by id."""
        _make_experiment(db_session, experiment_id="GRPT_001", number=9730)
        db_session.add(Experiment(experiment_id="GRPT_001a", experiment_number=9731,
                                   status=ExperimentStatus.ONGOING))
        db_session.add(Experiment(experiment_id="GRPT_001a-t7", experiment_number=9732,
                                   status=ExperimentStatus.ONGOING))
        db_session.commit()
        resp = client.get("/api/experiments?group_replicates=true&search=GRPT_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["experiment_id"] == "GRPT_001"
        replicate_ids = {r["experiment_id"] for r in item["replicates"]}
        assert replicate_ids == {"GRPT_001a", "GRPT_001a-t7"}
        assert [r["replicate_label"] for r in item["replicates"]] == ["a", "a"]

    def test_standalone_experiment_has_no_replicates(self, client, db_session):
        _make_experiment(db_session, experiment_id="GRP_STANDALONE_001", number=9745)
        resp = client.get("/api/experiments?group_replicates=true&search=GRP_STANDALONE_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0].get("replicates") is None

    def test_sequential_rerun_not_absorbed_into_coexisting_orphan_group(self, client, db_session):
        """The trap (brief TDD item 3): a naive COALESCE(base_experiment_id,
        experiment_id) bucket key applied uniformly would wrongly pull a
        sequential re-run (base_experiment_id == the stem, but
        replicate_label IS NULL) into a co-existing orphan lettered group
        that shares the same stem. GRPMIX_001a/b/c (orphan, no parent row)
        and GRPMIX_001-2 (sequential re-run) must remain two separate
        top-level buckets."""
        for i, letter in enumerate("abc"):
            db_session.add(Experiment(
                experiment_id=f"GRPMIX_001{letter}", experiment_number=9726 + i,
                status=ExperimentStatus.ONGOING,
            ))
        db_session.add(Experiment(experiment_id="GRPMIX_001-2", experiment_number=9729,
                                   status=ExperimentStatus.ONGOING))
        db_session.commit()

        resp = client.get("/api/experiments?group_replicates=true&search=GRPMIX_001")
        assert resp.status_code == 200
        data = resp.json()

        top_level_ids = {i["experiment_id"] for i in data["items"]}
        assert top_level_ids == {"GRPMIX_001a", "GRPMIX_001-2"}
        assert "GRPMIX_001b" not in top_level_ids
        assert "GRPMIX_001c" not in top_level_ids

        by_id = {i["experiment_id"]: i for i in data["items"]}

        group_item = by_id["GRPMIX_001a"]
        assert {r["experiment_id"] for r in group_item["replicates"]} == {
            "GRPMIX_001b", "GRPMIX_001c",
        }

        seq_item = by_id["GRPMIX_001-2"]
        assert seq_item.get("replicates") is None


class TestCreateReplicatesEndpoint:
    def test_create_replicates_batch(self, client, db_session):
        _make_experiment(db_session, experiment_id="CRE_001", number=9850)
        db_session.commit()
        resp = client.post("/api/experiments/replicates",
                           json={"base_experiment_id": "CRE_001", "count": 3})
        assert resp.status_code == 201
        data = resp.json()
        assert [e["experiment_id"] for e in data["created"]] == ["CRE_001a", "CRE_001b", "CRE_001c"]
        assert all(e["replicate_label"] in ("a", "b", "c") for e in data["created"])
        assert data["skipped"] == []

    def test_create_replicates_404_without_parent(self, client, db_session):
        resp = client.post("/api/experiments/replicates",
                           json={"base_experiment_id": "CRE_MISSING_001", "count": 3})
        assert resp.status_code == 404

    def test_create_replicates_count_bounds(self, client, db_session):
        _make_experiment(db_session, experiment_id="CRE_002", number=9860)
        db_session.commit()
        assert client.post("/api/experiments/replicates",
                           json={"base_experiment_id": "CRE_002", "count": 0}).status_code == 422
        assert client.post("/api/experiments/replicates",
                           json={"base_experiment_id": "CRE_002", "count": 26}).status_code == 422


from sqlalchemy import select as sa_select
from database.models import ModificationsLog


class TestOutlierFlagPatch:
    def _mk(self, db_session, exp_id, number):
        from database.models.enums import ExperimentStatus
        exp = Experiment(experiment_id=exp_id, experiment_number=number,
                         status=ExperimentStatus.ONGOING)
        db_session.add(exp)
        db_session.commit()
        return exp

    def test_patch_sets_and_clears_is_outlier(self, client, db_session):
        self._mk(db_session, "OUTL_API_001a", 920001)
        resp = client.patch("/api/experiments/OUTL_API_001a", json={"is_outlier": True})
        assert resp.status_code == 200
        assert resp.json()["is_outlier"] is True

        resp = client.patch("/api/experiments/OUTL_API_001a", json={"is_outlier": False})
        assert resp.status_code == 200
        assert resp.json()["is_outlier"] is False

    def test_get_detail_includes_is_outlier(self, client, db_session):
        self._mk(db_session, "OUTL_API_002a", 920002)
        client.patch("/api/experiments/OUTL_API_002a", json={"is_outlier": True})
        data = client.get("/api/experiments/OUTL_API_002a").json()
        assert data["is_outlier"] is True

    def test_patch_is_outlier_writes_modifications_log(self, client, db_session):
        exp = self._mk(db_session, "OUTL_API_003a", 920003)
        client.patch("/api/experiments/OUTL_API_003a", json={"is_outlier": True})
        db_session.expire_all()
        logs = db_session.execute(
            sa_select(ModificationsLog).where(ModificationsLog.experiment_fk == exp.id)
        ).scalars().all()
        assert any(
            l.new_values == {"is_outlier": True} and l.old_values == {"is_outlier": False}
            for l in logs
        )

    def test_list_items_include_is_outlier(self, client, db_session):
        self._mk(db_session, "OUTL_API_004a", 920004)
        client.patch("/api/experiments/OUTL_API_004a", json={"is_outlier": True})
        data = client.get("/api/experiments", params={"search": "OUTL_API_004a"}).json()
        assert data["items"][0]["is_outlier"] is True

    def test_patch_is_outlier_explicit_null_is_422(self, client, db_session):
        self._mk(db_session, "OUTL_API_005a", 920005)
        resp = client.patch("/api/experiments/OUTL_API_005a", json={"is_outlier": None})
        assert resp.status_code == 422

    def test_patch_is_outlier_noop_writes_no_audit_row(self, client, db_session):
        exp = self._mk(db_session, "OUTL_API_006a", 920006)
        client.patch("/api/experiments/OUTL_API_006a", json={"is_outlier": False})  # already False
        db_session.expire_all()
        logs = db_session.execute(
            sa_select(ModificationsLog).where(ModificationsLog.experiment_fk == exp.id)
        ).scalars().all()
        assert not any(
            l.old_values is not None and "is_outlier" in (l.old_values or {}) for l in logs
        )


def test_id_timepoint_days_in_responses(client, db_session):
    exp = Experiment(experiment_id="SERUM_074a-t7", experiment_number=6074, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.commit()  # before_flush sets id_timepoint_days = 7.0
    detail = client.get(f"/api/experiments/{exp.experiment_id}")
    assert detail.status_code == 200
    assert detail.json()["id_timepoint_days"] == 7.0
    listing = client.get("/api/experiments")
    item = next(i for i in listing.json()["items"] if i["experiment_id"] == "SERUM_074a-t7")
    assert item["id_timepoint_days"] == 7.0
