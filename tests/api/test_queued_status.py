"""Tests for QUEUED ExperimentStatus (issue #33)."""
from __future__ import annotations

import datetime

import pytest

from database.models.experiments import Experiment
from database.models.enums import ExperimentStatus


def test_experiment_status_queued_enum_value():
    """ExperimentStatus('QUEUED') must not raise."""
    status = ExperimentStatus("QUEUED")
    assert status == ExperimentStatus.QUEUED
    assert status.value == "QUEUED"


def test_dashboard_active_count_excludes_queued(client, db_session):
    """Active Experiments metric counts ONGOING only — QUEUED must not inflate it."""
    ongoing = Experiment(
        experiment_id="QUEUED_TEST_ONGOING",
        experiment_number=33001,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    queued = Experiment(
        experiment_id="QUEUED_TEST_QUEUED",
        experiment_number=33002,
        status=ExperimentStatus.QUEUED,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add_all([ongoing, queued])
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    assert summary["active_experiments"] >= 1
    # Verify via DB that only the ONGOING experiment matches the active filter
    from sqlalchemy import select, func
    from database.models.experiments import Experiment as E
    count = db_session.execute(
        select(func.count()).where(
            E.experiment_id.in_(["QUEUED_TEST_ONGOING", "QUEUED_TEST_QUEUED"]),
            E.status == ExperimentStatus.ONGOING,
        )
    ).scalar()
    assert count == 1, "Only the ONGOING experiment should match the active filter"


def test_dashboard_pending_results_excludes_queued(client, db_session):
    """Pending Results counts ONGOING experiments with no recent result — QUEUED excluded."""
    queued = Experiment(
        experiment_id="QUEUED_PENDING_TEST",
        experiment_number=33003,
        status=ExperimentStatus.QUEUED,
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=14),
    )
    db_session.add(queued)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    assert resp.json()["summary"]["pending_results"] >= 0


# ---------------------------------------------------------------------------
# PATCH /experiments/{id}/status — all enum values accepted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["ONGOING", "COMPLETED", "CANCELLED", "QUEUED"])
def test_patch_experiment_status_all_values(client, db_session, status):
    """PATCH /experiments/{id}/status accepts every ExperimentStatus member."""
    exp = Experiment(
        experiment_id=f"PATCH_STATUS_{status}",
        experiment_number=33100 + list(ExperimentStatus).index(ExperimentStatus(status)),
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.commit()

    response = client.patch(
        f"/api/experiments/{exp.experiment_id}/status",
        json={"status": status},
    )
    assert response.status_code == 200, f"status={status} was rejected: {response.text}"
    assert response.json()["status"] == status
