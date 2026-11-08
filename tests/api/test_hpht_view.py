"""v_hpht_samples (issue #149): cross-sample HPHT run values.

A run is one base ID split across sequential segments (HPHTV_001, HPHTV_001-2).
`_Text` children of a segment are variants (HPHTV_001_Desorption): shown, and
excluded from every derived column. Per-sample H2 is incremental, so the view's
running sums are the run's H2 to date.

Views are DDL created inside the test transaction (rolled back per test).
"""
import pytest
from sqlalchemy import text

from database.models import Experiment, ExperimentalResults, ScalarResults
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus

DERIVED = (
    "interval_days",
    "cumulative_h2_grams_per_ton",
    "h2_grams_per_ton_per_day",
    "cumulative_h2_micromoles",
    "cumulative_ferrous_iron_yield_h2_pct",
)


@pytest.fixture()
def reporting_views(db_session):
    from database.event_listeners import _VIEWS
    for view_name, _ in _VIEWS:
        db_session.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
    for _, view_sql in _VIEWS:
        db_session.execute(text(view_sql))
    db_session.flush()
    yield


def _experiment(db, exp_id, number, experiment_type="HPHT"):
    exp = Experiment(experiment_id=exp_id, experiment_number=number,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp.experiment_id,
        experiment_type=experiment_type, reactor_number=3,
    ))
    db.flush()
    return exp


def _sample(db, exp, cum_days, h2_gpt, umol=None, fe_pct=None, primary=True):
    result = ExperimentalResults(
        experiment_fk=exp.id,
        cumulative_time_post_reaction_days=cum_days,
        time_post_reaction_days=cum_days,
        time_post_reaction_bucket_days=cum_days,
        is_primary_timepoint_result=primary,
    )
    db.add(result)
    db.flush()
    # Write the derived H2 columns directly after the row exists: the
    # calculation engine would recompute them from inputs we do not seed.
    db.add(ScalarResults(result_id=result.id))
    db.flush()
    db.execute(text(
        "UPDATE scalar_results SET h2_grams_per_ton_yield = :g, h2_micromoles = :u,"
        " ferrous_iron_yield_h2_pct = :f WHERE result_id = :r"),
        {"g": h2_gpt, "u": umol, "f": fe_pct, "r": result.id})
    return result


def _rows(db, base_id):
    return [dict(r) for r in db.execute(text(
        "SELECT * FROM v_hpht_samples WHERE run_base_id = :b "
        "ORDER BY cumulative_time_post_reaction_days, result_id"
    ), {"b": base_id}).mappings()]


def _col(rows, name):
    return [r[name] for r in rows]


def _run(db):
    root = _experiment(db, "HPHTV_001", 96101)
    seg2 = _experiment(db, "HPHTV_001-2", 96102)
    _sample(db, root, 1.0, 0.1, umol=1.0, fe_pct=0.5)
    _sample(db, root, 4.0, 0.2, umol=2.0, fe_pct=1.0)
    _sample(db, seg2, 6.0, 0.4, umol=4.0, fe_pct=2.0)
    return root, seg2


def test_cumulative_runs_across_segments(db_session, reporting_views):
    _run(db_session)
    rows = _rows(db_session, "HPHTV_001")
    assert _col(rows, "experiment_id") == ["HPHTV_001", "HPHTV_001", "HPHTV_001-2"]
    assert _col(rows, "is_variant") == [False, False, False]
    assert _col(rows, "interval_days") == pytest.approx([1, 3, 2])
    # The -2 segment keeps adding to its root's total instead of restarting.
    assert _col(rows, "cumulative_h2_grams_per_ton") == pytest.approx([0.1, 0.3, 0.7])
    assert _col(rows, "cumulative_h2_micromoles") == pytest.approx([1, 3, 7])
    assert _col(rows, "cumulative_ferrous_iron_yield_h2_pct") == pytest.approx([0.5, 1.5, 3.5])
    assert _col(rows, "h2_grams_per_ton_per_day") == pytest.approx([0.1, 0.2 / 3, 0.2])
    assert _col(rows, "reactor_slot") == ["R03", "R03", "R03"]


