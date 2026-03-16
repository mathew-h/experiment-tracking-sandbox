"""
QuickUploadParser -- thin wrapper around ScalarResultsService for
metric-specific (partial) Excel uploads.

Each metric group (hydrogen, pH/conductivity, ammonium, etc.) gets a minimal
Excel template containing only its relevant columns.  Uploads are parsed,
validated against the group definition, and delegated to
``ScalarResultsService.create_scalar_result()`` with ``_overwrite=False``.
"""

from __future__ import annotations

import io
import math
import datetime as dt
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from backend.services.scalar_results_service import ScalarResultsService
from backend.services.bulk_uploads.metric_groups import METRIC_GROUPS


# ---------------------------------------------------------------------------
# Row-level feedback dataclass
# ---------------------------------------------------------------------------

class RowFeedback:
    """Structured per-row upload result."""

    __slots__ = (
        "row", "experiment_id", "time_post_reaction",
        "status", "fields_updated", "fields_preserved",
        "warnings", "errors",
    )

    def __init__(
        self,
        row: int,
        experiment_id: str = "",
        time_post_reaction: Optional[float] = None,
        status: str = "pending",
    ):
        self.row = row
        self.experiment_id = experiment_id
        self.time_post_reaction = time_post_reaction
        self.status: str = status  # "created" | "updated" | "skipped" | "error"
        self.fields_updated: List[str] = []
        self.fields_preserved: List[str] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row": self.row,
            "experiment_id": self.experiment_id,
            "time_post_reaction": self.time_post_reaction,
            "status": self.status,
            "fields_updated": list(self.fields_updated),
            "fields_preserved": list(self.fields_preserved),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------

