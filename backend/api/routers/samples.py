# backend/api/routers/samples.py
from __future__ import annotations
import os
import uuid
import structlog
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Response, File, Form, UploadFile
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
    ExternalAnalysisCreate, ExternalAnalysisWithWarnings,
    PXRFElementalData, XRDPhaseData,
)
from backend.services.samples import evaluate_characterized, log_sample_modification, normalize_pxrf_reading_no
from backend.config.settings import get_settings

PHOTO_ALLOWED_TYPES = {"image/jpeg", "image/png"}
MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB

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
            description=r.SampleInfo.description,
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
    from database.models.analysis import PXRFReading
    from database.models.xrd import XRDAnalysis

    sample = db.execute(
        select(SampleInfo)
        .where(SampleInfo.sample_id == sample_id)
        .options(
            selectinload(SampleInfo.photos),
            selectinload(SampleInfo.external_analyses).selectinload(ExternalAnalysis.analysis_files),
            selectinload(SampleInfo.external_analyses).selectinload(ExternalAnalysis.xrd_analysis),
            selectinload(SampleInfo.experiments).selectinload(Experiment.conditions),
        )
    ).scalar_one_or_none()
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")

    pxrf_map = _build_pxrf_map(list(sample.external_analyses), db)

    # Fetch elemental results via the external_analysis join to catch rows
    # where ElementalAnalysis.sample_id is NULL (historical import pattern).
    elemental_rows = db.execute(
        select(ElementalAnalysis)
        .join(ExternalAnalysis, ElementalAnalysis.external_analysis_id == ExternalAnalysis.id)
        .where(ExternalAnalysis.sample_id == sample_id)
        .options(selectinload(ElementalAnalysis.analyte))
    ).scalars().all()

    # Auto-correct characterized flag if pXRF readings have since been ingested
    new_characterized = evaluate_characterized(db, sample_id)
    if new_characterized != sample.characterized:
        sample.characterized = new_characterized
        db.commit()

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
        well_name=sample.well_name,
        core_lender=sample.core_lender,
        core_interval_ft=sample.core_interval_ft,
        on_loan_return_date=sample.on_loan_return_date,
        photos=[SamplePhotoResponse.model_validate(p) for p in sample.photos],
        analyses=[_to_analysis_response(a, pxrf_map) for a in sample.external_analyses],
        elemental_results=[
            ElementalAnalysisItem(
                analyte_symbol=r.analyte.analyte_symbol,
                unit=r.analyte.unit,
                analyte_composition=r.analyte_composition,
            )
            for r in elemental_rows
            if r.analyte
        ],
        experiments=[
            LinkedExperiment(
                experiment_id=e.experiment_id,
                experiment_type=(
                    e.conditions.experiment_type
                    if e.conditions and e.conditions.experiment_type else None
                ),
                status=e.status.value if e.status else None,
                date=e.date,
            )
            for e in sample.experiments
        ],
    )


_PXRF_ELEMENTS = ["fe", "mg", "ni", "cu", "si", "co", "mo", "al", "ca", "k", "au", "zn"]


def _build_pxrf_map(
    analyses: "list[ExternalAnalysis]",
    db: Session,
) -> "dict[str, PXRFReading]":
    """Return a {reading_no: PXRFReading} map for all pXRF analyses in the list."""
    from database.models.analysis import PXRFReading
    reading_nos: set[str] = set()
    for a in analyses:
        if a.analysis_type == "pXRF" and a.pxrf_reading_no:
            for raw in a.pxrf_reading_no.split(","):
                normed = normalize_pxrf_reading_no(raw)
                if normed:
                    reading_nos.add(normed)
    if not reading_nos:
        return {}
    rows = db.execute(
        select(PXRFReading).where(PXRFReading.reading_no.in_(reading_nos))
    ).scalars().all()
    return {r.reading_no: r for r in rows}


