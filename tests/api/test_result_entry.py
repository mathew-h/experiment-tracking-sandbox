"""Generic result entry (issue #146): POST/PATCH /api/experiments/{id}/results."""
from datetime import datetime

import pytest

from backend.services import result_entry_service
from backend.services.workdays import LAB_TZ
from database.models import Experiment, ExperimentalResults, ModificationsLog, ScalarResults
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus, NoteType
from database.models.experiments import ExperimentNotes

_NUM = iter(range(98500, 99500))
_START = datetime(2026, 10, 1, tzinfo=LAB_TZ)


def _experiment(db, exp_id, experiment_type="HPHT", date=_START, rock_mass_g=10.0):
    exp = Experiment(experiment_id=exp_id, experiment_number=next(_NUM),
                     status=ExperimentStatus.ONGOING, date=date)
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp.experiment_id,
        experiment_type=experiment_type, rock_mass_g=rock_mass_g,
    ))
    db.flush()
    return exp


def _post(client, exp_id, **body):
    body.setdefault("measurement_date", "2026-10-04")
    return client.post(f"/api/experiments/{exp_id}/results", json=body)


def _patch(client, exp_id, result_id, **body):
    return client.patch(f"/api/experiments/{exp_id}/results/{result_id}", json=body)


def _results(db, exp):
    return db.query(ExperimentalResults).filter_by(experiment_fk=exp.id).all()


def _notes(db, result_id, note_type=None):
    q = db.query(ExperimentNotes).filter_by(result_id=result_id)
    if note_type is not None:
        q = q.filter_by(note_type=note_type)
    return q.order_by(ExperimentNotes.id).all()


def _logs(db, exp, table=None):
    q = db.query(ModificationsLog).filter_by(experiment_fk=exp.id)
    if table is not None:
        q = q.filter_by(modified_table=table)
    return q.order_by(ModificationsLog.id).all()


_GAS = dict(h2_concentration=1000, gas_sampling_volume_ml=5, gas_sampling_pressure_MPa=0.1)


# --- create -------------------------------------------------------------------

def test_create_hpht_is_atomic_and_complete(client, db_session):
    exp = _experiment(db_session, "RE_HPHT_001")
    resp = _post(client, "RE_HPHT_001", sample_tube_number=7,
                 result_note="first gas draw", **_GAS)
    assert resp.status_code == 201, resp.text
    (row,) = _results(db_session, exp)
    db_session.refresh(row)
    assert row.sample_tube_number == 7
    assert row.cumulative_time_post_reaction_days is not None
    scalar = db_session.query(ScalarResults).filter_by(result_id=row.id).one()
    assert scalar.h2_grams_per_ton_yield is not None
    assert scalar.h2_concentration_unit == "ppm"
    assert [n.note_text for n in _notes(db_session, row.id)] == ["first gas draw"]
    logs = _logs(db_session, exp)
    creates = [m for m in logs if m.modified_table in ("experimental_results", "scalar_results")]
    assert {m.modified_table for m in creates} == {"experimental_results", "scalar_results"}
    assert {m.modification_type for m in creates} == {"create"}
    assert len(_logs(db_session, exp, "experiment_notes")) == 1
    assert len(logs) == 3
    body = resp.json()
    assert body["id"] == row.id
    assert body["sample_tube_number"] == 7
    assert body["h2_grams_per_ton_yield"] == pytest.approx(scalar.h2_grams_per_ton_yield)
    assert [n["note_text"] for n in body["notes"]] == ["first gas draw"]


def test_create_failure_commits_nothing(client, db_session, monkeypatch):
    exp = _experiment(db_session, "RE_HPHT_002")
    commits = []
    monkeypatch.setattr(db_session, "commit", lambda: commits.append(1))

    def boom(*_a, **_k):
        raise RuntimeError("recalculate failed")
    monkeypatch.setattr(result_entry_service, "recalculate", boom)

    savepoint = db_session.begin_nested()
    with pytest.raises(RuntimeError):
        _post(client, "RE_HPHT_002", **_GAS)
    assert commits == []
    # What get_db's close() does in production: discard the uncommitted flushes.
    savepoint.rollback()
    assert _results(db_session, exp) == []


def test_create_core_flood_rejected_writes_nothing(client, db_session):
    exp = _experiment(db_session, "RE_CF_001", experiment_type="Core Flood")
    resp = _post(client, "RE_CF_001", **_GAS)
    assert resp.status_code == 422
    assert resp.json()["detail"] == (
        "Use /api/core-floods/RE_CF_001/samples for Core Flood experiments")
    assert _results(db_session, exp) == []
    assert _logs(db_session, exp) == []


