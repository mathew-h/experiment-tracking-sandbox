"""M7 Dashboard API tests.

Covers:
- Schema validation for all new M7 types
- GET /api/dashboard/ — shape, auth, reactor card fields, performance
"""
from __future__ import annotations

import datetime
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser


# ---------------------------------------------------------------------------
# Extra fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def unauth_client(db_session):
    """Client with DB override but auth raises 401."""
    def override_get_db():
        yield db_session

    async def no_auth():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_firebase_token] = no_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Schema unit tests (no DB)
# ---------------------------------------------------------------------------

def test_dashboard_summary_schema():
    from backend.api.schemas.dashboard import DashboardSummary
    s = DashboardSummary(active_experiments=3, reactors_in_use=3, completed_this_month=1, pending_results=2)
    assert s.active_experiments == 3
    assert s.pending_results == 2


def test_reactor_card_data_schema_empty():
    from backend.api.schemas.dashboard import ReactorCardData
    r = ReactorCardData(reactor_number=5, reactor_label="R05")
    assert r.experiment_id is None
    assert r.description is None
    assert r.sample_id is None


def test_reactor_card_data_schema_occupied():
    from backend.api.schemas.dashboard import ReactorCardData
    r = ReactorCardData(
        reactor_number=1, reactor_label="R01",
        experiment_id="HPHT_MH_001",
        sample_id="SMP-001",
        description="Baseline serpentinization run",
        researcher="MH",
        days_running=14,
        temperature_c=200.0,
        experiment_type="HPHT",
    )
    assert r.description == "Baseline serpentinization run"
    assert r.sample_id == "SMP-001"
    assert r.reactor_label == "R01"


def test_gantt_entry_schema():
    from backend.api.schemas.dashboard import GanttEntry
    from database.models.enums import ExperimentStatus
    g = GanttEntry(
        experiment_id="HPHT_MH_001",
        experiment_db_id=1,
        status=ExperimentStatus.ONGOING,
        started_at=datetime.datetime.utcnow(),
        days_running=10,
    )
    assert g.experiment_id == "HPHT_MH_001"
    assert g.ended_at is None


def test_activity_entry_schema():
    from backend.api.schemas.dashboard import ActivityEntry
    a = ActivityEntry(
        id=1,
        modification_type="create",
        modified_table="experiments",
        created_at=datetime.datetime.utcnow(),
    )
    assert a.modification_type == "create"
    assert a.experiment_id is None


def test_dashboard_response_schema():
    from backend.api.schemas.dashboard import DashboardResponse, DashboardSummary
    resp = DashboardResponse(
        summary=DashboardSummary(
            active_experiments=0, reactors_in_use=0,
            completed_this_month=0, pending_results=0,
        ),
        reactors=[],
        timeline=[],
        recent_activity=[],
    )
    assert resp.summary.active_experiments == 0
    assert resp.reactors == []


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------

def test_get_dashboard_returns_200(client):
    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200


def test_get_dashboard_requires_auth(unauth_client):
    resp = unauth_client.get("/api/dashboard/")
    assert resp.status_code == 401


def test_get_dashboard_shape(client):
    resp = client.get("/api/dashboard/")
    data = resp.json()
    assert "summary" in data
    assert "reactors" in data
    assert "timeline" in data
    assert "recent_activity" in data
    s = data["summary"]
    for key in ("active_experiments", "reactors_in_use", "completed_this_month", "pending_results"):
        assert key in s, f"Missing summary key: {key}"


