"""
Master Results bulk upload — reads from fixed SharePoint path or uploaded bytes.

Dashboard sheet column spec:
  Experiment ID | Duration (Days) | Description | Sample Date | NMR Run Date |
  ICP Run Date  | GC Run Date     | XRD Run Date | NH4 (mM)   | H2 (ppm)    | Gas Volume (mL) |
  Gas Pressure (psi) | Sample pH | Sample Conductivity (mS/cm) |
  Sampled Solution Volume (mL) | Modification | Overwrite
"""
from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from backend.services.bulk_uploads.replicate_routing import combine_replicate_id
from backend.services.result_merge_utils import apply_id_timepoint
from database.experiment_id_parser import split_timepoint_token

_PSI_TO_MPA = 0.00689476
_DASHBOARD_SHEET = "Dashboard"

# Canonical Dashboard headers, keyed by the lowercased sheet header.
#
# Issue #111: the sheet was restructured twice. The single 'H2 (ppm)' block was
# renamed to a Full Loop ('FL ...') block and 'Overwrite' became 'OVERWRITE';
# then the wide DI block ('DI a/b/c H2 (ppm)' + avg + SD) collapsed to one
# 'DI H2 (ppm)' when a/b/c moved to their own rows. Every spelling is accepted
# so archived workbooks keep parsing; the values on the right are the only
# names the row reads below use.
_HEADER_ALIASES: Dict[str, str] = {
    # Full Loop — pre-rename spelling first in each pair
    "h2 (ppm)": "FL H2 (ppm)",
    "fl h2 (ppm)": "FL H2 (ppm)",
    "gas volume (ml)": "FL Gas Volume (mL)",
    "fl gas volume (ml)": "FL Gas Volume (mL)",
    "gas pressure (psi)": "FL Gas Pressure (psi)",
    "fl gas pressure (psi)": "FL Gas Pressure (psi)",
    # GC direct injection — 'DI avg' is the v2 spelling of v3's 'DI H2'
    "di h2 (ppm)": "DI H2 (ppm)",
    "di avg h2 (ppm)": "DI H2 (ppm)",
    "di gas volume (ml)": "DI gas volume (mL)",
    "di gas pressure (psi)": "DI gas pressure (psi)",
    # Casing-only normalisations (previously done inline)
    "overwrite": "Overwrite",
    "sampled solution volume (ml)": "Sampled Solution Volume (mL)",
    "replicate": "Replicate",
}

# H2 as a standalone token, so 'H2S (ppm)' and 'H2O' never look like a dropped
# hydrogen column while a real rename ('GC Loop H2 ppm') still does.
_H2_TOKEN = re.compile(r"\bh2\b", re.IGNORECASE)

# Columns whose header mentions H2 and that the parser deliberately handles.
_RECOGNIZED_H2_COLUMNS = {
    "FL H2 (ppm)",
    "DI H2 (ppm)",
}

# v2's wide DI block. Those letters are replicate VIALS, and v3 gives each vial
# its own row, so there is no correct way to fold three values into one result.
# Recognized so they are named in a specific warning rather than a generic one.
_WIDE_DI_COLUMNS = {
    "DI a H2 (ppm)",
    "DI b H2 (ppm)",
    "DI c H2 (ppm)",
    "DI SD (ppm)",
}


@dataclass
class MasterUploadResult:
    """Master Results upload outcome.

    Exists because the legacy 5-tuple has no slot for warnings and ~20 tests
    plus the router unpack it positionally. `from_bytes` keeps returning the
    tuple; `from_bytes_ex` returns this.
    """

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    feedbacks: List[Dict[str, Any]] = field(default_factory=list)

    def as_tuple(self) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
        """Legacy 5-tuple shape. Warnings are dropped — callers that need them
        should use from_bytes_ex()."""
        return self.created, self.updated, self.skipped, self.errors, self.feedbacks


def _normalize_headers(columns: Any) -> List[str]:
    """Map sheet headers onto canonical names.

    A sheet can carry two spellings of one field — a hand-merged workbook with
    both 'DI avg H2 (ppm)' and 'DI H2 (ppm)', or 'H2 (ppm)' beside its v3
    replacement 'FL H2 (ppm)'. Renaming both to the canonical name would give
    pandas duplicate columns, and `row.get()` would then return a Series rather
    than a scalar; `_parse_float` raises on that and its `except Exception`
    swallows the value — the exact silent loss issue #111 exists to fix.

    Two rules prevent it:
      1. A column never takes a canonical name that another column in the same
         sheet already carries literally. The literal (v3) column wins and the
         aliased one keeps its raw header.
      2. Any remaining collision falls back to the raw header.
    """
    raw = [str(c).strip() for c in columns]
    raw_names = set(raw)
    out: List[str] = []
    seen: set[str] = set()
    for name in raw:
        canonical = _HEADER_ALIASES.get(name.lower(), name)
        if canonical != name and canonical in raw_names:
            canonical = name
        if canonical in seen:
            canonical = name
        out.append(canonical)
        seen.add(canonical)
    return out


