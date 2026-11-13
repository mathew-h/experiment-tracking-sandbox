# tests/services/bulk_uploads/test_elemental_upload_recalc.py
"""
Tests: after actlabs elemental uploads, total_ferrous_iron_g is recalculated
on ExperimentalConditions for all experiments linked to the affected sample.
"""
from __future__ import annotations

import io

import pandas as pd
import pytest

import backend.services.calculations  # noqa: F401 — registers all calculators

from database import SampleInfo, Analyte, ElementalAnalysis
from database.models.analysis import ExternalAnalysis
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment

from backend.services.elemental_composition_service import (
    FE_IN_FEO_FRACTION,
    recalculate_conditions_for_samples,
)
from backend.services.bulk_uploads.actlabs_titration_data import (
    ActlabsRockTitrationService,
    ElementalCompositionService,
)
from tests.services.bulk_uploads.excel_helpers import make_excel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seed_sample_with_feo(db, sample_id: str, feo_wt_pct: float):
    """Add SampleInfo + ExternalAnalysis + Analyte + ElementalAnalysis for FeO."""
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


def _seed_experiment_with_conditions(db, sample_id: str, exp_id: str, exp_num: int, rock_mass_g):
    """Add Experiment + ExperimentalConditions linked to sample_id."""
    experiment = Experiment(
        experiment_id=exp_id,
        experiment_number=exp_num,
        sample_id=sample_id,
    )
    db.add(experiment)
    db.flush()

    conditions = ExperimentalConditions(
        experiment_id=exp_id,
        experiment_fk=experiment.id,
        rock_mass_g=rock_mass_g,
        water_volume_mL=500.0,
    )
    db.add(conditions)
    db.flush()
    return experiment, conditions


# ---------------------------------------------------------------------------
# Unit tests for recalculate_conditions_for_samples
# ---------------------------------------------------------------------------

def test_recalculate_conditions_for_samples_sets_total_ferrous_iron_g(db_session):
    """Helper should compute total_ferrous_iron_g from FeO data when rock_mass_g is present."""
    feo_wt_pct = 10.0
    rock_mass_g = 100.0
    _seed_sample_with_feo(db_session, "ROCK-001", feo_wt_pct)
    _, conditions = _seed_experiment_with_conditions(
        db_session, "ROCK-001", "EXP-001", 1, rock_mass_g
    )
    conditions.total_ferrous_iron_g = None  # simulate pre-existing NULL
    db_session.flush()

    recalculate_conditions_for_samples(db_session, {"ROCK-001"})

    db_session.refresh(conditions)
    expected = (feo_wt_pct / 100.0) * FE_IN_FEO_FRACTION * rock_mass_g
    assert conditions.total_ferrous_iron_g == pytest.approx(expected, rel=1e-4)


def test_recalculate_conditions_for_samples_skips_null_rock_mass(db_session):
    """When rock_mass_g is None, total_ferrous_iron_g stays None (silent skip)."""
    _seed_sample_with_feo(db_session, "ROCK-002", 12.0)
    _, conditions = _seed_experiment_with_conditions(
        db_session, "ROCK-002", "EXP-002", 2, rock_mass_g=None
    )
    conditions.total_ferrous_iron_g = None
    db_session.flush()

    recalculate_conditions_for_samples(db_session, {"ROCK-002"})

    db_session.refresh(conditions)
    assert conditions.total_ferrous_iron_g is None


def test_recalculate_conditions_for_samples_updates_multiple_experiments(db_session):
    """Two experiments linked to the same sample both get total_ferrous_iron_g set."""
    _seed_sample_with_feo(db_session, "ROCK-003", 8.0)
    _, cond_a = _seed_experiment_with_conditions(db_session, "ROCK-003", "EXP-003A", 3, 50.0)
    _, cond_b = _seed_experiment_with_conditions(db_session, "ROCK-003", "EXP-003B", 4, 200.0)
    cond_a.total_ferrous_iron_g = None
    cond_b.total_ferrous_iron_g = None
    db_session.flush()

    recalculate_conditions_for_samples(db_session, {"ROCK-003"})

    db_session.refresh(cond_a)
    db_session.refresh(cond_b)
    expected_a = (8.0 / 100.0) * FE_IN_FEO_FRACTION * 50.0
    expected_b = (8.0 / 100.0) * FE_IN_FEO_FRACTION * 200.0
    assert cond_a.total_ferrous_iron_g == pytest.approx(expected_a, rel=1e-4)
    assert cond_b.total_ferrous_iron_g == pytest.approx(expected_b, rel=1e-4)


