"""
LongFormatParser -- accepts row-wise ``(experiment_id, time, metric, value, unit)``
uploads, pivots them into wide-format dicts, and delegates to
``ScalarResultsService.create_scalar_result()`` via the same upsert pipeline
used by the full-template and quick-upload paths.

This is the "advanced" upload tier, primarily aimed at power users, LIMS
integrations, and programmatic workflows.
"""

from __future__ import annotations

import io
import math
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from backend.services.scalar_results_service import ScalarResultsService
from backend.services.bulk_uploads.metric_groups import METRIC_REGISTRY


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------

def generate_long_format_template() -> bytes:
    """Generate an Excel template for long-format uploads."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Instructions sheet
        valid_metrics = sorted(METRIC_REGISTRY.keys())
        metric_help = []
        for m in valid_metrics:
            info = METRIC_REGISTRY[m]
            units = ", ".join(info["allowed_units"]) or "(none)"
            metric_help.append([m, info["label"], info["default_unit"], units])

        instr_rows = [
            ["Long Format Upload Template", "", "", ""],
            ["", "", "", ""],
            ["Columns:", "", "", ""],
            ["  Experiment ID*", "Required. Must match an existing experiment.", "", ""],
            ["  Time (days)*", "Required. Numeric time post-reaction in days.", "", ""],
            ["  Metric*", "Required. Must be one of the recognised metric names below.", "", ""],
            ["  Value*", "Required. Numeric value.", "", ""],
            ["  Unit", "Optional. Defaults to the metric's default unit.", "", ""],
            ["", "", "", ""],
            ["Multiple rows for the same (Experiment ID, Time) are merged.", "", "", ""],
            ["Blank cells will NOT overwrite existing data.", "", "", ""],
            ["", "", "", ""],
            ["Recognised Metrics:", "", "", ""],
            ["metric_name", "Label", "Default Unit", "Allowed Units"],
        ]
        instr_rows.extend(metric_help)
        pd.DataFrame(instr_rows).to_excel(
            writer, sheet_name="Instructions", index=False, header=False,
        )

        # Data sheet
        df = pd.DataFrame(columns=[
            "Experiment ID*", "Time (days)*", "Metric*", "Value*", "Unit",
        ])
        df.to_excel(writer, sheet_name="Data", index=False)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Parsing + pivot + upsert
# ---------------------------------------------------------------------------

def _validate_metric_value(metric: str, value: Any, unit: Optional[str]) -> List[str]:
    """Validate a single metric value + unit against METRIC_REGISTRY."""
    errors: List[str] = []
    info = METRIC_REGISTRY.get(metric)
    if info is None:
        errors.append(f"Unknown metric '{metric}'. Valid: {sorted(METRIC_REGISTRY.keys())}.")
        return errors

    # Numeric check
    try:
        num = float(value)
    except (ValueError, TypeError):
        errors.append(f"Value for '{metric}' must be numeric, got '{value}'.")
        return errors

    if "min" in info and num < info["min"]:
        errors.append(f"'{metric}' must be >= {info['min']}, got {num}.")
    if "max" in info and num > info["max"]:
        errors.append(f"'{metric}' must be <= {info['max']}, got {num}.")

    # Unit check
    if unit and info.get("allowed_units"):
        if unit not in info["allowed_units"]:
            errors.append(
                f"Unit '{unit}' not allowed for '{metric}'. "
                f"Allowed: {info['allowed_units']}."
            )
    return errors


def long_format_upload_from_excel(
    db: Session,
    file_bytes: bytes,
    *,
    dry_run: bool = False,
) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
    """
    Parse a long-format Excel upload, pivot to wide-format dicts, and upsert.

    Expected columns: ``Experiment ID*, Time (days)*, Metric*, Value*, Unit``

    Returns ``(created, updated, skipped, errors, row_feedbacks)``.
    """
    # --- Read Excel --------------------------------------------------------
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        target_sheet = None
        if "Data" in xls.sheet_names:
            target_sheet = "Data"
        else:
            for sheet in xls.sheet_names:
                if "INSTRUCTION" not in sheet.upper():
                    target_sheet = sheet
                    break
        if target_sheet is None and xls.sheet_names:
            target_sheet = 0
        df = pd.read_excel(xls, sheet_name=target_sheet)
    except Exception as exc:
        return 0, 0, 0, [f"Failed to read Excel: {exc}"], []

    # Normalize headers
    df.columns = [str(c).replace("*", "").strip() for c in df.columns]
    col_map = {
        "Experiment ID": "experiment_id",
        "Time (days)": "time_post_reaction",
        "Metric": "metric",
        "Value": "value",
        "Unit": "unit",
    }
    df.rename(columns=col_map, inplace=True)

    required_cols = {"experiment_id", "time_post_reaction", "metric", "value"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        return 0, 0, 0, [f"Missing columns: {sorted(missing_cols)}"], []

    # --- Validate rows and group by (experiment_id, time) ------------------
    errors: List[str] = []
    input_feedbacks: List[Dict[str, Any]] = []

    # Group: (experiment_id, time_post_reaction) -> {field: value}
    groups: Dict[Tuple[str, float], Dict[str, Any]] = {}
    group_source_rows: Dict[Tuple[str, float], List[int]] = {}

    for idx, row in df.iterrows():
        row_num = int(idx) + 2  # Excel row
        exp_id = row.get("experiment_id")
        time_raw = row.get("time_post_reaction")
        metric = row.get("metric")
        value = row.get("value")
        unit = row.get("unit") if "unit" in row and pd.notna(row.get("unit")) else None

        # Skip fully empty rows
        if pd.isna(exp_id) and pd.isna(metric):
            continue

        # Required field checks
        row_errors: List[str] = []
        if pd.isna(exp_id) or str(exp_id).strip() == "":
            row_errors.append("Missing Experiment ID.")
        if pd.isna(time_raw):
            row_errors.append("Missing Time (days).")
        if pd.isna(metric) or str(metric).strip() == "":
            row_errors.append("Missing Metric.")
        if pd.isna(value):
            row_errors.append("Missing Value.")

        if row_errors:
            for e in row_errors:
                errors.append(f"Row {row_num}: {e}")
            input_feedbacks.append({
                "row": row_num,
                "experiment_id": str(exp_id) if pd.notna(exp_id) else "",
                "time_post_reaction": None,
                "status": "error",
                "fields_updated": [], "fields_preserved": [],
                "old_values": {}, "new_values": {},
                "warnings": [], "errors": row_errors,
            })
            continue

        exp_id_str = str(exp_id).strip()
        try:
            time_float = float(time_raw)
        except (ValueError, TypeError):
            errors.append(f"Row {row_num}: Time (days) must be numeric, got '{time_raw}'.")
            input_feedbacks.append({
                "row": row_num, "experiment_id": exp_id_str,
                "time_post_reaction": None, "status": "error",
                "fields_updated": [], "fields_preserved": [],
                "old_values": {}, "new_values": {},
                "warnings": [], "errors": [f"Time must be numeric, got '{time_raw}'."],
            })
            continue

        metric_str = str(metric).strip()
        info = METRIC_REGISTRY.get(metric_str)
        if info is None:
            errors.append(
                f"Row {row_num}: Unknown metric '{metric_str}'. "
                f"Valid: {sorted(METRIC_REGISTRY.keys())}."
            )
            input_feedbacks.append({
                "row": row_num, "experiment_id": exp_id_str,
                "time_post_reaction": time_float, "status": "error",
                "fields_updated": [], "fields_preserved": [],
                "old_values": {}, "new_values": {},
                "warnings": [], "errors": [f"Unknown metric '{metric_str}'."],
            })
            continue

        # Validate value + unit
        val_errors = _validate_metric_value(metric_str, value, unit)
        if val_errors:
            for e in val_errors:
                errors.append(f"Row {row_num}: {e}")
            input_feedbacks.append({
                "row": row_num, "experiment_id": exp_id_str,
                "time_post_reaction": time_float, "status": "error",
                "fields_updated": [], "fields_preserved": [],
                "old_values": {}, "new_values": {},
                "warnings": [], "errors": val_errors,
            })
            continue

        # Accumulate into group
        key = (exp_id_str, time_float)
        if key not in groups:
            groups[key] = {}
            group_source_rows[key] = []
        db_field = info["db_field"]
        groups[key][db_field] = float(value)
        group_source_rows[key].append(row_num)

        # H2 concentration is always stored in ppm
        if db_field == "h2_concentration":
            groups[key]["h2_concentration_unit"] = "ppm"

    # If we have parse-level errors and no valid groups, return early
    if errors and not groups:
        return 0, 0, 0, errors, input_feedbacks

    # --- Upsert (or dry run) per group ------------------------------------
    created = updated = skipped = 0
    upsert_feedbacks: List[Dict[str, Any]] = []

    for (exp_id, time_val), field_dict in groups.items():
        source_rows = group_source_rows[(exp_id, time_val)]
        row_label = ", ".join(str(r) for r in source_rows)

        fb: Dict[str, Any] = {
            "row": source_rows[0],
            "experiment_id": exp_id,
            "time_post_reaction": time_val,
            "status": "pending",
            "fields_updated": sorted(field_dict.keys()),
            "fields_preserved": [],
            "old_values": {}, "new_values": {},
            "warnings": [], "errors": [],
        }

        if dry_run:
            fb["status"] = "dry_run"
            upsert_feedbacks.append(fb)
            continue

        try:
            row_data = dict(field_dict)
            row_data["time_post_reaction"] = time_val
            row_data["description"] = f"Day {time_val} results"
            row_data["_overwrite"] = False  # Long format always uses partial update

            upsert = ScalarResultsService.create_scalar_result_ex(
                db=db,
                experiment_id=exp_id,
                result_data=row_data,
            )
            if upsert and upsert.experimental_result:
                fb["status"] = upsert.action
                fb["fields_updated"] = list(upsert.fields_updated)
                fb["fields_preserved"] = list(upsert.fields_preserved)
                fb["old_values"] = dict(upsert.old_values)
                fb["new_values"] = dict(upsert.new_values)
                if upsert.action == "created":
                    created += 1
                else:
                    updated += 1
            else:
                fb["status"] = "skipped"
                skipped += 1
        except ValueError as exc:
            fb["status"] = "error"
            fb["errors"].append(str(exc))
            errors.append(f"Rows {row_label}: {exc}")
        except Exception as exc:
            fb["status"] = "error"
            fb["errors"].append(f"Unexpected error - {exc}")
            errors.append(f"Rows {row_label}: Unexpected error - {exc}")

        upsert_feedbacks.append(fb)

    all_feedbacks = input_feedbacks + upsert_feedbacks
    return created, updated, skipped, errors, all_feedbacks
