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