def test_create_serum_accepts_gross_ammonium(client, db_session):
    exp = _experiment(db_session, "RE_SERUM_001", experiment_type="Serum")
    resp = _post(client, "RE_SERUM_001", gross_ammonium_concentration_mM=1.5)
    assert resp.status_code == 201, resp.text
    (row,) = _results(db_session, exp)
    scalar = db_session.query(ScalarResults).filter_by(result_id=row.id).one()
    assert scalar.gross_ammonium_concentration_mM == 1.5
    assert scalar.background_ammonium_concentration_mM == 0.2
    assert resp.json()["gross_ammonium_concentration_mM"] == 1.5


@pytest.mark.parametrize("field", [
    "flow_rate_mL_min", "background_ammonium_concentration_mM", "unknown_key"])
def test_create_unwritable_field_422(client, db_session, field):
    exp = _experiment(db_session, "RE_HPHT_003")
    assert _post(client, "RE_HPHT_003", **{field: 0.5}).status_code == 422
    assert _results(db_session, exp) == []


@pytest.mark.parametrize("body", [
    {"sample_tube_number": 0}, {"h2_concentration": -1},
    {"gas_sampling_volume_ml": -1}, {"result_note": "x" * 2001},
    {"modification_note": "x" * 2001},
])
def test_create_bounds_422(client, db_session, body):
    _experiment(db_session, "RE_HPHT_004")
    assert _post(client, "RE_HPHT_004", **body).status_code == 422


def test_create_derives_day_from_sample_date(client, db_session):
    exp = _experiment(db_session, "RE_HPHT_005")
    db_session.expire(exp)  # reload the start date the way Postgres returns it
    resp = _post(client, "RE_HPHT_005", measurement_date="2026-10-08")
    assert resp.status_code == 201, resp.text
    (row,) = _results(db_session, exp)
    assert row.time_post_reaction_days == 7.0
    scalar = db_session.query(ScalarResults).filter_by(result_id=row.id).one()
    assert scalar.gc_run_date == scalar.measurement_date


def test_create_t_token_rejects_other_day(client, db_session):
    exp = _experiment(db_session, "RE_SERUM_002-t7", experiment_type="Serum")
    resp = _post(client, "RE_SERUM_002-t7", time_post_reaction_days=8)
    assert resp.status_code == 422
    assert _results(db_session, exp) == []


def test_create_unknown_experiment_404(client, db_session):
    assert _post(client, "RE_NOPE_999").status_code == 404


def test_create_experiment_without_conditions_allowed(client, db_session):
    exp = Experiment(experiment_id="RE_BARE_001", experiment_number=next(_NUM),
                     status=ExperimentStatus.ONGOING, date=_START)
    db_session.add(exp)
    db_session.flush()
    assert _post(client, "RE_BARE_001", final_ph=7.1).status_code == 201


# --- modification notes -------------------------------------------------------

def test_modification_note_on_create_and_patch(client, db_session):
    exp = _experiment(db_session, "RE_HPHT_006")
    resp = _post(client, "RE_HPHT_006", modification_note="added 5 mL brine")
    assert resp.status_code == 201, resp.text
    rid = resp.json()["id"]
    assert resp.json()["has_modification_note"] is True
    (first,) = _notes(db_session, rid, NoteType.modification)
    assert first.created_by == "test@addisenergy.com"

    resp = _patch(client, "RE_HPHT_006", rid, modification_note="flushed headspace")
    assert resp.status_code == 200, resp.text
    mods = _notes(db_session, rid, NoteType.modification)
    assert [n.note_text for n in mods] == ["added 5 mL brine", "flushed headspace"]
    assert mods[0].id == first.id
    note_logs = _logs(db_session, exp, "experiment_notes")
    assert len(note_logs) == 2
    assert note_logs[-1].new_values == {
        "note_type": "modification", "note_text": "flushed headspace"}
    assert _logs(db_session, exp, "scalar_results")[-1].modification_type == "create"


def test_blank_modification_note_writes_nothing(client, db_session):
    exp = _experiment(db_session, "RE_HPHT_007")
    rid = _post(client, "RE_HPHT_007").json()["id"]
    before = len(_logs(db_session, exp))
    assert _patch(client, "RE_HPHT_007", rid, modification_note="  ").status_code == 200
    assert _notes(db_session, rid, NoteType.modification) == []
    assert len(_logs(db_session, exp)) == before


