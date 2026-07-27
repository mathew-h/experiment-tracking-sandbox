"""Tests for QUEUED ExperimentStatus (issue #33)."""
from __future__ import annotations

import datetime

import pytest

from database.models.experiments import Experiment
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus


def test_experiment_status_queued_enum_value():
    """ExperimentStatus('QUEUED') must not raise."""
    status = ExperimentStatus("QUEUED")
    assert status == ExperimentStatus.QUEUED
    assert status.value == "QUEUED"


def test_dashboard_active_count_excludes_queued(client, db_session):
    """Active Experiments metric counts ONGOING only — QUEUED must not inflate it.

    Both experiments are given a reactor_number (in the 1-16 HPHT range, isolated
    to this test's own transaction) and experiment_type="HPHT" so they actually
    land in reactor_cards and are counted by the new reactors.ongoing/queued
    occupancy tallies (see backend/api/routers/dashboard.py::_occupancy) —
    without ExperimentalConditions, neither experiment would appear in the
    reactor grid at all.
    """
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
    db_session.flush()
    db_session.add_all([
        ExperimentalConditions(
            experiment_fk=ongoing.id,
            experiment_id="QUEUED_TEST_ONGOING",
            reactor_number=10,
            experiment_type="HPHT",
        ),
        ExperimentalConditions(
            experiment_fk=queued.id,
            experiment_id="QUEUED_TEST_QUEUED",
            reactor_number=11,
            experiment_type="HPHT",
        ),
    ])
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    # This test's transaction is isolated (savepoint rollback per test — see
    # tests/api/conftest.py), so exactly the one ONGOING experiment above
    # contributes to reactors.ongoing.
    assert summary["reactors"]["ongoing"] == 1
    assert summary["reactors"]["queued"] == 1
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
