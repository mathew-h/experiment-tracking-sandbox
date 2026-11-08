"""Background vials in the rollup and H2 background views (issue #152).

Rule: a group with any non-background, non-outlier member averages only its
non-background vials; a group whose non-outlier members are all backgrounds
keeps its own rollup (is_background_group = true). A #144 background set with
any flagged vial uses only its flagged vials; without flags, all of them.

Views are DDL created inside the test transaction (rolled back per test).
"""
import pytest
from sqlalchemy import text

from database.models import Experiment, ExperimentalResults, H2BackgroundLink, ScalarResults
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus

DAY = 7.0


@pytest.fixture()
def reporting_views(db_session):
    from database.event_listeners import _VIEWS
    for view_name, _ in _VIEWS:
        db_session.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
    for _, view_sql in _VIEWS:
        db_session.execute(text(view_sql))
    db_session.flush()
    yield


def _vial(db, exp_id, number, umol, background=False, outlier=False, rock=1.0):
    exp = Experiment(experiment_id=exp_id, experiment_number=number,
                     status=ExperimentStatus.COMPLETED,
                     is_background=background, is_outlier=outlier)
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(experiment_fk=exp.id, experiment_id=exp_id, rock_mass_g=rock))
    db.flush()
    result = ExperimentalResults(
        experiment_fk=exp.id, time_post_reaction_days=DAY,
        time_post_reaction_bucket_days=DAY, is_primary_timepoint_result=True,
    )
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, h2_concentration=100.0, h2_micromoles=umol))
    db.flush()
    # The calculation engine may run on insert; pin the value the test asserts on.
    db.execute(text("UPDATE scalar_results SET h2_micromoles = :u WHERE result_id = :r"),
               {"u": umol, "r": result.id})
    return exp


def _scalar_rollup(db, base):
    return [dict(r) for r in db.execute(text(
        "SELECT * FROM v_results_scalar_rollup WHERE base_experiment_id = :b"), {"b": base}).mappings()]


def _bkg_rows(db, base):
    return [dict(r) for r in db.execute(text(
        "SELECT * FROM v_results_h2_bkg_adjusted WHERE base_experiment_id = :b ORDER BY experiment_id"),
        {"b": base}).mappings()]


def _bkg_rollup(db, base):
    return [dict(r) for r in db.execute(text(
        "SELECT * FROM v_results_h2_bkg_adjusted_rollup WHERE base_experiment_id = :b"),
        {"b": base}).mappings()]


def _link(db, base, bg_base=None, stem=None):
    db.add(H2BackgroundLink(base_experiment_id=base, background_base_id=bg_base,
                            background_stem_id=stem))
    db.flush()


# ---------------------------------------------------------------- scalar rollup

def test_mixed_group_leaves_background_out(db_session, reporting_views):
    _vial(db_session, "BGV_001a", 97001, 1.0)
    _vial(db_session, "BGV_001b", 97002, 3.0)
    _vial(db_session, "BGV_001c", 97003, 100.0, background=True)
    (row,) = _scalar_rollup(db_session, "BGV_001")
    assert row["n_vials"] == 2
    assert row["mean_h2_micromoles"] == pytest.approx(2.0)
    assert row["is_background_group"] is False


def test_all_background_group_keeps_its_rollup(db_session, reporting_views):
    _vial(db_session, "BGV_002a", 97011, 1.0, background=True)
    _vial(db_session, "BGV_002b", 97012, 3.0, background=True)
    (row,) = _scalar_rollup(db_session, "BGV_002")
    assert row["n_vials"] == 2
    assert row["mean_h2_micromoles"] == pytest.approx(2.0)
    assert row["is_background_group"] is True


def test_outlier_samples_do_not_make_a_group_mixed(db_session, reporting_views):
    # The only sample vial is an outlier, so the non-outlier members are all
    # backgrounds and the background keeps the group's rollup.
    _vial(db_session, "BGV_003a", 97021, 50.0, outlier=True)
    _vial(db_session, "BGV_003b", 97022, 2.0, background=True)
    (row,) = _scalar_rollup(db_session, "BGV_003")
    assert row["n_vials"] == 1
    assert row["mean_h2_micromoles"] == pytest.approx(2.0)
    assert row["is_background_group"] is True


