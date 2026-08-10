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
