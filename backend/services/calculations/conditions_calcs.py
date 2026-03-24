from __future__ import annotations

from sqlalchemy.orm import Session
from backend.services.calculations.registry import register
from database.models.conditions import ExperimentalConditions


@register(ExperimentalConditions)
def recalculate_conditions(instance: ExperimentalConditions, session: Session) -> None:
    """Recalculate derived fields on ExperimentalConditions.

    Derived fields:
    - water_to_rock_ratio = water_volume_mL / rock_mass_g
    """
    water_vol = instance.water_volume_mL
    rock_mass = instance.rock_mass_g

    if (
        water_vol is not None
        and rock_mass is not None
        and rock_mass > 0
    ):
        instance.water_to_rock_ratio = water_vol / rock_mass
    else:
        instance.water_to_rock_ratio = None

    # Propagate to all linked ScalarResults so that changes to total_ferrous_iron
    # (and rock_mass_g / water_volume_mL) are reflected in previously-stored scalar results.
    # Lazy import avoids load-time circular import: conditions_calcs ← scalar_calcs.
    from backend.services.calculations.scalar_calcs import recalculate_scalar
    experiment = getattr(instance, 'experiment', None)
    if experiment is not None:
        for result in getattr(experiment, 'results', None) or []:
            scalar = getattr(result, 'scalar_data', None)
            if scalar is not None:
                # Ensure scalar can resolve conditions via result_entry → experiment → conditions.
                # On real ORM objects this relationship is already set.  In tests (SimpleNamespace)
                # the back-reference may be absent, so we inject it temporarily.
                if getattr(scalar, 'result_entry', None) is None:
                    scalar.result_entry = result
                if getattr(result, 'experiment', None) is None:
                    result.experiment = experiment
                if getattr(experiment, 'conditions', None) is None:
                    experiment.conditions = instance
                recalculate_scalar(scalar, session)
