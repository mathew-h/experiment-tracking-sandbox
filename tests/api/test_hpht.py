"""HPHT run API (issue #149): run list, run detail and ICP read endpoints."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from database.models import Experiment, ExperimentalResults, ICPResults, ScalarResults
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


_NUM = iter(range(95000, 96000))


def _d(day):
    return datetime(2026, 10, day, tzinfo=timezone.utc)


def _hpht(db, exp_id, status=ExperimentStatus.COMPLETED, date=None, description="desc",
          experiment_type="HPHT", reactor_number=4, reactor_series=None, **conditions):
    exp = Experiment(experiment_id=exp_id, experiment_number=next(_NUM),
                     status=status, date=date)
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp.experiment_id,
        experiment_type=experiment_type, reactor_number=reactor_number,
        reactor_series=reactor_series, **conditions,
    ))
    if description is not None:
        db.add(ExperimentNotes(experiment_fk=exp.id, experiment_id=exp.experiment_id,
                               note_text=description, note_type=NoteType.description))
    db.flush()
    return exp


def _sample(db, exp, cum_days, h2_gpt=0.1, date=None):
    result = ExperimentalResults(
        experiment_fk=exp.id,
        cumulative_time_post_reaction_days=cum_days,
        time_post_reaction_days=cum_days,
        time_post_reaction_bucket_days=cum_days,
        is_primary_timepoint_result=True,
    )
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, measurement_date=date))
    db.flush()
    db.execute(text("UPDATE scalar_results SET h2_grams_per_ton_yield = :g WHERE result_id = :r"),
               {"g": h2_gpt, "r": result.id})
    return result


def _instant(iso):
    """Compare moments, not strings: the API may render them in the lab timezone."""
    return datetime.fromisoformat(iso).astimezone(timezone.utc)


def _bases(body):
    return [r["base_id"] for r in body]


# ---- GET /api/hpht ----

def test_scope_active_returns_only_runs_with_an_ongoing_segment(client, db_session, reporting_views):
    _hpht(db_session, "HPHTA_001")
    _hpht(db_session, "HPHTA_002")
    _hpht(db_session, "HPHTA_002-2", status=ExperimentStatus.ONGOING)
    active = _bases(client.get("/api/hpht").json())
    assert "HPHTA_002" in active and "HPHTA_001" not in active
    everything = _bases(client.get("/api/hpht", params={"scope": "all"}).json())
    assert {"HPHTA_001", "HPHTA_002"} <= set(everything)
    # Active runs sort first.
    assert everything.index("HPHTA_002") < everything.index("HPHTA_001")


def test_list_sorts_active_first_then_by_reactor_slot(
        client, db_session, reporting_views):
    ongoing = ExperimentStatus.ONGOING
    _hpht(db_session, "HPHTS_P02", status=ongoing, reactor_number=2,
          reactor_series="P")
    _hpht(db_session, "HPHTS_R10", status=ongoing, reactor_number=10)
    _hpht(db_session, "HPHTS_NONE", status=ongoing, reactor_number=None)
    _hpht(db_session, "HPHTS_R02", status=ongoing, reactor_number=2)
    _hpht(db_session, "HPHTS_R09", status=ongoing, reactor_number=9)
    _hpht(db_session, "HPHTS_D01", reactor_number=1)
    params = {"scope": "all", "q": "HPHTS_"}
    bases = _bases(client.get("/api/hpht", params=params).json())
    # Numeric (R09 before R10), R before Parr, no reactor last;
    # completed after all active.
    assert bases == ["HPHTS_R02", "HPHTS_R09", "HPHTS_R10", "HPHTS_P02",
                     "HPHTS_NONE", "HPHTS_D01"]


def test_q_matches_description_base_and_segment(client, db_session, reporting_views):
    _hpht(db_session, "HPHTQ_001", description="Olivine with nickel catalyst")
    _hpht(db_session, "HPHTQ_002", description="Basalt control")
    _hpht(db_session, "HPHTQ_002-3", description=None)

    def q(term):
        return _bases(client.get("/api/hpht", params={"scope": "all", "q": term}).json())

    assert q("NICKEL") == ["HPHTQ_001"]
    assert q("hphtq_002-3") == ["HPHTQ_002"]
    assert set(q("hphtq_00")) == {"HPHTQ_001", "HPHTQ_002"}
    assert q("   ") == q("") and len(q("")) >= 2


def test_list_item_fields(client, db_session, reporting_views):
    root = _hpht(db_session, "HPHTL_001", date=_d(1), description="Run L")
    seg2 = _hpht(db_session, "HPHTL_001-2", status=ExperimentStatus.ONGOING, date=_d(10),
                 reactor_number=3, reactor_series="P")
    _sample(db_session, root, 1.0, h2_gpt=0.2, date=_d(2))
    _sample(db_session, seg2, 3.0, h2_gpt=0.5, date=_d(12))
    (item,) = [r for r in client.get("/api/hpht").json() if r["base_id"] == "HPHTL_001"]
    assert item["description"] == "Run L"
    assert item["segment_count"] == 2
    assert item["ongoing_experiment_ids"] == ["HPHTL_001-2"]
    # From the latest segment, so a Parr vessel shows as P03, not R03.
    assert item["reactor_slot"] == "P03"
    assert item["sample_count"] == 2
    assert _instant(item["last_sample_date"]) == _d(12)
    assert item["latest_cumulative_h2_grams_per_ton"] == pytest.approx(0.7)
    assert item["warning_count"] == 0


def test_list_excludes_other_types(client, db_session, reporting_views):
    _hpht(db_session, "HPHTX_CF", status=ExperimentStatus.ONGOING, experiment_type="Core Flood")
    _hpht(db_session, "HPHTX_SV", status=ExperimentStatus.ONGOING, experiment_type="Serum")
    bases = _bases(client.get("/api/hpht", params={"scope": "all"}).json())
    assert "HPHTX_CF" not in bases and "HPHTX_SV" not in bases


# ---- GET /api/hpht/{base_id} ----

def test_run_has_segments_conditions_samples_and_notes(client, db_session, reporting_views):
    root = _hpht(db_session, "HPHTR_001", date=_d(1), temperature_c=90.0,
                 rock_mass_g=10.0, water_volume_mL=100.0, water_to_rock_ratio=10.0,
                 feedstock="Olivine")
    seg2 = _hpht(db_session, "HPHTR_001-2", status=ExperimentStatus.ONGOING, date=_d(8),
                 temperature_c=120.0, rxn_temp_pressure_psi=1500.0, rock_mass_g=9.0,
                 catalyst="NiCl2", catalyst_ppm=50.0)
    variant = _hpht(db_session, "HPHTR_001_Desorption", date=_d(20), temperature_c=25.0)
    r1 = _sample(db_session, root, 1.0, date=_d(2))
    _sample(db_session, seg2, 4.0, date=_d(9))
    _sample(db_session, variant, 2.0, date=_d(21))
    db_session.add(ExperimentNotes(experiment_fk=root.id, experiment_id=root.experiment_id,
                                   result_id=r1.id, note_type=NoteType.observation,
                                   note_text="Cloudy brine"))
    db_session.flush()

    resp = client.get("/api/hpht/HPHTR_001")
    assert resp.status_code == 200
    body = resp.json()
    assert [s["experiment_id"] for s in body["segments"]] == [
        "HPHTR_001", "HPHTR_001-2", "HPHTR_001_Desorption"]
    assert [s["is_variant"] for s in body["segments"]] == [False, False, True]

    # Latest NON-variant segment, so the later Desorption variant is skipped.
    cond = body["conditions"]
    assert cond["experiment_id"] == "HPHTR_001-2"
    assert cond["temperature_c"] == 120.0 and cond["rxn_temp_pressure_psi"] == 1500.0
    assert cond["rock_mass_g"] == 9.0
    assert cond["catalyst"] == "NiCl2" and cond["catalyst_ppm"] == 50.0
    assert _instant(cond["date"]) == _d(8)

    by_id = {s["result_id"]: s for s in body["samples"]}
    assert len(by_id) == 3
    assert [n["note_text"] for n in by_id[r1.id]["notes"]] == ["Cloudy brine"]
    assert by_id[r1.id]["notes"][0]["note_type"] == "observation"
    real = [s for s in body["samples"] if not s["is_variant"]]
    assert [s["cumulative_h2_grams_per_ton"] for s in real] == pytest.approx([0.1, 0.2])
    assert body["warnings"] == []


def test_run_404_unknown_base(client, db_session, reporting_views):
    assert client.get("/api/hpht/NOPE_404").status_code == 404


def test_run_404_for_core_flood_base(client, db_session, reporting_views):
    _hpht(db_session, "HPHTC_001", experiment_type="Core Flood")
    assert client.get("/api/hpht/HPHTC_001").status_code == 404


def test_base_mismatch_warning(client, db_session, reporting_views):
    _hpht(db_session, "HPHTM_196")
    other = _hpht(db_session, "HPHTM_197")
    # HPHT_196/197 in today's data: a segment filed under another run's base.
    db_session.execute(text("UPDATE experiments SET base_experiment_id = 'HPHTM_196' WHERE id = :i"),
                       {"i": other.id})
    db_session.expire_all()
    body = client.get("/api/hpht/HPHTM_196").json()
    assert {"code": "base_mismatch", "experiment_ids": ["HPHTM_197"]} in body["warnings"]
    listed = [r for r in client.get("/api/hpht", params={"scope": "all"}).json()
              if r["base_id"] == "HPHTM_196"]
    assert listed[0]["warning_count"] >= 1


def test_base_mismatch_needs_a_separator(client, db_session, reporting_views):
    _hpht(db_session, "HPHTM_19")
    other = _hpht(db_session, "HPHTM_190")
    db_session.execute(text("UPDATE experiments SET base_experiment_id = 'HPHTM_19' WHERE id = :i"),
                       {"i": other.id})
    db_session.expire_all()
    codes = {w["code"]: w["experiment_ids"] for w in client.get("/api/hpht/HPHTM_19").json()["warnings"]}
    assert codes.get("base_mismatch") == ["HPHTM_190"]


def test_multiple_ongoing_and_missing_description(client, db_session, reporting_views):
    _hpht(db_session, "HPHTW_001", status=ExperimentStatus.ONGOING)
    _hpht(db_session, "HPHTW_001-2", status=ExperimentStatus.ONGOING, description=None)
    codes = {w["code"]: w["experiment_ids"] for w in client.get("/api/hpht/HPHTW_001").json()["warnings"]}
    assert codes == {
        "multiple_ongoing": ["HPHTW_001", "HPHTW_001-2"],
        "missing_description": ["HPHTW_001-2"],
    }


# ---- GET /api/hpht/{base_id}/icp ----

def test_icp_omits_samples_without_icp(client, db_session, reporting_views):
    exp = _hpht(db_session, "HPHTI_001")
    with_icp = _sample(db_session, exp, 1.0, date=_d(5))
    _sample(db_session, exp, 2.0, date=_d(6))
    db_session.add(ICPResults(result_id=with_icp.id, fe=12.4, ca=210))
    db_session.flush()
    body = client.get("/api/hpht/HPHTI_001/icp").json()
    assert [r["result_id"] for r in body] == [with_icp.id]
    assert body[0]["elements"]["fe"] == pytest.approx(12.4)


def test_icp_404_unknown_base(client, db_session, reporting_views):
    assert client.get("/api/hpht/NOPE_404/icp").status_code == 404
