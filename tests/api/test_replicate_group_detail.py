"""API tests for the group-by-base-id resource (issue #87, Phase 1).

Covers `GET /api/experiments/groups/{base_id}` and
`GET /api/experiments/groups/{base_id}/rollup`, plus route-ordering and
wrapper-regression coverage for the refactored `/{experiment_id}/replicate-group`
and `/{experiment_id}/rollup` endpoints (see tests/api/test_experiment_rollup.py
for the pre-existing byte-identical assertions those two endpoints must
continue to satisfy).
"""
from __future__ import annotations
import pytest
from sqlalchemy import text

from database.models import Experiment, ExperimentalResults, ScalarResults
from database.models.conditions import ExperimentalConditions
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.enums import ExperimentStatus, AmountUnit


@pytest.fixture()
def reporting_views(db_session):
    """Reporting views are DDL, created inside the test transaction (rolled
    back per test), mirroring tests/api/test_experiment_rollup.py."""
    from database.event_listeners import _VIEWS
    for view_name, _ in _VIEWS:
        db_session.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
    for _, view_sql in _VIEWS:
        db_session.execute(text(view_sql))
    db_session.flush()
    yield


def _make_experiment(db, experiment_id, number, **kwargs):
    exp = Experiment(experiment_id=experiment_id, experiment_number=number,
                      status=ExperimentStatus.ONGOING, **kwargs)
    db.add(exp)
    db.flush()
    return exp


def _make_conditions(db, exp, **kwargs):
    cond = ExperimentalConditions(experiment_id=exp.experiment_id, experiment_fk=exp.id, **kwargs)
    db.add(cond)
    db.flush()
    return cond


def _add_additive(db, cond, compound_name, amount, unit=AmountUnit.GRAM):
    compound = db.query(Compound).filter(Compound.name == compound_name).first()
    if compound is None:
        compound = Compound(name=compound_name, molecular_weight_g_mol=100.0)
        db.add(compound)
        db.flush()
    additive = ChemicalAdditive(experiment_id=cond.id, compound_id=compound.id, amount=amount, unit=unit)
    db.add(additive)
    db.flush()
    return additive


