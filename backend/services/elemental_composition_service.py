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
