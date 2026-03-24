# backend/services/calculations/conditions_calcs.py
from __future__ import annotations

from sqlalchemy.orm import Session
from backend.services.calculations.registry import register
from backend.services.elemental_composition_service import (
    calculate_total_ferrous_iron_g,
    get_analyte_wt_pct,
)
from database.models.conditions import ExperimentalConditions


@register(ExperimentalConditions)
def recalculate_conditions(instance: ExperimentalConditions, session: Session) -> None:
    """Recalculate derived fields on ExperimentalConditions.

    Derived fields:
    - water_to_rock_ratio = water_volume_mL / rock_mass_g
    - total_ferrous_iron_g = (FeO wt% / 100) * FE_IN_FEO_FRACTION * rock_mass_g
      where FeO wt% is looked up from the most recent elemental characterization
      ExternalAnalysis (`Elemental` or `Bulk Elemental Composition`) for the
      experiment's sample.
    """
    water_vol = instance.water_volume_mL
    rock_mass = instance.rock_mass_g

    # water_to_rock_ratio
    if water_vol is not None and rock_mass is not None and rock_mass > 0:
        instance.water_to_rock_ratio = water_vol / rock_mass
    else:
        instance.water_to_rock_ratio = None

    # total_ferrous_iron_g: resolve sample_id through the parent Experiment
    from database.models.experiments import Experiment  # local import avoids circular import risk

    sample_id = None
    if instance.experiment_fk is not None:
        experiment = session.get(Experiment, instance.experiment_fk)
        if experiment is not None:
            sample_id = experiment.sample_id

    feo_wt_pct = get_analyte_wt_pct(sample_id=sample_id, db=session)
    instance.total_ferrous_iron_g = calculate_total_ferrous_iron_g(
        feo_wt_pct=feo_wt_pct,
        rock_mass_g=rock_mass,
    )