def test_recalculate_conditions_for_samples_ignores_unrelated_sample(db_session):
    """Experiments linked to a different sample are not touched."""
    _seed_sample_with_feo(db_session, "ROCK-004", 15.0)

    other_sample = SampleInfo(sample_id="ROCK-005")
    db_session.add(other_sample)
    db_session.flush()
    _, cond_other = _seed_experiment_with_conditions(
        db_session, "ROCK-005", "EXP-005", 5, 100.0
    )
    cond_other.total_ferrous_iron_g = None
    db_session.flush()

    recalculate_conditions_for_samples(db_session, {"ROCK-004"})

    db_session.refresh(cond_other)
    assert cond_other.total_ferrous_iron_g is None


# ---------------------------------------------------------------------------
# Integration: actlabs titration import triggers recalculation
# ---------------------------------------------------------------------------

def _build_actlabs_csv(sample_id: str, feo_val: float) -> bytes:
    """Minimal ActLabs-format CSV bytes for a single sample + FeO column."""
    rows = [
        ["Report Number", "", ""],
        ["Report Date", "", ""],
        ["Sample ID", "FeO", "SiO2"],
        ["", "%", "%"],
        ["Detection Limit", "0.01", "0.01"],
        ["Analysis Method: titration", "", ""],
        [sample_id, feo_val, 45.0],
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, header=False, index=False)
    buf.seek(0)
    return buf.getvalue()


def test_actlabs_import_recalculates_linked_experiments(db_session):
    """After ActlabsRockTitrationService.import_excel, linked conditions get total_ferrous_iron_g."""
    sample = SampleInfo(sample_id="ROCK-ACT")
    db_session.add(sample)
    _, conditions = _seed_experiment_with_conditions(
        db_session, "ROCK-ACT", "EXP-ACT", 10, 100.0
    )
    conditions.total_ferrous_iron_g = None
    db_session.flush()

    payload = _build_actlabs_csv("ROCK-ACT", feo_val=12.5)
    ActlabsRockTitrationService.import_excel(db_session, payload)

    db_session.refresh(conditions)
    expected = (12.5 / 100.0) * FE_IN_FEO_FRACTION * 100.0
    assert conditions.total_ferrous_iron_g == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# Integration: wide-format elemental composition import triggers recalculation
# ---------------------------------------------------------------------------

def test_wide_format_import_recalculates_linked_experiments(db_session):
    """After ElementalCompositionService.bulk_upsert_wide_from_excel, conditions get updated."""
    analyte = Analyte(analyte_symbol="FeO", unit="%")
    db_session.add(analyte)
    sample = SampleInfo(sample_id="ROCK-WIDE")
    db_session.add(sample)
    _, conditions = _seed_experiment_with_conditions(
        db_session, "ROCK-WIDE", "EXP-WIDE", 20, 80.0
    )
    conditions.total_ferrous_iron_g = None
    db_session.flush()

    payload = make_excel(
        headers=["sample_id", "FeO"],
        rows=[["ROCK-WIDE", 9.0]],
    )
    ElementalCompositionService.bulk_upsert_wide_from_excel(db_session, payload)

    db_session.refresh(conditions)
    expected = (9.0 / 100.0) * FE_IN_FEO_FRACTION * 80.0
    assert conditions.total_ferrous_iron_g == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# Issue #191 (E-06): one conditions query, FeO read once per sample, SAVEPOINT per row
# ---------------------------------------------------------------------------

