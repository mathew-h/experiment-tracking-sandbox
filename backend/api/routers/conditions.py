from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
import backend.services.calculations  # noqa: F401 — registers @register decorators
from backend.services.calculations.registry import recalculate
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.conditions import ConditionsCreate, ConditionsUpdate, ConditionsResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/conditions", tags=["conditions"])

_REACTOR_ALLOWED_TYPES = {"HPHT", "Core Flood"}


def _validate_reactor_number(reactor_number: int | None, experiment_type: str | None) -> None:
    """Raise 422 if reactor_number is set for a non-HPHT, non-Core Flood experiment."""
    if reactor_number is not None and experiment_type not in _REACTOR_ALLOWED_TYPES:
        raise HTTPException(
            status_code=422,
            detail="reactor_number may only be set for HPHT or Core Flood experiments",
        )


@router.get("/{conditions_id}", response_model=ConditionsResponse)
def get_conditions(
    conditions_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ConditionsResponse:
    """Return experimental conditions by primary key. 404 if not found."""
    cond = db.get(ExperimentalConditions, conditions_id)
    if cond is None:
        raise HTTPException(status_code=404, detail="Conditions not found")
    return ConditionsResponse.model_validate(cond)


@router.get("/by-experiment/{experiment_id}", response_model=ConditionsResponse)
def get_conditions_by_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ConditionsResponse:
    """Return conditions for a given experiment_id string. 404 if none exist.

    Resolved through experiment_fk, never through the denormalized
    ExperimentalConditions.experiment_id string: that string is not kept in sync
    by the rename paths (187 of 1013 rows were stale as of 2026-08-05), so a
    string-keyed lookup both missed rows that exist and matched rows belonging
    to another experiment. A 404 here is what made the detail page offer "Add
    Details" and create a duplicate conditions row -- see
    docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md

    .first() rather than .scalar_one_or_none(): UNIQUE (experiment_fk) makes a
    second row impossible going forward, but this endpoint must not 500 on a
    database that predates the constraint.
    """
    cond = db.execute(
        select(ExperimentalConditions)
        .join(Experiment, Experiment.id == ExperimentalConditions.experiment_fk)
        .where(Experiment.experiment_id == experiment_id)
        .order_by(ExperimentalConditions.id)
    ).scalars().first()
    if cond is None:
        raise HTTPException(status_code=404, detail="Conditions not found for this experiment")
    return ConditionsResponse.model_validate(cond)


@router.post("", response_model=ConditionsResponse, status_code=201)
def create_conditions(
    payload: ConditionsCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ConditionsResponse:
    """Create conditions and compute derived fields (water_to_rock_ratio)."""
    _validate_reactor_number(payload.reactor_number, payload.experiment_type)
    cond = ExperimentalConditions(**payload.model_dump())
    db.add(cond)
    db.flush()
    recalculate(cond, db)
    db.commit()
    db.refresh(cond)
    log.info("conditions_created", experiment_id=cond.experiment_id)
    return ConditionsResponse.model_validate(cond)


@router.patch("/{conditions_id}", response_model=ConditionsResponse)
def update_conditions(
    conditions_id: int,
    payload: ConditionsUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ConditionsResponse:
    """Update conditions and recompute derived fields."""
    cond = db.get(ExperimentalConditions, conditions_id)
    if cond is None:
        raise HTTPException(status_code=404, detail="Conditions not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cond, field, value)
    _validate_reactor_number(cond.reactor_number, cond.experiment_type)
    db.flush()
    recalculate(cond, db)
    db.commit()
    db.refresh(cond)
    return ConditionsResponse.model_validate(cond)