def _parse_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    try:
        return float(val)
    except Exception:
        return None


def _parse_measurement_float(val: Any) -> Optional[float]:
    """Like _parse_float but also treats 0 as None.

    Used for pH and conductivity: the Excel template produces 0 (not NaN) for
    blank cells in these columns, so 0 is indistinguishable from a blank entry.
    A genuinely measured 0 for either field is not physically meaningful in our
    experimental context.
    """
    result = _parse_float(val)
    return None if result == 0.0 else result


def _parse_date(val: Any) -> Optional[dt.datetime]:
    if val is None:
        return None
    if pd.isna(val):  # catches NaN and NaT — NaT spoofs isinstance(dt.datetime) so must check first
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


def _resolve_h2(
    row: Any,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[str], Optional[float]]:
    """Pick the winning GC reading for one Dashboard row (issue #111).

    Full Loop takes precedence over direct injection (Mat, 2026-07-30); DI is
    used only when the Full Loop cell is blank. Gas volume and pressure are
    taken from the same block as the winning concentration, because
    _calculate_hydrogen() combines all three into h2_micromoles — pairing a
    Full Loop ppm with a DI sampling volume would compute a number that
    describes no real injection.

    A value of 0 is a real measurement and wins normally; only a blank cell
    falls through.

    Returns (h2_ppm, gas_volume_mL, gas_pressure_psi, source, di_ppm), where
    source is 'full_loop', 'di', or None when neither block has a
    concentration. di_ppm is this row's own DI parse, returned whether or not
    DI won — callers that need to know whether a DI reading was superseded
    read it from here rather than re-parsing the cell themselves, so that
    decision can never drift from the precedence choice made above.
    """
    di_ppm = _parse_float(row.get("DI H2 (ppm)"))

    fl_ppm = _parse_float(row.get("FL H2 (ppm)"))
    if fl_ppm is not None:
        return (
            fl_ppm,
            _parse_float(row.get("FL Gas Volume (mL)")),
            _parse_float(row.get("FL Gas Pressure (psi)")),
            "full_loop",
            di_ppm,
        )

    if di_ppm is not None:
        return (
            di_ppm,
            _parse_float(row.get("DI gas volume (mL)")),
            _parse_float(row.get("DI gas pressure (psi)")),
            "di",
            di_ppm,
        )

    # No concentration in either block. Keep reading the Full Loop gas columns
    # so a row recording only the sampling geometry behaves as it did pre-#111.
    return (
        None,
        _parse_float(row.get("FL Gas Volume (mL)")),
        _parse_float(row.get("FL Gas Pressure (psi)")),
        None,
        di_ppm,
    )


