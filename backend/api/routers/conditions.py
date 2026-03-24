from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
import backend.services.calculations  # noqa: F401 — registers @register decorators
from backend.services.calculations.registry import recalculate
from database.models.conditions import ExperimentalConditions
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.conditions import ConditionsCreate, ConditionsUpdate, ConditionsResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/conditions", tags=["conditions"])


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
    """Return conditions for a given experiment_id string. 404 if no conditions record exists."""
    cond = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_id == experiment_id)
    ).scalar_one_or_none()
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
    db.flush()
    recalculate(cond, db)
    db.commit()
    db.refresh(cond)
    return ConditionsResponse.model_validate(cond)
