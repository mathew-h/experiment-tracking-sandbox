from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
import backend.services.calculations  # noqa: F401 — registers @register decorators
from backend.services.calculations.registry import recalculate
from database.models.experiments import Experiment
from database.models.results import ExperimentalResults, ScalarResults, ICPResults
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.results import (
    ResultCreate, ResultResponse, ScalarCreate, ScalarUpdate,
    ScalarResponse, ICPCreate, ICPResponse,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/results", tags=["results"])

# IMPORTANT: Static-segment routes (/scalar/*, /icp/*) registered BEFORE
# the dynamic /{experiment_id} route to prevent path shadowing.


@router.get("/scalar/{result_id}", response_model=ScalarResponse)
def get_scalar(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ScalarResponse:
    scalar = db.execute(
        select(ScalarResults).where(ScalarResults.result_id == result_id)
    ).scalar_one_or_none()
    if scalar is None:
        raise HTTPException(status_code=404, detail="Scalar result not found")
    return ScalarResponse.model_validate(scalar)


@router.get("/icp/{result_id}", response_model=ICPResponse)
def get_icp(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ICPResponse:
    icp = db.execute(
        select(ICPResults).where(ICPResults.result_id == result_id)
    ).scalar_one_or_none()
    if icp is None:
        raise HTTPException(status_code=404, detail="ICP result not found")
    return ICPResponse.model_validate(icp)


@router.get("/{experiment_id}", response_model=list[ResultResponse])
def list_results(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ResultResponse]:
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    rows = db.execute(
        select(ExperimentalResults)
        .where(ExperimentalResults.experiment_fk == exp.id)
        .order_by(ExperimentalResults.time_post_reaction_days)
    ).scalars().all()
    return [ResultResponse.model_validate(r) for r in rows]


@router.post("", response_model=ResultResponse, status_code=201)
def create_result(
    payload: ResultCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ResultResponse:
    result = ExperimentalResults(**payload.model_dump())
    db.add(result)
    db.commit()
    db.refresh(result)
    return ResultResponse.model_validate(result)


@router.post("/scalar", response_model=ScalarResponse, status_code=201)
def create_scalar(
    payload: ScalarCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ScalarResponse:
    """Create scalar results and trigger H2 + ammonium yield calculations."""
    result_entry = db.get(ExperimentalResults, payload.result_id)
    if result_entry is None:
        raise HTTPException(status_code=404, detail="Result entry not found")
    scalar = ScalarResults(**payload.model_dump())
    db.add(scalar)
    db.flush()
    recalculate(scalar, db)
    db.commit()
    db.refresh(scalar)
    log.info("scalar_created", result_id=scalar.result_id)
    return ScalarResponse.model_validate(scalar)


@router.patch("/scalar/{scalar_id}", response_model=ScalarResponse)
def update_scalar(
    scalar_id: int,
    payload: ScalarUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ScalarResponse:
    scalar = db.get(ScalarResults, scalar_id)
    if scalar is None:
        raise HTTPException(status_code=404, detail="Scalar result not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(scalar, field, value)
    db.flush()
    recalculate(scalar, db)
    db.commit()
    db.refresh(scalar)
    return ScalarResponse.model_validate(scalar)


@router.post("/icp", response_model=ICPResponse, status_code=201)
def create_icp(
    payload: ICPCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ICPResponse:
    result_entry = db.get(ExperimentalResults, payload.result_id)
    if result_entry is None:
        raise HTTPException(status_code=404, detail="Result entry not found")
    icp = ICPResults(**payload.model_dump())
    db.add(icp)
    db.commit()
    db.refresh(icp)
    return ICPResponse.model_validate(icp)
