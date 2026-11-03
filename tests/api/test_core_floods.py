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


# ---- POST /api/core-floods/{experiment_id}/samples (Task 3) ----

from backend.services.workdays import LAB_TZ  # noqa: E402
from database.models import ModificationsLog  # noqa: E402


def _result_count(db, exp):
    return db.query(ExperimentalResults).filter_by(experiment_fk=exp.id).count()


def _post(client, exp_id, **body):
    return client.post(f"/api/core-floods/{exp_id}/samples", json=body)


def test_create_on_derivation_persists_everything(client, db_session, reporting_views):
    parent = _cf_experiment(db_session, "CFA_100", date=_d(1))
    _sample(db_session, parent, 10.0, date=_d(11))
    child = _cf_experiment(db_session, "CFA_100-2", date=_d(1))
    resp = _post(client, "CFA_100-2", measurement_date="2026-10-05",
                 time_post_reaction_days=3, flow_rate_mL_min=0.5,
                 sample_tube_number=4, inlet_pressure_psi=100,
                 h2_concentration=1000, gas_sampling_volume_ml=5,
                 gas_sampling_pressure_MPa=0.1)
    assert resp.status_code == 201, resp.text
    row = db_session.query(ExperimentalResults).filter_by(experiment_fk=child.id).one()
    db_session.refresh(row)
    assert row.flow_rate_mL_min == 0.5
    assert row.sample_tube_number == 4
    assert row.inlet_pressure_psi == 100
    assert row.cumulative_time_post_reaction_days == 13.0
    scalar = db_session.query(ScalarResults).filter_by(result_id=row.id).one()
    assert scalar.h2_micromoles is not None
    assert resp.json()["result_id"] == row.id


