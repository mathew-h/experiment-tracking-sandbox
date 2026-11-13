"""Issue #191 (backend sweep PR 3): query counts that must not grow with row count.

Each test runs the same request against a small and a larger data set and
asserts the number of SQL statements is the same for both, and under a fixed
ceiling. Statements are counted with a `before_cursor_execute` listener on the
Engine class, so every connection the request uses is seen.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from database.models.chemicals import ChemicalAdditive, Compound
from database.models.conditions import ExperimentalConditions
from database.models.enums import AmountUnit, ExperimentStatus, NoteType
from database.models.experiments import Experiment, ExperimentNotes
from database.models.results import ExperimentalResults, ICPResults, ScalarResults


@contextmanager
def count_queries():
    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", _record)


def _compounds(db, prefix: str) -> list[Compound]:
    compounds = [Compound(name=f"{prefix} Compound {i}", molecular_weight_g_mol=100.0 + i) for i in range(2)]
    db.add_all(compounds)
    db.flush()
    return compounds


def _experiment(db, experiment_id: str, number: int, compounds, *, base=None, label=None,
                results: int = 0, with_icp: bool = False) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id, experiment_number=number, status=ExperimentStatus.ONGOING,
        base_experiment_id=base, replicate_label=label,
        date=datetime(2026, 6, 1, 12, tzinfo=timezone.utc),
    )
    db.add(exp)
    db.flush()
    cond = ExperimentalConditions(experiment_fk=exp.id, experiment_id=experiment_id, experiment_type="Serum",
                                  rock_mass_g=2.0, water_volume_mL=20.0)
    db.add(cond)
    db.flush()
    for order, compound in enumerate(compounds):
        db.add(ChemicalAdditive(experiment_id=cond.id, compound_id=compound.id, amount=1.0 + order,
                                unit=AmountUnit.GRAM, addition_order=order))
    db.add(ExperimentNotes(experiment_fk=exp.id, experiment_id=experiment_id,
                           note_text=f"about {experiment_id}", note_type=NoteType.description))
    for day in range(results):
        result = ExperimentalResults(experiment_fk=exp.id,
                                     time_post_reaction_days=float(day),
                                     time_post_reaction_bucket_days=float(day),
                                     is_primary_timepoint_result=True)
        db.add(result)
        db.flush()
        db.add(ScalarResults(result_id=result.id, h2_concentration=100.0 + day,
                             gas_sampling_volume_ml=5.0, gas_sampling_pressure_MPa=0.1,
                             gross_ammonium_concentration_mM=1.0 + day,
                             measurement_date=datetime(2026, 6, 2 + day, 12, tzinfo=timezone.utc)))
        if with_icp:
            db.add(ICPResults(result_id=result.id, fe=1.0 + day))
    return exp


def _flat_set(db, prefix: str, start: int, count: int) -> None:
    compounds = _compounds(db, prefix)
    for i in range(count):
        _experiment(db, f"{prefix}_{i + 1:03d}", start + i, compounds, results=1)
    db.commit()


def _grouped_set(db, prefix: str, start: int, groups: int) -> None:
    compounds = _compounds(db, prefix)
    number = start
    for g in range(groups):
        stem = f"{prefix}_{g + 1:03d}"
        for letter in "abc":
            _experiment(db, f"{stem}{letter}", number, compounds, base=stem, label=letter, results=1)
            number += 1
    db.commit()


def _compound_order(summary: str) -> list[str]:
    """Compound names of an additives summary ("<name> <amount> <unit>; ..."), in order."""
    return [part.rsplit(" ", 2)[0] for part in summary.split("; ")]


def _count(client, url: str) -> tuple[int, dict]:
    with count_queries() as statements:
        resp = client.get(url)
    assert resp.status_code == 200, resp.text
    return len(statements), resp.json()


# ── E-01: experiments list ───────────────────────────────────────────────────

FLAT_CEILING = 8
GROUPED_CEILING = 12


def test_flat_list_query_count_does_not_grow_with_rows(client, db_session):
    _flat_set(db_session, "QCFLATA", 9191000, 3)
    small, body_small = _count(client, "/api/experiments?search=QCFLATA&limit=100")
    _flat_set(db_session, "QCFLATB", 9191100, 15)
    large, body_large = _count(client, "/api/experiments?search=QCFLATB&limit=100")

    assert (len(body_small["items"]), len(body_large["items"])) == (3, 15)
    assert small == large, f"query count grew with rows: {small} for 3 rows, {large} for 15"
    assert large <= FLAT_CEILING, large

    first = body_large["items"][-1]
    assert first["experiment_id"] == "QCFLATB_001"
    assert first["experiment_type"] == "Serum"
    assert first["description"] == "about QCFLATB_001"
    assert _compound_order(first["additives_summary"]) == ["QCFLATB Compound 0", "QCFLATB Compound 1"]
    assert first["last_result_date"] == "2026-06-02"


def test_grouped_list_query_count_does_not_grow_with_groups(client, db_session):
    _grouped_set(db_session, "QCGRPA", 9192000, 2)
    small, body_small = _count(client, "/api/experiments?search=QCGRPA&limit=100&group_replicates=true")
    _grouped_set(db_session, "QCGRPB", 9192100, 8)
    large, body_large = _count(client, "/api/experiments?search=QCGRPB&limit=100&group_replicates=true")

    assert (len(body_small["items"]), len(body_large["items"])) == (2, 8)
    assert small == large, f"query count grew with groups: {small} for 2 groups, {large} for 8"
    assert large <= GROUPED_CEILING, large

    group = body_large["items"][-1]
    assert group["group_display_id"] == "QCGRPB_001"
    assert group["vial_count"] == 3
    assert group["replicate_letters"] == ["a", "b", "c"]
    assert [child["experiment_id"] for child in group["replicates"]] == [
        "QCGRPB_001a", "QCGRPB_001b", "QCGRPB_001c"]
    for child in group["replicates"]:
        assert _compound_order(child["additives_summary"]) == ["QCGRPB Compound 0", "QCGRPB Compound 1"]
    assert {child["description"] for child in group["replicates"]} == {
        "about QCGRPB_001a", "about QCGRPB_001b", "about QCGRPB_001c"}
    assert group["last_result_date"] == "2026-06-02"


def test_additives_summary_is_ordered_by_compound(client, db_session):
    """The summary lists additives in compound-id order whatever order they
    were added in. This is the order the per-row query happened to produce
    before issue #191; the batched query states it."""
    first, second = _compounds(db_session, "QCORDER")
    exp = Experiment(experiment_id="QCORDER_001", experiment_number=9193000, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(experiment_fk=exp.id, experiment_id="QCORDER_001")
    db_session.add(cond)
    db_session.flush()
    # Inserted second-compound first, and with the opposite addition_order.
    db_session.add(ChemicalAdditive(experiment_id=cond.id, compound_id=second.id, amount=9.0,
                                    unit=AmountUnit.GRAM, addition_order=0))
    db_session.flush()
    db_session.add(ChemicalAdditive(experiment_id=cond.id, compound_id=first.id, amount=4.0,
                                    unit=AmountUnit.GRAM, addition_order=1))
    db_session.commit()

    item = client.get("/api/experiments?search=QCORDER").json()["items"][0]
    assert _compound_order(item["additives_summary"]) == ["QCORDER Compound 0", "QCORDER Compound 1"]
    assert item["additives_summary"].count("; ") == 1


# ── E-02: results tab ────────────────────────────────────────────────────────

RESULTS_CEILING = 5


def test_results_tab_query_count_does_not_grow_with_results(client, db_session):
    compounds = _compounds(db_session, "QCRES")
    _experiment(db_session, "QCRES_001", 9194000, compounds, results=2, with_icp=True)
    _experiment(db_session, "QCRES_002", 9194001, compounds, results=9, with_icp=True)
    db_session.commit()

    small, body_small = _count(client, "/api/experiments/QCRES_001/results")
    large, body_large = _count(client, "/api/experiments/QCRES_002/results")
    assert (len(body_small), len(body_large)) == (2, 9)
    assert small == large, f"query count grew with results: {small} for 2, {large} for 9"
    assert large <= RESULTS_CEILING, large
    assert all(row["has_scalar"] and row["has_icp"] for row in body_large)


# ── E-07: background-ammonium recalculation ──────────────────────────────────

BACKGROUND_CEILING = 9


def test_background_ammonium_query_count_does_not_grow_with_results(client, db_session):
    compounds = _compounds(db_session, "QCBKG")
    _experiment(db_session, "QCBKG_001", 9197000, compounds, results=2)
    _experiment(db_session, "QCBKG_002", 9197001, compounds, results=10)
    db_session.commit()

    counts = {}
    for experiment_id in ("QCBKG_001", "QCBKG_002"):
        db_session.expire_all()
        with count_queries() as statements:
            resp = client.patch(f"/api/experiments/{experiment_id}/background-ammonium", json={"value": 0.5})
        assert resp.status_code == 200, resp.text
        counts[experiment_id] = len(statements)
    assert resp.json() == {"updated": 10}
    assert counts["QCBKG_001"] == counts["QCBKG_002"], counts
    assert counts["QCBKG_002"] <= BACKGROUND_CEILING, counts

    db_session.expire_all()
    scalars = (
        db_session.query(ScalarResults)
        .join(ExperimentalResults, ExperimentalResults.id == ScalarResults.result_id)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "QCBKG_002")
        .all()
    )
    assert len(scalars) == 10
    for scalar in scalars:
        assert scalar.background_ammonium_concentration_mM == 0.5
        ammonia_g = (max(0.0, scalar.gross_ammonium_concentration_mM - 0.5) / 1000.0) * (20.0 / 1000.0) * 18.04
        assert scalar.grams_per_ton_yield == pytest.approx(1_000_000.0 * ammonia_g / 2.0)