def _seed_experiments_on_sample(db, sample_id: str, prefix: str, start: int, count: int, rock_mass_g=10.0):
    conditions = []
    for i in range(count):
        exp = Experiment(experiment_id=f"{prefix}_{i + 1:03d}", experiment_number=start + i, sample_id=sample_id)
        db.add(exp)
        db.flush()
        cond = ExperimentalConditions(experiment_fk=exp.id, experiment_id=exp.experiment_id,
                                      rock_mass_g=rock_mass_g, water_volume_mL=50.0)
        db.add(cond)
        conditions.append(cond)
    db.flush()
    return conditions


def _feo_lookups(statements: list[str]) -> int:
    return sum(1 for s in statements if "elemental_analysis" in s and "analyte_composition" in s)


def test_feo_is_read_once_per_sample_not_once_per_experiment(db_session):
    from tests.api.test_query_counts import count_queries

    _seed_sample_with_feo(db_session, "E06_ROCK_A", 8.0)
    _seed_sample_with_feo(db_session, "E06_ROCK_B", 4.0)
    on_a = _seed_experiments_on_sample(db_session, "E06_ROCK_A", "E06A", 9196000, 6)
    on_b = _seed_experiments_on_sample(db_session, "E06_ROCK_B", "E06B", 9196100, 2)

    with count_queries() as statements:
        processed = recalculate_conditions_for_samples(db_session, {"E06_ROCK_A", "E06_ROCK_B"})

    assert processed == 8
    assert _feo_lookups(statements) == 2  # one per sample, not one per experiment
    for cond in on_a:
        assert cond.total_ferrous_iron_g == pytest.approx(0.08 * FE_IN_FEO_FRACTION * 10.0)
    for cond in on_b:
        assert cond.total_ferrous_iron_g == pytest.approx(0.04 * FE_IN_FEO_FRACTION * 10.0)


def test_the_feo_cache_does_not_outlive_the_call(db_session):
    """A later upload changes FeO; the next call must read the new value."""
    from backend.services import elemental_composition_service as service

    _seed_sample_with_feo(db_session, "E06_ROCK_C", 8.0)
    (cond,) = _seed_experiments_on_sample(db_session, "E06_ROCK_C", "E06C", 9196200, 1)
    recalculate_conditions_for_samples(db_session, {"E06_ROCK_C"})
    assert cond.total_ferrous_iron_g == pytest.approx(0.08 * FE_IN_FEO_FRACTION * 10.0)
    assert service._WT_PCT_CACHE.get() is None

    row = db_session.query(ElementalAnalysis).filter_by(sample_id="E06_ROCK_C").one()
    row.analyte_composition = 2.0
    db_session.flush()
    recalculate_conditions_for_samples(db_session, {"E06_ROCK_C"})
    assert cond.total_ferrous_iron_g == pytest.approx(0.02 * FE_IN_FEO_FRACTION * 10.0)


def test_one_failing_experiment_does_not_stop_or_poison_the_rest(db_session, monkeypatch):
    """A database error on one row is rolled back to its SAVEPOINT; the other
    rows are still recalculated and the session stays usable."""
    from sqlalchemy import text

    import backend.services.calculations.registry as registry

    _seed_sample_with_feo(db_session, "E06_ROCK_D", 8.0)
    first, bad, last = _seed_experiments_on_sample(db_session, "E06_ROCK_D", "E06D", 9196300, 3)
    real = registry.recalculate

    def flaky(instance, session):
        if instance is bad:
            session.execute(text("SELECT 1 / 0"))  # a real DBAPI error inside the row
        real(instance, session)

    monkeypatch.setattr(registry, "recalculate", flaky)
    processed = recalculate_conditions_for_samples(db_session, {"E06_ROCK_D"})

    assert processed == 2
    expected = pytest.approx(0.08 * FE_IN_FEO_FRACTION * 10.0)
    assert first.total_ferrous_iron_g == expected and last.total_ferrous_iron_g == expected
    assert bad.total_ferrous_iron_g is None
    assert db_session.execute(text("SELECT 1")).scalar() == 1  # not in a failed transaction
