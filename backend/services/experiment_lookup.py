"""Shared lookups for an experiment and the rows that hang off it (issue #190).

These are the single definitions of rules that used to be written out at each
call site. New code must use them; see docs/working/decisions.md (2026-11-13).

Every lookup here matches ``experiment_id`` exactly. Lenient matching of IDs
typed into upload sheets is a different job and lives in
``backend/services/bulk_uploads/_id_match.py``.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment
from database.models.results import ExperimentalResults, ScalarResults


def find_experiment(db: Session, experiment_id: str) -> Experiment | None:
    """The experiment with exactly this ``experiment_id``, or None."""
    return db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()


def series_key(exp: Experiment) -> str:
    """The ID that names an experiment's series: its base ID, else its own ID.

    Python twin of ``COALESCE(base_experiment_id, experiment_id)`` in the views.
    """
    return exp.base_experiment_id or exp.experiment_id


def lowest_conditions(db: Session, experiment_fk: int) -> ExperimentalConditions | None:
    """The experiment's conditions row, or None.

    ``uq_conditions_experiment_fk`` makes conditions 1:1 with an experiment, but
    a database that predates the constraint can hold a duplicate. The lowest id
    wins, and ``.first()`` (never ``scalar_one_or_none()``) keeps a duplicate
    from raising (issue #109).
    """
    return db.execute(
        select(ExperimentalConditions)
        .where(ExperimentalConditions.experiment_fk == experiment_fk)
        .order_by(ExperimentalConditions.id)
    ).scalars().first()


def lowest_conditions_map(
    db: Session, experiment_fks: Iterable[int],
) -> dict[int, ExperimentalConditions]:
    """``lowest_conditions`` for many experiments in one query, keyed by experiment_fk.

    An experiment with no conditions row has no key.
    """
    found: dict[int, ExperimentalConditions] = {}
    rows = db.execute(
        select(ExperimentalConditions)
        .where(ExperimentalConditions.experiment_fk.in_(list(experiment_fks)))
        .order_by(ExperimentalConditions.id)
    ).scalars()
    for cond in rows:
        found.setdefault(cond.experiment_fk, cond)  # first seen is the lowest id
    return found


def scalars_for_experiment(db: Session, experiment_fk: int) -> list[ScalarResults]:
    """Every ScalarResults row of the experiment's results, in id order (one query).

    Each row comes with its ``result_entry`` loaded from the same join, because
    recalculating a scalar reads it; lazy loading would cost one query per row
    (issue #191, E-07).
    """
    return list(db.execute(
        select(ScalarResults)
        .join(ScalarResults.result_entry)
        .options(contains_eager(ScalarResults.result_entry))
        .where(ExperimentalResults.experiment_fk == experiment_fk)
        .order_by(ScalarResults.id)
    ).scalars())


def is_variant(exp: Experiment) -> bool:
    """True for a side sample: an experiment whose ID is ``<parent ID>_<Text>``.

    Blanks and bypass samples (CF_027-2_Bypass1 under CF_027-2) are variants;
    a sequential segment (CF_027-2 under CF_027) is not. Python twin of the
    ``is_variant`` column in v_core_flood_samples and v_hpht_samples, and of
    ``_IS_VARIANT`` in icp_series.py. Reads ``exp.parent``, so load it eagerly
    when calling this in a loop.
    """
    parent = exp.parent
    return parent is not None and exp.experiment_id.startswith(parent.experiment_id + "_")
