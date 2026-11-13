# backend/services/elemental_composition_service.py
from __future__ import annotations

from contextvars import ContextVar

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.services.physical_constants import FE_MOLAR_MASS, FEO_MOLAR_MASS

log = structlog.get_logger(__name__)

# Set only while recalculate_conditions_for_samples runs: (sample_id, analyte
# symbol) -> wt%. None everywhere else, so every other caller of
# get_analyte_wt_pct always reads the database.
_WT_PCT_CACHE: ContextVar[dict[tuple[str, str], float | None] | None] = ContextVar(
    "elemental_wt_pct_cache", default=None)

# Fe atomic mass (55.845) / FeO molar mass (71.844)
FE_IN_FEO_FRACTION: float = FE_MOLAR_MASS / FEO_MOLAR_MASS


def calculate_total_ferrous_iron_g(
    feo_wt_pct: float | None,
    rock_mass_g: float | None,
) -> float | None:
    """Compute total ferrous iron mass in grams from FeO wt% and rock mass.

    Formula:
        fe_mass_fraction = (feo_wt_pct / 100) * FE_IN_FEO_FRACTION
        total_ferrous_iron_g = fe_mass_fraction * rock_mass_g

    Returns None when any required input is missing or rock_mass_g <= 0.
    """
    if feo_wt_pct is None or rock_mass_g is None:
        return None
    if rock_mass_g <= 0:
        log.warning("total_ferrous_iron_g_skipped", reason="rock_mass_g <= 0", rock_mass_g=rock_mass_g)
        return None
    return (feo_wt_pct / 100.0) * FE_IN_FEO_FRACTION * rock_mass_g


def recalculate_conditions_for_samples(db: Session, sample_ids: set[str]) -> int:
    """Recalculate total_ferrous_iron_g on ExperimentalConditions for all experiments
    linked to the given sample_ids. Cascades to ScalarResults via the registry.

    Called after any elemental upload that may have written new FeO data so that
    experiments created before the rock data arrived get their derived fields set.

    Returns count of conditions rows processed.
    """
    if not sample_ids:
        return 0

    from database.models.experiments import Experiment
    from backend.services.calculations.registry import recalculate
    from backend.services.experiment_lookup import lowest_conditions_map

    experiments = (
        db.query(Experiment)
        .filter(Experiment.sample_id.in_(sample_ids))
        .order_by(Experiment.id)
        .all()
    )
    # One query for every conditions row; the lowest id wins should a database
    # that predates uq_conditions_experiment_fk hold a duplicate (issue #109).
    conditions_by_experiment = lowest_conditions_map(db, [e.id for e in experiments])

    count = 0
    # Many experiments share one rock. Its FeO value cannot change inside this
    # call (the upload that triggered it has already written), so each sample's
    # lookup runs once instead of once per experiment (issue #191, E-06).
    token = _WT_PCT_CACHE.set({})
    try:
        for experiment in experiments:
            conditions = conditions_by_experiment.get(experiment.id)
            if conditions is None:
                continue
            try:
                # SAVEPOINT per row: a database error on one experiment rolls
                # back that row only and leaves the session usable for the rest.
                with db.begin_nested():
                    recalculate(conditions, db)
                count += 1
            except Exception:
                log.warning(
                    "recalculate_conditions_for_samples_failed",
                    experiment_id=experiment.experiment_id,
                    exc_info=True,
                )
    finally:
        _WT_PCT_CACHE.reset(token)

    return count


def get_analyte_wt_pct(
    sample_id: str | None,
    db: Session,
    analyte_symbol: str = "FeO",
) -> float | None:
    """Return the wt% composition for analyte_symbol from the most recent
    elemental characterization ExternalAnalysis linked to sample_id.

    Matches analysis_type in ('Elemental', 'Bulk Elemental Composition') — the
    titration uploader vs wide-format bulk elemental Excel uploader respectively.

    Returns analyte_composition (float) from ElementalAnalysis, or None if:
    - sample_id is None
    - No matching ExternalAnalysis exists for the sample
    - No ElementalAnalysis row exists for the given analyte_symbol with unit '%'
    - analyte_composition is NULL

    When multiple ExternalAnalysis records exist for the same sample and analyte,
    the most recent by analysis_date is used.
    """
    if sample_id is None:
        return None

    cache = _WT_PCT_CACHE.get()
    if cache is not None and (sample_id, analyte_symbol) in cache:
        return cache[(sample_id, analyte_symbol)]
    value = _query_analyte_wt_pct(sample_id, db, analyte_symbol)
    if cache is not None:
        cache[(sample_id, analyte_symbol)] = value
    return value


def _query_analyte_wt_pct(sample_id: str, db: Session, analyte_symbol: str) -> float | None:
    """The database lookup behind ``get_analyte_wt_pct``."""
    # Local imports to avoid circular import: this service is imported by
    # conditions_calcs.py, which is imported by the model layer event listeners.
    from database.models.analysis import ExternalAnalysis
    from database.models.characterization import ElementalAnalysis, Analyte

    result = db.execute(
        select(ElementalAnalysis.analyte_composition)
        .join(ExternalAnalysis, ElementalAnalysis.external_analysis_id == ExternalAnalysis.id)
        .join(Analyte, ElementalAnalysis.analyte_id == Analyte.id)
        .where(ExternalAnalysis.sample_id == sample_id)
        .where(
            ExternalAnalysis.analysis_type.in_(["Elemental", "Bulk Elemental Composition"])
        )
        .where(Analyte.analyte_symbol == analyte_symbol)
        .where(Analyte.unit == "%")
        .order_by(ExternalAnalysis.analysis_date.desc())
        .limit(1)
    ).scalar_one_or_none()

    return result
