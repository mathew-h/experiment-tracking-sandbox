from __future__ import annotations

from sqlalchemy.orm import Session
from backend.services.calculations.registry import register
from database.models.chemicals import ChemicalAdditive
from database.models.enums import AmountUnit


@register(ChemicalAdditive)
def recalculate_additive(instance: object, session: Session) -> None:
    """Recalculate all derived fields on a ChemicalAdditive instance.

    Sets: mass_in_grams, moles_added, final_concentration, concentration_units,
          elemental_metal_mass, catalyst_percentage, catalyst_ppm.

    Reads experiment.water_volume_mL and experiment.rock_mass_g from the
    linked ExperimentalConditions (via instance.experiment relationship).
    """
    # --- gather context ---
    water_volume_ml: float | None = None
    rock_mass: float | None = None
    volume_liters: float | None = None

    experiment = getattr(instance, 'experiment', None)
    if experiment is not None:
        water_volume_ml = getattr(experiment, 'water_volume_mL', None)
        rock_mass = getattr(experiment, 'rock_mass_g', None)
        if isinstance(water_volume_ml, (int, float)) and water_volume_ml and water_volume_ml > 0:
            volume_liters = water_volume_ml / 1000.0

    compound = getattr(instance, 'compound', None)
    molecular_weight: float | None = (
        getattr(compound, 'molecular_weight_g_mol', None) if compound else None
    )

    # --- reset outputs ---
    instance.mass_in_grams = None
    instance.moles_added = None
    instance.final_concentration = None
    instance.concentration_units = None
    instance.elemental_metal_mass = None
    instance.catalyst_percentage = None
    instance.catalyst_ppm = None

    amount = float(instance.amount)
    unit = instance.unit

    # --- mass / moles / concentration by unit ---
    if unit == AmountUnit.PERCENT_OF_ROCK:
        if rock_mass is not None and isinstance(rock_mass, (int, float)) and rock_mass > 0:
            instance.mass_in_grams = (amount / 100.0) * rock_mass
        if instance.mass_in_grams is not None and molecular_weight:
            instance.moles_added = instance.mass_in_grams / molecular_weight

    elif unit in (AmountUnit.PERCENT, AmountUnit.WEIGHT_PERCENT):
        if water_volume_ml is not None and water_volume_ml > 0:
            instance.mass_in_grams = (amount / 100.0) * water_volume_ml
        if instance.mass_in_grams is not None and molecular_weight:
            instance.moles_added = instance.mass_in_grams / molecular_weight
        instance.final_concentration = amount
        instance.concentration_units = unit.value

    elif unit == AmountUnit.PPM:
        # ppm = mg/L; mass_g = ppm * L / 1000
        if volume_liters is not None:
            instance.mass_in_grams = (amount * volume_liters) / 1000.0
        if instance.mass_in_grams is not None and molecular_weight:
            instance.moles_added = instance.mass_in_grams / molecular_weight
        instance.final_concentration = amount
        instance.concentration_units = 'ppm'

    elif unit == AmountUnit.MILLIMOLAR:
        if volume_liters is not None:
            moles = (amount / 1000.0) * volume_liters
            instance.moles_added = moles
            if molecular_weight:
                instance.mass_in_grams = moles * molecular_weight
        instance.final_concentration = amount
        instance.concentration_units = 'mM'

    elif unit == AmountUnit.MOLAR:
        if volume_liters is not None:
            moles = amount * volume_liters
            instance.moles_added = moles
            if molecular_weight:
                instance.mass_in_grams = moles * molecular_weight
        instance.final_concentration = amount
        instance.concentration_units = 'M'

    elif unit in (AmountUnit.MICROMOLE, AmountUnit.MILLIMOLE, AmountUnit.MOLE):
        scale = {
            AmountUnit.MICROMOLE: 1e-6,
            AmountUnit.MILLIMOLE: 1e-3,
            AmountUnit.MOLE: 1.0,
        }[unit]
        moles = amount * scale
        instance.moles_added = moles
        if molecular_weight:
            instance.mass_in_grams = moles * molecular_weight
        if volume_liters is not None:
            instance.final_concentration = (moles / volume_liters) * 1000.0
            instance.concentration_units = 'mM'

    else:
        # Mass / volume inputs: convert to grams
        instance.mass_in_grams = _to_grams(amount, unit)
        if instance.mass_in_grams is not None and molecular_weight:
            instance.moles_added = instance.mass_in_grams / molecular_weight
        if instance.mass_in_grams is not None and volume_liters is not None:
            instance.final_concentration = (instance.mass_in_grams / volume_liters) * 1_000_000.0
            instance.concentration_units = 'ppm'

    # --- catalyst fields ---
    if instance.mass_in_grams and instance.mass_in_grams > 0 and compound is not None:
        elemental_fraction = getattr(compound, 'elemental_fraction', None)
        if elemental_fraction:
            instance.elemental_metal_mass = instance.mass_in_grams * elemental_fraction
            if rock_mass is not None and rock_mass > 0:
                instance.catalyst_percentage = (instance.elemental_metal_mass / rock_mass) * 100
            if water_volume_ml is not None and water_volume_ml > 0:
                raw_ppm = (instance.elemental_metal_mass / water_volume_ml) * 1_000_000
                instance.catalyst_ppm = round(raw_ppm / 10) * 10


def _to_grams(amount: float, unit: AmountUnit) -> float | None:
    """Convert a mass/volume amount to grams. Returns None for concentration units."""
    conversions: dict[AmountUnit, float | None] = {
        AmountUnit.GRAM: 1.0,
        AmountUnit.MILLIGRAM: 1e-3,
        AmountUnit.MICROGRAM: 1e-6,
        AmountUnit.KILOGRAM: 1000.0,
        AmountUnit.MICROLITER: 1e-3,   # density ~1 g/mL
        AmountUnit.MILLILITER: 1.0,    # density ~1 g/mL
        AmountUnit.LITER: 1000.0,      # density ~1 g/mL
    }
    factor = conversions.get(unit)
    return amount * factor if factor is not None else None


def format_additives(conditions: object) -> str:
    """Return a newline-separated display string of all chemical additives.

    Replaces ExperimentalConditions.formatted_additives hybrid_property.
    Example output: "5 g Mg(OH)2\\n1 g Magnetite"
    """
    additives = getattr(conditions, 'chemical_additives', [])
    if not additives:
        return ""
    parts = []
    for a in additives:
        compound_name = getattr(getattr(a, 'compound', None), 'name', 'Unknown')
        parts.append(f"{a.amount} {a.unit.value} {compound_name}")
    return "\n".join(parts)