def test_unflagged_group_is_unchanged(db_session, reporting_views):
    _vial(db_session, "BGV_004a", 97031, 1.0)
    _vial(db_session, "BGV_004b", 97032, 3.0)
    (row,) = _scalar_rollup(db_session, "BGV_004")
    assert row["n_vials"] == 2
    assert row["mean_h2_micromoles"] == pytest.approx(2.0)
    assert row["is_background_group"] is False


def test_background_stays_in_per_row_views(db_session, reporting_views):
    exp = _vial(db_session, "BGV_005a", 97041, 1.0)
    bg = _vial(db_session, "BGV_005b", 97042, 9.0, background=True)
    ids = set(db_session.execute(text(
        "SELECT experiment_fk FROM v_results_scalar WHERE experiment_fk IN (:a, :b)"),
        {"a": exp.id, "b": bg.id}).scalars())
    assert ids == {exp.id, bg.id}
    assert db_session.execute(text(
        "SELECT is_background FROM v_experiments WHERE experiment_id = 'BGV_005b'")).scalar() is True


# ---------------------------------------------------------- #144 background set

def test_background_set_uses_only_flagged_vials(db_session, reporting_views):
    _vial(db_session, "BGV_010a", 97101, 10.0)
    _vial(db_session, "BGV_011a", 97111, 1.0, background=True)
    _vial(db_session, "BGV_011b", 97112, 50.0)  # unflagged member of the linked set
    _link(db_session, "BGV_010", bg_base="BGV_011")
    (row,) = _bkg_rows(db_session, "BGV_010")
    assert row["bkg_n_values"] == 1
    assert row["bkg_mean_h2_micromoles"] == pytest.approx(1.0)
    assert row["net_h2_micromoles"] == pytest.approx(9.0)


def test_background_set_without_flags_uses_every_vial(db_session, reporting_views):
    _vial(db_session, "BGV_020a", 97201, 10.0)
    _vial(db_session, "BGV_021a", 97211, 1.0)
    _vial(db_session, "BGV_021b", 97212, 3.0)
    _link(db_session, "BGV_020", bg_base="BGV_021")
    (row,) = _bkg_rows(db_session, "BGV_020")
    assert row["bkg_n_values"] == 2
    assert row["bkg_mean_h2_micromoles"] == pytest.approx(2.0)


def test_background_set_ignores_flagged_outliers(db_session, reporting_views):
    # The only flagged vial is an outlier, so the set falls back to all non-outliers.
    _vial(db_session, "BGV_030a", 97301, 10.0)
    _vial(db_session, "BGV_031a", 97311, 1.0, background=True, outlier=True)
    _vial(db_session, "BGV_031b", 97312, 4.0)
    _link(db_session, "BGV_030", bg_base="BGV_031")
    (row,) = _bkg_rows(db_session, "BGV_030")
    assert row["bkg_mean_h2_micromoles"] == pytest.approx(4.0)


def test_bkg_rollup_leaves_background_out_of_mixed_sample_group(db_session, reporting_views):
    _vial(db_session, "BGV_040a", 97401, 11.0)
    _vial(db_session, "BGV_040b", 97402, 13.0)
    _vial(db_session, "BGV_040c", 97403, 1.0, background=True)  # blank kept in the sample group
    _vial(db_session, "BGV_041a", 97411, 1.0, background=True)
    _link(db_session, "BGV_040", bg_base="BGV_041")
    assert len(_bkg_rows(db_session, "BGV_040")) == 3  # per-row view keeps every vial
    (row,) = _bkg_rollup(db_session, "BGV_040")
    assert row["n_values"] == 2
    assert row["mean_net_h2_micromoles"] == pytest.approx(11.0)
