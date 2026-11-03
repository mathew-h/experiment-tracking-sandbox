"""v_core_flood_samples (issue #132): cross-sample core flood run values.

A run is one base ID split across sequential segment experiments
(CFV_001, CFV_001-2, ...). `_Text` children of a segment are variants
(blanks, bypasses): flagged, shown, and excluded from every derived column.

Views are DDL created inside the test transaction (rolled back per test),
mirroring tests/api/test_experiment_rollup.py's reporting_views fixture.
"""
import pytest
from sqlalchemy import text

from database.models import Experiment, ExperimentalResults, ScalarResults
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus

DERIVED = (
    "interval_days",
    "cumulative_liquid_volume_mL",
    "cumulative_pore_volumes",
    "cumulative_h2_grams_per_ton",
    "h2_grams_per_ton_per_day",
    "is_hold_interval",
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


def _cf_experiment(db, exp_id, number, pore_volume_mL=20.0, experiment_type="Core Flood"):
    exp = Experiment(experiment_id=exp_id, experiment_number=number,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp.experiment_id,
        experiment_type=experiment_type, pore_volume_mL=pore_volume_mL,
    ))
    db.flush()
    return exp


def _sample(db, exp, cum_days, volume_mL, h2_gpt, flow=None, primary=True):
    result = ExperimentalResults(
        experiment_fk=exp.id,
        cumulative_time_post_reaction_days=cum_days,
        time_post_reaction_days=cum_days,
        time_post_reaction_bucket_days=cum_days,
        is_primary_timepoint_result=primary,
        flow_rate_mL_min=flow,
    )
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, sampling_volume_mL=volume_mL,
                         h2_grams_per_ton_yield=h2_gpt))
    db.flush()
    return result


def _rows(db, base_id):
    return [dict(r) for r in db.execute(text(
        "SELECT * FROM v_core_flood_samples WHERE run_base_id = :b "
        "ORDER BY cumulative_time_post_reaction_days, result_id"
    ), {"b": base_id}).mappings()]


def _col(rows, name):
    return [r[name] for r in rows]


def _spec_run(db):
    seg1 = _cf_experiment(db, "CFV_001", 98101)
    seg2 = _cf_experiment(db, "CFV_001-2", 98102)
    _sample(db, seg1, 1.0, 10.0, 0.1)
    _sample(db, seg2, 5.0, 0.0, 0.4)
    _sample(db, seg2, 8.0, 30.0, 0.3)
    return seg1, seg2


def _assert_spec_values(rows):
    assert _col(rows, "experiment_id") == ["CFV_001", "CFV_001-2", "CFV_001-2"]
    assert _col(rows, "interval_days") == pytest.approx([1, 4, 3])
    assert _col(rows, "cumulative_liquid_volume_mL") == pytest.approx([10, 10, 40])
    assert _col(rows, "cumulative_pore_volumes") == pytest.approx([0.5, 0.5, 2.0])
    assert _col(rows, "cumulative_h2_grams_per_ton") == pytest.approx([0.1, 0.5, 0.8])
    assert _col(rows, "h2_grams_per_ton_per_day") == pytest.approx([0.1, 0.1, 0.1])
    assert _col(rows, "is_variant") == [False, False, False]


def test_spec_three_sample_run(db_session, reporting_views):
    _spec_run(db_session)
    rows = _rows(db_session, "CFV_001")
    assert len(rows) == 3
    _assert_spec_values(rows)


def test_variant_is_flagged_and_excluded(db_session, reporting_views):
    _seg1, seg2 = _spec_run(db_session)
    bypass = _cf_experiment(db_session, "CFV_001-2_Bypass", 98103)
    assert bypass.parent_experiment_fk == seg2.id
    _sample(db_session, bypass, 6.0, 50.0, 9.9)

    rows = _rows(db_session, "CFV_001")
    variants = [r for r in rows if r["experiment_id"] == "CFV_001-2_Bypass"]
    segments = [r for r in rows if r["experiment_id"] != "CFV_001-2_Bypass"]
    assert len(variants) == 1
    (v,) = variants
    assert v["is_variant"] is True
    for name in DERIVED:
        assert v[name] is None, name
    # Raw per-sample values still pass through on the variant row.
    assert v["sampling_volume_mL"] == pytest.approx(50.0)
    assert v["h2_grams_per_ton_yield"] == pytest.approx(9.9)
    _assert_spec_values(segments)


