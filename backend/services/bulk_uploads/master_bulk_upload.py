"""
Master Results bulk upload — parses an uploaded Dashboard workbook.

Dashboard sheet column spec (v3, issue #111, 2026-07-30):
  Experiment ID | Description | Sample Date | Duration (Days) | NH4 (mM) |
  FL H2 (ppm)   | FL Gas Volume (mL) | FL Gas Pressure (psi) | Sample pH |
  Sample Conductivity (mS/cm) | Modification | NMR Run Date |
  Sampled Solution Volume (mL) | ICP Run Date | GC Run Date | XRD Run Date |
  OVERWRITE | DI H2 (ppm) | DI gas volume (mL) | DI gas pressure (psi)

One row per unique experiment ID. Replicate letters are separate vials, so
SERUM_001a/b/c at days 1 and 3 is six rows (SERUM_001a-t1, SERUM_001b-t1, ...),
not two rows with per-letter columns. Two rows sharing an ID and timepoint are
both rejected. Cross-replicate mean and SD are computed by
v_results_scalar_rollup, not carried on the sheet.

Hydrogen: Full Loop wins; 'DI H2 (ppm)' is used only when the Full Loop cell is
blank, and gas volume/pressure come from the same block. A value of 0 is a real
reading, not a blank. A row with no reading in either block stores no gas
geometry either — those columns carry stale values from previous runs.

Older spellings are still accepted — the pre-rename 'H2 (ppm)', 'Gas Volume
(mL)', 'Gas Pressure (psi)', 'Overwrite', and v2's 'DI avg H2 (ppm)'. v2's wide
'DI a/b/c H2 (ppm)' and 'DI SD (ppm)' are ignored with a warning. See
_HEADER_ALIASES.
"""
from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from backend.services.bulk_uploads._id_match import normalize_id
from backend.services.bulk_uploads.replicate_routing import combine_replicate_id
from backend.services.result_merge_utils import (
    TIMEPOINT_TOLERANCE_DAYS,
    normalize_timepoint,
)
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


@dataclass(frozen=True)
class TimepointCheck:
    """Outcome of comparing a row's Duration cell against its ID's -t token.

    `compared` is False when no comparison was possible — the ID carries no
    '-t<days>' token, or the Duration cell is blank (in which case the token
    simply supplies the day). It is the denominator of the file-level
    disagreement warning, which must count rows that could disagree rather
    than every row in the sheet.
    """

    compared: bool
    disagrees: bool


_NO_TIMEPOINT_CHECK = TimepointCheck(compared=False, disagrees=False)


@dataclass
class MasterUploadResult:
    """Master Results upload outcome.

    The one return shape. Issue #111 introduced it beside a legacy 5-tuple that
    had no slot for `warnings`; issue #114 deleted the tuple and the two entry
    points that produced it, since anything wired to them would compute warnings
    and drop them on the floor.
    """

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    feedbacks: List[Dict[str, Any]] = field(default_factory=list)


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
    concentration — in which case the geometry is None too, since the gas
    columns carry the previous run's values. di_ppm is this row's own DI parse,
    returned whether or not DI won — callers that need to know whether a DI
    reading was superseded read it from here rather than re-parsing the cell
    themselves, so that decision can never drift from the precedence choice
    made above.
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

    # No concentration in either block, so no geometry either (issue #114). The
    # pre-#111 allowance here kept the Full Loop gas columns so a row recording
    # only sampling geometry behaved as it always had. That assumed a blank gas
    # cell meant no data; carryover is now a permanent condition of the GC sheets
    # and 'H2 (ppm)' is the field of record (Mat, 2026-07-30), so those columns
    # hold a previous run's values on 207 of 499 rows. Nothing was computed from
    # them — _calculate_hydrogen needs a concentration — but persisting them put
    # a 4235 mL volume in ScalarResults that no later reader could tell from a
    # real measurement.
    return (None, None, None, None, di_ppm)


def _is_blank_duration(val: Any) -> bool:
    """True when the Duration cell carries no timepoint at all.

    A blank Duration is how a researcher defers to the '-t<days>' token in the
    experiment ID, so what counts as "blank" has to match what the spreadsheet
    can actually produce. The Dashboard's Duration column is a formula mirroring
    the Sampling sheet, whose own formula is
    `=IF(ISBLANK([Date Started]), " ", D-C)` — so an undated row arrives as a
    **single space**, not as an empty cell. Treating that as a number produced
    `invalid Duration (Days) ' '` on every row of a sheet whose timepoints were
    deliberately left blank.

    An empty string is included for the same reason: a formula returning `""`
    is the other common way Excel expresses "nothing here".
    """
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    if isinstance(val, str) and not val.strip():
        return True
    return False


