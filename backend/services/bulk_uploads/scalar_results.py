from __future__ import annotations

import io
from typing import List, Tuple, Dict, Any, Optional
import math
import datetime as dt

import pandas as pd
from sqlalchemy.orm import Session

from backend.services.scalar_results_service import ScalarResultsService
from frontend.config.variable_config import SCALAR_RESULTS_TEMPLATE_HEADERS


class ScalarResultsUploadService:
    @staticmethod
    def _parse_measurement_date(value: Any) -> Optional[dt.datetime]:
        """
        Normalize measurement_date to a Python datetime for SQLite DateTime columns.

        Accepts pandas Timestamp, datetime/date, or string-like values.
        Returns None if the value is empty/invalid.
        """
        if value is None:
            return None
        if isinstance(value, dt.datetime):
            return value
        if isinstance(value, dt.date):
            return dt.datetime.combine(value, dt.time.min)
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        if isinstance(value, str):
            parsed = pd.to_datetime(value, errors="coerce")
            if pd.isna(parsed):
                return None
            return parsed.to_pydatetime()
        # Try pandas as a last resort (handles numeric Excel dates)
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()

    @staticmethod
    def bulk_upsert_from_excel(
        db: Session,
        file_bytes: bytes,
        overwrite_all: bool = False,
    ) -> Tuple[int, int, int, List[str]]:
        """
        Parse the Solution Chemistry Excel and delegate creation/upsert to ScalarResultsService.

        Returns ``(created, updated, skipped, errors)``.
        """
        created, updated, skipped, errors, _feedbacks = (
            ScalarResultsUploadService.bulk_upsert_from_excel_ex(
                db, file_bytes, overwrite_all=overwrite_all, dry_run=False,
            )
        )
        return created, updated, skipped, errors

    @staticmethod
    def bulk_upsert_from_excel_ex(
        db: Session,
        file_bytes: bytes,
        overwrite_all: bool = False,
        dry_run: bool = False,
    ) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
        """
        Extended version that also returns per-row structured feedback and
        supports a *dry_run* mode (validate + preview without persisting).

        Returns ``(created, updated, skipped, errors, row_feedbacks)``.
        """
        errors: List[str] = []
        created = updated = skipped = 0

        try:
            xls = pd.ExcelFile(io.BytesIO(file_bytes))

            target_sheet = None
            if "Solution Chemistry" in xls.sheet_names:
                target_sheet = "Solution Chemistry"
            if target_sheet is None:
                for sheet in xls.sheet_names:
                    if "INSTRUCTION" not in sheet.upper():
                        target_sheet = sheet
                        break
            if target_sheet is None and xls.sheet_names:
                target_sheet = 0

            df = pd.read_excel(xls, sheet_name=target_sheet)
        except Exception as e:
            return 0, 0, 0, [f"Failed to read Excel: {e}"], []

        # Remove asterisks used to mark required columns in templates
        df.columns = [str(c).replace('*', '') for c in df.columns]

        # friendly header -> internal name  (from SCALAR_RESULTS_TEMPLATE_HEADERS)
        header_map = {v: k for k, v in SCALAR_RESULTS_TEMPLATE_HEADERS.items()}

        # Legacy / DB-column-name aliases that older templates may use.
        # Maps *alternative* spelling -> canonical internal field name.
        LEGACY_ALIASES = {
            # time field: DB column, raw key, and common human spellings
            "time_post_reaction":           "time_post_reaction",
            "time_post_reaction_days":      "time_post_reaction",
            "time (days)":                  "time_post_reaction",
            "time(days)":                   "time_post_reaction",
            "time days":                    "time_post_reaction",
            # experiment identifier
            "experiment_id":                "experiment_id",
            "experimentid":                 "experiment_id",
            "experiment id":                "experiment_id",
            # scalar fields – raw DB names (with units)
            "gross_ammonium_concentration_mm": "gross_ammonium_concentration_mM",
            "background_ammonium_concentration_mm": "background_ammonium_concentration_mM",
            "h2_concentration":             "h2_concentration",
            "gas_sampling_volume_ml":       "gas_sampling_volume_ml",
            "gas_sampling_pressure_mpa":    "gas_sampling_pressure_MPa",
            "final_ph":                     "final_ph",
            "final_dissolved_oxygen_mg_l":  "final_dissolved_oxygen_mg_L",
            "final_conductivity_ms_cm":     "final_conductivity_mS_cm",
            "sampling_volume_ml":           "sampling_volume_mL",
            "ferrous_iron_yield":           "ferrous_iron_yield",
            "measurement_date":             "measurement_date",
            "description":                  "description",
            "overwrite":                    "overwrite",
            # legacy names without trailing units
            "gross_ammonium_concentration":      "gross_ammonium_concentration_mM",
            "background_ammonium_concentration": "background_ammonium_concentration_mM",
            "gas_sampling_volume":               "gas_sampling_volume_ml",
            "gas_sampling_pressure":             "gas_sampling_pressure_MPa",
            "final_dissolved_oxygen":            "final_dissolved_oxygen_mg_L",
            "final_conductivity":                "final_conductivity_mS_cm",
            "sampling_volume":                   "sampling_volume_mL",
        }
        header_map.update(LEGACY_ALIASES)

        # Build a case-insensitive lookup so "Time_Post_Reaction_Days" still
        # resolves even if the alias table only contains the lowercase form.
        ci_header_map = {k.lower(): v for k, v in header_map.items()}

        new_columns = []
        for col in df.columns:
            col_str = str(col).strip()
            mapped = header_map.get(col_str) or ci_header_map.get(col_str.lower())
            new_columns.append(mapped if mapped else col_str)
        df.columns = new_columns

        records: List[Dict[str, Any]] = df.to_dict('records')
        cleaned_records: List[Dict[str, Any]] = []
        parse_feedbacks: List[Dict[str, Any]] = []

        for row_index, rec in enumerate(records):
            row_num = row_index + 2
            clean: Dict[str, Any] = {}
            for k, v in rec.items():
                if v is None:
                    continue
                if isinstance(v, float) and math.isnan(v):
                    continue
                if isinstance(v, str) and v.strip() == '':
                    continue
                clean[k] = v

            if not clean:
                continue

            if "measurement_date" in clean:
                parsed_date = ScalarResultsUploadService._parse_measurement_date(
                    clean.get("measurement_date"),
                )
                if parsed_date is None:
                    errors.append(
                        f"Row {row_num}: Invalid measurement_date (expected date/datetime)."
                    )
                    parse_feedbacks.append({
                        "row": row_num,
                        "experiment_id": str(clean.get("experiment_id", "")),
                        "time_post_reaction": None,
                        "status": "error",
                        "fields_updated": [], "fields_preserved": [],
                        "old_values": {}, "new_values": {},
                        "warnings": [],
                        "errors": ["Invalid measurement_date."],
                    })
                    continue
                clean["measurement_date"] = parsed_date

            time_val = clean.get('time_post_reaction')
            if time_val is None:
                errors.append(
                    f"Row {row_num}: 'Time (days)' is required. "
                    f"Use 0 for pre-reaction baselines."
                )
                parse_feedbacks.append({
                    "row": row_num,
                    "experiment_id": str(clean.get("experiment_id", "")),
                    "time_post_reaction": None,
                    "status": "error",
                    "fields_updated": [], "fields_preserved": [],
                    "old_values": {}, "new_values": {},
                    "warnings": [],
                    "errors": ["Missing Time (days)."],
                })
                continue
            try:
                clean['time_post_reaction'] = float(time_val)
            except (ValueError, TypeError):
                errors.append(
                    f"Row {row_num}: 'Time (days)' must be a number, got '{time_val}'."
                )
                parse_feedbacks.append({
                    "row": row_num,
                    "experiment_id": str(clean.get("experiment_id", "")),
                    "time_post_reaction": None,
                    "status": "error",
                    "fields_updated": [], "fields_preserved": [],
                    "old_values": {}, "new_values": {},
                    "warnings": [],
                    "errors": [f"Time (days) must be a number, got '{time_val}'."],
                })
                continue

            row_overwrite = clean.pop('overwrite', None)
            if row_overwrite is not None:
                if isinstance(row_overwrite, str):
                    clean['_overwrite'] = row_overwrite.lower() in ('true', '1', 'yes')
                else:
                    clean['_overwrite'] = bool(row_overwrite)
            else:
                clean['_overwrite'] = overwrite_all

            cleaned_records.append(clean)

        # --- Dry run: validate only, no persist ---
        if dry_run:
            dry_feedbacks: List[Dict[str, Any]] = list(parse_feedbacks)
            for idx, rec in enumerate(cleaned_records):
                row_num = idx + 2
                data_fields = sorted(
                    f for f in rec
                    if f not in ("_overwrite", "description", "time_post_reaction",
                                 "experiment_id", "measurement_date")
                    and rec.get(f) is not None
                )
                dry_feedbacks.append({
                    "row": row_num,
                    "experiment_id": str(rec.get("experiment_id", "")),
                    "time_post_reaction": rec.get("time_post_reaction"),
                    "status": "dry_run",
                    "fields_updated": data_fields,
                    "fields_preserved": [],
                    "old_values": {}, "new_values": {},
                    "warnings": [],
                    "errors": [],
                })
            return 0, 0, 0, errors, dry_feedbacks

        # --- Persist (row-level savepoints ensure failures are isolated) ---
        results, svc_errors, svc_feedbacks = (
            ScalarResultsService.bulk_create_scalar_results_ex(db, cleaned_records)
        )
        errors.extend(svc_errors)
        for fb in svc_feedbacks:
            if fb["status"] == "created":
                created += 1
            elif fb["status"] == "updated":
                updated += 1
            elif fb["status"] in ("skipped", "error"):
                skipped += 1
        all_feedbacks = parse_feedbacks + svc_feedbacks

        return created, updated, skipped, errors, all_feedbacks


