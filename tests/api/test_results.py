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