def test_order_is_cumulative_time_not_insert_order(db_session, reporting_views):
    root = _experiment(db_session, "HPHTV_002", 96111)
    _sample(db_session, root, 5.0, 0.5)
    _sample(db_session, root, 2.0, 0.2)
    rows = _rows(db_session, "HPHTV_002")
    assert _col(rows, "cumulative_time_post_reaction_days") == [2.0, 5.0]
    assert _col(rows, "cumulative_h2_grams_per_ton") == pytest.approx([0.2, 0.7])


def test_variant_is_flagged_and_excluded(db_session, reporting_views):
    root, _seg2 = _run(db_session)
    variant = _experiment(db_session, "HPHTV_001_Desorption", 96103)
    assert variant.parent_experiment_fk == root.id
    _sample(db_session, variant, 2.0, 9.9, umol=99.0, fe_pct=50.0)

    rows = _rows(db_session, "HPHTV_001")
    (v,) = [r for r in rows if r["experiment_id"] == "HPHTV_001_Desorption"]
    assert v["is_variant"] is True
    for name in DERIVED:
        assert v[name] is None, name
    assert v["h2_grams_per_ton_yield"] == pytest.approx(9.9)
    real = [r for r in rows if not r["is_variant"]]
    assert _col(real, "cumulative_h2_grams_per_ton") == pytest.approx([0.1, 0.3, 0.7])
    assert _col(real, "interval_days") == pytest.approx([1, 3, 2])


def test_zero_interval_gives_null_rate(db_session, reporting_views):
    root = _experiment(db_session, "HPHTV_003", 96121)
    seg2 = _experiment(db_session, "HPHTV_003-2", 96122)
    _sample(db_session, root, 3.0, 0.3)
    _sample(db_session, seg2, 3.0, 0.1)
    rows = _rows(db_session, "HPHTV_003")
    assert _col(rows, "interval_days") == pytest.approx([3, 0])
    assert rows[1]["h2_grams_per_ton_per_day"] is None
    assert rows[1]["cumulative_h2_grams_per_ton"] == pytest.approx(0.4)


def test_null_h2_adds_zero(db_session, reporting_views):
    root = _experiment(db_session, "HPHTV_004", 96131)
    _sample(db_session, root, 1.0, 0.2)
    _sample(db_session, root, 2.0, None)
    rows = _rows(db_session, "HPHTV_004")
    assert _col(rows, "cumulative_h2_grams_per_ton") == pytest.approx([0.2, 0.2])
    assert rows[1]["h2_grams_per_ton_per_day"] is None


def test_non_primary_rows_absent(db_session, reporting_views):
    root = _experiment(db_session, "HPHTV_005", 96141)
    _sample(db_session, root, 1.0, 0.2)
    _sample(db_session, root, 1.0, 5.0, primary=False)
    assert len(_rows(db_session, "HPHTV_005")) == 1


@pytest.mark.parametrize("experiment_type", ["Core Flood", "CF", "Serum", "SERUM", "Autoclave"])
def test_other_types_absent(db_session, reporting_views, experiment_type):
    exp = _experiment(db_session, "HPHTV_006", 96151, experiment_type=experiment_type)
    _sample(db_session, exp, 1.0, 0.2)
    assert _rows(db_session, "HPHTV_006") == []


def test_type_spelling_is_normalized(db_session, reporting_views):
    exp = _experiment(db_session, "HPHTV_007", 96161, experiment_type="  hpht ")
    _sample(db_session, exp, 1.0, 0.2)
    assert len(_rows(db_session, "HPHTV_007")) == 1


def test_no_nh3_columns(db_session, reporting_views):
    cols = db_session.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'v_hpht_samples'"
    )).scalars().all()
    assert cols, "view missing"
    assert not [c for c in cols if "nh3" in c.lower() or "ammon" in c.lower()]