# ── E-05: conditions cascade ─────────────────────────────────────────────────

CASCADE_CEILING = 10


def _patch_conditions(client, db_session, experiment_id: str) -> int:
    cond_id = db_session.query(ExperimentalConditions.id).filter_by(experiment_id=experiment_id).scalar()
    db_session.expire_all()
    with count_queries() as statements:
        resp = client.patch(f"/api/conditions/{cond_id}", json={"rock_mass_g": 4.0})
    assert resp.status_code == 200, resp.text
    return len(statements)


def test_conditions_cascade_query_count_does_not_grow_with_results(client, db_session):
    compounds = _compounds(db_session, "QCCAS")
    _experiment(db_session, "QCCAS_001", 9195000, compounds, results=2)
    _experiment(db_session, "QCCAS_002", 9195001, compounds, results=10)
    db_session.commit()

    small = _patch_conditions(client, db_session, "QCCAS_001")
    large = _patch_conditions(client, db_session, "QCCAS_002")
    assert small == large, f"query count grew with results: {small} for 2, {large} for 10"
    assert large <= CASCADE_CEILING, large

    # The cascade still reaches every scalar: rock mass doubled, so yields halved.
    db_session.expire_all()
    scalars = (
        db_session.query(ScalarResults)
        .join(ExperimentalResults, ExperimentalResults.id == ScalarResults.result_id)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "QCCAS_002")
        .all()
    )
    assert len(scalars) == 10
    for scalar in scalars:
        ammonia_g = (max(0.0, scalar.gross_ammonium_concentration_mM - 0.2) / 1000.0) * (20.0 / 1000.0) * 18.04
        assert scalar.grams_per_ton_yield == pytest.approx(1_000_000.0 * ammonia_g / 4.0)


