from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from database.models.samples import SampleInfo
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.samples import SampleCreate, SampleUpdate, SampleResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/samples", tags=["samples"])


@router.get("", response_model=list[SampleResponse])
def list_samples(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    country: str | None = None,
    rock_classification: str | None = None,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[SampleResponse]:
    stmt = select(SampleInfo).order_by(SampleInfo.sample_id)
    if country:
        stmt = stmt.where(SampleInfo.country == country)
    if rock_classification:
        stmt = stmt.where(SampleInfo.rock_classification == rock_classification)
    stmt = stmt.offset(skip).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [SampleResponse.model_validate(r) for r in rows]


@router.get("/{sample_id}", response_model=SampleResponse)
def get_sample(
    sample_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleResponse:
    sample = db.execute(
        select(SampleInfo).where(SampleInfo.sample_id == sample_id)
    ).scalar_one_or_none()
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return SampleResponse.model_validate(sample)


@router.post("", response_model=SampleResponse, status_code=201)
def create_sample(
    payload: SampleCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleResponse:
    sample = SampleInfo(**payload.model_dump())
    db.add(sample)
    db.commit()
    db.refresh(sample)
    log.info("sample_created", sample_id=sample.sample_id, user=current_user.email)
    return SampleResponse.model_validate(sample)


@router.patch("/{sample_id}", response_model=SampleResponse)
def update_sample(
    sample_id: str,
    payload: SampleUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleResponse:
    sample = db.execute(
        select(SampleInfo).where(SampleInfo.sample_id == sample_id)
    ).scalar_one_or_none()
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sample, field, value)
    db.commit()
    db.refresh(sample)
    return SampleResponse.model_validate(sample)
