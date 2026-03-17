from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.bulk_upload import UploadResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/bulk-uploads", tags=["bulk-uploads"])


@router.post("/scalar-results", response_model=UploadResponse)
async def upload_scalar_results(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload a Solution Chemistry Excel file and upsert scalar results."""
    # Lazy import to avoid loading frontend.config.variable_config at module startup
    from backend.services.bulk_uploads.scalar_results import ScalarResultsUploadService  # noqa: PLC0415
    file_bytes = await file.read()
    created, updated, skipped, errors, _ = ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db, file_bytes
    )
    log.info("scalar_upload", created=created, updated=updated, user=current_user.email)
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        message=f"Processed: {created} created, {updated} updated, {skipped} skipped",
    )


@router.post("/new-experiments", response_model=UploadResponse)
async def upload_new_experiments(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload a New Experiments Excel file."""
    from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        # Returns 6-tuple: (created, updated, skipped, errors, warnings, info_messages)
        created, updated, skipped, errors, _warnings, _info = (
            NewExperimentsUploadService.bulk_upsert_from_excel(db, file_bytes)
        )
    except Exception as exc:
        log.error("new_experiments_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(created=created, updated=updated, skipped=skipped, errors=errors,
                          message=f"{created} created, {updated} updated, {skipped} skipped")


@router.post("/pxrf", response_model=UploadResponse)
async def upload_pxrf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload a pXRF CSV/Excel file."""
    from backend.services.bulk_uploads.pxrf_data import PXRFUploadService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        # PXRFUploadService.ingest_from_bytes returns (created, updated, skipped, errors: List[str])
        created, updated, skipped, errors = PXRFUploadService.ingest_from_bytes(db, file_bytes)
    except Exception as exc:
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(created=created, updated=updated, skipped=skipped, errors=errors,
                          message=f"pXRF: {created} created, {updated} updated")


@router.post("/aeris-xrd", response_model=UploadResponse)
async def upload_aeris_xrd(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload an Aeris XRD file (time-series mineral phases)."""
    from backend.services.bulk_uploads.aeris_xrd import AerisXRDUploadService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        # AerisXRDUploadService.bulk_upsert_from_excel returns (created, updated, skipped, errors: List[str])
        created, updated, skipped, errors = AerisXRDUploadService.bulk_upsert_from_excel(db, file_bytes)
    except Exception as exc:
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(created=created, updated=updated, skipped=skipped, errors=errors,
                          message=f"XRD: {created} created, {updated} updated")
