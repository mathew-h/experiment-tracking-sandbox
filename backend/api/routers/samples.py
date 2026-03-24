# backend/api/routers/samples.py
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from database.models.samples import SampleInfo, SamplePhotos
from database.models.analysis import ExternalAnalysis
from database.models.experiments import Experiment
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.samples import (
    SampleCreate, SampleUpdate, SampleResponse,
    SampleListItem, SampleListResponse, SampleGeoItem, SampleDetail,
    LinkedExperiment, SamplePhotoResponse,
    ExternalAnalysisResponse, AnalysisFileResponse, ElementalAnalysisItem,
)
from backend.services.samples import evaluate_characterized, log_sample_modification

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/samples", tags=["samples"])


# ── GET /api/samples/geo  (must come before /{sample_id}) ─────────────────
@router.get("/geo", response_model=list[SampleGeoItem])
def list_samples_geo(
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[SampleGeoItem]:
    rows = db.execute(
        select(SampleInfo)
        .where(SampleInfo.latitude.isnot(None), SampleInfo.longitude.isnot(None))
        .order_by(SampleInfo.sample_id)
    ).scalars().all()
    return [
        SampleGeoItem(
            sample_id=r.sample_id,
            latitude=r.latitude,
            longitude=r.longitude,
            rock_classification=r.rock_classification,
            characterized=r.characterized,
        )
        for r in rows
    ]


# ── GET /api/samples ───────────────────────────────────────────────────────
@router.get("", response_model=SampleListResponse)
def list_samples(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    country: str | None = None,
    rock_classification: str | None = None,
    locality: str | None = None,
    characterized: bool | None = None,
    search: str | None = None,
    has_pxrf: bool | None = None,
    has_xrd: bool | None = None,
    has_elemental: bool | None = None,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleListResponse:
    exp_count_sq = (
        select(func.count(Experiment.id))
        .where(Experiment.sample_id == SampleInfo.sample_id)
        .correlate(SampleInfo)
        .scalar_subquery()
    )
    pxrf_count_sq = (
        select(func.count(ExternalAnalysis.id))
        .where(
            ExternalAnalysis.sample_id == SampleInfo.sample_id,
            ExternalAnalysis.analysis_type == "pXRF",
        )
        .correlate(SampleInfo)
        .scalar_subquery()
    )
    xrd_count_sq = (
        select(func.count(ExternalAnalysis.id))
        .where(
            ExternalAnalysis.sample_id == SampleInfo.sample_id,
            ExternalAnalysis.analysis_type == "XRD",
        )
        .correlate(SampleInfo)
        .scalar_subquery()
    )
    elemental_count_sq = (
        select(func.count(ExternalAnalysis.id))
        .where(
            ExternalAnalysis.sample_id == SampleInfo.sample_id,
            ExternalAnalysis.analysis_type.in_(["Elemental", "Titration"]),
        )
        .correlate(SampleInfo)
        .scalar_subquery()
    )

    stmt = select(
        SampleInfo,
        exp_count_sq.label("experiment_count"),
        pxrf_count_sq.label("pxrf_count"),
        xrd_count_sq.label("xrd_count"),
        elemental_count_sq.label("elemental_count"),
    ).order_by(SampleInfo.sample_id)

    if country:
        stmt = stmt.where(SampleInfo.country == country)
    if rock_classification:
        stmt = stmt.where(SampleInfo.rock_classification == rock_classification)
    if locality:
        stmt = stmt.where(SampleInfo.locality.ilike(f"%{locality}%"))
    if characterized is not None:
        stmt = stmt.where(SampleInfo.characterized == characterized)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            SampleInfo.sample_id.ilike(pattern) | SampleInfo.description.ilike(pattern)
        )
    if has_pxrf is True:
        stmt = stmt.where(pxrf_count_sq > 0)
    if has_xrd is True:
        stmt = stmt.where(xrd_count_sq > 0)
    if has_elemental is True:
        stmt = stmt.where(elemental_count_sq > 0)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.offset(skip).limit(limit)).all()

    items = [
        SampleListItem(
            sample_id=r.SampleInfo.sample_id,
            rock_classification=r.SampleInfo.rock_classification,
            locality=r.SampleInfo.locality,
            state=r.SampleInfo.state,
            country=r.SampleInfo.country,
            characterized=r.SampleInfo.characterized,
            created_at=r.SampleInfo.created_at,
            experiment_count=r.experiment_count,
            has_pxrf=r.pxrf_count > 0,
            has_xrd=r.xrd_count > 0,
            has_elemental=r.elemental_count > 0,
        )
        for r in rows
    ]
    return SampleListResponse(items=items, total=total, skip=skip, limit=limit)


