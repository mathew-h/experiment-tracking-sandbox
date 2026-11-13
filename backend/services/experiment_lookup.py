"""Shared lookups for an experiment and the rows that hang off it (issue #190).

These are the single definitions of rules that used to be written out at each
call site. New code must use them; see docs/working/decisions.md (2026-11-13).

Every lookup here matches ``experiment_id`` exactly. Lenient matching of IDs
typed into upload sheets is a different job and lives in
``backend/services/bulk_uploads/_id_match.py``.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.experiments import Experiment


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
