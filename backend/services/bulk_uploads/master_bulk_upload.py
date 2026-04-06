"""
Master Results bulk upload — reads from fixed SharePoint path or uploaded bytes.

Dashboard sheet column spec:
  Experiment ID | Duration (Days) | Description | Sample Date | NMR Run Date |
  ICP Run Date  | GC Run Date     | NH4 (mM)    | H2 (ppm)    | Gas Volume (mL) |
  Gas Pressure (psi) | Sample pH | Sample Conductivity (mS/cm) |
  Sampled Solution Volume (mL) | Modification | Overwrite
"""
from __future__ import annotations

import datetime as dt
import io
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

_PSI_TO_MPA = 0.00689476
_DASHBOARD_SHEET = "Dashboard"


def _parse_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    try:
        return float(val)
    except Exception:
        return None


def _parse_date(val: Any) -> Optional[dt.datetime]:
    if val is None:
        return None
    if isinstance(val, dt.datetime):
        return val
    if isinstance(val, dt.date):
        return dt.datetime.combine(val, dt.time.min)
    if isinstance(val, pd.Timestamp):
        return val.to_pydatetime()
    if isinstance(val, str):
        parsed = pd.to_datetime(val, errors="coerce")
        return None if pd.isna(parsed) else parsed.to_pydatetime()
    parsed = pd.to_datetime(val, errors="coerce")
    return None if pd.isna(parsed) else parsed.to_pydatetime()


def _parse_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val) if not pd.isna(val) else False
    if isinstance(val, str):
        return val.strip().lower() in {"true", "yes", "1", "y"}
    return False


def _find_sheet(xls: pd.ExcelFile) -> Optional[str]:
    """Return Dashboard sheet name (case-insensitive) or first sheet."""
    for name in xls.sheet_names:
        if name.strip().lower() == "dashboard":
            return name
    return xls.sheet_names[0] if xls.sheet_names else None


