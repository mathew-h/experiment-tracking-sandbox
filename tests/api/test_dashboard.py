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
    from backend.api.schemas.dashboard import DashboardSummary, SlotOccupancy
    s = DashboardSummary(
        reactors=SlotOccupancy(total=16, ongoing=3, queued=1, empty=12),
        core_floods=SlotOccupancy(total=3, ongoing=1, queued=0, empty=2),
        gc_measurements_7wd=5,
        gc_experiments_7wd=3,
        serum_vials_started_7wd=4,
        serum_experiments_7wd=2,
        workday_window_start="2026-07-21",
        workday_window_end="2026-07-29",
    )
    assert s.reactors.ongoing == 3
    assert s.core_floods.total == 3
    assert s.gc_measurements_7wd == 5
    assert s.serum_experiments_7wd == 2


def test_slot_occupancy_schema_rejects_missing_fields():
    from backend.api.schemas.dashboard import SlotOccupancy
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SlotOccupancy(total=16, ongoing=3, queued=1)  # missing `empty`


def test_dashboard_summary_schema_rejects_removed_fields():
    """Constructing DashboardSummary with only the old field names fails —
    the new required fields (reactors, core_floods, etc.) are all missing."""
    from backend.api.schemas.dashboard import DashboardSummary
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DashboardSummary(
            active_experiments=3,
            reactors_in_use=3,
            completed_this_month=1,
            pending_results=2,
        )


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
    from backend.api.schemas.dashboard import DashboardResponse, DashboardSummary, SlotOccupancy
    resp = DashboardResponse(
        summary=DashboardSummary(
            reactors=SlotOccupancy(total=16, ongoing=0, queued=0, empty=16),
            core_floods=SlotOccupancy(total=3, ongoing=0, queued=0, empty=3),
            gc_measurements_7wd=0,
            gc_experiments_7wd=0,
            serum_vials_started_7wd=0,
            serum_experiments_7wd=0,
            workday_window_start="2026-07-21",
            workday_window_end="2026-07-29",
        ),
        reactors=[],
        timeline=[],
        recent_activity=[],
    )
    assert resp.summary.reactors.total == 16
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
        experiment_type="HPHT",
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
        experiment_type="HPHT",
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
    # R04–R06: 500 mL Titanium, Yushen
    for rn in (4, 5, 6):
        assert REACTOR_SPECS[rn]["volume_mL"] == 500
        assert REACTOR_SPECS[rn]["material"] == "Titanium"
        assert REACTOR_SPECS[rn]["vendor"] == "Yushen"
    # R07: 300 mL Titanium, Tan
    assert REACTOR_SPECS[7]["volume_mL"] == 300
    assert REACTOR_SPECS[7]["material"] == "Titanium"
    assert REACTOR_SPECS[7]["vendor"] == "Tan"
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
        experiment_type="HPHT",
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


def test_cf01_does_not_inherit_hpht_reactor_1_hardware_specs(client, db_session):
    """CF01 (Core Flood, reactor_number=1) must not show R01's Hastelloy/Yushen HPHT vessel spec.

    REACTOR_SPECS is keyed by bare reactor_number and only covers the R01-R16
    HPHT vessel inventory. CF01/CF02 reuse reactor_number 1/2, so the lookup
    must be skipped for Core Flood experiments.
    """
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="CF_SPEC_LEAK_001",
        experiment_number=91010,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="CF_SPEC_LEAK_001",
        reactor_number=1,
        experiment_type="Core Flood",
    )
    db_session.add(cond)
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert "CF01" in cards
    assert cards["CF01"]["volume_mL"] is None, "CF01 must not show R01's HPHT volume_mL"
    assert cards["CF01"]["material"] is None, "CF01 must not show R01's HPHT material (Hastelloy)"
    assert cards["CF01"]["vendor"] is None, "CF01 must not show R01's HPHT vendor (Yushen)"


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


def test_null_experiment_type_in_reactor_1_excluded_from_grid(client, db_session):
    """Experiment with no experiment_type is excluded from the reactor grid (issue #38)."""
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
    all_exp_ids = [c["experiment_id"] for c in resp.json()["reactors"]]
    assert "NULL_TYPE_R1_001" not in all_exp_ids, (
        "NULL experiment_type should be excluded from reactor grid; "
        "only HPHT and Core Flood experiments appear."
    )