# ── GET /api/samples/{sample_id} ──────────────────────────────────────────
@router.get("/{sample_id}", response_model=SampleDetail)
def get_sample(
    sample_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleDetail:
    from database.models.conditions import ExperimentalConditions
    from database.models.characterization import ElementalAnalysis

    sample = db.execute(
        select(SampleInfo)
        .where(SampleInfo.sample_id == sample_id)
        .options(
            selectinload(SampleInfo.photos),
            selectinload(SampleInfo.external_analyses).selectinload(ExternalAnalysis.analysis_files),
            selectinload(SampleInfo.experiments).selectinload(Experiment.conditions),
            selectinload(SampleInfo.elemental_results).selectinload(ElementalAnalysis.analyte),
        )
    ).scalar_one_or_none()
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")

    return SampleDetail(
        sample_id=sample.sample_id,
        rock_classification=sample.rock_classification,
        state=sample.state,
        country=sample.country,
        locality=sample.locality,
        latitude=sample.latitude,
        longitude=sample.longitude,
        description=sample.description,
        characterized=sample.characterized,
        created_at=sample.created_at,
        photos=[SamplePhotoResponse.model_validate(p) for p in sample.photos],
        analyses=[_to_analysis_response(a) for a in sample.external_analyses],
        elemental_results=[
            ElementalAnalysisItem(
                analyte_symbol=r.analyte.analyte_symbol,
                unit=r.analyte.unit,
                analyte_composition=r.analyte_composition,
            )
            for r in sample.elemental_results
            if r.analyte
        ],
        experiments=[
            LinkedExperiment(
                experiment_id=e.experiment_id,
                experiment_type=(
                    e.conditions.experiment_type.value
                    if e.conditions and e.conditions.experiment_type else None
                ),
                status=e.status.value if e.status else None,
                date=e.date,
            )
            for e in sample.experiments
        ],
    )


def _to_analysis_response(a: ExternalAnalysis) -> ExternalAnalysisResponse:
    return ExternalAnalysisResponse(
        id=a.id,
        sample_id=a.sample_id,
        analysis_type=a.analysis_type,
        analysis_date=a.analysis_date,
        laboratory=a.laboratory,
        analyst=a.analyst,
        pxrf_reading_no=a.pxrf_reading_no,
        description=a.description,
        magnetic_susceptibility=a.magnetic_susceptibility,
        created_at=a.created_at,
        analysis_files=[AnalysisFileResponse.model_validate(f) for f in a.analysis_files],
    )


# ── POST /api/samples ─────────────────────────────────────────────────────
@router.post("", response_model=SampleResponse, status_code=201)
def create_sample(
    payload: SampleCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleResponse:
    """Create a new geological sample record."""
    existing = db.get(SampleInfo, payload.sample_id)
    if existing:
        raise HTTPException(status_code=409, detail="Sample ID already exists")
    sample = SampleInfo(**payload.model_dump(), characterized=False)
    db.add(sample)
    db.flush()
    log_sample_modification(
        db, sample_id=sample.sample_id, modified_by=current_user.email,
        modification_type="create", modified_table="sample_info",
        new_values=payload.model_dump(),
    )
    db.commit()
    db.refresh(sample)
    log.info("sample_created", sample_id=sample.sample_id, user=current_user.email)
    return SampleResponse.model_validate(sample)


# ── PATCH /api/samples/{sample_id} ────────────────────────────────────────
@router.patch("/{sample_id}", response_model=SampleResponse)
def update_sample(
    sample_id: str,
    payload: SampleUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SampleResponse:
    """Update mutable fields on a sample. 404 if the sample does not exist."""
    sample = db.get(SampleInfo, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")

    old_values = {k: getattr(sample, k) for k in payload.model_fields}
    updates = payload.model_dump(exclude_unset=True)
    manual_characterized = "characterized" in updates

    for field, value in updates.items():
        setattr(sample, field, value)

    if not manual_characterized:
        sample.characterized = evaluate_characterized(db, sample_id)

    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="update", modified_table="sample_info",
        old_values=old_values, new_values=updates,
    )
    db.commit()
    db.refresh(sample)
    return SampleResponse.model_validate(sample)


# ── DELETE /api/samples/{sample_id} ───────────────────────────────────────
@router.delete("/{sample_id}", status_code=204)
def delete_sample(
    sample_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
):
    """Delete a sample. Returns 409 if linked experiments exist."""
    sample = db.get(SampleInfo, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")

    linked = db.execute(
        select(func.count(Experiment.id))
        .where(Experiment.sample_id == sample_id)
    ).scalar_one()
    if linked > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Sample has {linked} linked experiment(s) and cannot be deleted",
        )

    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="delete", modified_table="sample_info",
    )
    db.delete(sample)
    db.commit()
    log.info("sample_deleted", sample_id=sample_id, user=current_user.email)
    return Response(status_code=204)