def _process_bytes(
    db: Session, file_bytes: bytes
) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
    """
    Parse the Master Results Excel and upsert scalar results.
    Returns (created, updated, skipped, errors, feedbacks).
    """
    from backend.services.scalar_results_service import ScalarResultsService  # noqa: PLC0415

    errors: List[str] = []
    feedbacks: List[Dict[str, Any]] = []
    created = updated = skipped = 0

    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception as exc:
        return 0, 0, 0, [f"Failed to read file: {exc}"], []

    sheet_name = _find_sheet(xls)
    if sheet_name is None:
        return 0, 0, 0, ["File has no sheets."], []

    try:
        df = xls.parse(sheet_name)
    except Exception as exc:
        return 0, 0, 0, [f"Failed to parse sheet '{sheet_name}': {exc}"], []

    df.columns = [str(c).strip() for c in df.columns]
    # Normalise the optional volume column header to canonical casing.
    df.columns = [
        "Sampled Solution Volume (mL)" if c.lower() == "sampled solution volume (ml)" else c
        for c in df.columns
    ]

    # Validate required columns
    required = {"Experiment ID", "Duration (Days)"}
    missing = required - set(df.columns)
    if missing:
        return 0, 0, 0, [
            f"Sheet '{sheet_name}' is missing required columns: {', '.join(sorted(missing))}. "
            f"Available: {', '.join(df.columns[:10])}"
        ], []

    for idx, row in df.iterrows():
        row_num = idx + 2
        exp_id = str(row.get("Experiment ID") or "").strip()
        if not exp_id:
            skipped += 1
            continue

        duration_raw = row.get("Duration (Days)")
        if duration_raw is None or (isinstance(duration_raw, float) and pd.isna(duration_raw)):
            skipped += 1
            continue

        time_post_reaction = _parse_float(duration_raw)
        if time_post_reaction is None:
            errors.append(f"Row {row_num}: invalid Duration (Days) '{duration_raw}'")
            continue

        description = str(row.get("Description") or "").strip() or None
        sample_date = _parse_date(row.get("Sample Date"))
        nmr_run_date = _parse_date(row.get("NMR Run Date"))
        icp_run_date = _parse_date(row.get("ICP Run Date"))
        gc_run_date = _parse_date(row.get("GC Run Date"))

        nh4_mm = _parse_float(row.get("NH4 (mM)"))
        h2_ppm = _parse_float(row.get("H2 (ppm)"))
        gas_vol_ml = _parse_float(row.get("Gas Volume (mL)"))
        gas_psi = _parse_float(row.get("Gas Pressure (psi)"))
        gas_mpa = gas_psi * _PSI_TO_MPA if gas_psi is not None else None
        ph = _parse_float(row.get("Sample pH"))
        conductivity = _parse_float(row.get("Sample Conductivity (mS/cm)"))
        sampling_vol_ml = _parse_float(row.get("Sampled Solution Volume (mL)"))
        modification = str(row.get("Modification") or "").strip() or None
        overwrite = _parse_bool(row.get("Overwrite"))

        result_data: Dict[str, Any] = {
            "time_post_reaction": time_post_reaction,
            "description": description or f"Master upload — day {time_post_reaction}",
            "measurement_date": sample_date,
            "nmr_run_date": nmr_run_date,
            "icp_run_date": icp_run_date,
            "gc_run_date": gc_run_date,
            "gross_ammonium_concentration_mM": nh4_mm,
            "h2_concentration": h2_ppm,
            "h2_concentration_unit": "ppm" if h2_ppm is not None else None,
            "gas_sampling_volume_ml": gas_vol_ml,
            "gas_sampling_pressure_MPa": gas_mpa,
            "final_ph": ph,
            "final_conductivity_mS_cm": conductivity,
            "sampling_volume_mL": sampling_vol_ml,
            "_overwrite": overwrite,
        }
        # Remove None-valued optional fields so the service skips them
        result_data = {k: v for k, v in result_data.items() if v is not None or k == "_overwrite"}

        savepoint = db.begin_nested()
        try:
            upsert = ScalarResultsService.create_scalar_result_ex(db, exp_id, result_data)
            exp_result = upsert.experimental_result

            # Apply modification description if provided
            if modification:
                exp_result.brine_modification_description = modification

            action = upsert.action
            if action == "created":
                created += 1
            else:
                updated += 1
            savepoint.commit()
            feedbacks.append({"row": row_num, "experiment_id": exp_id, "action": action})

        except ValueError as exc:
            savepoint.rollback()
            errors.append(f"Row {row_num} ({exp_id}): {exc}")
        except Exception as exc:
            savepoint.rollback()
            errors.append(f"Row {row_num} ({exp_id}): unexpected error — {exc}")

    return created, updated, skipped, errors, feedbacks


class MasterBulkUploadService:
    @staticmethod
    def sync_from_path(db: Session) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
        """
        Read the Master Results file from the configured path.
        Priority: AppConfig table > MASTER_RESULTS_PATH env/settings.
        Returns (created, updated, skipped, errors, feedbacks).
        """
        from backend.config.settings import get_settings  # noqa: PLC0415
        from database.models.app_config import AppConfig  # noqa: PLC0415

        cfg = db.query(AppConfig).filter_by(key="master_results_path").first()
        path = cfg.value if cfg else get_settings().master_results_path

        try:
            with open(path, "rb") as fh:
                file_bytes = fh.read()
        except FileNotFoundError:
            return 0, 0, 0, [
                f"Master Results file not found at: {path}. "
                "Configure the path via Bulk Uploads → Master Results Sync → Settings."
            ], []
        except PermissionError:
            return 0, 0, 0, [
                f"Permission denied reading: {path}. "
                "Ensure the file is not open in Excel."
            ], []
        except Exception as exc:
            return 0, 0, 0, [f"Failed to read Master Results file: {exc}"], []

        return _process_bytes(db, file_bytes)

    @staticmethod
    def from_bytes(
        db: Session, file_bytes: bytes
    ) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
        """
        Parse a manually uploaded Master Results file.
        Returns (created, updated, skipped, errors, feedbacks).
        """
        return _process_bytes(db, file_bytes)