def _resolve_row_identity(
    row: Any, row_num: int
) -> Tuple[Optional[str], Optional[float], Optional[str], bool, TimepointCheck]:
    """Resolve one Dashboard row to its (experiment_id, timepoint).

    Extracted from the upsert loop so the duplicate pre-pass and the loop share
    one implementation (issue #111).

    Returns (experiment_id, time_post_reaction, error_message, skip, check):
      * skip=True      — intentionally passed over; count toward `skipped`
      * error_message  — per-row error; count toward `errors`
      * check          — whether this row's Duration could be compared against
                         a '-t<days>' token and whether it disagreed. The row
                         still uploads either way; the caller aggregates these
                         into one file-level warning.
      * error None / skip False — a good row
    """
    raw_id = row.get("Experiment ID")
    # A numeric 0 in this column is a stale/blank Excel formula cache, never a
    # real experiment ID (e.g. Master_Results_Tracker_v3.xlsx reads 0.0 here on
    # all 499 rows) — skip it the same as None/NaN/empty string.
    if (raw_id is None
            or (isinstance(raw_id, float) and pd.isna(raw_id))
            or (isinstance(raw_id, (int, float)) and raw_id == 0)):
        return None, None, None, True, _NO_TIMEPOINT_CHECK
    exp_id = str(raw_id).strip()
    if not exp_id:
        return None, None, None, True, _NO_TIMEPOINT_CHECK

    # Skip calibration-standard rows (Issue #39)
    if "standard" in exp_id.lower():
        return None, None, None, True, _NO_TIMEPOINT_CHECK

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
        return (
            exp_id,
            None,
            f"Row {row_num} ({exp_id}): {exc}",
            False,
            _NO_TIMEPOINT_CHECK,
        )

    # Issue #81: '-t<days>' in the experiment ID is canonical for the
    # timepoint — fill a blank Duration from it, error a conflict.
    duration_raw = row.get("Duration (Days)")
    if _is_blank_duration(duration_raw):
        if id_timepoint is None:
            return exp_id, None, None, True, _NO_TIMEPOINT_CHECK
        return exp_id, id_timepoint, None, False, _NO_TIMEPOINT_CHECK

    time_post_reaction = _parse_float(duration_raw)
    if time_post_reaction is None:
        return (
            exp_id, None,
            f"Row {row_num}: invalid Duration (Days) '{duration_raw}'",
            False, _NO_TIMEPOINT_CHECK,
        )

    # The '-t<days>' token defines the vial's elapsed days (Mat, 2026-07-30), so
    # it wins outright — a disagreeing Duration is reported, not rejected. This
    # deliberately differs from POST /api/results, which still 400s on a
    # conflict via apply_id_timepoint: a hand-entered result has one author to
    # correct, whereas the Duration column here is a formula derived from
    # sampling dates, and letting it veto the ID would reject a whole sheet's
    # readings over provenance the ID already settles.
    check = _NO_TIMEPOINT_CHECK
    if id_timepoint is not None:
        check = TimepointCheck(
            compared=True,
            disagrees=abs(time_post_reaction - id_timepoint) > TIMEPOINT_TOLERANCE_DAYS,
        )
        time_post_reaction = id_timepoint

    return exp_id, time_post_reaction, None, False, check


