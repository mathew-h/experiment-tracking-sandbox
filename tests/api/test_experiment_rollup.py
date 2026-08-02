"""API tests for /rollup and /replicate-group (issue #70 P2).

Views are DDL created inside the test transaction (rolled back per test),
mirroring tests/views/test_v_results_scalar_rollup.py's view_db fixture.
"""
import pytest
from sqlalchemy import select, text

from database.models import Experiment, ExperimentalResults, ScalarResults
from database.models.conditions import ExperimentalConditions
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


def _add_primary_scalar(db, exp, bucket, gross_nh4, h2_ppm=None):
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=bucket, time_post_reaction_bucket_days=bucket,
        is_primary_timepoint_result=True, description=f"t={bucket}",
    )
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id,
                         gross_ammonium_concentration_mM=gross_nh4,
                         h2_concentration=h2_ppm))
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
        assert row["n_vials"] == 3
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
        assert row["n_vials"] == 2
        assert row["mean_gross_ammonium_mM"] == pytest.approx(1.5)


class TestRollupH2Ppm:
    """Issue #90: rollup view/endpoint expose mean_h2_ppm / sd_h2_ppm
    (AVG / stddev_samp over scalar_results.h2_concentration)."""

    def test_mean_h2_ppm_matches_member_values(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RUP_H2_001", 9850)
        for i, letter in enumerate("abc"):
            member = _make_experiment(db_session, f"RUP_H2_001{letter}", 9851 + i)
            _add_primary_scalar(db_session, member, 7.0, 1.0, h2_ppm=float((i + 1) * 100))  # 100, 200, 300
        db_session.commit()
        (row,) = client.get("/api/experiments/RUP_H2_001a/rollup").json()
        assert row["n_vials"] == 3
        assert row["mean_h2_ppm"] == pytest.approx(200.0)
        assert row["sd_h2_ppm"] == pytest.approx(100.0)

    def test_sd_h2_ppm_null_for_single_member(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RUP_H2_002", 9860)
        member = _make_experiment(db_session, "RUP_H2_002a", 9861)
        _add_primary_scalar(db_session, member, 7.0, 1.0, h2_ppm=420.0)
        db_session.commit()
        (row,) = client.get("/api/experiments/RUP_H2_002a/rollup").json()
        assert row["n_vials"] == 1
        assert row["mean_h2_ppm"] == pytest.approx(420.0)
        assert row["sd_h2_ppm"] is None

    def test_outlier_member_excluded_from_mean_h2_ppm(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RUP_H2_003", 9865)
        members = []
        for i, letter in enumerate("abc"):
            member = _make_experiment(db_session, f"RUP_H2_003{letter}", 9866 + i)
            _add_primary_scalar(db_session, member, 7.0, 1.0, h2_ppm=float((i + 1) * 100))  # 100, 200, 300
            members.append(member)
        members[2].is_outlier = True  # drop the 300 value
        db_session.commit()
        (row,) = client.get("/api/experiments/RUP_H2_003a/rollup").json()
        assert row["n_vials"] == 2
        assert row["mean_h2_ppm"] == pytest.approx(150.0)


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


class TestReplicateGroupWrapperShapes:
    """Issue #87 review finding: /{experiment_id}/replicate-group is
    deliberately NOT delegated to replicate_groups.resolve_group() — it keeps
    its original row-relative parent/member resolution byte-for-byte. These
    lock in the two shapes where the two resolution strategies diverge, plus
    a re-confirmation of the orphan-set case (the actual bug #87 fixes,
    served by the new /groups/{base_id} endpoint instead)."""

    def test_bare_sequential_rerun_is_its_own_parent_with_no_members(self, client, db_session):
        """SERUM_001-2 has no replicate letter, so the old logic treats it as
        its own 'parent' with an empty member list — even though its base
        stem SERUM_001 has a real lettered a/b/c set. Resolving by base-ID
        string (resolve_group) would instead surface that a/b/c set; the
        wrapper must NOT do that.
        """
        _make_experiment(db_session, "RGRP_SEQ_001", 9970)
        for i, letter in enumerate("abc"):
            _make_experiment(db_session, f"RGRP_SEQ_001{letter}", 9971 + i)
        sequential = _make_experiment(db_session, "RGRP_SEQ_001-2", 9974)
        db_session.commit()
        data = client.get("/api/experiments/RGRP_SEQ_001-2/replicate-group").json()
        assert data["parent"]["id"] == sequential.id
        assert data["parent"]["experiment_id"] == "RGRP_SEQ_001-2"
        assert data["members"] == []

    def test_letter_sequential_rerun_parent_is_lettered_sibling(self, client, db_session):
        """SERUM_001a-2 (letter + sequential) links to its lettered sibling
        SERUM_001a as parent_experiment_fk (P5 lineage rule). The wrapper's
        FK-based member lookup then returns whatever else points at
        SERUM_001a via parent_experiment_fk — which is just the rerun itself
        (it satisfies its own member criteria: parent_experiment_fk ==
        member_a.id AND replicate_label is not null) — never the sibling
        SERUM_001b, which links to the group parent instead, not member_a.
        """
        _make_experiment(db_session, "RGRP_LS_001", 9980)
        member_a = _make_experiment(db_session, "RGRP_LS_001a", 9981)
        _make_experiment(db_session, "RGRP_LS_001b", 9982)
        rerun = _make_experiment(db_session, "RGRP_LS_001a-2", 9983)
        db_session.commit()
        assert rerun.parent_experiment_fk == member_a.id  # lineage precondition
        data = client.get("/api/experiments/RGRP_LS_001a-2/replicate-group").json()
        assert data["parent"]["id"] == member_a.id
        assert data["parent"]["experiment_id"] == "RGRP_LS_001a"
        assert [m["id"] for m in data["members"]] == [rerun.id]
        assert data["members"][0]["experiment_id"] == "RGRP_LS_001a-2"


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
        assert day7["n_vials"] == 2
        assert day7["mean_gross_ammonium_mM"] == pytest.approx(2.0)
        assert day14["n_vials"] == 1
        assert day14["mean_gross_ammonium_mM"] == pytest.approx(5.0)


class TestGroupLettersVsVials:
    """Issue #98: the group response must distinguish replicates from vials."""

    def _make_2x2(self, db_session, prefix: str, start: int):
        n = start
        for letter in ("a", "b"):
            for day in (1, 3):
                db_session.add(Experiment(
                    experiment_id=f"{prefix}_001{letter}-t{day}",
                    experiment_number=n, status=ExperimentStatus.ONGOING,
                ))
                n += 1
        db_session.commit()

    def test_reports_two_replicates_and_four_vials(self, client, db_session, reporting_views):
        """Issue #98 AC5."""
        self._make_2x2(db_session, "G98AC5", 9910)
        resp = client.get("/api/experiments/groups/G98AC5_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["replicate_count"] == 2
        assert data["member_count"] == 4          # unchanged per-vial meaning
        assert len(data["members"]) == 4
        assert [r["replicate_label"] for r in data["replicates"]] == ["a", "b"]
        assert [
            [v["experiment_id"] for v in r["vials"]] for r in data["replicates"]
        ] == [
            ["G98AC5_001a-t1", "G98AC5_001a-t3"],
            ["G98AC5_001b-t1", "G98AC5_001b-t3"],
        ]

    def test_vials_carry_timepoint_and_result_count(self, client, db_session, reporting_views):
        """Gap 6: result_count is per vial, not per letter."""
        self._make_2x2(db_session, "G98RC", 9920)
        vial = db_session.execute(
            select(Experiment).where(Experiment.experiment_id == "G98RC_001a-t1")
        ).scalar_one()
        db_session.add(ExperimentalResults(
            experiment_fk=vial.id,
            time_post_reaction_days=1.0, time_post_reaction_bucket_days=1.0,
            is_primary_timepoint_result=True, description="t1",
        ))
        db_session.commit()

        resp = client.get("/api/experiments/groups/G98RC_001")
        letter_a = resp.json()["replicates"][0]
        by_id = {v["experiment_id"]: v for v in letter_a["vials"]}
        assert by_id["G98RC_001a-t1"]["result_count"] == 1
        assert by_id["G98RC_001a-t1"]["id_timepoint_days"] == 1.0
        assert by_id["G98RC_001a-t3"]["result_count"] == 0

    def test_single_vial_letters_still_produce_one_vial_each(self, client, db_session, reporting_views):
        """D10 regression guard: a plain a/b/c set nests one vial per letter."""
        for i, letter in enumerate("abc"):
            db_session.add(Experiment(
                experiment_id=f"G98PLAIN_001{letter}", experiment_number=9930 + i,
                status=ExperimentStatus.ONGOING,
            ))
        db_session.commit()
        data = client.get("/api/experiments/groups/G98PLAIN_001").json()
        assert data["replicate_count"] == 3
        assert data["member_count"] == 3
        assert all(len(r["vials"]) == 1 for r in data["replicates"])

    def test_parent_reports_its_own_result_count(self, client, db_session, reporting_views):
        """Regression: the parent's result_count was hardcoded 0, so a parent
        with results displayed "0" on the group page (worse than the "--" it
        showed before the parent field was widened)."""
        parent = Experiment(experiment_id="G98PAR_001", experiment_number=9690,
                            status=ExperimentStatus.ONGOING)
        db_session.add(parent)
        db_session.add(Experiment(experiment_id="G98PAR_001a", experiment_number=9691,
                                  status=ExperimentStatus.ONGOING))
        db_session.flush()
        for day in (1.0, 3.0):
            db_session.add(ExperimentalResults(
                experiment_fk=parent.id,
                time_post_reaction_days=day, time_post_reaction_bucket_days=day,
                is_primary_timepoint_result=True, description=f"t{day}",
            ))
        db_session.commit()

        data = client.get("/api/experiments/groups/G98PAR_001").json()

        assert data["parent"]["result_count"] == 2
        assert data["parent"]["conditions"] == {}   # deliberately not computed
        assert data["member_count"] == 1            # parent is NOT a member


class TestGroupConditionsDivergence:
    """Issue #98 AC8 / D5: a vial with no conditions row must not push every
    field into divergent_fields."""

    def test_missing_conditions_row_does_not_amplify_divergence(self, client, db_session, reporting_views):
        a = Experiment(experiment_id="G98DIV_001a-t1", experiment_number=9940,
                       status=ExperimentStatus.ONGOING)
        b = Experiment(experiment_id="G98DIV_001b-t1", experiment_number=9941,
                       status=ExperimentStatus.ONGOING)
        no_cond = Experiment(experiment_id="G98DIV_001b-t3", experiment_number=9942,
                             status=ExperimentStatus.ONGOING)
        db_session.add_all([a, b, no_cond])
        db_session.flush()
        for exp in (a, b):
            db_session.add(ExperimentalConditions(
                experiment_fk=exp.id, experiment_id=exp.experiment_id,
                temperature_c=90.0, experiment_type="Serum", rock_mass_g=5.0,
            ))
        db_session.commit()

        data = client.get("/api/experiments/groups/G98DIV_001").json()

        assert data["shared_conditions"]["temperature_c"] == 90.0
        assert data["shared_conditions"]["rock_mass_g"] == 5.0
        assert "temperature_c" not in data["divergent_fields"]
        assert "rock_mass_g" not in data["divergent_fields"]

    def test_real_divergence_is_still_reported(self, db_session, client, reporting_views):
        """D6: the comparison grain stays per-vial, so genuinely differing
        values still surface -- including between two vials of one letter."""
        a1 = Experiment(experiment_id="G98REAL_001a-t1", experiment_number=9950,
                        status=ExperimentStatus.ONGOING)
        a3 = Experiment(experiment_id="G98REAL_001a-t3", experiment_number=9951,
                        status=ExperimentStatus.ONGOING)
        db_session.add_all([a1, a3])
        db_session.flush()
        db_session.add(ExperimentalConditions(
            experiment_fk=a1.id, experiment_id=a1.experiment_id, rock_mass_g=5.0))
        db_session.add(ExperimentalConditions(
            experiment_fk=a3.id, experiment_id=a3.experiment_id, rock_mass_g=5.4))
        db_session.commit()

        data = client.get("/api/experiments/groups/G98REAL_001").json()

        assert "rock_mass_g" in data["divergent_fields"]
        vials = data["replicates"][0]["vials"]
        assert {v["conditions"]["rock_mass_g"] for v in vials} == {5.0, 5.4}

    def test_all_vials_missing_conditions_yields_empty_scan(self, client, db_session, reporting_views):
        for i, letter in enumerate("ab"):
            db_session.add(Experiment(
                experiment_id=f"G98NONE_001{letter}", experiment_number=9960 + i,
                status=ExperimentStatus.ONGOING,
            ))
        db_session.commit()
        data = client.get("/api/experiments/groups/G98NONE_001").json()
        assert data["divergent_fields"] == []
        assert data["shared_conditions"] == {}


class TestReplicateGroupWrapperOrdering:
    """Gap 5: /{experiment_id}/replicate-group ordered by replicate_label only,
    so member order was nondeterministic for duplicate labels."""

    def test_member_order_is_deterministic_for_duplicate_labels(self, client, db_session):
        db_session.add(Experiment(experiment_id="G98ORD_001a-t3", experiment_number=9971,
                                   status=ExperimentStatus.ONGOING))
        db_session.add(Experiment(experiment_id="G98ORD_001a-t1", experiment_number=9970,
                                   status=ExperimentStatus.ONGOING))
        db_session.commit()
        data = client.get("/api/experiments/G98ORD_001a-t1/replicate-group").json()
        assert [m["experiment_id"] for m in data["members"]] == [
            "G98ORD_001a-t1", "G98ORD_001a-t3",
        ]
