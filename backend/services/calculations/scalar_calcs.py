from __future__ import annotations

from sqlalchemy.orm import Session
from backend.services.calculations.registry import register
from database.models.results import ScalarResults


FE_MOLAR_MASS = 55.845  # g/mol


def calculate_ferrous_iron_yield_h2(
    h2_micromoles: float | None,
    total_ferrous_iron_g: float | None,
) -> float | None:
    """H2-derived ferrous iron yield (%).

    Stoichiometry: 3 mol Fe2+ per 1 mol H2

        Fe2+_consumed_g = (h2_micromoles * 3 / 1e6) * FE_MOLAR_MASS
        yield_h2_pct    = (Fe2+_consumed_g / total_ferrous_iron_g) * 100

    Returns None if h2_micromoles is None or total_ferrous_iron_g is None or <= 0.
    """
    if h2_micromoles is None or total_ferrous_iron_g is None or total_ferrous_iron_g <= 0:
        return None
    fe2_consumed_g = (h2_micromoles * 3 / 1_000_000) * FE_MOLAR_MASS
    return (fe2_consumed_g / total_ferrous_iron_g) * 100


def calculate_ferrous_iron_yield_nh3(
    gross_ammonium_mM: float | None,
    background_ammonium_mM: float | None,
    solution_volume_mL: float | None,
    total_ferrous_iron_g: float | None,
) -> float | None:
    """NH3-derived ferrous iron yield (%).

    Stoichiometry: 9 mol Fe2+ per 2 mol NH3 (ratio = 4.5)

        net_ammonium_mM  = max(0, gross_ammonium_mM - background_ammonium_mM)
                           [background defaults to 0.3 mM if None]
        total_NH3_mol    = (net_ammonium_mM / 1000) * (solution_volume_mL / 1000)
        Fe2+_consumed_g  = total_NH3_mol * 4.5 * FE_MOLAR_MASS
        yield_nh3_pct    = (Fe2+_consumed_g / total_ferrous_iron_g) * 100

    Returns None if gross_ammonium_mM, solution_volume_mL, or total_ferrous_iron_g
    is None or <= 0.
    """
    if (
        gross_ammonium_mM is None
        or solution_volume_mL is None
        or solution_volume_mL <= 0
        or total_ferrous_iron_g is None
        or total_ferrous_iron_g <= 0
    ):
        return None
    bg = background_ammonium_mM if background_ammonium_mM is not None else 0.3
    net_mM = max(0.0, gross_ammonium_mM - bg)
    total_nh3_mol = (net_mM / 1000.0) * (solution_volume_mL / 1000.0)
    fe2_consumed_g = total_nh3_mol * 4.5 * FE_MOLAR_MASS
    return (fe2_consumed_g / total_ferrous_iron_g) * 100