def test_cf_and_hpht_in_same_reactor_number_each_get_own_slot(client, db_session):
    """
    Core Flood and HPHT experiments sharing the same reactor_number must each
    appear in their own dashboard slot (CF01 and R01 respectively), even when
    the HPHT experiment was created more recently.

    Regression test for the prod failure where HPHT_109 (created 2026-03-31,
    reactor_number=1) blocked CF-015 (Core Flood, reactor_number=1) from
    appearing in CF01 because the old dedup tracked reactor_number instead of
    reactor_label.
    """
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    older = datetime.datetime.utcnow() - datetime.timedelta(days=10)
    newer = datetime.datetime.utcnow()

    cf_exp = Experiment(
        experiment_id="CF_SLOT_TEST_001",
        experiment_number=91005,
        status=ExperimentStatus.ONGOING,
        created_at=older,
    )
    hpht_exp = Experiment(
        experiment_id="HPHT_SLOT_TEST_001",
        experiment_number=91006,
        status=ExperimentStatus.ONGOING,
        created_at=newer,
    )
    db_session.add_all([cf_exp, hpht_exp])
    db_session.flush()

    db_session.add(ExperimentalConditions(
        experiment_fk=cf_exp.id,
        experiment_id="CF_SLOT_TEST_001",
        reactor_number=1,
        experiment_type="Core Flood",
    ))
    db_session.add(ExperimentalConditions(
        experiment_fk=hpht_exp.id,
        experiment_id="HPHT_SLOT_TEST_001",
        reactor_number=1,
        experiment_type="HPHT",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}

    assert "CF01" in cards, "CF01 slot must be populated by the Core Flood experiment"
    assert cards["CF01"]["experiment_id"] == "CF_SLOT_TEST_001"

    assert "R01" in cards, "R01 slot must be populated by the HPHT experiment"
    assert cards["R01"]["experiment_id"] == "HPHT_SLOT_TEST_001"


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
            experiment_type="HPHT",
        )
        conds.append(cond)
    db_session.add_all(conds)
    db_session.commit()

    start = time.perf_counter()
    resp = client.get("/api/dashboard/")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert resp.status_code == 200
    assert elapsed_ms < 1500, f"Dashboard took {elapsed_ms:.0f}ms — exceeds 1500ms threshold"


