"""v_results_h2_bkg_adjusted and its rollup (issue #144).

A sample group (base experiment) is linked to a background serum vial set
through h2_background_links: either a whole background replicate group
(group mode, background_base_id) or one vial stem (vial mode,
background_stem_id, matched with the '-t<days>' token peeled off). Each
sample row is matched to the nearest background bucket (ties go earlier)
and the background mean H2 (umol) is subtracted.

Views are DDL created inside the test transaction (rolled back per test),
mirroring tests/api/test_core_flood_view.py's reporting_views fixture.
"""
import re
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.services.calculations.scalar_calcs import calculate_ferrous_iron_yield_h2
from database.experiment_id_parser import split_timepoint_token
from database.models import (
    Experiment, ExperimentalResults, H2BackgroundLink, ScalarResults,
)
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus

H2_MOLAR_MASS = 2.01588


@pytest.fixture()
def reporting_views(db_session):
    from database.event_listeners import _VIEWS
    for view_name, _ in _VIEWS:
        db_session.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
    for _, view_sql in _VIEWS:
        db_session.execute(text(view_sql))
    db_session.flush()
    yield


def _exp(db, exp_id, number, base=None, rock=1.0, fe=None, outlier=False):
    exp = Experiment(experiment_id=exp_id, experiment_number=number,
                     status=ExperimentStatus.COMPLETED, is_outlier=outlier)
    db.add(exp)
    db.flush()
    if base is not None:
        exp.base_experiment_id = base
    db.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp.experiment_id,
        rock_mass_g=rock, total_ferrous_iron_g=fe,
    ))
    db.flush()
    return exp


def _h2(db, exp, bucket, umol, ppm=100.0):
    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=bucket,
        time_post_reaction_bucket_days=bucket,
        is_primary_timepoint_result=True,
    )
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, h2_concentration=ppm, h2_micromoles=umol))
    db.flush()
    # The calc engine may run on insert; force the inputs the test asserts on.
    db.execute(text(
        "UPDATE scalar_results SET h2_concentration = :p, h2_micromoles = :u "
        "WHERE result_id = :r"
    ), {"p": ppm, "u": umol, "r": result.id})
    return result


def _link(db, base, bg_base=None, stem=None):
    link = H2BackgroundLink(base_experiment_id=base, background_base_id=bg_base,
                            background_stem_id=stem)
    db.add(link)
    db.flush()
    return link


def _rows(db, base):
    return [dict(r) for r in db.execute(text(
        "SELECT * FROM v_results_h2_bkg_adjusted WHERE base_experiment_id = :b "
        "ORDER BY time_post_reaction_bucket_days NULLS LAST, experiment_id, result_id"
    ), {"b": base}).mappings()]


def _rollup(db, base):
    return [dict(r) for r in db.execute(text(
        "SELECT * FROM v_results_h2_bkg_adjusted_rollup WHERE base_experiment_id = :b "
        "ORDER BY time_post_reaction_bucket_days"
    ), {"b": base}).mappings()]


def _col(rows, name):
    return [r[name] for r in rows]


def _group(db, base, number, values, bucket, letters="abc", **kw):
    exps = []
    for i, (letter, v) in enumerate(zip(letters, values)):
        e = _exp(db, f"{base}{letter}", number + i, **kw)
        _h2(db, e, bucket, v)
        exps.append(e)
    return exps


PER_ROW_COLUMNS = [
    "result_id", "experiment_id", "experiment_fk", "base_experiment_id",
    "time_post_reaction_bucket_days", "background_mode", "background_ref",
    "bkg_time_bucket_days", "bkg_time_gap_days", "bkg_n_values", "bkg_mean_h2_ppm",
    "bkg_mean_h2_micromoles", "bkg_sd_h2_micromoles", "h2_micromoles",
    "net_h2_micromoles_unclamped", "net_h2_micromoles", "u_bkg_h2_micromoles",
    "net_h2_mass_ug", "net_h2_grams_per_ton_unclamped", "net_h2_grams_per_ton",
    "u_bkg_h2_grams_per_ton", "net_fe_yield_h2_pct_unclamped", "net_fe_yield_h2_pct",
    "u_bkg_fe_yield_h2_pct", "below_background",
]
ROLLUP_COLUMNS = [
    "base_experiment_id", "time_post_reaction_bucket_days", "n_values",
    "bkg_time_bucket_days", "bkg_time_gap_days", "bkg_n_values",
    "bkg_mean_h2_micromoles", "bkg_sd_h2_micromoles", "mean_net_h2_micromoles",
    "sd_net_h2_micromoles", "mean_net_h2_grams_per_ton", "sd_net_h2_grams_per_ton",
    "mean_net_fe_yield_h2_pct", "sd_net_fe_yield_h2_pct", "below_background",
]


