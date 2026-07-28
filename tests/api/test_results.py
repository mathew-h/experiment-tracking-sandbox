import pytest
from datetime import datetime, timezone

from database.models.experiments import Experiment
from database.models.results import ExperimentalResults, ScalarResults
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


# ── Issue #8: experiment_fk must be experiments.id (integer PK) ──────────────


def test_create_result_rejects_nonexistent_fk(client):
    """POST /api/results with an experiment_fk that has no matching row → 404.

    This catches the case where a developer accidentally passes a valid integer
    but one that references nothing (e.g. passes 1 when the actual PK is 42).
    """
    payload = {
        "experiment_fk": 999999,  # no experiment with this integer PK
        "description": "Should fail",
        "is_primary_timepoint_result": False,
    }
    resp = client.post("/api/results", json=payload)
    assert resp.status_code == 404
    # The error message should include the bad PK value to guide the caller
    assert "999999" in resp.json()["detail"]


def test_create_result_rejects_nonnumeric_string_fk(client):
    """POST /api/results with experiment_fk as a non-numeric string → 422.

    "HPHT_001" cannot be parsed as int even without strict mode, so this
    verifies the baseline rejection behavior.
    """
    payload = {
        "experiment_fk": "HPHT_001",  # the string experiment_id — wrong field
        "description": "Should fail",
    }
    resp = client.post("/api/results", json=payload)
    assert resp.status_code == 422


def test_create_result_rejects_numeric_string_fk(client):
    """POST /api/results with experiment_fk as a numeric string → 422.

    With ConfigDict(strict=True) on ResultCreate, "42" must be rejected (no coercion).
    Without strict=True this would return 201 — the test fails and tells you to add it.
    """
    payload = {
        "experiment_fk": "42",  # a numeric string — should be rejected by strict mode
        "description": "Should fail",
    }
    resp = client.post("/api/results", json=payload)
    assert resp.status_code == 422


def test_create_result_404_message_guides_caller(client):
    """404 detail message must mention 'experiment' and the bad PK value."""
    payload = {"experiment_fk": 888888, "description": "x"}
    resp = client.post("/api/results", json=payload)
    assert resp.status_code == 404
    detail = resp.json()["detail"].lower()
    assert "experiment" in detail
    assert "888888" in resp.json()["detail"]


def test_get_experiment_results_includes_scalar_measurement_date(client, db_session):
    """scalar_measurement_date is exposed in the results list endpoint."""
    exp, result = _seed(db_session)
    sample_date = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    scalar = ScalarResults(
        result_id=result.id,
        gross_ammonium_concentration_mM=1.0,
        measurement_date=sample_date,
    )
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["scalar_measurement_date"] is not None
    assert "2026-03-15" in data[0]["scalar_measurement_date"]


def test_scalar_results_has_xrd_run_date_field():
    """ScalarResults model must have an xrd_run_date column."""
    from database.models.results import ScalarResults
    assert hasattr(ScalarResults, 'xrd_run_date'), "xrd_run_date column missing from ScalarResults"



def test_results_endpoint_includes_ferrous_yield_columns(client, db_session):
    """GET /experiments/{id}/results returns ferrous_iron_yield_h2_pct and _nh3_pct."""
    exp, result = _seed(db_session)
    scalar = ScalarResults(
        result_id=result.id,
        ferrous_iron_yield_h2_pct=16.8,
        ferrous_iron_yield_nh3_pct=24.6,
    )
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["ferrous_iron_yield_h2_pct"] == pytest.approx(16.8)
    assert data[0]["ferrous_iron_yield_nh3_pct"] == pytest.approx(24.6)


def test_results_endpoint_includes_h2_concentration(client, db_session):
    """GET /experiments/{id}/results returns h2_concentration (ppm) per row (issue #90)."""
    exp, result = _seed(db_session)
    scalar = ScalarResults(
        result_id=result.id,
        h2_concentration=500.0,
    )
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["h2_concentration"] == pytest.approx(500.0)