@register(ScalarResults)
def recalculate_scalar(instance: object, session: Session) -> None:
    """Recalculate all derived fields on a ScalarResults instance.

    Sets: grams_per_ton_yield, h2_micromoles, h2_mass_ug, h2_grams_per_ton_yield,
          ferrous_iron_yield_h2_pct, ferrous_iron_yield_nh3_pct.

    Reads rock_mass_g and water_volume_mL via:
        instance.result_entry.experiment.conditions
    """
    rock_mass: float | None = None
    liquid_volume_ml: float | None = None
    total_ferrous_iron_g: float | None = None

    result_entry = getattr(instance, 'result_entry', None)
    if result_entry is not None:
        experiment = getattr(result_entry, 'experiment', None)
        if experiment is not None:
            conditions = getattr(experiment, 'conditions', None)
            if conditions is not None:
                rock_mass = getattr(conditions, 'rock_mass_g', None)
                liquid_volume_ml = getattr(conditions, 'water_volume_mL', None)
                total_ferrous_iron_g = getattr(conditions, 'total_ferrous_iron', None)

    # Prefer sampling_volume_mL when available
    sampling_vol = getattr(instance, 'sampling_volume_mL', None)
    if sampling_vol is not None and sampling_vol > 0:
        liquid_volume_ml = sampling_vol

    # H2 calculation
    _calculate_hydrogen(instance)

    # h2_grams_per_ton_yield
    h2_mass_ug = getattr(instance, 'h2_mass_ug', None)
    if rock_mass is not None and rock_mass > 0 and h2_mass_ug is not None:
        h2_mass_g = h2_mass_ug / 1_000_000.0
        instance.h2_grams_per_ton_yield = 1_000_000.0 * (h2_mass_g / rock_mass)
    else:
        instance.h2_grams_per_ton_yield = None

    # Ammonium yield
    gross = getattr(instance, 'gross_ammonium_concentration_mM', None)
    if gross is not None and liquid_volume_ml is not None and liquid_volume_ml > 0:
        bg = getattr(instance, 'background_ammonium_concentration_mM', None)
        bg = bg if bg is not None else 0.3
        net_conc = max(0.0, gross - bg)
        ammonia_mass_g = (net_conc / 1000.0) * (liquid_volume_ml / 1000.0) * 18.04
        if rock_mass is not None and rock_mass > 0:
            instance.grams_per_ton_yield = 1_000_000.0 * (ammonia_mass_g / rock_mass)
        else:
            instance.grams_per_ton_yield = None
    else:
        instance.grams_per_ton_yield = None

    # Ferrous iron yield — H2 derived
    h2_micromoles = getattr(instance, 'h2_micromoles', None)
    instance.ferrous_iron_yield_h2_pct = calculate_ferrous_iron_yield_h2(
        h2_micromoles=h2_micromoles,
        total_ferrous_iron_g=total_ferrous_iron_g,
    )

    # Ferrous iron yield — NH3 derived
    gross = getattr(instance, 'gross_ammonium_concentration_mM', None)
    bg_nh3 = getattr(instance, 'background_ammonium_concentration_mM', None)
    instance.ferrous_iron_yield_nh3_pct = calculate_ferrous_iron_yield_nh3(
        gross_ammonium_mM=gross,
        background_ammonium_mM=bg_nh3,
        solution_volume_mL=liquid_volume_ml,
        total_ferrous_iron_g=total_ferrous_iron_g,
    )


def _calculate_hydrogen(instance: object) -> None:
    """Calculate H2 amount from gas-phase ppm using PV = nRT at 20 degrees C.

    Inputs (on instance):
        h2_concentration       -- ppm (vol/vol)
        gas_sampling_volume_ml -- mL
        gas_sampling_pressure_MPa -- MPa

    Outputs set on instance:
        h2_micromoles  (umol)
        h2_mass_ug     (ug)
    """
    h2_ppm = getattr(instance, 'h2_concentration', None)
    vol_ml = getattr(instance, 'gas_sampling_volume_ml', None)
    pressure_mpa = getattr(instance, 'gas_sampling_pressure_MPa', None)

    if h2_ppm is None or vol_ml is None or vol_ml <= 0 or pressure_mpa is None or pressure_mpa <= 0:
        instance.h2_micromoles = None
        instance.h2_mass_ug = None
        return

    R = 0.082057          # L·atm/(mol·K)
    T_K = 293.15          # 20°C
    H2_MOLAR_MASS = 2.01588  # g/mol

    P_atm = pressure_mpa * 9.86923
    V_L = vol_ml / 1000.0
    n_total = (P_atm * V_L) / (R * T_K)
    fraction = h2_ppm / 1_000_000.0

    if fraction < 0:
        instance.h2_micromoles = None
        instance.h2_mass_ug = None
        return

    h2_moles = n_total * fraction
    instance.h2_micromoles = h2_moles * 1_000_000.0
    instance.h2_mass_ug = h2_moles * H2_MOLAR_MASS * 1_000_000.0