def _view_columns(db, view):
    return [r[0] for r in db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = :v ORDER BY ordinal_position"
    ), {"v": view})]


def test_view_columns_exact(db_session, reporting_views):
    assert _view_columns(db_session, "v_results_h2_bkg_adjusted") == PER_ROW_COLUMNS
    cols = _view_columns(db_session, "v_results_h2_bkg_adjusted_rollup")
    assert cols == ROLLUP_COLUMNS


def test_group_mode_t7(db_session, reporting_views):
    _group(db_session, "H2BKS_11", 94100, [10, 12, 14], 7)
    _group(db_session, "H2BKB_11", 94110, [2, 3, 4], 7)
    _link(db_session, "H2BKS_11", bg_base="H2BKB_11")

    rows = _rows(db_session, "H2BKS_11")
    assert _col(rows, "net_h2_micromoles") == pytest.approx([7, 9, 11])
    assert _col(rows, "background_mode") == ["group"] * 3
    assert _col(rows, "background_ref") == ["H2BKB_11"] * 3
    assert _col(rows, "bkg_n_values") == [3, 3, 3]
    assert rows[0]["bkg_mean_h2_micromoles"] == pytest.approx(3.0)
    assert rows[0]["bkg_sd_h2_micromoles"] == pytest.approx(1.0)
    assert rows[0]["bkg_mean_h2_ppm"] == pytest.approx(100.0)
    assert rows[0]["u_bkg_h2_micromoles"] == pytest.approx(1.0)
    assert rows[0]["net_h2_mass_ug"] == pytest.approx(7 * H2_MOLAR_MASS)

    (r,) = _rollup(db_session, "H2BKS_11")
    assert r["n_values"] == 3
    assert r["bkg_time_bucket_days"] == 7
    assert r["bkg_time_gap_days"] == 0
    assert r["mean_net_h2_micromoles"] == pytest.approx(9.0)
    assert r["sd_net_h2_micromoles"] == pytest.approx(5 ** 0.5, abs=1e-3)
    assert r["mean_net_h2_grams_per_ton"] == pytest.approx(18.143, abs=1e-3)
    expected = H2_MOLAR_MASS * 5 ** 0.5
    assert r["sd_net_h2_grams_per_ton"] == pytest.approx(expected, abs=1e-3)
    assert r["below_background"] is False


def test_clamp(db_session, reporting_views):
    _group(db_session, "H2BKS_12", 94200, [1, 2, 3], 7)
    _group(db_session, "H2BKB_12", 94210, [2, 3, 4], 7)
    _link(db_session, "H2BKS_12", bg_base="H2BKB_12")

    rows = _rows(db_session, "H2BKS_12")
    assert _col(rows, "net_h2_micromoles") == pytest.approx([0, 0, 0])
    assert _col(rows, "net_h2_micromoles_unclamped") == pytest.approx([-2, -1, 0])
    assert _col(rows, "below_background") == [True, True, False]

    (r,) = _rollup(db_session, "H2BKS_12")
    assert r["mean_net_h2_micromoles"] == pytest.approx(0.0)
    assert r["sd_net_h2_micromoles"] == pytest.approx(1.414, abs=1e-3)
    assert r["below_background"] is True


def test_nearest_match(db_session, reporting_views):
    s = _exp(db_session, "H2BKS_13a", 94300)
    for b in (1, 3, 7):
        _h2(db_session, s, b, 10)
    bg = _exp(db_session, "H2BKB_13a", 94310)
    for b in (0, 7):
        _h2(db_session, bg, b, 1)
    _link(db_session, "H2BKS_13", bg_base="H2BKB_13")

    rows = _rows(db_session, "H2BKS_13")
    assert _col(rows, "bkg_time_bucket_days") == [0, 0, 7]
    assert _col(rows, "bkg_time_gap_days") == [-1, -3, 0]


def test_nearest_tie_goes_earlier(db_session, reporting_views):
    s = _exp(db_session, "H2BKS_14a", 94400)
    _h2(db_session, s, 3, 10)
    bg = _exp(db_session, "H2BKB_14a", 94410)
    _h2(db_session, bg, 2, 1)
    _h2(db_session, bg, 4, 5)
    _link(db_session, "H2BKS_14", bg_base="H2BKB_14")

    (row,) = _rows(db_session, "H2BKS_14")
    assert row["bkg_time_bucket_days"] == 2
    assert row["bkg_mean_h2_micromoles"] == pytest.approx(1.0)


