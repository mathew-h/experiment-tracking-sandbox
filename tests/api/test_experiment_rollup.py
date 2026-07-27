"""API tests for /rollup and /replicate-group (issue #70 P2).

Views are DDL created inside the test transaction (rolled back per test),
mirroring tests/views/test_v_results_scalar_rollup.py's view_db fixture.
"""
import pytest
from sqlalchemy import text

from database.models import Experiment, ExperimentalResults, ScalarResults
from database.models.enums import ExperimentStatus


@pytest.fixture()
def reporting_views(db_session):
    from database.event_listeners import _VIEWS
    for view_name, _ in _VIEWS:
        db_session.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
    for _, view_sql in _VIEWS:
        db_session.execute(text(view_sql))
    db_session.flush()
    yield


def _make_experiment(db, experiment_id, number):
    exp = Experiment(experiment_id=experiment_id, experiment_number=number,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    return exp


def _add_primary_scalar(db, exp, bucket, gross_nh4):
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=bucket, time_post_reaction_bucket_days=bucket,
        is_primary_timepoint_result=True, description=f"t={bucket}",
    )
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id,
                         gross_ammonium_concentration_mM=gross_nh4))
    db.flush()
    return result


class TestRollupEndpoint:
    def test_rollup_stats_for_replicate_set(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RUP_001", 9750)
        for i, letter in enumerate("abc"):
            member = _make_experiment(db_session, f"RUP_001{letter}", 9751 + i)
            _add_primary_scalar(db_session, member, 7.0, float(i + 1))  # 1, 2, 3
        db_session.commit()
        resp = client.get("/api/experiments/RUP_001a/rollup")
        assert resp.status_code == 200
        (row,) = resp.json()
        assert row["base_experiment_id"] == "RUP_001"
        assert row["n_replicates"] == 3
        assert row["mean_gross_ammonium_mM"] == pytest.approx(2.0)
        assert row["sd_gross_ammonium_mM"] == pytest.approx(1.0)

    def test_rollup_same_series_from_parent_and_member(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RUP_002", 9760)
        member = _make_experiment(db_session, "RUP_002a", 9761)
        _add_primary_scalar(db_session, member, 3.0, 5.0)
        db_session.commit()
        from_parent = client.get("/api/experiments/RUP_002/rollup").json()
        from_member = client.get("/api/experiments/RUP_002a/rollup").json()
        assert from_parent == from_member

    def test_rollup_404_unknown_experiment(self, client, db_session, reporting_views):
        assert client.get("/api/experiments/NOPE_999/rollup").status_code == 404

    def test_rollup_excludes_outlier_flagged_member(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RUP_003", 9765)
        members = []
        for i, letter in enumerate("abc"):
            member = _make_experiment(db_session, f"RUP_003{letter}", 9766 + i)
            _add_primary_scalar(db_session, member, 7.0, float(i + 1))  # 1, 2, 3
            members.append(member)
        members[2].is_outlier = True
        db_session.commit()
        (row,) = client.get("/api/experiments/RUP_003a/rollup").json()
        assert row["n_replicates"] == 2
        assert row["mean_gross_ammonium_mM"] == pytest.approx(1.5)


class TestReplicateGroupEndpoint:
    def test_group_from_parent_and_member(self, client, db_session):
        parent = _make_experiment(db_session, "RGRP_001", 9770)
        for i, letter in enumerate("ab"):
            _make_experiment(db_session, f"RGRP_001{letter}", 9771 + i)
        db_session.commit()
        for query_id in ("RGRP_001", "RGRP_001b"):
            data = client.get(f"/api/experiments/{query_id}/replicate-group").json()
            assert data["base_experiment_id"] == "RGRP_001"
            assert data["parent"]["id"] == parent.id
            assert [m["replicate_label"] for m in data["members"]] == ["a", "b"]

    def test_group_empty_for_non_replicate(self, client, db_session):
        _make_experiment(db_session, "RGRP_SOLO_001", 9780)
        db_session.commit()
        data = client.get("/api/experiments/RGRP_SOLO_001/replicate-group").json()
        assert data["members"] == []
        assert data["parent"]["experiment_id"] == "RGRP_SOLO_001"

    def test_group_orphan_member_lists_siblings(self, client, db_session):
        _make_experiment(db_session, "RGRP_ORPH_001a", 9790)
        _make_experiment(db_session, "RGRP_ORPH_001b", 9791)
        db_session.commit()
        data = client.get("/api/experiments/RGRP_ORPH_001a/replicate-group").json()
        assert data["parent"] is None
        assert [m["replicate_label"] for m in data["members"]] == ["a", "b"]

    def test_replicate_group_exposes_is_outlier(self, client, db_session):
        _make_experiment(db_session, "RGRP_OUT_001", 9795)
        flagged = _make_experiment(db_session, "RGRP_OUT_001a", 9796)
        flagged.is_outlier = True
        db_session.commit()
        data = client.get("/api/experiments/RGRP_OUT_001/replicate-group").json()
        assert data["parent"]["is_outlier"] is False
        assert data["members"][0]["is_outlier"] is True


class TestRollupFromHandEnteredResults:
    """Issue #83: results created via POST /api/results (the Add Results modal
    path) must land in per-day rollup buckets, not one bucket=null row."""

    def _post_result_with_scalar(self, client, experiment_pk, day, gross_nh4):
        resp = client.post("/api/results", json={
            "experiment_fk": experiment_pk,
            "description": f"day {day}",
            "time_post_reaction_days": day,
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["time_post_reaction_bucket_days"] == pytest.approx(day)
        resp = client.post("/api/results/scalar", json={
            "result_id": body["id"],
            "gross_ammonium_concentration_mM": gross_nh4,
        })
        assert resp.status_code == 201

    def test_hand_entered_results_roll_up_per_day(
        self, client, db_session, reporting_views
    ):
        _make_experiment(db_session, "RUP_083", 9800)
        a = _make_experiment(db_session, "RUP_083a", 9801)
        b = _make_experiment(db_session, "RUP_083b", 9802)
        db_session.commit()
        # day 7 on both replicates, day 14 on replicate a only — via API
        self._post_result_with_scalar(client, a.id, 7.0, 1.0)
        self._post_result_with_scalar(client, b.id, 7.0, 3.0)
        self._post_result_with_scalar(client, a.id, 14.0, 5.0)
        rows = client.get("/api/experiments/RUP_083a/rollup").json()
        buckets = [r["time_post_reaction_bucket_days"] for r in rows]
        assert buckets == [7.0, 14.0]
        day7, day14 = rows
        assert day7["n_replicates"] == 2
        assert day7["mean_gross_ammonium_mM"] == pytest.approx(2.0)
        assert day14["n_replicates"] == 1
        assert day14["mean_gross_ammonium_mM"] == pytest.approx(5.0)