# ── E-09: cumulative time across a lineage chain ─────────────────────────────

CHAIN_CEILING = 6


def _chain(db, base: str, start: int, depth: int) -> list[Experiment]:
    """base, base-2, base-3 ... each the child of the one before, each with
    results at days 1 and 4."""
    chain: list[Experiment] = []
    for level in range(depth):
        experiment_id = base if level == 0 else f"{base}-{level + 1}"
        exp = Experiment(experiment_id=experiment_id, experiment_number=start + level,
                         status=ExperimentStatus.ONGOING, base_experiment_id=base,
                         parent_experiment_fk=chain[-1].id if chain else None)
        db.add(exp)
        db.flush()
        for day in (1.0, 4.0):
            db.add(ExperimentalResults(experiment_fk=exp.id, time_post_reaction_days=day,
                                       time_post_reaction_bucket_days=day,
                                       is_primary_timepoint_result=True))
        chain.append(exp)
    db.flush()
    return chain


def _cumulative(db, exp: Experiment) -> list[float]:
    return sorted(
        r.cumulative_time_post_reaction_days
        for r in db.query(ExperimentalResults).filter_by(experiment_fk=exp.id)
    )


def test_cumulative_time_query_count_does_not_grow_with_chain_depth(db_session):
    from backend.services.result_merge_utils import update_cumulative_times_for_chain

    short = _chain(db_session, "QCCHAINA_001", 9198000, 2)
    long = _chain(db_session, "QCCHAINB_001", 9198100, 7)

    counts = []
    for chain in (short, long):
        db_session.expire_all()
        with count_queries() as statements:
            update_cumulative_times_for_chain(db_session, chain[-1].id)
        counts.append(len([s for s in statements if s.lstrip().upper().startswith("SELECT")]))
    assert counts[0] == counts[1], f"SELECT count grew with chain depth: {counts}"
    assert counts[1] <= CHAIN_CEILING, counts

    # Each segment starts where its ancestors' last samples ended (4 days each).
    for level, exp in enumerate(long):
        assert _cumulative(db_session, exp) == [4.0 * level + 1.0, 4.0 * level + 4.0]