def test_get_dashboard_reactor_cards_have_label(client, db_session):
    """Any reactor cards returned must have reactor_label."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="DASH_LABEL_001",
        experiment_number=8801,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="DASH_LABEL_001",
        reactor_number=3,
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_number"]: c for c in resp.json()["reactors"]}
    assert 3 in cards
    assert cards[3]["reactor_label"] == "R03"


def test_get_dashboard_with_ongoing_experiment(client, db_session):
    """Occupied reactor card contains description, sample_id, researcher, days_running."""
    from database.models.experiments import Experiment, ExperimentNotes
    from database.models.conditions import ExperimentalConditions
    from database.models.samples import SampleInfo
    from database.models.enums import ExperimentStatus

    sample = SampleInfo(sample_id="SMP-DASH", rock_classification="Dunite")
    db_session.add(sample)
    db_session.flush()

    exp = Experiment(
        experiment_id="DASH_FULL_001",
        experiment_number=8802,
        sample_id="SMP-DASH",
        researcher="Test User",
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=5),
    )
    db_session.add(exp)
    db_session.flush()

    note = ExperimentNotes(
        experiment_id="DASH_FULL_001",
        experiment_fk=exp.id,
        note_text="Dashboard integration test description",
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(note)

    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="DASH_FULL_001",
        reactor_number=9,
        temperature_c=150.0,
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    data = resp.json()

    cards = {c["reactor_number"]: c for c in data["reactors"]}
    assert 9 in cards
    card = cards[9]
    assert card["experiment_id"] == "DASH_FULL_001"
    assert card["sample_id"] == "SMP-DASH"
    assert card["researcher"] == "Test User"
    assert card["description"] == "Dashboard integration test description"
    assert card["reactor_label"] == "R09"
    assert card["days_running"] is not None and card["days_running"] >= 4

    assert data["summary"]["active_experiments"] >= 1
    assert data["summary"]["reactors_in_use"] >= 1


def test_get_dashboard_timeline_entries_have_required_fields(client, db_session):
    """Timeline entries have experiment_id and status."""
    from database.models.experiments import Experiment
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="TIMELINE_TEST_001",
        experiment_number=8804,
        status=ExperimentStatus.COMPLETED,
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=10),
    )
    db_session.add(exp)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    timeline = resp.json()["timeline"]
    assert len(timeline) >= 1
    for entry in timeline:
        assert "experiment_id" in entry
        assert "status" in entry
        assert "experiment_db_id" in entry


def test_get_dashboard_activity_capped_at_20(client):
    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    assert len(resp.json()["recent_activity"]) <= 20


def test_get_dashboard_completed_this_month(client, db_session):
    """completed_this_month count includes experiments completed this month."""
    from database.models.experiments import Experiment
    from database.models.enums import ExperimentStatus

    now = datetime.datetime.utcnow()
    exp = Experiment(
        experiment_id="COMPLETED_MONTH_001",
        experiment_number=8805,
        status=ExperimentStatus.COMPLETED,
        created_at=now - datetime.timedelta(days=5),
        updated_at=now,
    )
    db_session.add(exp)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    assert resp.json()["summary"]["completed_this_month"] >= 1


# ---------------------------------------------------------------------------
# Reactor spec-merge tests (issue #2)
# ---------------------------------------------------------------------------

def test_reactor_specs_constant_coverage():
    """REACTOR_SPECS covers all 16 standard reactors with required keys."""
    from backend.api.routers.dashboard import REACTOR_SPECS
    assert len(REACTOR_SPECS) == 16
    for rn in range(1, 17):
        spec = REACTOR_SPECS[rn]
        assert "volume_mL" in spec
        assert "material" in spec
        assert "vendor" in spec


def test_reactor_specs_values():
    """Spot-check key spec values against the hardware inventory."""
    from backend.api.routers.dashboard import REACTOR_SPECS
    # R01–R03: Hastelloy, 100 mL, Yushen
    for rn in (1, 2, 3):
        assert REACTOR_SPECS[rn]["material"] == "Hastelloy"
        assert REACTOR_SPECS[rn]["volume_mL"] == 100
        assert REACTOR_SPECS[rn]["vendor"] == "Yushen"
    # R04: 300 mL Titanium, Tan
    assert REACTOR_SPECS[4]["volume_mL"] == 300
    assert REACTOR_SPECS[4]["material"] == "Titanium"
    assert REACTOR_SPECS[4]["vendor"] == "Tan"
    # R05–R07: 500 mL Titanium, Yushen
    for rn in (5, 6, 7):
        assert REACTOR_SPECS[rn]["volume_mL"] == 500
        assert REACTOR_SPECS[rn]["vendor"] == "Yushen"
    # R08–R09: 100 mL Titanium, Tan
    for rn in (8, 9):
        assert REACTOR_SPECS[rn]["vendor"] == "Tan"
    # R10–R16: 100 mL Titanium, Yushen
    for rn in range(10, 17):
        assert REACTOR_SPECS[rn]["volume_mL"] == 100
        assert REACTOR_SPECS[rn]["vendor"] == "Yushen"


def test_reactor_card_includes_specs(client, db_session):
    """Reactor cards returned by GET /api/dashboard/ include volume_mL, material, vendor."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="SPECS_TEST_001",
        experiment_number=8900,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="SPECS_TEST_001",
        reactor_number=5,  # R05: 500 mL, Titanium, Yushen
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_number"]: c for c in resp.json()["reactors"]}
    assert 5 in cards
    card = cards[5]
    assert card["volume_mL"] == 500
    assert card["material"] == "Titanium"
    assert card["vendor"] == "Yushen"