def test_hold_interval(db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFV_002", 98201)
    _sample(db_session, exp, 1.0, 5.0, 0.1, flow=0.1)
    _sample(db_session, exp, 2.0, 5.0, 0.1, flow=0.0)
    _sample(db_session, exp, 3.0, 5.0, 0.1, flow=None)
    rows = _rows(db_session, "CFV_002")
    assert _col(rows, "is_hold_interval") == [False, True, None]


def test_zero_interval_gives_null_rate(db_session, reporting_views):
    # Segment boundary: the last sample of CFV_004 and the first of CFV_004-2
    # share cumulative day 3. (Two primary rows in ONE experiment at one day
    # are rejected by uq_primary_result_per_experiment_bucket.)
    seg1 = _cf_experiment(db_session, "CFV_004", 98401)
    seg2 = _cf_experiment(db_session, "CFV_004-2", 98402)
    _sample(db_session, seg1, 3.0, 5.0, 0.3)
    _sample(db_session, seg2, 3.0, 5.0, 0.2)
    rows = _rows(db_session, "CFV_004")
    assert _col(rows, "interval_days") == pytest.approx([3, 0])
    assert rows[0]["h2_grams_per_ton_per_day"] == pytest.approx(0.1)
    assert rows[1]["interval_days"] == 0
    assert rows[1]["h2_grams_per_ton_per_day"] is None
    # Cumulative H2 still counts the zero-interval sample.
    assert _col(rows, "cumulative_h2_grams_per_ton") == pytest.approx([0.3, 0.5])


def test_null_volume_and_missing_pore_volume(db_session, reporting_views):
    seg1 = _cf_experiment(db_session, "CFV_005", 98501, pore_volume_mL=20.0)
    seg2 = _cf_experiment(db_session, "CFV_005-2", 98502, pore_volume_mL=None)
    seg3 = _cf_experiment(db_session, "CFV_005-3", 98503, pore_volume_mL=0.0)
    _sample(db_session, seg1, 1.0, 10.0, 0.1)
    _sample(db_session, seg1, 2.0, None, 0.1)   # gas-only sample
    _sample(db_session, seg2, 3.0, 6.0, 0.1)
    _sample(db_session, seg3, 4.0, 4.0, 0.1)
    rows = _rows(db_session, "CFV_005")
    assert _col(rows, "cumulative_liquid_volume_mL") == pytest.approx([10, 10, 16, 20])
    assert rows[0]["cumulative_pore_volumes"] == pytest.approx(0.5)
    assert rows[1]["cumulative_pore_volumes"] == pytest.approx(0.5)
    assert rows[1]["sampling_volume_mL"] is None
    assert rows[2]["cumulative_pore_volumes"] is None   # pore volume NULL
    assert rows[3]["cumulative_pore_volumes"] is None   # pore volume 0


def test_excludes_non_primary_and_non_core_flood(db_session, reporting_views):
    exp = _cf_experiment(db_session, "CFV_003", 98301)
    serum = _cf_experiment(db_session, "CFV_003-2", 98302, experiment_type="Serum")
    _sample(db_session, exp, 1.0, 10.0, 0.1)
    non_primary = _sample(db_session, exp, 2.0, 100.0, 5.0, primary=False)
    serum_result = _sample(db_session, serum, 3.0, 200.0, 7.0)

    rows = _rows(db_session, "CFV_003")
    ids = {r["result_id"] for r in rows}
    assert non_primary.id not in ids
    assert serum_result.id not in ids
    assert len(rows) == 1
    assert rows[0]["cumulative_liquid_volume_mL"] == pytest.approx(10.0)
    assert rows[0]["cumulative_h2_grams_per_ton"] == pytest.approx(0.1)
