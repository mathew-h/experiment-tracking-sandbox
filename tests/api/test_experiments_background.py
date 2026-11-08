"""experiments.is_background through the API (issue #152): create, PATCH with
audit, list filter, replicate inheritance, group payloads, the rollup's
is_background_group, and the #144 link's usable-background check."""
import pytest
from sqlalchemy import select as sa_select, text

from database.models import Experiment, ExperimentalResults, ScalarResults
from database.models.enums import ExperimentStatus
from database.models.experiments import ModificationsLog


@pytest.fixture()
def reporting_views(db_session):
    from database.event_listeners import _VIEWS
    for view_name, _ in _VIEWS:
        db_session.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
    for _, view_sql in _VIEWS:
        db_session.execute(text(view_sql))
    db_session.flush()
    yield


def _mk(db, exp_id, number, background=False, commit=True):
    exp = Experiment(experiment_id=exp_id, experiment_number=number,
                     status=ExperimentStatus.ONGOING, is_background=background)
    db.add(exp)
    if commit:
        db.commit()
    else:
        db.flush()
    return exp


def _h2(db, exp, bucket, umol):
    r = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=bucket,
                            time_post_reaction_bucket_days=bucket, is_primary_timepoint_result=True)
    db.add(r)
    db.flush()
    db.add(ScalarResults(result_id=r.id, h2_concentration=100.0, h2_micromoles=umol))
    db.flush()
    db.execute(text("UPDATE scalar_results SET h2_micromoles = :u WHERE result_id = :r"),
               {"u": umol, "r": r.id})


def _audit(db, exp_id):
    db.expire_all()
    return [log for log in db.execute(
        sa_select(ModificationsLog).where(ModificationsLog.experiment_id == exp_id)
    ).scalars() if "is_background" in (log.new_values or {})]


def test_create_defaults_false_and_accepts_true(client, db_session):
    plain = client.post("/api/experiments", json={"experiment_id": "BGA_001"})
    assert plain.status_code == 201
    assert plain.json()["is_background"] is False
    bg = client.post("/api/experiments", json={"experiment_id": "BGA_002", "is_background": True})
    assert bg.status_code == 201
    assert bg.json()["is_background"] is True


def test_patch_sets_clears_and_audits(client, db_session):
    _mk(db_session, "BGA_010", 930010)
    on = client.patch("/api/experiments/BGA_010", json={"is_background": True})
    assert on.status_code == 200
    assert on.json()["is_background"] is True
    off = client.patch("/api/experiments/BGA_010", json={"is_background": False})
    assert off.json()["is_background"] is False
    logs = _audit(db_session, "BGA_010")
    assert [(log.old_values, log.new_values) for log in logs] == [
        ({"is_background": False}, {"is_background": True}),
        ({"is_background": True}, {"is_background": False}),
    ]


def test_patch_noop_writes_no_audit_row(client, db_session):
    _mk(db_session, "BGA_011", 930011)
    assert client.patch("/api/experiments/BGA_011", json={"is_background": False}).status_code == 200
    assert _audit(db_session, "BGA_011") == []


def test_patch_null_is_422(client, db_session):
    _mk(db_session, "BGA_012", 930012)
    resp = client.patch("/api/experiments/BGA_012", json={"is_background": None})
    assert resp.status_code == 422
    assert "is_background cannot be null" in resp.text


def test_list_filter_and_item_field(client, db_session):
    _mk(db_session, "BGA_020", 930020, background=True)
    _mk(db_session, "BGA_021", 930021)
    both = client.get("/api/experiments", params={"search": "BGA_02"}).json()["items"]
    assert {i["experiment_id"]: i["is_background"] for i in both} == {"BGA_020": True, "BGA_021": False}
    bg = client.get("/api/experiments", params={"search": "BGA_02", "is_background": True}).json()
    assert [i["experiment_id"] for i in bg["items"]] == ["BGA_020"]
    assert bg["total"] == 1
    samples = client.get("/api/experiments", params={"search": "BGA_02", "is_background": False}).json()
    assert [i["experiment_id"] for i in samples["items"]] == ["BGA_021"]


def test_replicates_inherit_the_flag(client, db_session):
    _mk(db_session, "BGA_030", 930030, background=True)
    _mk(db_session, "BGA_031", 930031)
    r1 = client.post("/api/experiments/replicates", json={"base_experiment_id": "BGA_030", "count": 2})
    assert r1.status_code == 201
    assert [e["is_background"] for e in r1.json()["created"]] == [True, True]
    r2 = client.post("/api/experiments/replicates", json={"base_experiment_id": "BGA_031", "count": 1})
    assert [e["is_background"] for e in r2.json()["created"]] == [False]


def test_group_payload_carries_the_flag(client, db_session, reporting_views):
    _mk(db_session, "BGA_040a", 930040)
    _mk(db_session, "BGA_040b", 930041, background=True)
    data = client.get("/api/experiments/groups/BGA_040").json()
    flags = {v["experiment_id"]: v["is_background"]
             for r in data["replicates"] for v in r["vials"]}
    assert flags == {"BGA_040a": False, "BGA_040b": True}


def test_rollup_endpoint_reports_background_group(client, db_session, reporting_views):
    a = _mk(db_session, "BGA_050a", 930050, background=True, commit=False)
    b = _mk(db_session, "BGA_050b", 930051, background=True, commit=False)
    _h2(db_session, a, 7, 1.0)
    _h2(db_session, b, 7, 3.0)
    db_session.commit()
    rows = client.get("/api/experiments/groups/BGA_050/rollup").json()
    assert len(rows) == 1
    assert rows[0]["is_background_group"] is True
    assert rows[0]["mean_h2_micromoles"] == pytest.approx(2.0)


def test_h2_link_needs_a_usable_flagged_vial(client, db_session):
    # The linked set has a flagged vial with no H2 and an unflagged one with H2:
    # only flagged vials count, so there is nothing usable to subtract.
    _mk(db_session, "BGA_060a", 930060, commit=False)
    _mk(db_session, "BGA_061a", 930061, background=True, commit=False)
    plain = _mk(db_session, "BGA_061b", 930062, commit=False)
    _h2(db_session, plain, 7, 2.0)
    db_session.commit()
    url = "/api/experiments/groups/BGA_060/h2-background"
    assert client.put(url, json={"experiment_id": "BGA_061a", "mode": "group"}).status_code == 422
    # Unflagging the empty vial makes the set "no flags", so every vial counts again.
    client.patch("/api/experiments/BGA_061a", json={"is_background": False})
    assert client.put(url, json={"experiment_id": "BGA_061a", "mode": "group"}).status_code == 200