def test_results_endpoint_h2_concentration_null_when_no_scalar(client, db_session):
    """h2_concentration is null in the response when the result has no scalar record (issue #90)."""
    exp, result = _seed(db_session)  # result created with no ScalarResults row
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["has_scalar"] is False
    assert data[0]["h2_concentration"] is None


def test_results_endpoint_includes_xrd_run_date(client, db_session):
    """GET /experiments/{id}/results returns xrd_run_date per row."""
    exp, result = _seed(db_session)
    scalar = ScalarResults(
        result_id=result.id,
        xrd_run_date=datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["xrd_run_date"] is not None
    assert "2026-04-15" in data[0]["xrd_run_date"]


def test_results_endpoint_xrd_run_date_null_when_absent(client, db_session):
    """xrd_run_date is null in the response when not set on the scalar row."""
    exp, result = _seed(db_session)
    scalar = ScalarResults(result_id=result.id, gross_ammonium_concentration_mM=1.0)
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["xrd_run_date"] is None


def test_results_endpoint_includes_nmr_icp_gc_run_dates(client, db_session):
    """GET /experiments/{id}/results returns nmr_run_date, icp_run_date, gc_run_date per row."""
    exp, result = _seed(db_session)
    scalar = ScalarResults(
        result_id=result.id,
        nmr_run_date=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        icp_run_date=datetime(2026, 4, 11, 9, 0, 0, tzinfo=timezone.utc),
        gc_run_date=datetime(2026, 4, 12, 9, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert "2026-04-10" in data[0]["nmr_run_date"]
    assert "2026-04-11" in data[0]["icp_run_date"]
    assert "2026-04-12" in data[0]["gc_run_date"]


def test_results_endpoint_nmr_icp_gc_run_dates_null_when_absent(client, db_session):
    """nmr_run_date/icp_run_date/gc_run_date are null in the response when not set on the scalar row."""
    exp, result = _seed(db_session)
    scalar = ScalarResults(result_id=result.id, gross_ammonium_concentration_mM=1.0)
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["nmr_run_date"] is None
    assert data[0]["icp_run_date"] is None
    assert data[0]["gc_run_date"] is None


def test_scalar_response_schema_includes_all_four_run_dates():
    """ScalarResponse (not just ResultWithFlagsResponse) now carries all four run-date fields."""
    from backend.api.schemas.results import ScalarResponse
    s = ScalarResponse(
        id=1, result_id=1,
        nmr_run_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        icp_run_date=datetime(2026, 4, 11, tzinfo=timezone.utc),
        gc_run_date=datetime(2026, 4, 12, tzinfo=timezone.utc),
        xrd_run_date=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    assert s.gc_run_date is not None


def test_scalar_update_schema_accepts_all_four_run_dates():
    """ScalarUpdate accepts all four run-date fields so a wrong one can be corrected via PATCH."""
    from backend.api.schemas.results import ScalarUpdate
    u = ScalarUpdate(
        nmr_run_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        icp_run_date=datetime(2026, 4, 11, tzinfo=timezone.utc),
        gc_run_date=datetime(2026, 4, 12, tzinfo=timezone.utc),
        xrd_run_date=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    assert u.icp_run_date is not None


# ── Issue #81: '-t<days>' ID timepoint is canonical on POST /api/results ─────


def _seed_timepoint_exp(db, experiment_id, number):
    exp = Experiment(experiment_id=experiment_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.commit()  # commit fires before_flush -> id_timepoint_days is populated
    db.refresh(exp)
    return exp


def test_create_result_omitted_time_filled_from_id(client, db_session):
    exp = _seed_timepoint_exp(db_session, "SERUM_070a-t7", 6070)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "auto-filled",
        "is_primary_timepoint_result": True,
    })
    assert resp.status_code == 201
    assert resp.json()["time_post_reaction_days"] == 7.0


def test_create_result_matching_time_accepted(client, db_session):
    exp = _seed_timepoint_exp(db_session, "SERUM_071a-t7", 6071)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "match",
        "time_post_reaction_days": 7.0,
        "is_primary_timepoint_result": True,
    })
    assert resp.status_code == 201


def test_create_result_conflicting_time_422(client, db_session):
    exp = _seed_timepoint_exp(db_session, "SERUM_072a-t7", 6072)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "conflict",
        "time_post_reaction_days": 3.0,
        "is_primary_timepoint_result": True,
    })
    assert resp.status_code == 422
    assert "canonical" in resp.json()["detail"]