# --- PATCH --------------------------------------------------------------------

def test_patch_single_field_audits_only_that_key(client, db_session):
    exp = _experiment(db_session, "RE_HPHT_008")
    rid = _post(client, "RE_HPHT_008", final_ph=6.5, **_GAS).json()["id"]
    before = len(_logs(db_session, exp))
    resp = _patch(client, "RE_HPHT_008", rid, final_ph=7.25)
    assert resp.status_code == 200, resp.text
    assert resp.json()["final_ph"] == 7.25
    new_logs = _logs(db_session, exp)[before:]
    assert len(new_logs) == 1
    assert new_logs[0].modification_type == "update"
    assert new_logs[0].old_values == {"final_ph": 6.5}
    assert new_logs[0].new_values == {"final_ph": 7.25}


def test_patch_unchanged_value_writes_nothing(client, db_session):
    exp = _experiment(db_session, "RE_HPHT_009")
    rid = _post(client, "RE_HPHT_009", final_ph=6.5).json()["id"]
    before = len(_logs(db_session, exp))
    assert _patch(client, "RE_HPHT_009", rid, final_ph=6.5).status_code == 200
    assert len(_logs(db_session, exp)) == before


def test_patch_h2_recalculates(client, db_session):
    _experiment(db_session, "RE_HPHT_010")
    rid = _post(client, "RE_HPHT_010", **_GAS).json()["id"]
    scalar = db_session.query(ScalarResults).filter_by(result_id=rid).one()
    old = scalar.h2_grams_per_ton_yield
    resp = _patch(client, "RE_HPHT_010", rid, h2_concentration=2000)
    assert resp.status_code == 200, resp.text
    db_session.refresh(scalar)
    assert scalar.h2_grams_per_ton_yield == pytest.approx(2 * old)


def test_patch_tube_and_result_note(client, db_session):
    _experiment(db_session, "RE_HPHT_011")
    rid = _post(client, "RE_HPHT_011", sample_tube_number=3,
                result_note="cloudy").json()["id"]
    resp = _patch(client, "RE_HPHT_011", rid, sample_tube_number=4, result_note="clear")
    assert resp.status_code == 200, resp.text
    assert resp.json()["sample_tube_number"] == 4
    assert [n.note_text for n in _notes(db_session, rid, NoteType.result_note)] == ["clear"]
    resp = _patch(client, "RE_HPHT_011", rid, result_note="")
    assert _notes(db_session, rid, NoteType.result_note) == []


def test_patch_result_of_other_experiment_404(client, db_session):
    _experiment(db_session, "RE_HPHT_012")
    other = _experiment(db_session, "RE_HPHT_013")
    rid = _post(client, "RE_HPHT_013", final_ph=6.0).json()["id"]
    before = len(_logs(db_session, other))
    assert _patch(client, "RE_HPHT_012", rid, final_ph=8.0).status_code == 404
    scalar = db_session.query(ScalarResults).filter_by(result_id=rid).one()
    assert scalar.final_ph == 6.0
    assert len(_logs(db_session, other)) == before


def test_patch_core_flood_422(client, db_session):
    exp = _experiment(db_session, "RE_CF_002", experiment_type="Core Flood")
    result = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=1,
                                 time_post_reaction_bucket_days=1,
                                 is_primary_timepoint_result=True)
    db_session.add(result)
    db_session.flush()
    assert _patch(client, "RE_CF_002", result.id, final_ph=7).status_code == 422


@pytest.mark.parametrize("body", [
    {"time_post_reaction_days": 3}, {"flow_rate_mL_min": 0.1}, {"measurement_date": None}])
def test_patch_rejected_bodies_422(client, db_session, body):
    _experiment(db_session, "RE_HPHT_014")
    rid = _post(client, "RE_HPHT_014").json()["id"]
    assert _patch(client, "RE_HPHT_014", rid, **body).status_code == 422


def test_patch_missing_result_404(client, db_session):
    _experiment(db_session, "RE_HPHT_015")
    assert _patch(client, "RE_HPHT_015", 99999999, final_ph=7).status_code == 404


# --- GET rows carry the tube number --------------------------------------------

def test_get_results_includes_tube_number(client, db_session):
    _experiment(db_session, "RE_HPHT_016")
    _post(client, "RE_HPHT_016", sample_tube_number=12)
    rows = client.get("/api/experiments/RE_HPHT_016/results").json()
    assert [r["sample_tube_number"] for r in rows] == [12]