def test_dashboard_started_at_reflects_patched_date(client, db_session):
    """After PATCHing Experiment.date, dashboard reactor card started_at reflects the new value."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    # Create experiment with reactor_number so it appears on dashboard
    exp = Experiment(
        experiment_id="DASH_DATE_001",
        experiment_number=7001,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()

    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="DASH_DATE_001",
        reactor_number=15,
        experiment_type="HPHT",
    )
    db_session.add(cond)
    db_session.commit()

    # Patch experiment date
    new_date = "2026-01-10T00:00:00"
    patch_resp = client.patch(
        "/api/experiments/DASH_DATE_001",
        json={"date": new_date},
    )
    assert patch_resp.status_code == 200

    # Dashboard should reflect Experiment.date in started_at, not created_at
    dash_resp = client.get("/api/dashboard/")
    assert dash_resp.status_code == 200
    reactors = dash_resp.json()["reactors"]
    card = next((r for r in reactors if r["experiment_id"] == "DASH_DATE_001"), None)
    assert card is not None
    assert card["started_at"] is not None
    assert "2026-01-10" in card["started_at"]


def test_serum_experiment_does_not_overwrite_hpht_reactor_slot(client, db_session):
    """
    Issue #38: If both an HPHT and a Serum experiment share the same
    reactor_number and both are ONGOING, only the HPHT experiment must
    appear in the reactor grid. The Serum experiment is silently excluded.
    """
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    older = datetime.datetime.utcnow() - datetime.timedelta(days=10)
    newer = datetime.datetime.utcnow()

    hpht_exp = Experiment(
        experiment_id="HPHT_SLOT38_001",
        experiment_number=38001,
        status=ExperimentStatus.ONGOING,
        created_at=older,
    )
    serum_exp = Experiment(
        experiment_id="SERUM_SLOT38_001",
        experiment_number=38002,
        status=ExperimentStatus.ONGOING,
        created_at=newer,  # higher id / newer — would win old tiebreak
    )
    db_session.add_all([hpht_exp, serum_exp])
    db_session.flush()

    db_session.add(ExperimentalConditions(
        experiment_fk=hpht_exp.id,
        experiment_id="HPHT_SLOT38_001",
        reactor_number=5,
        experiment_type="HPHT",
    ))
    db_session.add(ExperimentalConditions(
        experiment_fk=serum_exp.id,
        experiment_id="SERUM_SLOT38_001",
        reactor_number=5,
        experiment_type="Serum",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}

    assert "R05" in cards, "R05 slot must be populated by the HPHT experiment"
    assert cards["R05"]["experiment_id"] == "HPHT_SLOT38_001"
    # Serum experiment must NOT appear anywhere in reactors
    all_exp_ids = [c["experiment_id"] for c in resp.json()["reactors"]]
    assert "SERUM_SLOT38_001" not in all_exp_ids


def test_reactor_status_excludes_non_hpht_experiments(client, db_session):
    """
    Issue #38: GET /api/dashboard/reactor-status must also filter by
    experiment_type, matching the main dashboard endpoint behaviour.
    """
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.enums import ExperimentStatus

    hpht_exp = Experiment(
        experiment_id="RS_HPHT_001",
        experiment_number=38010,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=5),
    )
    serum_exp = Experiment(
        experiment_id="RS_SERUM_001",
        experiment_number=38011,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add_all([hpht_exp, serum_exp])
    db_session.flush()

    db_session.add(ExperimentalConditions(
        experiment_fk=hpht_exp.id,
        experiment_id="RS_HPHT_001",
        reactor_number=7,
        experiment_type="HPHT",
    ))
    db_session.add(ExperimentalConditions(
        experiment_fk=serum_exp.id,
        experiment_id="RS_SERUM_001",
        reactor_number=7,
        experiment_type="Serum",
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/reactor-status")
    assert resp.status_code == 200
    exp_ids = [r["experiment_id"] for r in resp.json()]
    assert "RS_HPHT_001" in exp_ids
    assert "RS_SERUM_001" not in exp_ids


# ---------------------------------------------------------------------------
# Today's reactor modification on cards (issue #72)
# ---------------------------------------------------------------------------

def _utc_today() -> datetime.date:
    """The dashboard's definition of 'today' — UTC, matching the pop-out save path."""
    return datetime.datetime.now(datetime.timezone.utc).date()


def test_reactor_card_data_schema_todays_modification_defaults_none():
    from backend.api.schemas.dashboard import ReactorCardData
    r = ReactorCardData(reactor_number=5, reactor_label="R05")
    assert r.todays_modification is None


