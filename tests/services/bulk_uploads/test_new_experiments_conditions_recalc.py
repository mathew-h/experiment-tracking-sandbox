# tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py
"""Tests: the New Experiments bulk upload recalculates stored derived fields on
every ExperimentalConditions row it touches.

water_to_rock_ratio and total_ferrous_iron_g are written by recalculate_conditions()
in the calculation registry. This uploader never called it, so bulk-created
experiments landed with both NULL — which made ferrous_iron_yield_h2_pct and
ferrous_iron_yield_nh3_pct NULL on all of their scalar results, because
calculate_ferrous_iron_yield_h2() returns None when total_ferrous_iron_g is None.

Motivating production case: SERUM_Catalyst_001a-t3 (353.88 ppm H2, 30 mL, 14.7 psi)
had h2_micromoles = 0.4415 and h2_grams_per_ton_yield = 0.8899 but no Fe2+ %H2.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

import backend.services.calculations  # noqa: F401 — registers all calculators

from database import Analyte, ElementalAnalysis, Experiment, ExperimentalConditions, SampleInfo
from database.models.analysis import ExternalAnalysis
from backend.services.bulk_uploads.new_experiments import (
    NewExperimentsUploadService,
    _recalculate_touched_conditions,
)
from backend.services.elemental_composition_service import FE_IN_FEO_FRACTION

from .excel_helpers import make_excel, make_excel_multisheet

_EXP_HEADERS = [
    "experiment_id", "old_experiment_id", "sample_id", "researcher",
    "date", "status", "initial_note", "overwrite",
]


def _seed_sample_with_feo(db: Session, sample_id: str, feo_wt_pct: float) -> SampleInfo:
    """SampleInfo + Elemental ExternalAnalysis + FeO Analyte + ElementalAnalysis."""
    sample = SampleInfo(sample_id=sample_id)
    db.add(sample)
    db.flush()

    ext = ExternalAnalysis(sample_id=sample_id, analysis_type="Elemental")
    db.add(ext)
    db.flush()

    analyte = db.query(Analyte).filter_by(analyte_symbol="FeO").first()
    if not analyte:
        analyte = Analyte(analyte_symbol="FeO", unit="%")
        db.add(analyte)
        db.flush()

    db.add(ElementalAnalysis(
        external_analysis_id=ext.id,
        sample_id=sample_id,
        analyte_id=analyte.id,
        analyte_composition=feo_wt_pct,
    ))
    db.flush()
    return sample


def test_helper_sets_both_derived_fields(db_session: Session):
    """The helper writes water_to_rock_ratio and total_ferrous_iron_g, and counts the row."""
    _seed_sample_with_feo(db_session, "ROCK-RC-001", 9.5)
    exp = Experiment(experiment_id="SERUM_RC_001", experiment_number=990001,
                     sample_id="ROCK-RC-001")
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_id="SERUM_RC_001", experiment_fk=exp.id,
        rock_mass_g=1.0, water_volume_mL=20.0,
    )
    db_session.add(cond)
    db_session.flush()
    cond.total_ferrous_iron_g = None
    cond.water_to_rock_ratio = None
    db_session.flush()

    recalculated, warnings = _recalculate_touched_conditions(db_session, {cond.id})

    assert recalculated == 1
    assert warnings == []
    db_session.refresh(cond)
    assert cond.water_to_rock_ratio == pytest.approx(20.0)
    assert cond.total_ferrous_iron_g == pytest.approx(
        (9.5 / 100.0) * FE_IN_FEO_FRACTION * 1.0, rel=1e-4
    )


def test_helper_skips_unknown_id_without_warning(db_session: Session):
    """An id whose row is gone (rolled-back savepoint) is skipped, not warned about."""
    recalculated, warnings = _recalculate_touched_conditions(db_session, {987654321})

    assert recalculated == 0
    assert warnings == []


def test_helper_recalculates_remaining_rows_after_one_failure(db_session: Session, monkeypatch):
    """One unusable row must not cost the other rows their derived fields."""
    _seed_sample_with_feo(db_session, "ROCK-RC-002", 8.0)
    ids = []
    for n in (1, 2):
        exp = Experiment(experiment_id=f"SERUM_RC_01{n}", experiment_number=990010 + n,
                         sample_id="ROCK-RC-002")
        db_session.add(exp)
        db_session.flush()
        cond = ExperimentalConditions(
            experiment_id=f"SERUM_RC_01{n}", experiment_fk=exp.id,
            rock_mass_g=2.0, water_volume_mL=40.0,
        )
        db_session.add(cond)
        db_session.flush()
        cond.total_ferrous_iron_g = None
        cond.water_to_rock_ratio = None
        ids.append(cond.id)
    db_session.flush()

    # Fail on the lowest id only; the helper iterates sorted(conditions_ids).
    import backend.services.bulk_uploads.new_experiments as mod
    real = mod.recalculate
    first = min(ids)

    def flaky(instance, session):
        if getattr(instance, "id", None) == first:
            raise RuntimeError("boom")
        return real(instance, session)

    monkeypatch.setattr(mod, "recalculate", flaky)

    recalculated, warnings = _recalculate_touched_conditions(db_session, set(ids))

    assert recalculated == 1
    assert len(warnings) == 1
    assert "boom" in warnings[0]
    survivor = db_session.get(ExperimentalConditions, max(ids))
    assert survivor.water_to_rock_ratio == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Integration: all three conditions write paths in bulk_upsert_from_excel
# ---------------------------------------------------------------------------

def test_conditions_sheet_path_recalculates(db_session: Session):
    """A conditions sheet row gets both derived fields computed by the upload."""
    _seed_sample_with_feo(db_session, "ROCK-RC-010", 9.5)

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_RC_100", None, "ROCK-RC-010", "MH", "2026-08-03", "ONGOING", None, None]],
        ),
        "conditions": (
            ["experiment_id", "rock_mass_g", "water_volume_mL"],
            [["SERUM_RC_100", 1.0, 20.0]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    exp = db_session.query(Experiment).filter_by(experiment_id="SERUM_RC_100").one()
    cond = db_session.query(ExperimentalConditions).filter_by(experiment_fk=exp.id).one()
    assert cond.water_to_rock_ratio == pytest.approx(20.0)
    assert cond.total_ferrous_iron_g == pytest.approx(
        (9.5 / 100.0) * FE_IN_FEO_FRACTION * 1.0, rel=1e-4
    ), "conditions-sheet path did not recalculate total_ferrous_iron_g"
    assert any("Recalculated derived fields" in m for m in info)


def test_conditions_sheet_overwrite_of_existing_row_recalculates(db_session: Session):
    """An overwrite that changes rock_mass_g must recompute, not keep the old value."""
    _seed_sample_with_feo(db_session, "ROCK-RC-011", 10.0)
    exp = Experiment(experiment_id="SERUM_RC_110", experiment_number=990110,
                     sample_id="ROCK-RC-011")
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_id="SERUM_RC_110", experiment_fk=exp.id,
        rock_mass_g=1.0, water_volume_mL=20.0,
        total_ferrous_iron_g=(10.0 / 100.0) * FE_IN_FEO_FRACTION * 1.0,
        water_to_rock_ratio=20.0,
    )
    db_session.add(cond)
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_RC_110", None, None, None, None, None, None, True]],
        ),
        "conditions": (
            ["experiment_id", "rock_mass_g"],
            [["SERUM_RC_110", 4.0]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    db_session.refresh(cond)
    assert cond.water_to_rock_ratio == pytest.approx(5.0), "stale ratio after overwrite"
    assert cond.total_ferrous_iron_g == pytest.approx(
        (10.0 / 100.0) * FE_IN_FEO_FRACTION * 4.0, rel=1e-4
    ), "stale total_ferrous_iron_g after overwrite"


def test_parent_autocopy_path_recalculates(db_session: Session):
    """A sequential re-run with no conditions sheet row copies the parent's conditions
    and must still get its own derived fields computed."""
    _seed_sample_with_feo(db_session, "ROCK-RC-012", 9.5)
    parent = Experiment(experiment_id="SERUM_RC_120", experiment_number=990120,
                        sample_id="ROCK-RC-012")
    db_session.add(parent)
    db_session.flush()
    db_session.add(ExperimentalConditions(
        experiment_id="SERUM_RC_120", experiment_fk=parent.id,
        rock_mass_g=2.0, water_volume_mL=20.0, experiment_type="Serum",
    ))
    db_session.flush()

    # No conditions sheet at all -> the auto-copy pass creates the child's row.
    xlsx = make_excel(
        _EXP_HEADERS,
        [["SERUM_RC_120-2", None, "ROCK-RC-012", "MH", None, "ONGOING", None, None]],
        sheet_name="experiments",
    )
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    child = db_session.query(Experiment).filter_by(experiment_id="SERUM_RC_120-2").one()
    cond = db_session.query(ExperimentalConditions).filter_by(experiment_fk=child.id).one()
    assert cond.rock_mass_g == pytest.approx(2.0), "parent conditions were not copied"
    assert cond.water_to_rock_ratio == pytest.approx(10.0)
    assert cond.total_ferrous_iron_g == pytest.approx(
        (9.5 / 100.0) * FE_IN_FEO_FRACTION * 2.0, rel=1e-4
    ), "auto-copy path did not recalculate total_ferrous_iron_g"


def test_additives_only_path_recalculates(db_session: Session):
    """An experiment reaching conditions creation only through the additives sheet
    gets its derived fields computed (NULL here — that row carries no rock mass).

    The additives sheet creates a bare conditions row with no rock_mass_g, so both
    derived fields are None either way and cannot themselves gate on the fix. What
    does gate is the cascade: recalculate_conditions() recomputes every linked
    ScalarResults row (conditions_calcs.py:48-57), so a stored yield left over from a
    state that no longer holds is rewritten. Without the recalculation pass the stale
    values survive the upload untouched. (An earlier version of this test asserted on
    info_messages instead — a message the router discards, so no user ever sees it;
    see docs/issues/issue-bulk-upload-never-recalculates-conditions.md.)
    """
    from backend.services.scalar_results_service import ScalarResultsService

    _seed_sample_with_feo(db_session, "ROCK-RC-013", 9.5)
    exp = Experiment(experiment_id="SERUM_RC_130", experiment_number=990130,
                     sample_id="ROCK-RC-013")
    db_session.add(exp)
    db_session.flush()

    # A real H2 chain, but with the two rock-mass-dependent stored fields holding
    # stale values that no longer follow from this experiment's inputs.
    upsert = ScalarResultsService.create_scalar_result_ex(
        db_session, "SERUM_RC_130",
        {
            "time_post_reaction": 3.0,
            "description": "DI, GC-A",
            "h2_concentration": 353.8808110781404,
            "gas_sampling_volume_ml": 30.0,
            "gas_sampling_pressure_MPa": 0.10135297199999999,
        },
    )
    scalar = upsert.experimental_result.scalar_data
    scalar.ferrous_iron_yield_h2_pct = 0.5
    scalar.h2_grams_per_ton_yield = 42.0
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_RC_130", None, None, None, None, None, None, True]],
        ),
        "additives": (
            ["experiment_id", "compound", "amount", "unit"],
            [["SERUM_RC_130", "NiCl2", 5.0, "mg"]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    cond = db_session.query(ExperimentalConditions).filter_by(experiment_fk=exp.id).one()
    # No rock_mass_g on this row, so both stay None — but explicitly computed as
    # None rather than left uncomputed, matching backfill_total_ferrous_iron_017's
    # stated philosophy.
    assert cond.total_ferrous_iron_g is None
    assert cond.water_to_rock_ratio is None

    db_session.refresh(scalar)
    assert scalar.h2_micromoles is not None, "the H2 chain itself must survive"
    assert scalar.ferrous_iron_yield_h2_pct is None, (
        "stale stored Fe2+ %H2 survived the upload — the additives-path conditions "
        "row was not recorded or the recalculation pass did not run"
    )
    assert scalar.h2_grams_per_ton_yield is None, (
        "stale stored h2_grams_per_ton_yield survived the upload"
    )


def test_overwrite_repairs_stored_yield_on_pre_existing_scalar_row(db_session: Session):
    """The mechanism the whole production backfill rests on.

    An `overwrite=TRUE` conditions row must push the corrected `total_ferrous_iron_g`
    through `recalculate_conditions()`'s ScalarResults cascade
    (`backend/services/calculations/conditions_calcs.py:48-57`) into the **stored**
    `ferrous_iron_yield_h2_pct` of a scalar row that already existed before the
    upload. `test_conditions_sheet_overwrite_of_existing_row_recalculates` seeds no
    results, and `test_bulk_created_experiment_gets_fe_yield_h2_on_scalar_result`
    creates its scalar row *after* the upload, so that value comes from
    `ScalarResultsService` rather than from the cascade. Only this test covers it.
    """
    from backend.services.scalar_results_service import ScalarResultsService

    feo_wt_pct = 10.0
    old_rock_mass_g = 1.0
    new_rock_mass_g = 4.0
    _seed_sample_with_feo(db_session, "ROCK-RC-014", feo_wt_pct)

    exp = Experiment(experiment_id="SERUM_RC_140", experiment_number=990140,
                     sample_id="ROCK-RC-014")
    db_session.add(exp)
    db_session.flush()
    cond = ExperimentalConditions(
        experiment_id="SERUM_RC_140", experiment_fk=exp.id,
        rock_mass_g=old_rock_mass_g, water_volume_mL=20.0,
        total_ferrous_iron_g=(feo_wt_pct / 100.0) * FE_IN_FEO_FRACTION * old_rock_mass_g,
        water_to_rock_ratio=20.0,
    )
    db_session.add(cond)
    db_session.flush()

    # A pre-existing scalar row whose stored yield describes the OLD rock mass.
    upsert = ScalarResultsService.create_scalar_result_ex(
        db_session, "SERUM_RC_140",
        {
            "time_post_reaction": 3.0,
            "description": "DI, GC-A",
            "h2_concentration": 353.8808110781404,
            "gas_sampling_volume_ml": 30.0,
            "gas_sampling_pressure_MPa": 0.10135297199999999,
        },
    )
    scalar = upsert.experimental_result.scalar_data
    db_session.flush()
    h2_micromoles = scalar.h2_micromoles
    yield_before = scalar.ferrous_iron_yield_h2_pct
    assert h2_micromoles is not None
    assert yield_before is not None, (
        "fixture is not exercising the cascade — the pre-existing scalar row must "
        "start with a non-NULL stored yield"
    )

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_RC_140", None, None, None, None, None, None, True]],
        ),
        "conditions": (
            ["experiment_id", "rock_mass_g"],
            [["SERUM_RC_140", new_rock_mass_g]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected errors: {errors}"

    # 3 mol Fe2+ per mol H2; umol -> mol; x 55.845 g/mol (scalar_calcs.py:26).
    fe_consumed_g = (h2_micromoles * 3 / 1e6) * 55.845
    new_total_fe_g = (feo_wt_pct / 100.0) * FE_IN_FEO_FRACTION * new_rock_mass_g
    expected_yield_pct = fe_consumed_g / new_total_fe_g * 100.0

    db_session.refresh(cond)
    db_session.refresh(scalar)
    assert cond.total_ferrous_iron_g == pytest.approx(new_total_fe_g, rel=1e-4)
    assert scalar.ferrous_iron_yield_h2_pct == pytest.approx(expected_yield_pct, rel=1e-4), (
        "stored Fe2+ %H2 on the pre-existing scalar row still describes the old rock "
        "mass — the recalculate_conditions -> recalculate_scalar cascade did not run"
    )
    # 4x the rock mass, so a quarter of the yield: the value must actually have moved.
    assert scalar.ferrous_iron_yield_h2_pct == pytest.approx(yield_before / 4.0, rel=1e-4)


# ---------------------------------------------------------------------------
# End-to-end: the production case that motivated this work
# ---------------------------------------------------------------------------

def test_bulk_created_experiment_gets_fe_yield_h2_on_scalar_result(db_session: Session):
    """Reproduces SERUM_Catalyst_001a-t3: a bulk-created vial with a DI H2 reading
    must end up with a non-NULL ferrous_iron_yield_h2_pct."""
    from backend.services.scalar_results_service import ScalarResultsService

    _seed_sample_with_feo(db_session, "20250616_RC", 9.5)

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_RCat_001a-t3", None, "20250616_RC", "MH", "2026-08-03",
              "ONGOING", None, None]],
        ),
        "conditions": (
            ["experiment_id", "rock_mass_g", "water_volume_mL"],
            [["SERUM_RCat_001a-t3", 1.0, 20.0]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected errors: {errors}"

    # The real row's numbers: 353.88 ppm through a 30 mL / 14.7 psi DI injection.
    upsert = ScalarResultsService.create_scalar_result_ex(
        db_session, "SERUM_RCat_001a-t3",
        {
            "time_post_reaction": 3.0,
            "description": "DI, GC-A",
            "h2_concentration": 353.8808110781404,
            "gas_sampling_volume_ml": 30.0,
            "gas_sampling_pressure_MPa": 0.10135297199999999,
        },
    )
    scalar = upsert.experimental_result.scalar_data

    assert scalar.h2_micromoles == pytest.approx(0.4414611531787, rel=1e-6)
    assert scalar.ferrous_iron_yield_h2_pct is not None, (
        "Fe2+ %H2 is still NULL — total_ferrous_iron_g was not computed by the upload"
    )
    assert scalar.ferrous_iron_yield_h2_pct == pytest.approx(0.10015684764938, rel=1e-4)