def test_cumulative_time_follows_a_parent_outside_the_chain(db_session):
    """A parent with a different base ID is still walked (it is loaded on demand)."""
    from backend.services.result_merge_utils import update_cumulative_times_for_chain

    (outside,) = _chain(db_session, "QCCHAINC_001", 9198200, 1)
    (inside,) = _chain(db_session, "QCCHAIND_001", 9198300, 1)
    inside.parent_experiment_fk = outside.id
    db_session.flush()

    update_cumulative_times_for_chain(db_session, inside.id)
    assert _cumulative(db_session, inside) == [5.0, 8.0]   # 4 days of the outside parent, then 1 and 4
    # The outside experiment belongs to another chain; this call leaves it alone.
    untouched = db_session.query(ExperimentalResults).filter_by(experiment_fk=outside.id).all()
    assert [r.cumulative_time_post_reaction_days for r in untouched] == [None, None]


def test_cumulative_time_is_none_without_a_time_and_survives_a_cycle(db_session):
    from backend.services.result_merge_utils import update_cumulative_times_for_chain

    first, second = _chain(db_session, "QCCHAINE_001", 9198400, 2)
    first.parent_experiment_fk = second.id  # a cycle; the walk must stop, not spin
    undated = ExperimentalResults(experiment_fk=second.id, time_post_reaction_days=None,
                                  is_primary_timepoint_result=False)
    db_session.add(undated)
    db_session.flush()

    update_cumulative_times_for_chain(db_session, second.id)
    assert undated.cumulative_time_post_reaction_days is None
    assert all(value is not None for value in _cumulative(db_session, first))


# ── E-10: replicate group page ───────────────────────────────────────────────

GROUP_DETAIL_CEILING = 12


def _replicate_group(db, stem: str, start: int, letters: str) -> None:
    compounds = _compounds(db, stem)
    for offset, letter in enumerate(letters):
        _experiment(db, f"{stem}{letter}", start + offset, compounds, base=stem, label=letter, results=1)
    db.commit()


def test_group_detail_query_count_does_not_grow_with_members(client, db_session, reporting_views):
    _replicate_group(db_session, "QCGDA_001", 9199000, "ab")
    _replicate_group(db_session, "QCGDB_001", 9199100, "abcdefgh")

    small, body_small = _count(client, "/api/experiments/groups/QCGDA_001")
    large, body_large = _count(client, "/api/experiments/groups/QCGDB_001")
    assert (len(body_small["members"]), len(body_large["members"])) == (2, 8)
    assert small == large, f"query count grew with members: {small} for 2, {large} for 8"
    assert large <= GROUP_DETAIL_CEILING, large
    assert body_large["shared_conditions"]["rock_mass_g"] == 2.0
    assert body_large["divergent_fields"] == []


# ── E-11: experiment delete ──────────────────────────────────────────────────

DELETE_SELECT_CEILING = 30


def _select_count(statements: list[str]) -> int:
    return sum(1 for s in statements if s.lstrip().upper().startswith("SELECT"))


def test_delete_select_count_does_not_grow_with_results(client, db_session):
    compounds = _compounds(db_session, "QCDEL")
    _experiment(db_session, "QCDEL_001", 9199200, compounds, results=2, with_icp=True)
    _experiment(db_session, "QCDEL_002", 9199201, compounds, results=10, with_icp=True)
    db_session.commit()

    counts, impacts = [], []
    for experiment_id in ("QCDEL_001", "QCDEL_002"):
        db_session.expire_all()
        with count_queries() as statements:
            resp = client.delete(f"/api/experiments/{experiment_id}")
        assert resp.status_code == 200, resp.text
        counts.append(_select_count(statements))
        impacts.append(resp.json())
    assert counts[0] == counts[1], f"SELECT count grew with results: {counts}"
    assert counts[1] <= DELETE_SELECT_CEILING, counts

    # What gets deleted is unchanged: the impact counts still describe it.
    for body, expected in zip(impacts, (2, 10)):
        impact = body["impact"]
        assert (impact["results"], impact["scalar_results"], impact["icp_results"]) == (expected,) * 3
    db_session.expire_all()
    assert db_session.query(Experiment).filter(Experiment.experiment_id.like("QCDEL_%")).count() == 0
    assert db_session.query(ScalarResults).join(
        ExperimentalResults, ExperimentalResults.id == ScalarResults.result_id
    ).join(Experiment, Experiment.id == ExperimentalResults.experiment_fk).filter(
        Experiment.experiment_id.like("QCDEL_%")).count() == 0


