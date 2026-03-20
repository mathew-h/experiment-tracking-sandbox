from __future__ import annotations

import io
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.bulk_upload import UploadResponse

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/bulk-uploads", tags=["bulk-uploads"])


# ---------------------------------------------------------------------------
# Existing endpoints (preserved exactly)
# ---------------------------------------------------------------------------

@router.post("/scalar-results", response_model=UploadResponse)
async def upload_scalar_results(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload a Solution Chemistry Excel file and upsert scalar results."""
    from backend.services.bulk_uploads.scalar_results import ScalarResultsUploadService  # noqa: PLC0415
    file_bytes = await file.read()
    created, updated, skipped, errors, feedbacks = ScalarResultsUploadService.bulk_upsert_from_excel_ex(
        db, file_bytes
    )
    log.info("scalar_upload", created=created, updated=updated, user=current_user.email)
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        feedbacks=feedbacks,
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
        created, updated, skipped, errors, warnings, _info = (
            NewExperimentsUploadService.bulk_upsert_from_excel(db, file_bytes)
        )
    except Exception as exc:
        log.error("new_experiments_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(created=created, updated=updated, skipped=skipped, errors=errors,
                          warnings=warnings,
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
        created, updated, skipped, errors = AerisXRDUploadService.bulk_upsert_from_excel(db, file_bytes)
    except Exception as exc:
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(created=created, updated=updated, skipped=skipped, errors=errors,
                          message=f"XRD: {created} created, {updated} updated")


# ---------------------------------------------------------------------------
# New endpoints (Chunk C)
# ---------------------------------------------------------------------------

@router.post("/master-results", response_model=UploadResponse)
async def upload_master_results(
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """
    Master Results upload.

    - No file: sync from the configured SharePoint path (MASTER_RESULTS_PATH).
    - With file: parse the uploaded file (manual override).
    """
    from backend.services.bulk_uploads.master_bulk_upload import MasterBulkUploadService  # noqa: PLC0415
    try:
        if file is None:
            created, updated, skipped, errors, feedbacks = MasterBulkUploadService.sync_from_path(db)
            mode = "sync"
        else:
            file_bytes = await file.read()
            created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(db, file_bytes)
            mode = "upload"
        if not errors:
            db.commit()
    except Exception as exc:
        db.rollback()
        log.error("master_results_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    log.info("master_results", mode=mode, created=created, updated=updated, user=current_user.email)
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        feedbacks=feedbacks,
        message=f"Master Results ({mode}): {created} created, {updated} updated, {skipped} skipped",
    )


@router.post("/icp-oes", response_model=UploadResponse)
async def upload_icp_oes(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload an ICP-OES CSV file and ingest elemental data."""
    from backend.services.icp_service import ICPService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        processed_data, parse_errors = ICPService.parse_and_process_icp_file(file_bytes)
        if parse_errors and not processed_data:
            return UploadResponse(created=0, updated=0, skipped=0, errors=parse_errors,
                                  message="ICP parse failed")
        created_rows, ingest_errors = ICPService.bulk_create_icp_results(db, processed_data)
        all_errors = parse_errors + ingest_errors
        db.commit()
    except Exception as exc:
        db.rollback()
        log.error("icp_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    created = len(created_rows)
    log.info("icp_upload", created=created, user=current_user.email)
    return UploadResponse(
        created=created, updated=0, skipped=0, errors=all_errors,
        message=f"ICP-OES: {created} result rows created",
    )


@router.post("/xrd-mineralogy", response_model=UploadResponse)
async def upload_xrd_mineralogy(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload an XRD file — auto-detects Aeris or ActLabs format."""
    from backend.services.bulk_uploads.xrd_upload import XRDAutoDetectService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        created, updated, skipped, errors = XRDAutoDetectService.upload(db, file_bytes)
        if not errors:
            db.commit()
    except Exception as exc:
        db.rollback()
        log.error("xrd_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        message=f"XRD: {created} created, {updated} updated",
    )


@router.post("/timepoint-modifications", response_model=UploadResponse)
async def upload_timepoint_modifications(
    file: UploadFile = File(...),
    overwrite_existing: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Bulk-set brine modification descriptions on existing result rows."""
    from backend.services.bulk_uploads.timepoint_modifications import TimepointModificationsService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        updated, skipped, errors, feedbacks = TimepointModificationsService.bulk_set_from_bytes(
            db, file_bytes,
            overwrite_existing=overwrite_existing,
            modified_by=current_user.email,
        )
        if not errors:
            db.commit()
        else:
            db.rollback()
    except Exception as exc:
        db.rollback()
        log.error("timepoint_mod_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(
        created=0, updated=updated, skipped=skipped, errors=errors,
        feedbacks=feedbacks,
        message=f"Timepoint Modifications: {updated} updated, {skipped} skipped",
    )


@router.post("/rock-inventory", response_model=UploadResponse)
async def upload_rock_inventory(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload a Rock Inventory Excel file."""
    from backend.services.bulk_uploads.rock_inventory import RockInventoryUploadService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        created, updated, _images, skipped, errors, warnings = (
            RockInventoryUploadService.bulk_upsert_samples(db, file_bytes)
        )
        if not errors:
            db.commit()
        else:
            db.rollback()
    except Exception as exc:
        db.rollback()
        log.error("rock_inventory_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        warnings=warnings,
        message=f"Rock Inventory: {created} created, {updated} updated",
    )


@router.post("/chemical-inventory", response_model=UploadResponse)
async def upload_chemical_inventory(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload a Chemical Inventory Excel file."""
    from backend.services.bulk_uploads.chemical_inventory import ChemicalInventoryUploadService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        created, updated, skipped, errors = ChemicalInventoryUploadService.bulk_upsert_from_excel(
            db, file_bytes
        )
        if not errors:
            db.commit()
        else:
            db.rollback()
    except Exception as exc:
        db.rollback()
        log.error("chemical_inventory_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        message=f"Chemical Inventory: {created} created, {updated} updated",
    )


@router.post("/elemental-composition", response_model=UploadResponse)
async def upload_elemental_composition(
    file: UploadFile = File(...),
    default_unit: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """
    Upload Sample Chemical Composition (wide-format Excel).

    ``default_unit`` — when provided, any analyte column not already in the
    Analyte table is auto-created with this unit (e.g. "ppm", "%", "wt%").
    """
    from backend.services.bulk_uploads.actlabs_titration_data import ElementalCompositionService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        created, updated, skipped, errors = ElementalCompositionService.bulk_upsert_wide_from_excel(
            db, file_bytes, default_unit=default_unit
        )
        if not errors:
            db.commit()
        else:
            db.rollback()
    except Exception as exc:
        db.rollback()
        log.error("elemental_composition_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        message=f"Elemental Composition: {created} created, {updated} updated",
    )


@router.post("/actlabs-rock", response_model=UploadResponse)
async def upload_actlabs_rock(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload an ActLabs Rock Analysis file (titration report)."""
    from backend.services.bulk_uploads.actlabs_titration_data import ActlabsRockTitrationService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        created, updated, skipped, errors = ActlabsRockTitrationService.import_excel(db, file_bytes)
        if not errors:
            db.commit()
        else:
            db.rollback()
    except Exception as exc:
        db.rollback()
        log.error("actlabs_rock_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        message=f"ActLabs Rock: {created} created, {updated} updated",
    )


@router.post("/experiment-status", response_model=UploadResponse)
async def upload_experiment_status(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload an Experiment Status Excel file (bulk ONGOING / COMPLETED changes)."""
    from backend.services.bulk_uploads.experiment_status import ExperimentStatusService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        preview = ExperimentStatusService.preview_status_changes_from_excel(db, file_bytes)
        if preview.errors:
            return UploadResponse(
                created=0, updated=0, skipped=len(preview.missing_ids),
                errors=preview.errors,
                message="Validation failed — no changes applied",
            )
        to_ongoing_ids = [item["experiment_id"] for item in preview.to_ongoing]
        reactor_map = {
            item["experiment_id"]: item["new_reactor_number"]
            for item in preview.to_ongoing
            if item.get("new_reactor_number") is not None
        }
        marked_ongoing, marked_completed, _reactor_updates, errors = (
            ExperimentStatusService.apply_status_changes(db, to_ongoing_ids, reactor_map)
        )
        if not errors:
            db.commit()
        else:
            db.rollback()
    except Exception as exc:
        db.rollback()
        log.error("experiment_status_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    total = marked_ongoing + marked_completed
    return UploadResponse(
        created=0, updated=total, skipped=len(preview.missing_ids),
        errors=errors,
        feedbacks=[
            {"marked_ongoing": marked_ongoing, "marked_completed": marked_completed}
        ],
        message=(
            f"Status update: {marked_ongoing} → ONGOING, "
            f"{marked_completed} → COMPLETED, {len(preview.missing_ids)} not found"
        ),
    )


# ---------------------------------------------------------------------------
# Template downloads
# ---------------------------------------------------------------------------

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_NO_TEMPLATE = {
    "master-results", "icp-oes", "aeris-xrd", "actlabs-rock", "pxrf",
}


def _simple_template(
    headers: list[str],
    required: set[str],
    sheet_title: str = "Template",
    example_row: list | None = None,
) -> bytes:
    """Generate a minimal Excel template with highlighted required columns."""
    import openpyxl  # noqa: PLC0415
    from openpyxl.styles import PatternFill, Font, Alignment  # noqa: PLC0415

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    req_fill = PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid")
    opt_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")

    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)
        cell.fill = req_fill if h in required else opt_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = max(len(h) + 4, 16)

    if example_row:
        for col, val in enumerate(example_row, start=1):
            ws.cell(row=2, column=col, value=val)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _get_template_bytes(upload_type: str) -> bytes:
    if upload_type == "xrd-mineralogy":
        from backend.services.bulk_uploads.xrd_upload import XRDAutoDetectService  # noqa: PLC0415
        return XRDAutoDetectService.generate_template_bytes()

    if upload_type == "timepoint-modifications":
        from backend.services.bulk_uploads.timepoint_modifications import TimepointModificationsService  # noqa: PLC0415
        return TimepointModificationsService.generate_template_bytes()

    if upload_type == "scalar-results":
        return _simple_template(
            headers=[
                "Experiment ID", "Time (days)", "Description", "Date",
                "Gross Ammonium (mM)", "Sampling Vol (mL)", "Bkg Ammonium (mM)", "Bkg Exp ID",
                "H2 Conc (ppm)", "Gas Sample Vol (mL)", "Gas Pressure (MPa)",
                "Final pH", "Fe2+ Yield (%)", "Final DO (mg/L)",
                "Conductivity (mS/cm)", "Overwrite",
            ],
            required={"Experiment ID", "Time (days)"},
            example_row=["HPHT_001", 7.0, "Day 7 sample", None, 5.2, 2.0, 0.3, None,
                         120.0, 5.0, 0.5, 7.2, None, None, 12.5, "FALSE"],
        )

    if upload_type == "new-experiments":
        return _simple_template(
            headers=["experiment_id", "experiment_type", "date", "researcher",
                     "sample_id", "temperature_c", "description"],
            required={"experiment_id", "experiment_type"},
            example_row=["HPHT_072", "HPHT", None, "MH", "S001", 200.0, ""],
        )

    if upload_type == "rock-inventory":
        return _simple_template(
            headers=["sample_id", "rock_classification", "state", "country",
                     "locality", "latitude", "longitude", "description", "characterized"],
            required={"sample_id"},
            example_row=["S001", "Basalt", "BC", "Canada", "Vancouver Island",
                         49.5, -125.0, "Fresh olivine basalt", "FALSE"],
        )

    if upload_type == "chemical-inventory":
        return _simple_template(
            headers=["name", "formula", "cas_number", "molecular_weight",
                     "density", "hazard_class", "supplier", "catalog_number", "notes"],
            required={"name"},
            example_row=["Magnesium hydroxide", "Mg(OH)2", "1309-42-8",
                         58.32, 2.34, None, "Sigma-Aldrich", "309907", None],
        )

    if upload_type == "elemental-composition":
        return _simple_template(
            headers=["sample_id", "SiO2", "Al2O3", "Fe2O3", "MgO", "CaO", "Na2O"],
            required={"sample_id"},
            example_row=["S001", 47.2, 13.5, 11.0, 8.4, 10.2, 2.6],
        )

    if upload_type == "experiment-status":
        return _simple_template(
            headers=["experiment_id", "reactor_number"],
            required={"experiment_id"},
            example_row=["HPHT_072", 3],
        )

    raise ValueError(f"Unknown template type: {upload_type}")


@router.get("/templates/{upload_type}")
async def download_template(
    upload_type: str,
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> StreamingResponse:
    """Download an Excel upload template for the specified upload type."""
    if upload_type in _NO_TEMPLATE:
        raise HTTPException(
            status_code=404,
            detail=f"No template available for '{upload_type}'. "
                   "This upload type uses instrument exports or fixed-format files.",
        )
    try:
        template_bytes = _get_template_bytes(upload_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.error("template_generation_failed", upload_type=upload_type, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to generate template: {exc}")

    filename = f"{upload_type}-template.xlsx"
    return StreamingResponse(
        io.BytesIO(template_bytes),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
