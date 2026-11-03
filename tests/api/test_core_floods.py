"""Core flood API (issue #133): run list and run detail read endpoints."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from database.models import Experiment, ExperimentalResults, ScalarResults
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus, NoteType
from database.models.experiments import ExperimentNotes


@pytest.fixture()
def reporting_views(db_session):
    from database.event_listeners import _VIEWS
    for view_name, _ in _VIEWS:
        db_session.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
    for _, view_sql in _VIEWS:
        db_session.execute(text(view_sql))
    db_session.flush()
    yield


_NUM = iter(range(97000, 98000))


def _cf_experiment(db, exp_id, status=ExperimentStatus.COMPLETED, date=None,
                   experiment_type="Core Flood", reactor_number=2,
                   pore_volume_mL=20.0, description="desc"):
    exp = Experiment(experiment_id=exp_id, experiment_number=next(_NUM),
                     status=status, date=date)
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp.experiment_id,
        experiment_type=experiment_type, reactor_number=reactor_number,
        pore_volume_mL=pore_volume_mL,
    ))
    if description is not None:
        db.add(ExperimentNotes(experiment_fk=exp.id, experiment_id=exp.experiment_id,
                               note_text=description, note_type=NoteType.description))
    db.flush()
    return exp


def _sample(db, exp, cum_days, volume_mL=5.0, h2_gpt=0.1, flow=0.1, date=None):
    result = ExperimentalResults(
        experiment_fk=exp.id,
        cumulative_time_post_reaction_days=cum_days,
        time_post_reaction_days=cum_days,
        time_post_reaction_bucket_days=cum_days,
        is_primary_timepoint_result=True,
        flow_rate_mL_min=flow,
    )
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, sampling_volume_mL=volume_mL,
                         h2_grams_per_ton_yield=h2_gpt, measurement_date=date))
    db.flush()
    return result


def _view_rows(db, base_id):
    return [dict(r) for r in db.execute(text(
        "SELECT * FROM v_core_flood_samples WHERE run_base_id = :b "
        "ORDER BY cumulative_time_post_reaction_days, result_id"
    ), {"b": base_id}).mappings()]


def _d(day):
    return datetime(2026, 10, day, tzinfo=timezone.utc)


def _seed_two_runs(db):
    a1 = _cf_experiment(db, "CFA_001", date=_d(1))
    _sample(db, a1, 1.0, date=_d(20))
    _sample(db, a1, 2.0, date=_d(25))
    b1 = _cf_experiment(db, "CFA_002", date=_d(2))
    b2 = _cf_experiment(db, "CFA_002-2", status=ExperimentStatus.ONGOING, date=_d(3))
    _sample(db, b1, 1.0, date=_d(5))
    _sample(db, b2, 3.0, date=_d(6))


def test_list_puts_active_runs_first(client, db_session, reporting_views):
    _seed_two_runs(db_session)
    items = client.get("/api/core-floods", params={"scope": "all", "q": "CFA_"}).json()
    assert [i["base_id"] for i in items][:2] == ["CFA_002", "CFA_001"]
    items = client.get("/api/core-floods", params={"scope": "active", "q": "CFA_"}).json()
    assert [i["base_id"] for i in items] == ["CFA_002"]


def test_list_q_filter_narrows(client, db_session, reporting_views):
    _seed_two_runs(db_session)
    for q in ("cfa_002", "CFA_002-2"):
        items = client.get("/api/core-floods", params={"scope": "all", "q": q}).json()
        assert [i["base_id"] for i in items] == ["CFA_002"]


def test_list_item_fields(client, db_session, reporting_views):
    _seed_two_runs(db_session)
    items = client.get("/api/core-floods", params={"scope": "all", "q": "CFA_002"}).json()
    (item,) = items
    rows = _view_rows(db_session, "CFA_002")
    assert item["segment_count"] == 2
    assert item["rig"] == "CF02"
    assert item["sample_count"] == 2
    assert item["ongoing_experiment_ids"] == ["CFA_002-2"]
    assert item["latest_cumulative_h2_grams_per_ton"] == pytest.approx(
        rows[-1]["cumulative_h2_grams_per_ton"])
    assert datetime.fromisoformat(item["first_sample_date"]) == _d(5)
    assert datetime.fromisoformat(item["last_sample_date"]) == _d(6)


def test_list_excludes_non_core_flood(client, db_session, reporting_views):
    _cf_experiment(db_session, "CFA_010", experiment_type="HPHT")
    _cf_experiment(db_session, "CFA_011", experiment_type="CF")
    ids = [i["base_id"] for i in client.get(
        "/api/core-floods", params={"scope": "all", "q": "CFA_01"}).json()]
    assert ids == ["CFA_011"]


def test_run_warnings_cf027_shape(client, db_session, reporting_views):
    _cf_experiment(db_session, "CFA_027", status=ExperimentStatus.ONGOING, date=_d(1))
    _cf_experiment(db_session, "CFA_027-1", status=ExperimentStatus.ONGOING, date=_d(2))
    _cf_experiment(db_session, "CFA_027-2", date=_d(3))
    body = client.get("/api/core-floods/CFA_027").json()
    warnings = {w["code"]: w["experiment_ids"] for w in body["warnings"]}
    assert warnings["multiple_roots"] == ["CFA_027", "CFA_027-1"]
    assert warnings["multiple_ongoing"] == ["CFA_027", "CFA_027-1"]


def test_run_missing_field_warnings(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_030", pore_volume_mL=None, description=None)
    _sample(db_session, exp, 1.0, flow=None)
    body = client.get("/api/core-floods/CFA_030").json()
    warnings = {w["code"]: w["experiment_ids"] for w in body["warnings"]}
    assert warnings["missing_pore_volume"] == ["CFA_030"]
    assert warnings["missing_description"] == ["CFA_030"]
    assert warnings["sample_missing_flow_rate"] == ["CFA_030"]


def test_run_samples_come_from_view(client, db_session, reporting_views):
    _seed_two_runs(db_session)
    body = client.get("/api/core-floods/CFA_002").json()
    rows = _view_rows(db_session, "CFA_002")
    assert [s["result_id"] for s in body["samples"]] == [r["result_id"] for r in rows]
    assert [s["cumulative_h2_grams_per_ton"] for s in body["samples"]] == pytest.approx(
        [r["cumulative_h2_grams_per_ton"] for r in rows])
    assert [s["experiment_id"] for s in body["segments"]] == ["CFA_002", "CFA_002-2"]
    seg = body["segments"][1]
    assert seg["parent_experiment_id"] == "CFA_002"
    assert seg["reactor_slot"] == "CF02"
    assert seg["conditions_id"] is not None
    assert seg["pore_volume_mL"] == 20.0


def test_segment_is_variant_matches_view(client, db_session, reporting_views):
    _cf_experiment(db_session, "CFA_005")
    seg2 = _cf_experiment(db_session, "CFA_005-2")
    bypass = _cf_experiment(db_session, "CFA_005-2_Bypass1")
    _sample(db_session, bypass, 1.0)
    row = _view_rows(db_session, "CFA_005")[0]
    body = client.get("/api/core-floods/CFA_005").json()
    seg = next(s for s in body["segments"] if s["experiment_id"] == "CFA_005-2_Bypass1")
    assert row["is_variant"] is True
    assert seg["is_variant"] is True
    assert next(s for s in body["segments"] if s["experiment_id"] == "CFA_005-2")["is_variant"] is False


def test_run_404_unknown_base(client, db_session, reporting_views):
    assert client.get("/api/core-floods/NOPE_999").status_code == 404


def test_run_404_non_core_flood_base(client, db_session, reporting_views):
    _cf_experiment(db_session, "CFA_020", experiment_type="HPHT")
    assert client.get("/api/core-floods/CFA_020").status_code == 404
