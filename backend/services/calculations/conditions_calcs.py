# backend/services/calculations/conditions_calcs.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from backend.services.calculations.registry import register
from backend.services.elemental_composition_service import (
    calculate_total_ferrous_iron_g,
    get_analyte_wt_pct,
)
from database.models.conditions import ExperimentalConditions


def _preload_scalars(session: Session, experiment: object) -> None:
    """Load the scalar row of every result of the experiment in one query.

    The cascade below reads ``result.scalar_data`` for each result. Left to
    lazy loading that is one query per result (issue #191, E-05). This changes
    which statements run, not which rows are recalculated.

    ``experiment.results`` is read first on purpose: the session only holds
    weak references, so results loaded by a query whose return value is
    dropped can be garbage-collected before the cascade reaches them. The
    collection keeps them alive, and the query then fills ``scalar_data`` on
    those same objects.
    """
    from database.models.experiments import Experiment
    from database.models.results import ExperimentalResults

    if not isinstance(session, Session) or not isinstance(experiment, Experiment):
        return  # unit tests pass plain objects; nothing to preload
    result_ids = [result.id for result in experiment.results if result.id is not None]
    if not result_ids:
        return
    session.execute(
        select(ExperimentalResults)
        .where(ExperimentalResults.id.in_(result_ids))
        .options(selectinload(ExperimentalResults.scalar_data))
    ).scalars().all()


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
    if getattr(instance, 'experiment_fk', None) is not None:
        experiment = session.get(Experiment, instance.experiment_fk)
        if experiment is not None:
            sample_id = experiment.sample_id

    feo_wt_pct = get_analyte_wt_pct(sample_id=sample_id, db=session)
    instance.total_ferrous_iron_g = calculate_total_ferrous_iron_g(
        feo_wt_pct=feo_wt_pct,
        rock_mass_g=rock_mass,
    )

    # Propagate to all linked ScalarResults so that changes to total_ferrous_iron
    # (and rock_mass_g / water_volume_mL) are reflected in previously-stored scalar results.
    # Lazy import avoids load-time circular import: conditions_calcs ← scalar_calcs.
    from backend.services.calculations.scalar_calcs import recalculate_scalar
    experiment = getattr(instance, 'experiment', None)
    if experiment is not None:
        _preload_scalars(session, experiment)
        for result in getattr(experiment, 'results', None) or []:
            scalar = getattr(result, 'scalar_data', None)
            if scalar is not None:
                recalculate_scalar(scalar, session)
