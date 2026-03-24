# backend/services/elemental_composition_service.py
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)

# Fe atomic mass (55.845) / FeO molar mass (71.844)
FE_IN_FEO_FRACTION: float = 55.845 / 71.844


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
