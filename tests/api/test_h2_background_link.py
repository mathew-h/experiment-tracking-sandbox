"""PUT/DELETE/GET /api/experiments/groups/{base_id}/h2-background (issue #144)."""
from unittest.mock import patch

import pytest
from sqlalchemy import text

from database.models import Experiment, ExperimentalResults, H2BackgroundLink, ScalarResults
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


def _exp(db, exp_id, number, base=None):
    exp = Experiment(experiment_id=exp_id, experiment_number=number,
                     status=ExperimentStatus.COMPLETED)
    db.add(exp)
    db.flush()
    if base is not None:
        exp.base_experiment_id = base
        db.flush()
    return exp


def _h2(db, exp, bucket, umol):
    r = ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=bucket,
                            time_post_reaction_bucket_days=bucket,
                            is_primary_timepoint_result=True)
    db.add(r)
    db.flush()
    db.add(ScalarResults(result_id=r.id, h2_concentration=100.0, h2_micromoles=umol))
    db.flush()
    db.execute(text("UPDATE scalar_results SET h2_concentration = 100, h2_micromoles = :u WHERE result_id = :r"),
               {"u": umol, "r": r.id})


@pytest.fixture()
def seeded(db_session):
    """Sample group H2L_001 (a, b) and background group H2L_002 with t7/t14 vials."""
    db = db_session
    _exp(db, "H2L_001a", 95001, base="H2L_001")
    _exp(db, "H2L_001b", 95002, base="H2L_001")
    bg = _exp(db, "H2L_002a-t7", 95003, base="H2L_002")
    _h2(db, bg, 7, 3.0)
    bg2 = _exp(db, "H2L_002a-t14", 95004, base="H2L_002")
    _h2(db, bg2, 14, 4.0)
    _exp(db, "H2L_003", 95005)  # no H2 results
    db.commit()
    return db


URL = "/api/experiments/groups/H2L_001/h2-background"


def _logs(db):
    return db.query(ModificationsLog).filter(
        ModificationsLog.modified_table == "h2_background_links").count()


def test_put_group_mode_creates_link(client, seeded):
    resp = client.put(URL, json={"experiment_id": "H2L_002a-t7", "mode": "group"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "group"
    assert body["background_ref"] == "H2L_002"
    assert body["created_by"] == "test@addisenergy.com"
    assert body["updated_at"] is not None


def test_put_vial_mode_stores_stem(client, seeded):
    resp = client.put(URL, json={"experiment_id": "H2L_002a-t7", "mode": "vial"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "vial"
    assert resp.json()["background_ref"] == "H2L_002a"
    link = seeded.query(H2BackgroundLink).one()
    assert link.background_stem_id == "H2L_002a"
    assert link.background_base_id is None


def test_put_self_reference_422(client, seeded):
    r1 = client.put(URL, json={"experiment_id": "H2L_001a", "mode": "group"})
    assert r1.status_code == 422
    r2 = client.put(URL, json={"experiment_id": "H2L_001b", "mode": "vial"})
    assert r2.status_code == 422
    assert seeded.query(H2BackgroundLink).count() == 0


def test_put_background_without_h2_422(client, seeded):
    resp = client.put(URL, json={"experiment_id": "H2L_003", "mode": "group"})
    assert resp.status_code == 422
    assert seeded.query(H2BackgroundLink).count() == 0


def test_put_unknown_group_404(client, seeded):
    resp = client.put("/api/experiments/groups/H2L_NOGROUP/h2-background",
                      json={"experiment_id": "H2L_002a-t7", "mode": "group"})
    assert resp.status_code == 404


def test_put_unknown_experiment_404(client, seeded):
    resp = client.put(URL, json={"experiment_id": "H2L_MISSING", "mode": "group"})
    assert resp.status_code == 404


def test_second_put_replaces(client, seeded):
    client.put(URL, json={"experiment_id": "H2L_002a-t7", "mode": "group"})
    resp = client.put(URL, json={"experiment_id": "H2L_002a-t14", "mode": "vial"})
    assert resp.status_code == 200
    (link,) = seeded.query(H2BackgroundLink).all()
    assert link.background_stem_id == "H2L_002a"
    assert link.background_base_id is None


def test_put_and_delete_each_log_once(client, seeded):
    assert _logs(seeded) == 0
    client.put(URL, json={"experiment_id": "H2L_002a-t7", "mode": "group"})
    assert _logs(seeded) == 1
    client.put(URL, json={"experiment_id": "H2L_002a-t7", "mode": "vial"})
    assert _logs(seeded) == 2
    assert client.delete(URL).status_code == 204
    assert _logs(seeded) == 3
    types = [m.modification_type for m in seeded.query(ModificationsLog)
             .filter(ModificationsLog.modified_table == "h2_background_links")
             .order_by(ModificationsLog.id)]
    assert types == ["create", "update", "delete"]


def test_delete_204(client, seeded):
    client.put(URL, json={"experiment_id": "H2L_002a-t7", "mode": "group"})
    assert client.delete(URL).status_code == 204
    assert seeded.query(H2BackgroundLink).count() == 0
    # No link left: still 204, and nothing more is logged.
    n = _logs(seeded)
    assert client.delete(URL).status_code == 204
    assert _logs(seeded) == n


def test_delete_unknown_group_404(client, seeded):
    assert client.delete("/api/experiments/groups/H2L_NOGROUP/h2-background").status_code == 404


def test_rollup_endpoint_ordered(client, seeded, reporting_views):
    sample = _exp(seeded, "H2L_001c", 95010, base="H2L_001")
    _h2(seeded, sample, 14, 10.0)
    _h2(seeded, seeded.query(Experiment).filter_by(experiment_id="H2L_001a").one(), 7, 8.0)
    client.put(URL, json={"experiment_id": "H2L_002a-t7", "mode": "group"})
    resp = client.get(URL + "/rollup")
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["time_post_reaction_bucket_days"] for r in rows] == [7, 14]
    assert rows[0]["mean_net_h2_micromoles"] == pytest.approx(5.0)
    assert rows[1]["mean_net_h2_micromoles"] == pytest.approx(6.0)
    missing = client.get("/api/experiments/groups/H2L_NOGROUP/h2-background/rollup")
    assert missing.status_code == 404


def test_put_does_not_recalculate(client, seeded):
    with patch("backend.api.routers.experiments.recalculate") as rc:
        resp = client.put(URL, json={"experiment_id": "H2L_002a-t7", "mode": "group"})
    assert resp.status_code == 200
    rc.assert_not_called()