def _process_bytes(db: Session, file_bytes: bytes) -> MasterUploadResult:
    """
    Parse the Master Results Excel and upsert scalar results.
    """
    from backend.services.scalar_results_service import ScalarResultsService  # noqa: PLC0415

    out = MasterUploadResult()
    sheet_errors = out.errors
    warnings = out.warnings
    feedbacks = out.feedbacks
    created = updated = skipped = 0

    # Row-level errors carry their sheet row number and are sorted in at the end
    # (issue #114 item 3). This function is two-phase by necessity — identity and
    # duplicate tallying for every row, then the upserts — so appending straight
    # to out.errors listed every Phase-1 error above every Phase-2 one: a row 5
    # Duration error above a row 2 upsert failure, while researchers read this
    # list against the sheet top-down. Sheet-level messages have no row number
    # and belong at the top; every one of them returns immediately, so
    # out.errors is empty by the time the sort runs, and extending rather than
    # assigning keeps them first if a non-returning one is ever added.
    # Every warning is now file-level: the per-row Duration-vs-token warning was
    # aggregated into a single coverage line at the end of this function, so the
    # ordering hazard that applied to row-level warnings no longer exists. A
    # future per-row warning would need the same row-number sorting the errors
    # get below.
    row_errors: List[Tuple[int, str]] = []

    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception as exc:
        sheet_errors.append(f"Failed to read file: {exc}")
        return out

    sheet_name = _find_sheet(xls)
    if sheet_name is None:
        sheet_errors.append("File has no sheets.")
        return out

    try:
        df = xls.parse(sheet_name)
    except Exception as exc:
        sheet_errors.append(f"Failed to parse sheet '{sheet_name}': {exc}")
        return out

    df.columns = _normalize_headers(df.columns)

    # Validate required columns
    required = {"Experiment ID", "Duration (Days)"}
    missing = required - set(df.columns)
    if missing:
        sheet_errors.append(
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
            + ", ".join(f"'{c}'" for c in sorted(unmapped_h2))
            + ". No hydrogen value was read from them — check the Dashboard "
              "headers against the parser's expected names."
        )

    if not _RECOGNIZED_H2_COLUMNS & set(df.columns):
        warnings.append(
            f"Sheet '{sheet_name}' has no recognized H2 column "
            "('FL H2 (ppm)' or 'DI H2 (ppm)') — no hydrogen data was ingested."
        )

    # Phase 1 — resolve every row's identity, then find collisions. v3 is one
    # row per unique experiment ID (issue #111): two rows claiming the same
    # vial at the same day are two readings fighting over one timepoint, and
    # letting the later one win would destroy the earlier silently. Both are
    # rejected. A collision is only discoverable once the LATER row has been
    # read, by which point the earlier row has already been flushed, counted
    # and given a feedback record — hence a pre-pass rather than an in-loop
    # check. (The upload commits once, at the endpoint, via _finalize_write.)
    resolved: List[Tuple[int, str, float, Any]] = []
    # Denominators for the file-level disagreement warning below. Counted here
    # rather than warned per row: the Duration column is a formula off the
    # Sampling sheet and drifts wholesale, so 109 of 202 rows disagreed on the
    # team's v3 workbook (2026-08-07) — one line each buried every other
    # warning in the upload panel.
    comparable_rows = 0
    disagreement_rows: List[int] = []
    for idx, row in df.iterrows():
        row_num = idx + 2
        exp_id, time_post_reaction, error, skip, check = _resolve_row_identity(
            row, row_num
        )
        if check.compared:
            comparable_rows += 1
            if check.disagrees:
                disagreement_rows.append(row_num)
        if skip:
            skipped += 1
            continue
        if error is not None:
            row_errors.append((row_num, error))
            continue
        resolved.append((row_num, exp_id, time_post_reaction, row))

    # Keyed on the normalized ID, not the raw string: `_id_match.normalize_id`
    # is what the DB lookup resolves through, so two spellings that differ only
    # by case or zero padding ('SERUM_cation_001c-t5' vs 'SERUM_Cation_001c-t5')
    # name ONE stored experiment. Keying on the raw string let both rows pass
    # this guard and both upsert onto that one experiment — the later row
    # silently overwriting the earlier, which is precisely what the guard
    # exists to prevent. Three such pairs were live in the team's v3 workbook
    # (2026-08-07). The converse risk — two genuinely different experiments
    # whose IDs differ only by case/padding, each with its own sheet row, now
    # being rejected as a false duplicate — was accepted (Mat, 2026-08-07):
    # 0 of 1009 dev-DB experiments share a normalized key, and a loud stop
    # beats the silent overwrite it replaces.
    #
    # Keyed on the normalized (rounded) timepoint so 7.0 and 7.00005 — which
    # `find_timepoint_candidates` would merge into the same result row anyway
    # — collide here too. This narrows the gap but does not close it:
    # normalization only rounds to 4 decimals, so two values on opposite sides
    # of a rounding boundary (e.g. 7.00004 and 7.00006) still key differently
    # even though they fall within the ±1e-4 tolerance of each other.
    dup_groups: Dict[Tuple[str, float], List[Tuple[int, str]]] = {}
    for row_num, exp_id, time_post_reaction, _row in resolved:
        key = (normalize_id(exp_id), normalize_timepoint(time_post_reaction))
        dup_groups.setdefault(key, []).append((row_num, exp_id))

    # One error per collision, not per row. Each names every row in the group,
    # so a researcher reading this list against the sheet is told where the
    # partner reading is instead of having to search for it — the same reason
    # an ambiguous ID names both candidates. Anchored at the group's first row
    # so the sort at the end of this function keeps the list in sheet order.
    duplicate_rows: set[int] = set()
    for (_norm_id, day), members in dup_groups.items():
        if len(members) < 2:
            continue
        duplicate_rows.update(row_num for row_num, _ in members)
        rows_text = ", ".join(str(row_num) for row_num, _ in members)
        # dict.fromkeys keeps sheet order while dropping repeats.
        spellings = list(dict.fromkeys(exp_id for _, exp_id in members))
        # Differing spellings collided on the normalized key, which is not
        # visible from the cells themselves — say so, or the researcher
        # searches the sheet for a string only one of the rows contains.
        variant_clause = (
            " These spellings differ but resolve to one experiment, so one "
            "reading would have silently overwritten the other."
            if len(spellings) > 1 else ""
        )
        row_errors.append((members[0][0], (
            f"Rows {rows_text} ({', '.join(spellings)}): duplicate experiment "
            f"ID and timepoint (day {day:g}).{variant_clause} Each vial gets "
            f"one row per timepoint — give each vial its own ID (e.g. "
            f"SERUM_001a-t7, SERUM_001b-t7). No row for this vial-day was "
            f"written."
        )))

    # Phase 2 — upsert what is left.
    # Rows where Full Loop overrode a populated direct-injection cell. Reported
    # once, at file level, after the loop (issue #114 item 1).
    superseded_rows: List[int] = []
    # Rows whose H2 reading landed with no GC Run Date (issue #115).
    missing_gc_date_rows: List[int] = []
    # Denominator for the coverage warning below: rows actually written that
    # carried an H2 reading (missing_gc_date_rows is the numerator).
    h2_reading_rows = 0
    for row_num, exp_id, time_post_reaction, row in resolved:
        # The error was already emitted once for the whole group above.
        if row_num in duplicate_rows:
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
        }
        # Issue #116: declare the fields this sheet has columns for, so an
        # OVERWRITE row can clear one it carries and left blank without nulling
        # the eight SCALAR_UPDATABLE_FIELDS entries the Dashboard never carries
        # (background ammonium, quant method, nitrate, alkalinity, CO2 partial
        # pressure, dissolved oxygen, background experiment ID, ferrous iron
        # yield) -- all UI-entered, by someone other than whoever runs the
        # upload. Derived from the literal above rather than restated, so adding
        # a column here cannot silently leave the new field unclearable.
        sheet_fields = frozenset(result_data)

        # Remove None-valued optional fields so the service skips them.
        # Underscore-prefixed control keys are directives, not data, and are
        # kept regardless of value.
        result_data["_overwrite"] = overwrite
        result_data["_sheet_fields"] = sheet_fields
        result_data = {
            k: v for k, v in result_data.items()
            if v is not None or k.startswith("_")
        }

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
            # di_ppm comes from _resolve_h2's own parse — re-reading the cell
            # here would let this flag drift from the precedence decision if the
            # DI branch ever gains filtering.
            di_superseded = h2_source == "full_loop" and di_ppm is not None
            if di_superseded:
                superseded_rows.append(row_num)
            if h2_ppm is not None:
                h2_reading_rows += 1
                if gc_run_date is None:
                    missing_gc_date_rows.append(row_num)
            feedbacks.append({
                "row": row_num,
                "experiment_id": exp_id,
                "action": action,
                "h2_source": h2_source,
                "h2_di_superseded": di_superseded,
            })

        except ValueError as exc:
            savepoint.rollback()
            row_errors.append((row_num, f"Row {row_num} ({exp_id}): {exc}"))
        except Exception as exc:
            savepoint.rollback()
            row_errors.append((row_num, f"Row {row_num} ({exp_id}): unexpected error — {exc}"))

    # The per-row h2_di_superseded flag above reaches the client in `feedbacks`
    # and nothing renders it, so a researcher could not learn from the app why a
    # stored value is not the DI number they entered — and the discarded reading
    # is not persisted either. One file-level warning says it in the panel the UI
    # already draws (issue #114 item 1). Deliberately silent when precedence was
    # never contested: 0 of 499 rows on the v3 Dashboard (2026-07-30) carry a
    # reading in both blocks, and a warning that fires on ordinary sheets is one
    # researchers learn to ignore.
    if superseded_rows:
        shown = ", ".join(str(r) for r in superseded_rows[:10])
        if len(superseded_rows) > 10:
            shown += f", and {len(superseded_rows) - 10} more"
        label = "row" if len(superseded_rows) == 1 else "rows"
        warnings.append(
            f"Full Loop reading used instead of direct injection on "
            f"{len(superseded_rows)} {label} ({shown}). 'DI H2 (ppm)' also held a "
            "value there and Full Loop takes precedence, so the direct-injection "
            "reading was not stored and cannot be recovered from the database."
        )

    # A missing or unreadable GC Run Date fails silently in every direction: the
    # H2 reading is stored, no error is raised, and nothing in the app renders
    # the field -- so the Dashboard's GC Measurements card (issue #85) just
    # stops counting the row. That is issue #115: 115 of 1056 dev-DB scalar
    # rows carry a GC run date and every one falls in Mar-May 2026, while H2
    # readings kept arriving through July. Gated on an H2 reading being
    # present, so a row that did no GC work stays quiet. This WILL fire on
    # most uploads until the column is filled in again -- that is the intended
    # signal, not noise to soften.
    #
    # The gate (h2_ppm is not None and gc_run_date is None) is a fact about the
    # SHEET CELL, not the stored row: on the non-overwrite path a blank cell is
    # stripped before the service call (the "Remove None-valued optional
    # fields" comprehension above) and an existing stored gc_run_date is left
    # untouched, so the wording below never claims the row goes uncounted --
    # only that no date was supplied on this upload.
    #
    # Reported as coverage (n of total), not a full row list: on a real upload
    # this is the ~128-row production path, not a corner case, so naming every
    # row would be exactly the noise this file otherwise avoids. Individual
    # rows are still named when there are few enough (<=10) to be a useful
    # lookup, matching the #114 supersede warning's threshold above.
    if missing_gc_date_rows:
        n = len(missing_gc_date_rows)
        total = h2_reading_rows
        if n <= 10:
            where = " (" + ", ".join(str(r) for r in missing_gc_date_rows) + ")"
        else:
            where = ""
        label = "row" if total == 1 else "rows"
        stored_clause = (
            "The reading was stored, but this upload supplied no run date for it."
            if n == 1
            else "The readings were stored, but this upload supplied no run date for them."
        )
        warnings.append(
            f"'GC Run Date' is missing or unreadable on {n} of {total} {label} "
            f"carrying an H2 reading{where}. {stored_clause} "
            "The Dashboard's 'GC Measurements' card counts GC "
            "Run Date entries falling in the last 7 workdays, so backfilling "
            "an older date will not make a row appear there — only dates "
            "entered going forward will count."
        )

    # One line, not 109. The Dashboard's Duration column is a formula derived
    # from sampling dates and has drifted from the '-t<days>' tokens wholesale
    # -- 109 of 202 comparable rows disagreed on the team's v3 workbook
    # (2026-08-07). The ID wins either way (Mat, 2026-07-30) so no row is
    # rejected, which is exactly why this must stay visible without drowning
    # the other warnings. Row list only at <=10, matching the supersede and
    # GC-date warnings above.
    if disagreement_rows:
        n = len(disagreement_rows)
        label = "row" if comparable_rows == 1 else "rows"
        where = (
            " (" + ", ".join(str(r) for r in disagreement_rows) + ")"
            if n <= 10 else ""
        )
        warnings.append(
            f"Duration (Days) disagrees with the ID's -t token on {n} of "
            f"{comparable_rows} {label}{where}. The ID is canonical, so each "
            "reading was recorded at the day its ID encodes and the Duration "
            "value was not used. That column is a formula derived from sampling "
            "dates -- a disagreement on many rows means the formula no longer "
            "tracks the vials' intended days."
        )

    # Stable sort — two errors on one row keep the order they were found in.
    out.errors.extend(message for _, message in sorted(row_errors, key=lambda item: item[0]))

    out.created, out.updated, out.skipped = created, updated, skipped
    return out


class MasterBulkUploadService:
    @staticmethod
    def from_bytes_ex(db: Session, file_bytes: bytes) -> MasterUploadResult:
        """Parse an uploaded Master Results file.

        The only entry point. `POST /api/bulk-uploads/master-results` requires a
        multipart file (issue #74 removed path-based sync along with the
        /master-results/config endpoints and the sync button), so there is no
        second way in.
        """
        return _process_bytes(db, file_bytes)