def test_vial_mode(db_session, reporting_views):
    v3 = _exp(db_session, "SERUM_009a-t3", 94500)
    _h2(db_session, v3, 3, 2)
    v7 = _exp(db_session, "SERUM_009a-t7", 94501)
    _h2(db_session, v7, 7, 4)
    other = _exp(db_session, "SERUM_009b", 94502)
    _h2(db_session, other, 3, 100)
    _h2(db_session, other, 7, 100)

    _group(db_session, "H2BKS_15", 94510, [10, 13], 3, letters="ab")
    _link(db_session, "H2BKS_15", stem="SERUM_009a")

    rows = _rows(db_session, "H2BKS_15")
    assert _col(rows, "background_mode") == ["vial", "vial"]
    assert _col(rows, "background_ref") == ["SERUM_009a", "SERUM_009a"]
    assert _col(rows, "bkg_n_values") == [1, 1]
    assert _col(rows, "bkg_mean_h2_micromoles") == pytest.approx([2, 2])
    assert _col(rows, "bkg_sd_h2_micromoles") == [None, None]
    assert _col(rows, "u_bkg_h2_micromoles") == [None, None]
    assert _col(rows, "net_h2_micromoles") == pytest.approx([8, 11])

    (r,) = _rollup(db_session, "H2BKS_15")
    assert r["bkg_sd_h2_micromoles"] is None
    assert r["mean_net_h2_micromoles"] == pytest.approx(9.5)
    # stddev_samp(8, 11) alone
    assert r["sd_net_h2_micromoles"] == pytest.approx(2 ** 0.5 * 1.5, abs=1e-9)


def test_stem_pattern_matches_python(db_session, reporting_views):
    from backend.services.replicate_collapse import TIMEPOINT_TOKEN_SQL_PATTERN
    from database.event_listeners import _VIEWS

    view_sql = dict(_VIEWS)["v_results_h2_bkg_adjusted"]
    assert f"'{TIMEPOINT_TOKEN_SQL_PATTERN}'" in view_sql
    m = re.search(r"regexp_replace\(e\.experiment_id, '([^']*)', ''\)", view_sql)
    assert m is not None
    for exp_id in ("SERUM_009a-t7.5", "SERUM_009a-t7", "SERUM_009a"):
        sql_stem = db_session.execute(
            text("SELECT regexp_replace(:x, :p, '')"), {"x": exp_id, "p": m.group(1)}
        ).scalar()
        assert sql_stem == split_timepoint_token(exp_id)[0]

    # And end to end: a decimal-day vial is covered by its stem.
    v = _exp(db_session, "SERUM_019a-t7.5", 94600)
    _h2(db_session, v, 7.5, 3)
    s = _exp(db_session, "H2BKS_16a", 94610)
    _h2(db_session, s, 7.5, 10)
    _link(db_session, "H2BKS_16", stem="SERUM_019a")
    (row,) = _rows(db_session, "H2BKS_16")
    assert row["net_h2_micromoles"] == pytest.approx(7.0)


def test_outlier_background_excluded(db_session, reporting_views):
    _group(db_session, "H2BKS_17", 94700, [10, 12, 14], 7)
    bgs = _group(db_session, "H2BKB_17", 94710, [2, 3, 4], 7)
    bad = _exp(db_session, "H2BKB_17d", 94720, outlier=True)
    _h2(db_session, bad, 7, 500)
    _link(db_session, "H2BKS_17", bg_base="H2BKB_17")
    assert all(not b.is_outlier for b in bgs)

    rows = _rows(db_session, "H2BKS_17")
    assert _col(rows, "bkg_n_values") == [3, 3, 3]
    assert rows[0]["bkg_mean_h2_micromoles"] == pytest.approx(3.0)
    assert rows[0]["bkg_sd_h2_micromoles"] == pytest.approx(1.0)


def test_sample_outlier_in_rows_not_rollup(db_session, reporting_views):
    _group(db_session, "H2BKS_18", 94800, [10, 12, 14], 7)
    bad = _exp(db_session, "H2BKS_18d", 94803, outlier=True)
    _h2(db_session, bad, 7, 1000)
    _group(db_session, "H2BKB_18", 94810, [2, 3, 4], 7)
    _link(db_session, "H2BKS_18", bg_base="H2BKB_18")

    assert len(_rows(db_session, "H2BKS_18")) == 4
    (r,) = _rollup(db_session, "H2BKS_18")
    assert r["n_values"] == 3
    assert r["mean_net_h2_micromoles"] == pytest.approx(9.0)


def test_background_all_null_buckets_gives_null_net(db_session, reporting_views):
    _group(db_session, "H2BKS_19", 94900, [10, 12], 7, letters="ab")
    bg = _exp(db_session, "H2BKB_19a", 94910)
    _h2(db_session, bg, None, 2)
    _link(db_session, "H2BKS_19", bg_base="H2BKB_19")

    rows = _rows(db_session, "H2BKS_19")
    assert len(rows) == 2
    for r in rows:
        assert r["bkg_time_bucket_days"] is None
        assert r["bkg_n_values"] is None
        assert r["net_h2_micromoles"] is None
        assert r["net_h2_micromoles_unclamped"] is None
        assert r["below_background"] is None
    (r,) = _rollup(db_session, "H2BKS_19")
    assert r["n_values"] == 0
    assert r["mean_net_h2_micromoles"] is None
    assert r["sd_net_h2_micromoles"] is None