def _avg_pxrf(a: ExternalAnalysis, pxrf_map: dict) -> "PXRFElementalData | None":
    """Average elemental values across all resolved pXRF readings for an analysis."""
    if a.analysis_type != "pXRF" or not a.pxrf_reading_no:
        return None
    readings = []
    for raw in a.pxrf_reading_no.split(","):
        normed = normalize_pxrf_reading_no(raw)
        if normed and normed in pxrf_map:
            readings.append(pxrf_map[normed])
    if not readings:
        return None
    averaged: dict = {"reading_count": len(readings)}
    for el in _PXRF_ELEMENTS:
        vals = [v for r in readings if (v := getattr(r, el)) is not None]
        averaged[el] = sum(vals) / len(vals) if vals else None
    return PXRFElementalData(**averaged)


def _get_xrd_data(a: ExternalAnalysis) -> "XRDPhaseData | None":
    """Extract mineral phases from a linked XRDAnalysis record."""
    if a.analysis_type != "XRD":
        return None
    xrd = getattr(a, "xrd_analysis", None)
    if not xrd or not xrd.mineral_phases:
        return None
    return XRDPhaseData(
        mineral_phases=xrd.mineral_phases,
        analysis_parameters=xrd.analysis_parameters,
    )


def _to_analysis_response(
    a: ExternalAnalysis,
    pxrf_map: dict | None = None,
) -> ExternalAnalysisResponse:
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
        pxrf_data=_avg_pxrf(a, pxrf_map or {}),
        xrd_data=_get_xrd_data(a),
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

    old_values = {k: getattr(sample, k) for k in type(payload).model_fields}
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


# ── POST /api/samples/{sample_id}/photos ──────────────────────────────────
@router.post("/{sample_id}/photos", response_model=SamplePhotoResponse, status_code=201)
async def upload_photo(
    sample_id: str,
    file: UploadFile = File(...),
    description: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> SamplePhotoResponse:
    if db.get(SampleInfo, sample_id) is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    if file.content_type not in PHOTO_ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Photo must be image/jpeg or image/png; got {file.content_type}",
        )
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=422, detail="File exceeds 20 MB limit")

    settings = get_settings()
    dest_dir = Path(settings.sample_photos_dir) / sample_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(file.filename or "photo").stem
    ext = Path(file.filename or "photo").suffix or ".jpg"
    filename = f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
    dest = dest_dir / filename
    dest.write_bytes(content)

    photo = SamplePhotos(
        sample_id=sample_id,
        file_path=str(dest),
        file_name=file.filename,
        file_type=file.content_type,
        description=description,
    )
    db.add(photo)
    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="create", modified_table="sample_photos",
        new_values={"file_name": file.filename},
    )
    db.commit()
    db.refresh(photo)
    return SamplePhotoResponse.model_validate(photo)


# ── DELETE /api/samples/{sample_id}/photos/{photo_id} ─────────────────────
@router.delete("/{sample_id}/photos/{photo_id}", status_code=204)
def delete_photo(
    sample_id: str,
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
):
    photo = db.execute(
        select(SamplePhotos)
        .where(SamplePhotos.id == photo_id, SamplePhotos.sample_id == sample_id)
    ).scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    file_path = Path(photo.file_path)
    if file_path.exists():
        file_path.unlink()

    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="delete", modified_table="sample_photos",
        old_values={"file_name": photo.file_name},
    )
    db.delete(photo)
    db.commit()