def test_create_missing_flow_422_no_rows(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_101", date=_d(1))
    resp = _post(client, "CFA_101", measurement_date="2026-10-05",
                 time_post_reaction_days=1)
    assert resp.status_code == 422
    assert _result_count(db_session, exp) == 0


def test_create_negative_flow_422_no_rows(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_102", date=_d(1))
    resp = _post(client, "CFA_102", measurement_date="2026-10-05",
                 time_post_reaction_days=1, flow_rate_mL_min=-1)
    assert resp.status_code == 422
    assert _result_count(db_session, exp) == 0


def test_create_non_core_flood_422(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_103", experiment_type="HPHT", date=_d(1))
    resp = _post(client, "CFA_103", measurement_date="2026-10-05",
                 time_post_reaction_days=1, flow_rate_mL_min=0.1)
    assert resp.status_code == 422
    assert _result_count(db_session, exp) == 0


def test_create_no_conditions_422(client, db_session, reporting_views):
    exp = Experiment(experiment_id="CFA_104", experiment_number=next(_NUM),
                     status=ExperimentStatus.COMPLETED, date=_d(1))
    db_session.add(exp)
    db_session.flush()
    resp = _post(client, "CFA_104", measurement_date="2026-10-05",
                 time_post_reaction_days=1, flow_rate_mL_min=0.1)
    assert resp.status_code == 422
    assert _result_count(db_session, exp) == 0


def test_create_defaults_day_and_gc_run_date(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_105", date=datetime(2026, 10, 1, tzinfo=LAB_TZ))
    resp = _post(client, "CFA_105", measurement_date="2026-10-04", flow_rate_mL_min=0.1)
    assert resp.status_code == 201, resp.text
    row = db_session.query(ExperimentalResults).filter_by(experiment_fk=exp.id).one()
    assert row.time_post_reaction_days == 3.0
    scalar = db_session.query(ScalarResults).filter_by(result_id=row.id).one()
    assert scalar.gc_run_date == scalar.measurement_date


def test_create_no_start_date_without_day_422(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_106", date=None)
    resp = _post(client, "CFA_106", measurement_date="2026-10-04", flow_rate_mL_min=0.1)
    assert resp.status_code == 422
    assert _result_count(db_session, exp) == 0


def test_create_date_before_start_422(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_107", date=datetime(2026, 10, 1, tzinfo=LAB_TZ))
    resp = _post(client, "CFA_107", measurement_date="2026-09-30", flow_rate_mL_min=0.1)
    assert resp.status_code == 422
    assert _result_count(db_session, exp) == 0


def test_create_same_day_newest_wins(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_108", date=_d(1))
    ids = []
    for flow in (0.1, 0.2):
        resp = _post(client, "CFA_108", measurement_date="2026-10-03",
                     time_post_reaction_days=2, flow_rate_mL_min=flow)
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["result_id"])
    primaries = db_session.query(ExperimentalResults).filter_by(
        experiment_fk=exp.id, is_primary_timepoint_result=True).count()
    assert primaries == 1
    assert [r["result_id"] for r in _view_rows(db_session, "CFA_108")] == [ids[1]]


def test_create_writes_audit_rows(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_109", date=_d(1))
    resp = _post(client, "CFA_109", measurement_date="2026-10-03",
                 time_post_reaction_days=2, flow_rate_mL_min=0.1)
    assert resp.status_code == 201, resp.text
    logs = db_session.query(ModificationsLog).filter_by(experiment_fk=exp.id).all()
    assert len(logs) == 2
    assert {m.modified_table for m in logs} == {"experimental_results", "scalar_results"}
    assert {m.modification_type for m in logs} == {"create"}
    assert {m.modified_by for m in logs} == {"test@addisenergy.com"}


def test_create_unknown_experiment_404(client, db_session, reporting_views):
    resp = _post(client, "NOPE_999", measurement_date="2026-10-03",
                 time_post_reaction_days=2, flow_rate_mL_min=0.1)
    assert resp.status_code == 404


def test_create_unknown_key_422(client, db_session, reporting_views):
    _cf_experiment(db_session, "CFA_110", date=_d(1))
    resp = _post(client, "CFA_110", measurement_date="2026-10-03",
                 time_post_reaction_days=2, flow_rate_mL_min=0.1, bogus=1)
    assert resp.status_code == 422


def test_create_local_midnight_start_day_and_storage(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_111", date=datetime(2026, 10, 23, tzinfo=LAB_TZ))
    r0 = _post(client, "CFA_111", measurement_date="2026-10-23", flow_rate_mL_min=0.1)
    assert r0.status_code == 201, r0.text
    r3 = _post(client, "CFA_111", measurement_date="2026-10-26", flow_rate_mL_min=0.1)
    assert r3.status_code == 201, r3.text
    rows = db_session.query(ExperimentalResults).filter_by(
        experiment_fk=exp.id).order_by(ExperimentalResults.id).all()
    assert [r.time_post_reaction_days for r in rows] == [0.0, 3.0]
    scalar = db_session.query(ScalarResults).filter_by(result_id=rows[1].id).one()
    assert scalar.measurement_date == datetime(2026, 10, 26, tzinfo=LAB_TZ)


def test_create_t_token_conflict_422_no_demotion(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_312-t5", date=_d(1))
    existing = _sample(db_session, exp, 5.0)
    resp = _post(client, "CFA_312-t5", measurement_date="2026-10-03",
                 time_post_reaction_days=2, flow_rate_mL_min=0.1)
    assert resp.status_code == 422
    db_session.refresh(existing)
    assert existing.is_primary_timepoint_result is True
    assert _result_count(db_session, exp) == 1


def test_create_negative_day_422(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFA_313", date=_d(1))
    resp = _post(client, "CFA_313", measurement_date="2026-10-03",
                 time_post_reaction_days=-1, flow_rate_mL_min=0.1)
    assert resp.status_code == 422
    assert _result_count(db_session, exp) == 0


# --- PATCH /api/core-floods/samples/{result_id} -------------------------------

def _patch(client, result_id, **body):
    return client.patch(f"/api/core-floods/samples/{result_id}", json=body)


def _seed_posted_sample(client, db, exp_id, **extra):
    exp = _cf_experiment(db, exp_id, date=_d(1))
    body = dict(measurement_date="2026-10-03", time_post_reaction_days=2,
                flow_rate_mL_min=0.1, final_ph=6.5, h2_concentration=1000,
                gas_sampling_volume_ml=5, gas_sampling_pressure_MPa=0.1)
    body.update(extra)
    resp = _post(client, exp_id, **body)
    assert resp.status_code == 201, resp.text
    return exp, resp.json()["result_id"]


def _scalar(db, result_id):
    row = db.query(ScalarResults).filter_by(result_id=result_id).one()
    db.refresh(row)
    return row


def _log_count(db, exp):
    return db.query(ModificationsLog).filter_by(experiment_fk=exp.id).count()


def test_patch_conductivity_persists(client, db_session, reporting_views):
    _, rid = _seed_posted_sample(client, db_session, "CFP_001")
    resp = _patch(client, rid, final_conductivity_mS_cm=12.5)
    assert resp.status_code == 200, resp.text
    assert resp.json()["final_conductivity_mS_cm"] == 12.5
    assert _scalar(db_session, rid).final_conductivity_mS_cm == 12.5


def test_patch_unknown_key_422(client, db_session, reporting_views):
    _, rid = _seed_posted_sample(client, db_session, "CFP_002")
    assert _patch(client, rid, bogus=1).status_code == 422


def test_patch_day_not_editable_422(client, db_session, reporting_views):
    _, rid = _seed_posted_sample(client, db_session, "CFP_003")
    assert _patch(client, rid, time_post_reaction_days=4).status_code == 422


def test_patch_audit_changed_fields_only(client, db_session, reporting_views):
    exp, rid = _seed_posted_sample(client, db_session, "CFP_004")
    before = _log_count(db_session, exp)
    resp = _patch(client, rid, final_ph=7.1, flow_rate_mL_min=0.1)
    assert resp.status_code == 200, resp.text
    new = (db_session.query(ModificationsLog).filter_by(experiment_fk=exp.id)
           .order_by(ModificationsLog.id).all()[before:])
    assert len(new) == 1
    assert new[0].modification_type == "update"
    assert new[0].modified_table == "scalar_results"
    assert new[0].old_values == {"final_ph": 6.5}
    assert new[0].new_values == {"final_ph": 7.1}
    assert new[0].modified_by == "test@addisenergy.com"


def test_patch_noop_writes_no_audit(client, db_session, reporting_views):
    exp, rid = _seed_posted_sample(client, db_session, "CFP_005")
    before = _log_count(db_session, exp)
    assert _patch(client, rid).status_code == 200
    assert _patch(client, rid, final_ph=6.5, flow_rate_mL_min=0.1,
                  measurement_date="2026-10-03").status_code == 200
    assert _log_count(db_session, exp) == before


def test_patch_creates_missing_scalar(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFP_006", date=_d(1))
    result = ExperimentalResults(
        experiment_fk=exp.id, time_post_reaction_days=2.0,
        time_post_reaction_bucket_days=2.0, cumulative_time_post_reaction_days=2.0,
        is_primary_timepoint_result=True)
    db_session.add(result)
    db_session.flush()
    resp = _patch(client, result.id, flow_rate_mL_min=0.2, final_ph=7)
    assert resp.status_code == 200, resp.text
    db_session.refresh(result)
    assert result.flow_rate_mL_min == 0.2
    assert _scalar(db_session, result.id).final_ph == 7
    logs = db_session.query(ModificationsLog).filter_by(experiment_fk=exp.id).all()
    assert sorted((m.modified_table, m.modification_type) for m in logs) == [
        ("experimental_results", "update"), ("scalar_results", "create")]


def test_patch_h2_change_recalculates(client, db_session, reporting_views):
    _, rid = _seed_posted_sample(client, db_session, "CFP_007")
    before = _scalar(db_session, rid).h2_micromoles
    assert _patch(client, rid, h2_concentration=2000).status_code == 200
    after = _scalar(db_session, rid).h2_micromoles
    assert before is not None and after is not None and after != before


def test_patch_clear_h2_clears_micromoles(client, db_session, reporting_views):
    _, rid = _seed_posted_sample(client, db_session, "CFP_008")
    assert _scalar(db_session, rid).h2_micromoles is not None
    assert _patch(client, rid, h2_concentration=None).status_code == 200
    assert _scalar(db_session, rid).h2_micromoles is None


def test_patch_missing_result_404(client, db_session, reporting_views):
    assert _patch(client, 99999999, final_ph=7).status_code == 404


def test_patch_non_core_flood_422(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFP_009", experiment_type="HPHT", date=_d(1))
    sample = _sample(db_session, exp, 1.0)
    assert _patch(client, sample.id, final_ph=7).status_code == 422


def test_patch_non_primary_404_writes_nothing(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFP_010", date=_d(1))
    sample = _sample(db_session, exp, 1.0)
    sample.is_primary_timepoint_result = False
    db_session.flush()
    before = _log_count(db_session, exp)
    assert _patch(client, sample.id, flow_rate_mL_min=0.9).status_code == 404
    db_session.refresh(sample)
    assert sample.flow_rate_mL_min == 0.1
    assert _log_count(db_session, exp) == before


# --- Final-review fixes: day default across DST and non-midnight starts -------
#
# These tests expire `exp` before the POST. The client shares db_session, so
# without the expire the identity map hands create_sample the same Experiment
# object the test built, whose `date` still carries tzinfo=LAB_TZ. Postgres
# returns a FIXED offset (-04:00 / -05:00) instead, and that is the shape the
# service sees in production; expiring forces the reload.

def _day_of(db, exp):
    row = db.query(ExperimentalResults).filter_by(experiment_fk=exp.id).one()
    return row.time_post_reaction_days


def test_create_day_across_dst_is_whole(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFD_001", date=datetime(2026, 10, 23, tzinfo=LAB_TZ))
    db_session.expire(exp)
    resp = _post(client, "CFD_001", measurement_date="2026-11-03", flow_rate_mL_min=0.1)
    assert resp.status_code == 201, resp.text
    assert _day_of(db_session, exp) == 11.0


@pytest.mark.parametrize("sample_date, expected", [
    ("2026-09-08", 0.0), ("2026-09-09", 1.0),
])
def test_create_date_only_counts_calendar_days(
        client, db_session, reporting_views, sample_date, expected):
    exp = _cf_experiment(db_session, "CFD_002",
                         date=datetime(2026, 9, 8, 14, 4, tzinfo=LAB_TZ))
    db_session.expire(exp)
    resp = _post(client, "CFD_002", measurement_date=sample_date, flow_rate_mL_min=0.1)
    assert resp.status_code == 201, resp.text
    assert _day_of(db_session, exp) == expected


def test_create_full_timestamp_keeps_fraction(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFD_003",
                         date=datetime(2026, 9, 8, 12, 0, tzinfo=LAB_TZ))
    db_session.expire(exp)
    resp = _post(client, "CFD_003", measurement_date="2026-09-09T00:00:00-04:00",
                 flow_rate_mL_min=0.1)
    assert resp.status_code == 201, resp.text
    assert _day_of(db_session, exp) == 0.5


# --- Final-review fixes: PATCH nulls ------------------------------------------

def test_patch_null_on_missing_scalar_writes_nothing(client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFD_004", date=_d(1))
    result = ExperimentalResults(
        experiment_fk=exp.id, time_post_reaction_days=2.0,
        time_post_reaction_bucket_days=2.0, cumulative_time_post_reaction_days=2.0,
        is_primary_timepoint_result=True)
    db_session.add(result)
    db_session.flush()
    before = _log_count(db_session, exp)
    resp = _patch(client, result.id, final_ph=None)
    assert resp.status_code == 200, resp.text
    assert db_session.query(ScalarResults).filter_by(result_id=result.id).count() == 0
    assert _log_count(db_session, exp) == before


@pytest.mark.parametrize("field", ["flow_rate_mL_min", "measurement_date"])
def test_patch_explicit_null_rejected(client, db_session, reporting_views, field):
    exp, rid = _seed_posted_sample(client, db_session, f"CFD_005_{field}")
    before = _log_count(db_session, exp)
    resp = _patch(client, rid, **{field: None})
    assert resp.status_code == 422
    row = db_session.get(ExperimentalResults, rid)
    db_session.refresh(row)
    assert row.flow_rate_mL_min == 0.1
    assert _scalar(db_session, rid).measurement_date is not None
    assert _log_count(db_session, exp) == before


def test_create_full_timestamp_across_dst_uses_wall_clock(
        client, db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFD_006", date=datetime(2026, 10, 23, tzinfo=LAB_TZ))
    db_session.expire(exp)  # see the section comment above
    resp = _post(client, "CFD_006", measurement_date="2026-11-03T12:00:00",
                 flow_rate_mL_min=0.1)
    assert resp.status_code == 201, resp.text
    assert _day_of(db_session, exp) == 11.5
