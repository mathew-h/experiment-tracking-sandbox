"""Tests for background ammonium default (0.2 mM) and bulk-apply endpoint.

Plan ref: docs/superpowers/plans/2026-03-25-background-ammonium-default.md
"""
from __future__ import annotations

import backend.services.calculations  # noqa: F401 — registers @register decorators
from database.models.experiments import Experiment
from database.models.conditions import ExperimentalConditions
from database.models.results import ExperimentalResults, ScalarResults
from database.models.enums import ExperimentStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_experiment(db, exp_id="BGNH4_001", number=7001):
    exp = Experiment(experiment_id=exp_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _make_conditions(db, exp, rock_g=100.0, water_ml=500.0):
    cond = ExperimentalConditions(
        experiment_id=exp.experiment_id,
        experiment_fk=exp.id,
        rock_mass_g=rock_g,
        water_volume_mL=water_ml,
    )
    db.add(cond)
    db.flush()
    return cond


def _make_scalar(db, exp, time_days=7.0, gross_mM=10.0, background_mM=0.2):
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=time_days,
        time_post_reaction_bucket_days=time_days,
        description=f"t={time_days}d",
        is_primary_timepoint_result=True,
    )
    db.add(result)
    db.flush()
    scalar = ScalarResults(
        result_id=result.id,
        gross_ammonium_concentration_mM=gross_mM,
        background_ammonium_concentration_mM=background_mM,
        sampling_volume_mL=100.0,
    )
    db.add(scalar)
    db.flush()
    return scalar


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_set_background_ammonium_404_unknown_experiment(client):
    """PATCH on a non-existent experiment_id returns 404."""
    resp = client.patch(
        "/api/experiments/DOES_NOT_EXIST/background-ammonium",
        json={"value": 0.5},
    )
    assert resp.status_code == 404


def test_set_background_ammonium_no_scalars_returns_zero(client, db_session):
    """Experiment with no scalar results returns updated=0."""
    exp = _make_experiment(db_session, "BGNH4_002", 7002)
    db_session.commit()
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/background-ammonium",
        json={"value": 0.5},
    )
    assert resp.status_code == 200
    assert resp.json() == {"updated": 0}


def test_set_background_ammonium_updates_all_scalars(client, db_session):
    """PATCH updates background_ammonium_concentration_mM on all scalar rows."""
    exp = _make_experiment(db_session, "BGNH4_003", 7003)
    _make_conditions(db_session, exp)
    s1 = _make_scalar(db_session, exp, time_days=7.0)
    s2 = _make_scalar(db_session, exp, time_days=14.0)
    s3 = _make_scalar(db_session, exp, time_days=28.0)
    db_session.commit()

    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/background-ammonium",
        json={"value": 0.5},
    )
    assert resp.status_code == 200
    assert resp.json() == {"updated": 3}

    # Re-fetch from DB and verify
    db_session.expire_all()
    for scalar_id in (s1.id, s2.id, s3.id):
        from sqlalchemy import select
        s = db_session.execute(
            select(ScalarResults).where(ScalarResults.id == scalar_id)
        ).scalar_one()
        assert s.background_ammonium_concentration_mM == 0.5


def test_set_background_ammonium_triggers_recalculation(client, db_session):
    """Changing background ammonium recalculates grams_per_ton_yield."""
    exp = _make_experiment(db_session, "BGNH4_004", 7004)
    _make_conditions(db_session, exp, rock_g=100.0, water_ml=500.0)
    scalar = _make_scalar(db_session, exp, time_days=7.0, gross_mM=10.0, background_mM=0.2)
    db_session.commit()

    # Trigger a recalculation to establish initial yield value
    client.patch(
        f"/api/experiments/{exp.experiment_id}/background-ammonium",
        json={"value": 0.2},
    )
    db_session.expire_all()
    from sqlalchemy import select
    s_initial = db_session.execute(
        select(ScalarResults).where(ScalarResults.id == scalar.id)
    ).scalar_one()
    initial_yield = s_initial.grams_per_ton_yield

    # Now apply a large background change
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/background-ammonium",
        json={"value": 5.0},
    )
    assert resp.status_code == 200

    db_session.expire_all()
    s_after = db_session.execute(
        select(ScalarResults).where(ScalarResults.id == scalar.id)
    ).scalar_one()
    assert s_after.grams_per_ton_yield is not None
    assert s_after.grams_per_ton_yield != initial_yield


def test_set_background_ammonium_negative_value_rejected(client, db_session):
    """Negative background value fails Pydantic validation with 422."""
    exp = _make_experiment(db_session, "BGNH4_005", 7005)
    db_session.commit()
    resp = client.patch(
        f"/api/experiments/{exp.experiment_id}/background-ammonium",
        json={"value": -0.1},
    )
    assert resp.status_code == 422


def test_scalar_create_default_background_ammonium(client, db_session):
    """Creating a scalar without background_ammonium gets the 0.2 mM default."""
    exp = _make_experiment(db_session, "BGNH4_006", 7006)
    db_session.flush()
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=7.0,
        time_post_reaction_bucket_days=7.0,
        description="t=7d",
        is_primary_timepoint_result=True,
    )
    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)

    resp = client.post(
        "/api/results/scalar",
        json={
            "result_id": result.id,
            "gross_ammonium_concentration_mM": 5.0,
            "sampling_volume_mL": 100.0,
            # background_ammonium_concentration_mM intentionally omitted
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["background_ammonium_concentration_mM"] == 0.2