# ── POST /api/samples/{sample_id}/analyses ────────────────────────────────
@router.post("/{sample_id}/analyses", response_model=ExternalAnalysisWithWarnings, status_code=201)
def create_analysis(
    sample_id: str,
    payload: ExternalAnalysisCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExternalAnalysisWithWarnings:
    from database.models.analysis import ExternalAnalysis as EA, PXRFReading
    from sqlalchemy.orm import selectinload as sl

    if db.get(SampleInfo, sample_id) is None:
        raise HTTPException(status_code=404, detail="Sample not found")

    warnings: list[str] = []

    normalized_readings: list[str] = []
    if payload.pxrf_reading_no:
        for raw in payload.pxrf_reading_no.split(","):
            normed = normalize_pxrf_reading_no(raw)
            if normed:
                normalized_readings.append(normed)
                if db.get(PXRFReading, normed) is None:
                    warnings.append(
                        f"pXRF reading '{normed}' not found in database — "
                        "it may be uploaded later via bulk upload"
                    )

    ea_data = payload.model_dump()
    if normalized_readings:
        ea_data["pxrf_reading_no"] = ",".join(normalized_readings)

    ea = EA(sample_id=sample_id, **ea_data)
    db.add(ea)
    db.flush()

    # Reload with files relationship to satisfy _to_analysis_response
    db.execute(
        select(EA)
        .where(EA.id == ea.id)
        .options(sl(EA.analysis_files))
    ).scalar_one()

    sample = db.get(SampleInfo, sample_id)
    sample.characterized = evaluate_characterized(db, sample_id)

    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="create", modified_table="external_analyses",
        new_values={**ea_data, "id": ea.id},
    )
    db.commit()
    db.refresh(ea)
    pxrf_map = _build_pxrf_map([ea], db)
    return ExternalAnalysisWithWarnings(
        analysis=_to_analysis_response(ea, pxrf_map), warnings=warnings
    )


# ── GET /api/samples/{sample_id}/analyses ────────────────────────────────
@router.get("/{sample_id}/analyses", response_model=list[ExternalAnalysisResponse])
def list_analyses(
    sample_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ExternalAnalysisResponse]:
    from database.models.analysis import ExternalAnalysis as EA
    from sqlalchemy.orm import selectinload as sl

    rows = db.execute(
        select(EA)
        .where(EA.sample_id == sample_id)
        .options(sl(EA.analysis_files), sl(EA.xrd_analysis))
        .order_by(EA.analysis_date)
    ).scalars().all()
    pxrf_map = _build_pxrf_map(list(rows), db)
    return [_to_analysis_response(r, pxrf_map) for r in rows]


# ── DELETE /api/samples/{sample_id}/analyses/{analysis_id} ───────────────
@router.delete("/{sample_id}/analyses/{analysis_id}", status_code=204)
def delete_analysis(
    sample_id: str,
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
):
    from database.models.analysis import ExternalAnalysis as EA
    from sqlalchemy.orm import selectinload as sl

    ea = db.execute(
        select(EA)
        .where(
            EA.id == analysis_id,
            EA.sample_id == sample_id,
        )
        .options(sl(EA.analysis_files))
    ).scalar_one_or_none()
    if ea is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    for af in ea.analysis_files:
        p = Path(af.file_path)
        if p.exists():
            p.unlink()

    log_sample_modification(
        db, sample_id=sample_id, modified_by=current_user.email,
        modification_type="delete", modified_table="external_analyses",
        old_values={"id": ea.id, "analysis_type": ea.analysis_type},
    )
    db.delete(ea)

    sample = db.get(SampleInfo, sample_id)
    if sample:
        sample.characterized = evaluate_characterized(db, sample_id)

    db.commit()


# ── GET /api/samples/{sample_id}/activity ─────────────────────────────────
@router.get("/{sample_id}/activity")
def get_sample_activity(
    sample_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
):
    from database.models.experiments import ModificationsLog

    rows = db.execute(
        select(ModificationsLog)
        .where(ModificationsLog.sample_id == sample_id)
        .order_by(ModificationsLog.created_at.desc())
        .limit(100)
    ).scalars().all()
    return [
        {
            "id": r.id,
            "modified_by": r.modified_by,
            "modification_type": r.modification_type,
            "modified_table": r.modified_table,
            "old_values": r.old_values,
            "new_values": r.new_values,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