def test_reactor_card_shows_todays_modification(client, db_session):
    """A card whose experiment has a change request with sync_date == today (UTC)
    returns the requested_change text in todays_modification."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.notion_sync import ReactorChangeRequest
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="MOD_TODAY_001",
        experiment_number=72001,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="MOD_TODAY_001",
        reactor_number=4,
        experiment_type="HPHT",
    ))
    db_session.add(ReactorChangeRequest(
        reactor_label="R04",
        experiment_id="MOD_TODAY_001",
        requested_change="Swapped stir shaft; topped up catalyst",
        sync_date=_utc_today(),
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert "R04" in cards
    assert cards["R04"]["todays_modification"] == "Swapped stir shaft; topped up catalyst"


def test_reactor_card_prior_day_modification_not_shown(client, db_session):
    """A modification saved yesterday must NOT surface on the card."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.notion_sync import ReactorChangeRequest
    from database.models.enums import ExperimentStatus

    exp = Experiment(
        experiment_id="MOD_YDAY_001",
        experiment_number=72002,
        status=ExperimentStatus.ONGOING,
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id="MOD_YDAY_001",
        reactor_number=5,
        experiment_type="HPHT",
    ))
    db_session.add(ReactorChangeRequest(
        reactor_label="R05",
        experiment_id="MOD_YDAY_001",
        requested_change="Yesterday's note",
        sync_date=_utc_today() - datetime.timedelta(days=1),
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert "R05" in cards
    assert cards["R05"]["todays_modification"] is None


def test_todays_modification_keys_on_experiment_and_reactor_label(client, db_session):
    """Three cards: ONGOING with a today-mod, QUEUED with a today-mod, ONGOING without.
    Only the two with a matching (experiment_id, reactor_label, today) row are populated.
    A same-day row saved under a DIFFERENT reactor_label must not leak onto the card."""
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.notion_sync import ReactorChangeRequest
    from database.models.enums import ExperimentStatus

    specs = [
        ("MOD_KEY_ON", 72010, ExperimentStatus.ONGOING, 6),
        ("MOD_KEY_QU", 72011, ExperimentStatus.QUEUED, 7),
        ("MOD_KEY_NO", 72012, ExperimentStatus.ONGOING, 8),
        ("MOD_KEY_WRONG_SLOT", 72013, ExperimentStatus.ONGOING, 9),
    ]
    for exp_id, num, status, rn in specs:
        exp = Experiment(
            experiment_id=exp_id,
            experiment_number=num,
            status=status,
            created_at=datetime.datetime.utcnow(),
        )
        db_session.add(exp)
        db_session.flush()
        db_session.add(ExperimentalConditions(
            experiment_fk=exp.id,
            experiment_id=exp_id,
            reactor_number=rn,
            experiment_type="HPHT",
        ))
    db_session.add(ReactorChangeRequest(
        reactor_label="R06", experiment_id="MOD_KEY_ON",
        requested_change="ongoing mod", sync_date=_utc_today(),
    ))
    db_session.add(ReactorChangeRequest(
        reactor_label="R07", experiment_id="MOD_KEY_QU",
        requested_change="queued mod", sync_date=_utc_today(),
    ))
    # Saved today for MOD_KEY_WRONG_SLOT but under a reactor label it does NOT occupy:
    db_session.add(ReactorChangeRequest(
        reactor_label="R01", experiment_id="MOD_KEY_WRONG_SLOT",
        requested_change="wrong slot mod", sync_date=_utc_today(),
    ))
    db_session.commit()

    resp = client.get("/api/dashboard/")
    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert cards["R06"]["todays_modification"] == "ongoing mod"
    assert cards["R07"]["todays_modification"] == "queued mod"
    assert cards["R08"]["todays_modification"] is None
    assert cards["R09"]["todays_modification"] is None, (
        "A same-day row under a different reactor_label must not appear on this card"
    )


def test_dashboard_modification_lookup_is_single_batched_query(client, db_session):
    """The enrichment must add exactly ONE query touching reactor_change_requests,
    regardless of how many cards are occupied (no per-card N+1)."""
    import sqlalchemy
    from sqlalchemy.engine import Engine
    from database.models.experiments import Experiment
    from database.models.conditions import ExperimentalConditions
    from database.models.notion_sync import ReactorChangeRequest
    from database.models.enums import ExperimentStatus

    for i, rn in enumerate((10, 11, 12)):
        exp = Experiment(
            experiment_id=f"MOD_BATCH_{rn}",
            experiment_number=72100 + i,
            status=ExperimentStatus.ONGOING,
            created_at=datetime.datetime.utcnow(),
        )
        db_session.add(exp)
        db_session.flush()
        db_session.add(ExperimentalConditions(
            experiment_fk=exp.id, experiment_id=exp.experiment_id,
            reactor_number=rn, experiment_type="HPHT",
        ))
        db_session.add(ReactorChangeRequest(
            reactor_label=f"R{rn:02d}", experiment_id=exp.experiment_id,
            requested_change=f"mod {rn}", sync_date=_utc_today(),
        ))
    db_session.commit()

    statements: list[str] = []

    def counter(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sqlalchemy.event.listen(Engine, "before_cursor_execute", counter)
    try:
        resp = client.get("/api/dashboard/")
    finally:
        sqlalchemy.event.remove(Engine, "before_cursor_execute", counter)

    assert resp.status_code == 200
    cards = {c["reactor_label"]: c for c in resp.json()["reactors"]}
    assert cards["R10"]["todays_modification"] == "mod 10"
    assert cards["R12"]["todays_modification"] == "mod 12"
    cr_queries = [s for s in statements if "reactor_change_requests" in s]
    assert len(cr_queries) == 1, (
        f"Expected exactly 1 batched change-request query, got {len(cr_queries)}"
    )
