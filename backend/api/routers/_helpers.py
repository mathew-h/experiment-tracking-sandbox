"""Small helpers shared by the API routers (issue #190).

Kept free of router imports so any router can import it without a cycle.
"""
from __future__ import annotations

from typing import Callable, Sequence, TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.services.experiment_lookup import find_experiment
from database.models.experiments import Experiment

T = TypeVar("T")


def get_experiment_or_404(
    db: Session, experiment_id: str, detail: str = "Experiment not found",
) -> Experiment:
    """The experiment with exactly this ID, or a 404 carrying ``detail``."""
    exp = find_experiment(db, experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail=detail)
    return exp


def call_or_http(
    fn: Callable[[], T],
    errors: Sequence[tuple[type[Exception], int]],
    detail: Callable[[Exception], str] = str,
) -> T:
    """Run ``fn`` and turn a service exception into an HTTPException.

    ``errors`` pairs an exception type with an HTTP status. Pairs are tried in
    order, so list a subclass before its base class. An exception that matches
    no pair propagates unchanged. ``detail`` builds the response detail.
    """
    try:
        return fn()
    except tuple(exc_type for exc_type, _ in errors) as exc:
        for exc_type, status_code in errors:
            if isinstance(exc, exc_type):
                raise HTTPException(status_code=status_code, detail=detail(exc))
        raise