def test_create_result_untimed_experiment_unaffected(client, db_session):
    exp = _seed_timepoint_exp(db_session, "SERUM_073a", 6073)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "free",
        "time_post_reaction_days": 3.0,
        "is_primary_timepoint_result": True,
    })
    assert resp.status_code == 201


# ── Issue #83: POST /api/results must set time_post_reaction_bucket_days ────


def test_create_result_sets_bucket_from_days(client, db_session):
    """The server derives the bucket from the resolved time (round to 4 dp)."""
    exp, _ = _seed(db_session)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "Day 7",
        "time_post_reaction_days": 7.0,
    })
    assert resp.status_code == 201
    assert resp.json()["time_post_reaction_bucket_days"] == pytest.approx(7.0)


def test_create_result_bucket_rounds_to_4_decimals(client, db_session):
    exp, _ = _seed(db_session)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "odd time",
        "time_post_reaction_days": 7.123456,
    })
    assert resp.status_code == 201
    bucket = resp.json()["time_post_reaction_bucket_days"]
    assert bucket == pytest.approx(7.1235)


def test_create_result_overrides_client_supplied_bucket(client, db_session):
    """The server owns the bucket; a client-sent value must be ignored."""
    exp, _ = _seed(db_session)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "lying client",
        "time_post_reaction_days": 7.0,
        "time_post_reaction_bucket_days": 99.0,
    })
    assert resp.status_code == 201
    assert resp.json()["time_post_reaction_bucket_days"] == pytest.approx(7.0)


def test_create_result_null_days_null_bucket(client, db_session):
    """No time and no ID token → bucket stays null (pre-#83 behavior)."""
    exp, _ = _seed(db_session)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "no time yet",
        "is_primary_timepoint_result": False,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["time_post_reaction_days"] is None
    assert body["time_post_reaction_bucket_days"] is None


def test_create_result_bucket_from_id_timepoint_token(client, db_session):
    """A '-t<days>' ID fills a blank time AND the bucket (issues #81 + #83)."""
    exp = Experiment(experiment_id="RES_T_001-t7", experiment_number=6002,
                     status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.commit()
    # sanity: lineage listener parsed the token
    assert exp.id_timepoint_days == 7.0
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "token vial",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["time_post_reaction_days"] == pytest.approx(7.0)
    assert body["time_post_reaction_bucket_days"] == pytest.approx(7.0)


def test_create_result_same_day_newest_wins(client, db_session):
    """A second primary entry at the same day demotes the first instead of
    500ing on uq_primary_result_per_experiment_bucket."""
    exp, first = _seed(db_session)  # first: day 0.0, bucket 0.0, primary
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "corrected day-0 entry",
        "time_post_reaction_days": 0.0,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["is_primary_timepoint_result"] is True
    db_session.expire_all()
    old = db_session.get(ExperimentalResults, first.id)
    assert old.is_primary_timepoint_result is False


def test_create_result_nonprimary_leaves_existing_primary(client, db_session):
    exp, first = _seed(db_session)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "extra vial draw",
        "time_post_reaction_days": 0.0,
        "is_primary_timepoint_result": False,
    })
    assert resp.status_code == 201
    db_session.expire_all()
    old = db_session.get(ExperimentalResults, first.id)
    assert old.is_primary_timepoint_result is True