# ── E-12: run lists filter by series in SQL and skip inactive runs' samples ──

def test_type_prefilters_never_exclude_a_spelling_the_python_rule_accepts():
    """type_contains only narrows the SQL; it must be a superset of the rule.
    Every spelling the Python rule accepts has to contain one of the substrings
    once lower-cased, or a run would silently vanish from its list."""
    from backend.services.core_flood_service import CORE_FLOOD_TYPE_CONTAINS
    from backend.services.hpht_service import HPHT_TYPE_CONTAINS
    from database.reactor_slot import _SERIES_BY_TYPE, series_prefix

    for prefix, parts in (("R", HPHT_TYPE_CONTAINS), ("CF", CORE_FLOOD_TYPE_CONTAINS)):
        canonical = [name for name, series in _SERIES_BY_TYPE.items() if series == prefix]
        assert canonical, prefix
        spellings = []
        for name in canonical:
            spellings += [name, name.upper(), name.title(), f"  {name}  ", name.replace(" ", "   "),
                          name.replace(" ", "\t")]
        for spelling in spellings:
            assert series_prefix(spelling) == prefix, spelling
            assert any(part in spelling.lower() for part in parts), (spelling, parts)


def _run(db, base: str, number: int, experiment_type: str, status: ExperimentStatus) -> None:
    exp = Experiment(experiment_id=base, experiment_number=number, status=status, base_experiment_id=base,
                     date=datetime(2026, 6, 1, 12, tzinfo=timezone.utc))
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(experiment_fk=exp.id, experiment_id=base, experiment_type=experiment_type))
    db.flush()


@pytest.mark.parametrize("spelling", ["HPHT", "hpht", " Hpht  "])
def test_hpht_list_finds_every_spelling_and_no_other_series(client, db_session, reporting_views, spelling):
    _run(db_session, "QCRUNH_001", 9199300, spelling, ExperimentStatus.ONGOING)
    _run(db_session, "QCRUNS_001", 9199301, "Serum", ExperimentStatus.ONGOING)
    _run(db_session, "QCRUNC_001", 9199302, "Core Flood", ExperimentStatus.ONGOING)
    db_session.commit()
    bases = {row["base_id"] for row in client.get("/api/hpht?scope=all&q=QCRUN").json()}
    assert bases == {"QCRUNH_001"}


@pytest.mark.parametrize("spelling", ["Core Flood", "core  flood", "CoreFlood", "CF", " cf "])
def test_core_flood_list_finds_every_spelling_and_no_other_series(client, db_session, reporting_views, spelling):
    _run(db_session, "QCRUNC_002", 9199310, spelling, ExperimentStatus.ONGOING)
    _run(db_session, "QCRUNH_002", 9199311, "HPHT", ExperimentStatus.ONGOING)
    db_session.commit()
    bases = {row["base_id"] for row in client.get("/api/core-floods?scope=all&q=QCRUN").json()}
    assert bases == {"QCRUNC_002"}


def test_active_run_list_reads_samples_only_for_active_runs(client, db_session, reporting_views):
    from backend.services import run_service

    _run(db_session, "QCRUNH_010", 9199320, "HPHT", ExperimentStatus.ONGOING)
    _run(db_session, "QCRUNH_011", 9199321, "HPHT", ExperimentStatus.COMPLETED)
    db_session.commit()

    asked: list[list[str]] = []
    real = run_service.fetch_samples

    def spy(db, view, *, base_ids=None, result_id=None):
        asked.append(sorted(b for b in (base_ids or []) if b.startswith("QCRUNH_01")))
        return real(db, view, base_ids=base_ids, result_id=result_id)

    run_service.fetch_samples = spy
    try:
        active = client.get("/api/hpht?scope=active&q=QCRUNH_01").json()
        everything = client.get("/api/hpht?scope=all&q=QCRUNH_01").json()
    finally:
        run_service.fetch_samples = real

    assert [row["base_id"] for row in active] == ["QCRUNH_010"]
    assert {row["base_id"] for row in everything} == {"QCRUNH_010", "QCRUNH_011"}
    assert asked == [["QCRUNH_010"], ["QCRUNH_010", "QCRUNH_011"]]