def test_reactor_card_data_schema_includes_specs():
    """ReactorCardData schema accepts and returns hardware spec fields."""
    from backend.api.schemas.dashboard import ReactorCardData
    card = ReactorCardData(
        reactor_number=4, reactor_label="R04",
        volume_mL=300, material="Titanium", vendor="Tan",
    )
    assert card.volume_mL == 300
    assert card.material == "Titanium"
    assert card.vendor == "Tan"


# ---------------------------------------------------------------------------
# CF slot label derivation tests (issue #26)
# ---------------------------------------------------------------------------

def test_core_flood_experiment_in_reactor_1_gets_cf01_label(client, db_session):
    """Core Flood experiment in reactor 1 must produce reactor_label = 'CF01'."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="CF_LABEL_R1_001",
        experiment_number=91001,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="CF_LABEL_R1_001",
        reactor_number=1,
        experiment_type="Core Flood",
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_number"]: c for c in resp.json()["reactors"]}
    assert 1 in cards, "reactor_number=1 not found in reactor cards"
    assert cards[1]["reactor_label"] == "CF01", (
        f"Expected CF01 but got {cards[1]['reactor_label']!r}. "
        "experiment_type='Core Flood' should produce label CF01."
    )
    assert cards[1]["experiment_id"] == "CF_LABEL_R1_001"


def test_core_flood_experiment_in_reactor_2_gets_cf02_label(client, db_session):
    """Core Flood experiment in reactor 2 must produce reactor_label = 'CF02'."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="CF_LABEL_R2_001",
        experiment_number=91002,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="CF_LABEL_R2_001",
        reactor_number=2,
        experiment_type="Core Flood",
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_number"]: c for c in resp.json()["reactors"]}
    assert 2 in cards, "reactor_number=2 not found in reactor cards"
    assert cards[2]["reactor_label"] == "CF02", (
        f"Expected CF02 but got {cards[2]['reactor_label']!r}."
    )
    assert cards[2]["experiment_id"] == "CF_LABEL_R2_001"


def test_hpht_experiment_in_reactor_1_gets_r01_not_cf01(client, db_session):
    """HPHT experiment in reactor 1 must produce reactor_label = 'R01', not CF01."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="HPHT_LABEL_R1_001",
        experiment_number=91003,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="HPHT_LABEL_R1_001",
        reactor_number=1,
        experiment_type="HPHT",
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_number"]: c for c in resp.json()["reactors"]}
    assert 1 in cards
    assert cards[1]["reactor_label"] == "R01", (
        f"Expected R01 but got {cards[1]['reactor_label']!r}. "
        "Non-Core Flood experiments must not be mapped to CF slots."
    )


def test_null_experiment_type_in_reactor_1_gets_r01_not_cf01(client, db_session):
    """Experiment with no experiment_type in reactor 1 falls back to R01, not CF01."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="NULL_TYPE_R1_001",
        experiment_number=91004,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="NULL_TYPE_R1_001",
        reactor_number=1,
        experiment_type=None,
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_number"]: c for c in resp.json()["reactors"]}
    assert 1 in cards
    assert cards[1]["reactor_label"] == "R01", (
        f"Expected R01 but got {cards[1]['reactor_label']!r}. "
        "NULL experiment_type should produce R-prefix label, not CF."
    )


# ---------------------------------------------------------------------------
# Performance test
# ---------------------------------------------------------------------------

def test_dashboard_performance_500_experiments(client, db_session):
    """Dashboard endpoint must respond under 1500ms with 500 experiments."""
    import random
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    statuses = [ExperimentStatus.ONGOING, ExperimentStatus.COMPLETED, ExperimentStatus.CANCELLED]
    exps = []
    for i in range(500):
        status = statuses[i % 3]
        exp = Experiment(
            experiment_id=f"PERF_{i:04d}",
            experiment_number=20000 + i,
            status=status,
            created_at=datetime.datetime.utcnow() - datetime.timedelta(days=random.randint(1, 365)),
        )
        exps.append(exp)
    db_session.add_all(exps)
    db_session.flush()

    conds = []
    for i, exp in enumerate(exps[:50]):
        cond = ExperimentalConditions(
            experiment_fk=exp.id,
            experiment_id=exp.experiment_id,
            reactor_number=(i % 16) + 1,
        )
        conds.append(cond)
    db_session.add_all(conds)
    db_session.commit()

    start = time.perf_counter()
    resp = client.get("/api/dashboard/")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert resp.status_code == 200
    assert elapsed_ms < 1500, f"Dashboard took {elapsed_ms:.0f}ms — exceeds 1500ms threshold"