def _process_bytes(db: Session, file_bytes: bytes) -> MasterUploadResult:
    """
    Parse the Master Results Excel and upsert scalar results.
    """
    from backend.services.scalar_results_service import ScalarResultsService  # noqa: PLC0415

    out = MasterUploadResult()
    errors = out.errors
    warnings = out.warnings
    feedbacks = out.feedbacks
    created = updated = skipped = 0

    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception as exc:
        errors.append(f"Failed to read file: {exc}")
        return out

    sheet_name = _find_sheet(xls)
    if sheet_name is None:
        errors.append("File has no sheets.")
        return out

    try:
        df = xls.parse(sheet_name)
    except Exception as exc:
        errors.append(f"Failed to parse sheet '{sheet_name}': {exc}")
        return out

    df.columns = _normalize_headers(df.columns)

    # Validate required columns
    required = {"Experiment ID", "Duration (Days)"}
    missing = required - set(df.columns)
    if missing:
        errors.append(
            f"Sheet '{sheet_name}' is missing required columns: {', '.join(sorted(missing))}. "
            f"Available: {', '.join(df.columns[:10])}"
        )
        return out

    # Issue #111: an H2 column the parser cannot map used to vanish silently —
    # every other field upserted fine, so a sync looked healthy while the
    # hydrogen value was lost. Say so instead.
    stale_wide_di = [c for c in df.columns if c in _WIDE_DI_COLUMNS]
    if stale_wide_di:
        warnings.append(
            "Ignoring wide direct-injection column(s): "
            + ", ".join(f"'{c}'" for c in sorted(stale_wide_di))
            + ". Those letters are replicate vials — give each one row per "
              "experiment ID (e.g. SERUM_001a-t1, SERUM_001b-t1) and put its "
              "reading in 'DI H2 (ppm)'."
        )

    # Match H2 only as a standalone token. A substring test would also fire on
    # an H2S or H2O column, telling a researcher a hydrogen reading was dropped
    # when none was — a false alarm in exactly the place this warning is meant
    # to be trustworthy. A genuine rename keeps H2 as its own token
    # ('GC Loop H2 ppm'), so detection is unaffected.
    unmapped_h2 = [
        c for c in df.columns
        if _H2_TOKEN.search(c)
        and c not in _RECOGNIZED_H2_COLUMNS
        and c not in _WIDE_DI_COLUMNS
    ]
    if unmapped_h2:
        warnings.append(
            "Unrecognized H2 column(s) ignored: "
            + ", ".join(f"'{c}'" for c in unmapped_h2)
            + ". No hydrogen value was read from them — check the Dashboard "
              "headers against the parser's expected names."
        )

    if not _RECOGNIZED_H2_COLUMNS & set(df.columns):
        warnings.append(
            f"Sheet '{sheet_name}' has no recognized H2 column "
            "('FL H2 (ppm)' or 'DI H2 (ppm)') — no hydrogen data was ingested."
        )

    for idx, row in df.iterrows():
        row_num = idx + 2
        exp_id = str(row.get("Experiment ID") or "").strip()
        if not exp_id:
            skipped += 1
            continue

        # Skip calibration-standard rows (Issue #39)
        if "standard" in exp_id.lower():
            skipped += 1
            continue

        # Split the '-t<days>' token once, up front, so both the replicate
        # combination below and the Duration fill further down share a single
        # split (issue #81 I1/M-fix — do not re-split exp_id later).
        stem, id_timepoint = split_timepoint_token(exp_id)

        # Optional replicate column: resolve base + letter to the sibling ID
        # before anything downstream sees exp_id (issue #70 P3). A token ID
        # ("SERUM_001-t7") combined with a real Replicate letter is rejected —
        # the letter must be encoded in the ID itself (e.g. SERUM_001a-t7).
        try:
            combined = combine_replicate_id(
                stem if id_timepoint is not None else exp_id, row.get("Replicate"),
            )
            if id_timepoint is not None and combined != stem:
                raise ValueError(
                    "Replicate column cannot be combined with a -t<days> ID token; "
                    "encode the letter in the ID itself (e.g. SERUM_001a-t7)."
                )
            if id_timepoint is None:
                exp_id = combined
        except ValueError as exc:
            errors.append(f"Row {row_num} ({exp_id}): {exc}")
            continue

        # Issue #81: '-t<days>' in the experiment ID is canonical for the
        # timepoint — fill a blank Duration from it, error a conflict.
        # (id_timepoint already computed above.)

        duration_raw = row.get("Duration (Days)")
        if duration_raw is None or (isinstance(duration_raw, float) and pd.isna(duration_raw)):
            if id_timepoint is None:
                skipped += 1
                continue
            time_post_reaction = id_timepoint
        else:
            time_post_reaction = _parse_float(duration_raw)
            if time_post_reaction is None:
                errors.append(
                    f"Row {row_num}: invalid Duration (Days) '{duration_raw}'"
                )
                continue
            try:
                time_post_reaction = apply_id_timepoint(
                    id_timepoint, time_post_reaction,
                )
            except ValueError as exc:
                errors.append(f"Row {row_num} ({exp_id}): {exc}")
                continue

        description = str(row.get("Description") or "").strip() or None
        sample_date = _parse_date(row.get("Sample Date"))
        nmr_run_date = _parse_date(row.get("NMR Run Date"))
        icp_run_date = _parse_date(row.get("ICP Run Date"))
        gc_run_date = _parse_date(row.get("GC Run Date"))
        xrd_run_date = _parse_date(row.get("XRD Run Date"))

        nh4_mm = _parse_float(row.get("NH4 (mM)"))
        h2_ppm, gas_vol_ml, gas_psi, h2_source, di_ppm = _resolve_h2(row)
        gas_mpa = gas_psi * _PSI_TO_MPA if gas_psi is not None else None
        ph = _parse_measurement_float(row.get("Sample pH"))
        conductivity = _parse_measurement_float(row.get("Sample Conductivity (mS/cm)"))
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
            "xrd_run_date": xrd_run_date,
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
            feedbacks.append({
                "row": row_num,
                "experiment_id": exp_id,
                "action": action,
                "h2_source": h2_source,
                # di_ppm comes from _resolve_h2's own parse — re-reading the
                # cell here would let this flag drift from the precedence
                # decision if the DI branch ever gains filtering.
                "h2_di_superseded": h2_source == "full_loop" and di_ppm is not None,
            })

        except ValueError as exc:
            savepoint.rollback()
            errors.append(f"Row {row_num} ({exp_id}): {exc}")
        except Exception as exc:
            savepoint.rollback()
            errors.append(f"Row {row_num} ({exp_id}): unexpected error — {exc}")

    out.created, out.updated, out.skipped = created, updated, skipped
    return out


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

        return _process_bytes(db, file_bytes).as_tuple()

    @staticmethod
    def from_bytes(
        db: Session, file_bytes: bytes
    ) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
        """Parse a manually uploaded Master Results file.

        Legacy 5-tuple shape, kept for existing callers. Use from_bytes_ex()
        to also receive warnings.
        """
        return _process_bytes(db, file_bytes).as_tuple()

    @staticmethod
    def from_bytes_ex(db: Session, file_bytes: bytes) -> MasterUploadResult:
        """Parse a manually uploaded Master Results file, warnings included."""
        return _process_bytes(db, file_bytes)
