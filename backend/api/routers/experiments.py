from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from database.models.experiments import Experiment
from database.models.enums import ExperimentStatus
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.experiments import ExperimentListItem, ExperimentResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentListItem])
def list_experiments(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    status: ExperimentStatus | None = None,
    researcher: str | None = None,
    sample_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ExperimentListItem]:
    """List experiments with optional filters and pagination."""
    stmt = select(Experiment).order_by(Experiment.experiment_number.desc())
    if status:
        stmt = stmt.where(Experiment.status == status)
    if researcher:
        stmt = stmt.where(Experiment.researcher == researcher)
    if sample_id:
        stmt = stmt.where(Experiment.sample_id == sample_id)
    stmt = stmt.offset(skip).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [ExperimentListItem.model_validate(r) for r in rows]


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Get a single experiment by its string identifier."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return ExperimentResponse.model_validate(exp)