class TestGroupDetailEndpoint:
    def test_group_with_parent(self, client, db_session, reporting_views):
        parent = _make_experiment(db_session, "RGD_001", 9900)
        _make_experiment(db_session, "RGD_001a", 9901)
        _make_experiment(db_session, "RGD_001b", 9902)
        db_session.commit()
        resp = client.get("/api/experiments/groups/RGD_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["base_experiment_id"] == "RGD_001"
        assert data["parent"]["id"] == parent.id
        assert data["member_count"] == 2
        assert [m["replicate_label"] for m in data["members"]] == ["a", "b"]

    def test_group_orphan_no_parent_row(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RGD_002a", 9910)
        _make_experiment(db_session, "RGD_002b", 9911)
        db_session.commit()
        resp = client.get("/api/experiments/groups/RGD_002")
        assert resp.status_code == 200
        data = resp.json()
        assert data["parent"] is None
        assert data["member_count"] == 2

    def test_group_parent_dash0_spelling(self, client, db_session, reporting_views):
        parent = _make_experiment(db_session, "RGD_003-0", 9920)
        _make_experiment(db_session, "RGD_003a", 9921)
        db_session.commit()
        resp = client.get("/api/experiments/groups/RGD_003")
        data = resp.json()
        assert data["parent"]["id"] == parent.id
        assert data["parent"]["experiment_id"] == "RGD_003-0"

    def test_group_parent_dash1_spelling(self, client, db_session, reporting_views):
        parent = _make_experiment(db_session, "RGD_004-1", 9930)
        _make_experiment(db_session, "RGD_004a", 9931)
        db_session.commit()
        resp = client.get("/api/experiments/groups/RGD_004")
        data = resp.json()
        assert data["parent"]["id"] == parent.id
        assert data["parent"]["experiment_id"] == "RGD_004-1"

    def test_group_t_vial_shares_letter_with_parent_vial(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RGD_005", 9940)
        member_a = _make_experiment(db_session, "RGD_005a", 9941)
        member_a_t7 = _make_experiment(db_session, "RGD_005a-t7", 9942)
        db_session.commit()
        resp = client.get("/api/experiments/groups/RGD_005")
        data = resp.json()
        assert data["member_count"] == 2
        ids = [m["id"] for m in data["members"]]
        assert member_a.id in ids and member_a_t7.id in ids
        assert all(m["replicate_label"] == "a" for m in data["members"])
        # NULLs-first on id_timepoint_days: bare 'a' (no timepoint) orders before 'a-t7'
        assert data["members"][0]["id"] == member_a.id
        assert data["members"][1]["id"] == member_a_t7.id
        assert data["members"][1]["id_timepoint_days"] == pytest.approx(7.0)

    def test_group_divergent_temperature(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RGD_006", 9950)
        a = _make_experiment(db_session, "RGD_006a", 9951)
        b = _make_experiment(db_session, "RGD_006b", 9952)
        _make_conditions(db_session, a, temperature_c=60.0, rock_mass_g=100.0)
        _make_conditions(db_session, b, temperature_c=80.0, rock_mass_g=100.0)
        db_session.commit()
        resp = client.get("/api/experiments/groups/RGD_006")
        data = resp.json()
        assert "temperature_c" in data["divergent_fields"]
        assert "temperature_c" not in data["shared_conditions"]
        assert data["shared_conditions"]["rock_mass_g"] == 100.0
        by_label = {m["replicate_label"]: m for m in data["members"]}
        assert by_label["a"]["conditions"]["temperature_c"] == 60.0
        assert by_label["b"]["conditions"]["temperature_c"] == 80.0
        assert "rock_mass_g" not in by_label["a"]["conditions"]

    def test_group_divergent_additives(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RGD_007", 9960)
        a = _make_experiment(db_session, "RGD_007a", 9961)
        b = _make_experiment(db_session, "RGD_007b", 9962)
        cond_a = _make_conditions(db_session, a)
        cond_b = _make_conditions(db_session, b)
        _add_additive(db_session, cond_a, "Iron Oxide", 5.0)
        _add_additive(db_session, cond_b, "Magnetite", 3.0)
        db_session.commit()
        resp = client.get("/api/experiments/groups/RGD_007")
        data = resp.json()
        assert data["additives_diverge"] is True
        assert data["additives_summary"] is None
        assert data["additive_names"] is None

    def test_group_agreeing_additives(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RGD_008", 9970)
        a = _make_experiment(db_session, "RGD_008a", 9971)
        b = _make_experiment(db_session, "RGD_008b", 9972)
        cond_a = _make_conditions(db_session, a)
        cond_b = _make_conditions(db_session, b)
        _add_additive(db_session, cond_a, "Iron Oxide", 5.0)
        _add_additive(db_session, cond_b, "Iron Oxide", 5.0)
        db_session.commit()
        resp = client.get("/api/experiments/groups/RGD_008")
        data = resp.json()
        assert data["additives_diverge"] is False
        assert data["additives_summary"] is not None
        assert data["additive_names"] == "Iron Oxide"

    def test_group_unknown_base_id_404(self, client, db_session, reporting_views):
        resp = client.get("/api/experiments/groups/NOPE_DOES_NOT_EXIST")
        assert resp.status_code == 404

    def test_route_ordering_groups_not_captured_by_experiment_id(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RGD_009", 9980)
        _make_experiment(db_session, "RGD_009a", 9981)
        db_session.commit()
        resp = client.get("/api/experiments/groups/RGD_009")
        assert resp.status_code == 200
        data = resp.json()
        # ExperimentDetailResponse (the catch-all's shape) has no member_count field
        assert "member_count" in data
        assert data["base_experiment_id"] == "RGD_009"


class TestGroupRollupEndpoint:
    def test_group_rollup_matches_existing_rollup_endpoint(self, client, db_session, reporting_views):
        _make_experiment(db_session, "RGD_010", 9990)
        for i, letter in enumerate("ab"):
            member = _make_experiment(db_session, f"RGD_010{letter}", 9991 + i)
            result = ExperimentalResults(
                experiment_fk=member.id,
                time_post_reaction_days=7.0, time_post_reaction_bucket_days=7.0,
                is_primary_timepoint_result=True, description="t=7",
            )
            db_session.add(result)
            db_session.flush()
            db_session.add(ScalarResults(result_id=result.id, gross_ammonium_concentration_mM=float(i + 1)))
        db_session.commit()
        via_group = client.get("/api/experiments/groups/RGD_010/rollup").json()
        via_wrapper = client.get("/api/experiments/RGD_010a/rollup").json()
        assert via_group == via_wrapper
        assert via_group[0]["n_vials"] == 2

    def test_group_rollup_unknown_base_id_404(self, client, db_session, reporting_views):
        resp = client.get("/api/experiments/groups/NOPE_DOES_NOT_EXIST/rollup")
        assert resp.status_code == 404
