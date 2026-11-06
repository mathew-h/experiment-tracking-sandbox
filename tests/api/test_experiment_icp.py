"""GET /api/experiments/{experiment_id}/icp (issue #143): ICP over time for a series."""
from datetime import datetime, timezone

from database.models import Experiment, ExperimentalResults, ScalarResults
from database.models.enums import ExperimentStatus
from database.models.results import ICPResults

_NUM = iter(range(98500, 99000))


def _exp(db, exp_id):
    exp = Experiment(experiment_id=exp_id, experiment_number=next(_NUM),
                     status=ExperimentStatus.COMPLETED)
    db.add(exp)
    db.flush()
    return exp


def _result(db, exp, cum, *, primary=True, date=None, icp=None):
    r = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=cum,
        time_post_reaction_bucket_days=cum,
        cumulative_time_post_reaction_days=cum,
        is_primary_timepoint_result=primary,
    )
    db.add(r)
    db.flush()
    if date is not None:
        db.add(ScalarResults(result_id=r.id, measurement_date=date))
    if icp is not None:
        db.add(ICPResults(result_id=r.id, **icp))
    db.flush()
    return r


def _get(client, exp_id):
    return client.get(f"/api/experiments/{exp_id}/icp")


def test_rows_for_single_experiment(client, db_session):
    exp = _exp(db_session, "ICPT_001")
    date = datetime(2026, 10, 5, tzinfo=timezone.utc)
    r = _result(db_session, exp, 2.0, date=date,
                icp={"fe": 12.4, "ca": 210, "cu": None, "s": 3.0})
    _result(db_session, exp, 4.0)  # no ICP -> omitted
    body = _get(client, "ICPT_001").json()
    assert body["segment_starts"] == []
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["result_id"] == r.id
    assert row["experiment_id"] == "ICPT_001"
    assert row["is_variant"] is False
    assert row["cumulative_time_post_reaction_days"] == 2.0
    assert datetime.fromisoformat(row["sample_date"]) == date
    # S comes from icp_results directly (v_results_icp has no s_ppm).
    assert row["elements"] == {"fe": 12.4, "ca": 210.0, "s": 3.0}


def test_whole_series_from_any_member_ordered_by_day(client, db_session):
    root = _exp(db_session, "ICPT_002")
    seg2 = _exp(db_session, "ICPT_002-2")
    assert seg2.parent_experiment_fk == root.id
    _result(db_session, seg2, 9.0, icp={"fe": 2.0})
    _result(db_session, root, 3.0, icp={"fe": 1.0})
    for member in ("ICPT_002", "ICPT_002-2"):
        body = _get(client, member).json()
        days = [r["cumulative_time_post_reaction_days"] for r in body["rows"]]
        assert days == [3.0, 9.0]
        assert [r["experiment_id"] for r in body["rows"]] == ["ICPT_002", "ICPT_002-2"]


def test_segment_starts_only_for_chained_segments(client, db_session):
    root = _exp(db_session, "ICPT_003")
    seg2 = _exp(db_session, "ICPT_003-2")
    seg3 = _exp(db_session, "ICPT_003-3")
    side = _exp(db_session, "ICPT_003-2_Bypass1")
    _result(db_session, root, 1.0, icp={"fe": 1.0})
    # seg2 starts at day 5 even though its ICP is only on day 6.
    _result(db_session, seg2, 5.0)
    _result(db_session, seg2, 6.0, icp={"fe": 2.0})
    _result(db_session, seg3, 8.0, icp={"fe": 3.0})
    _result(db_session, side, 5.5, icp={"fe": 9.0})
    body = _get(client, "ICPT_003").json()
    assert body["segment_starts"] == [
        {"experiment_id": "ICPT_003-2", "day": 5.0},
        {"experiment_id": "ICPT_003-3", "day": 8.0},
    ]
    variant = [r for r in body["rows"] if r["experiment_id"] == "ICPT_003-2_Bypass1"]
    assert variant and variant[0]["is_variant"] is True


def test_serum_vials_plot_as_one_series_without_markers(client, db_session):
    for day in (1, 3, 7):
        vial = _exp(db_session, f"ICPV_004-t{day}")
        assert vial.parent_experiment_fk is None
        _result(db_session, vial, float(day), icp={"ca": float(day)})
    body = _get(client, "ICPV_004-t3").json()
    days = [r["cumulative_time_post_reaction_days"] for r in body["rows"]]
    assert days == [1.0, 3.0, 7.0]
    assert body["segment_starts"] == []


def test_non_primary_results_excluded(client, db_session):
    exp = _exp(db_session, "ICPT_005")
    _result(db_session, exp, 2.0, primary=False, icp={"fe": 1.0})
    assert _get(client, "ICPT_005").json()["rows"] == []


def test_no_icp_returns_empty(client, db_session):
    exp = _exp(db_session, "ICPT_006")
    _result(db_session, exp, 1.0)
    resp = _get(client, "ICPT_006")
    assert resp.status_code == 200
    assert resp.json() == {"rows": [], "segment_starts": []}


def test_unknown_experiment_404(client, db_session):
    assert _get(client, "NOPE_ICP_999").status_code == 404


def test_read_only(client, db_session, monkeypatch):
    exp = _exp(db_session, "ICPT_007")
    _result(db_session, exp, 1.0, icp={"fe": 1.0})
    calls = []
    monkeypatch.setattr(db_session, "commit", lambda: calls.append(1))
    assert _get(client, "ICPT_007").status_code == 200
    assert calls == []