def generate_quick_template(group_key: str) -> bytes:
    """
    Generate an Excel template for a specific metric group.

    Returns raw xlsx bytes suitable for ``st.download_button``.
    """
    group = METRIC_GROUPS.get(group_key)
    if group is None:
        raise ValueError(f"Unknown metric group: {group_key}")

    headers: OrderedDict = group["template_headers"]
    english_headers = list(headers.values())

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Instructions sheet
        instructions = [
            ["Quick Upload Template", ""],
            ["Metric Group", group["label"]],
            ["", ""],
            ["Fields marked with * are required.", ""],
            ["Leave optional fields blank to skip them.", ""],
            ["Blank cells will NOT overwrite existing data.", ""],
            ["", ""],
            ["Overwrite behaviour:", ""],
            ["  By default, only provided fields are updated.", ""],
            ["  Existing values for other metrics are preserved.", ""],
        ]
        pd.DataFrame(instructions, columns=["", ""]).to_excel(
            writer, sheet_name="Instructions", index=False, header=False,
        )

        # Data sheet
        df = pd.DataFrame(columns=english_headers)
        df.to_excel(writer, sheet_name="Data", index=False)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_measurement_date(value: Any) -> Optional[dt.datetime]:
    """Best-effort date coercion (replicates ScalarResultsUploadService logic)."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time.min)
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _validate_field(field: str, value: Any, rules: Dict[str, Any]) -> List[str]:
    """Validate a single field value against its rules from METRIC_GROUPS."""
    errors: List[str] = []
    if rules.get("type") == "numeric":
        try:
            numeric_val = float(value)
        except (ValueError, TypeError):
            errors.append(f"'{field}' must be a number, got '{value}'.")
            return errors
        if "min" in rules and numeric_val < rules["min"]:
            errors.append(f"'{field}' must be >= {rules['min']}, got {numeric_val}.")
        if "max" in rules and numeric_val > rules["max"]:
            errors.append(f"'{field}' must be <= {rules['max']}, got {numeric_val}.")
    if "allowed" in rules:
        if value not in rules["allowed"]:
            errors.append(
                f"'{field}' must be one of {rules['allowed']}, got '{value}'."
            )
    return errors


# ---------------------------------------------------------------------------
# Quick upload parse + upsert
# ---------------------------------------------------------------------------

def quick_upload_from_excel(
    db: Session,
    file_bytes: bytes,
    group_key: str,
    *,
    overwrite_all: bool = False,
    dry_run: bool = False,
) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
    """
    Parse a metric-specific Excel upload and upsert via ScalarResultsService.

    Args:
        db: Database session.
        file_bytes: Raw xlsx bytes.
        group_key: Key into ``METRIC_GROUPS``.
        overwrite_all: Global overwrite flag (default False = partial update).
        dry_run: If True, validate only -- do not persist.

    Returns:
        ``(created, updated, skipped, errors, row_feedback_list)``
    """
    group = METRIC_GROUPS.get(group_key)
    if group is None:
        return 0, 0, 0, [f"Unknown metric group: {group_key}"], []

    headers: OrderedDict = group["template_headers"]
    required = group["required_fields"]
    defaults: Dict[str, Any] = group.get("defaults", {})
    validations: Dict[str, Dict] = group.get("validations", {})

    # Reverse map: English header -> variable_name
    header_map = {v.replace("*", "").strip(): k for k, v in headers.items()}

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

    # Strip asterisks from headers and remap
    df.columns = [str(c).replace("*", "").strip() for c in df.columns]
    new_cols = []
    for col in df.columns:
        new_cols.append(header_map.get(col, col))
    df.columns = new_cols

    # --- Clean + validate each row ----------------------------------------
    records = df.to_dict("records")
    feedbacks: List[Dict[str, Any]] = []
    cleaned: List[Dict[str, Any]] = []
    parse_errors: List[str] = []

    for row_index, rec in enumerate(records):
        row_num = row_index + 2  # Excel row (1-indexed header + 1)
        fb = RowFeedback(row=row_num)

        # Drop NaN / empty
        clean: Dict[str, Any] = {}
        for k, v in rec.items():
            if v is None:
                continue
            if isinstance(v, float) and math.isnan(v):
                continue
            if isinstance(v, str) and v.strip() == "":
                continue
            clean[k] = v

        # Apply defaults
        for dk, dv in defaults.items():
            if dk not in clean:
                clean[dk] = dv

        fb.experiment_id = str(clean.get("experiment_id", ""))
        time_raw = clean.get("time_post_reaction")

        # Required-field check
        missing = required - set(clean.keys())
        if missing:
            fb.status = "error"
            fb.errors.append(f"Missing required field(s): {', '.join(sorted(missing))}.")
            parse_errors.append(f"Row {row_num}: {fb.errors[-1]}")
            feedbacks.append(fb.to_dict())
            continue

        # Coerce time_post_reaction
        try:
            clean["time_post_reaction"] = float(time_raw)
            fb.time_post_reaction = clean["time_post_reaction"]
        except (ValueError, TypeError):
            fb.status = "error"
            fb.errors.append(f"'Time (days)' must be a number, got '{time_raw}'.")
            parse_errors.append(f"Row {row_num}: {fb.errors[-1]}")
            feedbacks.append(fb.to_dict())
            continue

        # Coerce measurement_date
        if "measurement_date" in clean:
            parsed_date = _parse_measurement_date(clean["measurement_date"])
            if parsed_date is None:
                fb.status = "error"
                fb.errors.append("Invalid measurement_date (expected date/datetime).")
                parse_errors.append(f"Row {row_num}: {fb.errors[-1]}")
                feedbacks.append(fb.to_dict())
                continue
            clean["measurement_date"] = parsed_date

        # Field-level validation
        row_valid = True
        for field, rules in validations.items():
            if field in clean:
                field_errors = _validate_field(field, clean[field], rules)
                if field_errors:
                    fb.errors.extend(field_errors)
                    parse_errors.extend(f"Row {row_num}: {e}" for e in field_errors)
                    row_valid = False
        if not row_valid:
            fb.status = "error"
            feedbacks.append(fb.to_dict())
            continue

        # Coerce numerics
        for field in clean:
            if field in ("experiment_id", "description", "measurement_date",
                         "h2_concentration_unit", "background_experiment_id"):
                continue
            if field == "time_post_reaction":
                continue
            if isinstance(clean[field], str):
                try:
                    clean[field] = float(clean[field])
                except (ValueError, TypeError):
                    pass

        # Auto-generate description
        if not clean.get("description"):
            clean["description"] = f"Day {clean['time_post_reaction']} results"

        clean["_overwrite"] = overwrite_all

        fb.status = "pending"
        cleaned.append((row_num, clean, fb))

    # --- Persist (or dry-run) ---------------------------------------------
    created = updated = skipped = 0
    svc_errors: List[str] = []

    for row_num, row_data, fb in cleaned:
        if dry_run:
            fb.status = "dry_run"
            fb.fields_updated = [
                f for f in row_data
                if f not in ("experiment_id", "time_post_reaction", "description",
                             "_overwrite", "measurement_date")
            ]
            feedbacks.append(fb.to_dict())
            continue

        try:
            exp_id = row_data.pop("experiment_id")
            result = ScalarResultsService.create_scalar_result(
                db=db,
                experiment_id=exp_id,
                result_data=row_data,
            )
            if result:
                # Determine created vs updated by checking scalar_data age
                scalar = result.scalar_data
                if scalar and scalar.id and result.updated_at:
                    fb.status = "updated"
                    updated += 1
                else:
                    fb.status = "created"
                    created += 1

                # Report which fields were provided
                data_fields = {
                    f for f in row_data
                    if f not in ("_overwrite", "description", "time_post_reaction")
                    and row_data.get(f) is not None
                }
                fb.fields_updated = sorted(data_fields)
            else:
                fb.status = "skipped"
                skipped += 1

        except ValueError as exc:
            fb.status = "error"
            fb.errors.append(str(exc))
            svc_errors.append(f"Row {row_num}: {exc}")
        except Exception as exc:
            fb.status = "error"
            fb.errors.append(f"Unexpected error - {exc}")
            svc_errors.append(f"Row {row_num}: Unexpected error - {exc}")

        feedbacks.append(fb.to_dict())

    all_errors = parse_errors + svc_errors
    return created, updated, skipped, all_errors, feedbacks
