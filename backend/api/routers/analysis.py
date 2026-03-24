from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from database.models.analysis import PXRFReading, ExternalAnalysis
from database.models.xrd import XRDPhase
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.analysis import XRDPhaseResponse, PXRFResponse, ExternalAnalysisResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/xrd/{experiment_id}", response_model=list[XRDPhaseResponse])
def get_xrd_phases(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[XRDPhaseResponse]:
    """Return XRD mineral phases for an experiment, ordered by timepoint and mineral name."""
    rows = db.execute(
        select(XRDPhase)
        .where(XRDPhase.experiment_id == experiment_id)
        .order_by(XRDPhase.time_post_reaction_days, XRDPhase.mineral_name)
    ).scalars().all()
    return [XRDPhaseResponse.model_validate(r) for r in rows]


@router.get("/pxrf", response_model=list[PXRFResponse])
def list_pxrf(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[PXRFResponse]:
    """List pXRF readings ordered by reading number."""
    rows = db.execute(
        select(PXRFReading).order_by(PXRFReading.reading_no).offset(skip).limit(limit)
    ).scalars().all()
    return [PXRFResponse.model_validate(r) for r in rows]


@router.get("/external/{experiment_id}", response_model=list[ExternalAnalysisResponse])
def get_external_analyses(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ExternalAnalysisResponse]:
    """Return external analyses linked to an experiment, ordered by analysis date."""
    rows = db.execute(
        select(ExternalAnalysis)
        .where(ExternalAnalysis.experiment_id == experiment_id)
        .order_by(ExternalAnalysis.analysis_date)
    ).scalars().all()
    return [ExternalAnalysisResponse.model_validate(r) for r in rows]