def test_null_bucket_sample_null_net(db_session, reporting_views):
    s = _exp(db_session, "H2BKS_110a", 95000)
    _h2(db_session, s, None, 10)
    bg = _exp(db_session, "H2BKB_110a", 95010)
    _h2(db_session, bg, 7, 2)
    _link(db_session, "H2BKS_110", bg_base="H2BKB_110")

    (row,) = _rows(db_session, "H2BKS_110")
    assert row["time_post_reaction_bucket_days"] is None
    assert row["bkg_time_bucket_days"] is None
    assert row["net_h2_micromoles"] is None
    assert _rollup(db_session, "H2BKS_110") == []


def test_null_micromoles_row_null_net(db_session, reporting_views):
    _group(db_session, "H2BKS_111", 95100, [10, 12], 7, letters="ab")
    nul = _exp(db_session, "H2BKS_111c", 95102)
    _h2(db_session, nul, 7, None)
    _group(db_session, "H2BKB_111", 95110, [2, 3, 4], 7)
    _link(db_session, "H2BKS_111", bg_base="H2BKB_111")

    rows = _rows(db_session, "H2BKS_111")
    assert len(rows) == 3
    (n,) = [r for r in rows if r["experiment_id"] == "H2BKS_111c"]
    assert n["h2_micromoles"] is None
    assert n["net_h2_micromoles"] is None
    assert n["net_h2_grams_per_ton"] is None
    assert n["below_background"] is None
    (r,) = _rollup(db_session, "H2BKS_111")
    assert r["n_values"] == 2
    assert r["mean_net_h2_micromoles"] == pytest.approx(8.0)


def test_sql_python_agreement(db_session, reporting_views):
    s = _exp(db_session, "H2BKS_112a", 95200, rock=2.5, fe=0.8)
    _h2(db_session, s, 7, 10)
    bg = _exp(db_session, "H2BKB_112a", 95210)
    _h2(db_session, bg, 7, 2.5)
    _link(db_session, "H2BKS_112", bg_base="H2BKB_112")

    (row,) = _rows(db_session, "H2BKS_112")
    net_umol = 7.5
    assert row["net_h2_micromoles"] == pytest.approx(net_umol)
    assert row["net_fe_yield_h2_pct"] == pytest.approx(
        calculate_ferrous_iron_yield_h2(net_umol, 0.8))
    assert row["net_h2_grams_per_ton"] == pytest.approx(
        1e6 * (net_umol * H2_MOLAR_MASS / 1e6) / 2.5)


def test_zero_rock_and_fe_give_null(db_session, reporting_views):
    s = _exp(db_session, "H2BKS_113a", 95300, rock=0.0, fe=0.0)
    _h2(db_session, s, 7, 10)
    bg = _exp(db_session, "H2BKB_113a", 95310)
    _h2(db_session, bg, 7, 2)
    _link(db_session, "H2BKS_113", bg_base="H2BKB_113")

    (row,) = _rows(db_session, "H2BKS_113")
    assert row["net_h2_micromoles"] == pytest.approx(8.0)
    assert row["net_h2_grams_per_ton"] is None
    assert row["net_fe_yield_h2_pct"] is None


def test_unlinked_group_absent(db_session, reporting_views):
    _group(db_session, "H2BKS_114", 95400, [10, 12], 7, letters="ab")
    assert _rows(db_session, "H2BKS_114") == []
    assert _rollup(db_session, "H2BKS_114") == []


def _norm(sql: str) -> str:
    return " ".join(sql.split())


@pytest.mark.parametrize(
    "name", ["v_results_scalar", "v_results_h2"]
)
def test_existing_views_untouched(name):
    """One-time #144 guard: this branch left v_results_scalar, v_results_h2 and
    v_results_scalar_rollup unchanged versus 1817bed, the develop head it
    started from. Delete this test when any of those views is changed on
    purpose. v_results_scalar_rollup was changed on purpose by issue #152
    (is_background) and is dropped from the list; its definition is now pinned by
    tests/models/test_is_background_column.py.
    """
    from database.event_listeners import _VIEWS

    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ["git", "show", "1817bed:database/event_listeners.py"],
        capture_output=True, text=True, cwd=repo_root,
    )
    assert proc.returncode == 0, proc.stderr
    start_marker = f'("{name}", """'
    start = proc.stdout.index(start_marker) + len(start_marker)
    end = proc.stdout.index('"""', start)
    assert _norm(proc.stdout[start:end]) == _norm(dict(_VIEWS)[name])
