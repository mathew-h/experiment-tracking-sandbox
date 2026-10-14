"""Bulk-add 'modification' notes to existing result timepoints.

Issue #118 introduced the typed-note slot; issue #122 PR-D dropped the legacy
column this upload used to set, so a row writes only the note. The note's
`created_by` is this call's `modified_by`, which is also the slot key in
backend.services.notes.sync_result_note, so a researcher's hand-written
modification note on the same result is never overwritten by an upload.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Experiment, ExperimentalResults, ExperimentNotes, ModificationsLog
from database.models.enums import NoteType
from backend.services.notes import sync_result_note
from backend.services.result_merge_utils import find_timepoint_candidates
from backend.services.bulk_uploads._id_match import find_experiment_matches

# Column aliases accepted in the upload file
_EXPERIMENT_ID_ALIASES = {"experiment_id", "experiment id", "exp_id", "exp id"}
_TIME_POINT_ALIASES = {"time_point", "time (days)", "time(days)", "duration (days)", "days"}
_MODIFICATION_ALIASES = {
    "modification_description", "experiment_modification", "modification", "description",
    "modification note",  # Dashboard template v4 spelling (issue #118)
}
_OVERWRITE_ALIASES = {"overwrite_existing", "overwrite"}


def _resolve_col(columns: List[str], aliases: set[str]) -> Optional[str]:
    for c in columns:
        if c.strip().lower() in aliases:
            return c
    return None


def _parse_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in {"true", "yes", "1", "y"}
    return False


def _modification_notes(db: Session, result: ExperimentalResults) -> List[ExperimentNotes]:
    """Every 'modification' note scoped to this result, any author, id order."""
    return list(db.execute(
        select(ExperimentNotes)
        .where(ExperimentNotes.result_id == result.id, ExperimentNotes.note_type == NoteType.modification)
        .order_by(ExperimentNotes.id)
    ).scalars())


class TimepointModificationsService:
    @staticmethod
    def bulk_set_from_bytes(
        db: Session,
        file_bytes: bytes,
        overwrite_existing: bool = False,
        modified_by: str = "bulk_upload",
    ) -> Tuple[int, int, List[str], List[Dict[str, Any]]]:
        """
        Read an Excel/CSV file and set the 'modification' note on matching
        ExperimentalResults rows (one slot per modified_by).

        Returns (updated, skipped, errors, feedbacks).
        """
        updated = skipped = 0
        errors: List[str] = []
        feedbacks: List[Dict[str, Any]] = []

        # --- Load file -------------------------------------------------------
        try:
            if file_bytes[:2] in (b"PK", b"\xd0\xcf"):  # xlsx / xls
                df = pd.read_excel(io.BytesIO(file_bytes))
            else:
                df = pd.read_csv(io.BytesIO(file_bytes))
        except Exception as exc:
            try:
                df = pd.read_excel(io.BytesIO(file_bytes))
            except Exception:
                return 0, 0, [f"Failed to read file: {exc}"], []

        df.columns = [str(c).strip() for c in df.columns]
        cols = list(df.columns)

        exp_col = _resolve_col(cols, _EXPERIMENT_ID_ALIASES)
        tp_col = _resolve_col(cols, _TIME_POINT_ALIASES)
        mod_col = _resolve_col(cols, _MODIFICATION_ALIASES)
        ow_col = _resolve_col(cols, _OVERWRITE_ALIASES)

        missing = []
        if not exp_col:
            missing.append("experiment_id")
        if not tp_col:
            missing.append("time_point")
        if not mod_col:
            missing.append("modification_description")
        if missing:
            return 0, 0, [f"Missing required columns: {', '.join(missing)}"], []

        # --- Pre-scan for duplicates within the file -------------------------
        seen: set[tuple[str, float]] = set()
        duplicates: List[str] = []
        for idx, row in df.iterrows():
            exp_id = str(row.get(exp_col) or "").strip()
            tp_raw = row.get(tp_col)
            if not exp_id or tp_raw is None:
                continue
            try:
                tp = float(tp_raw)
            except Exception:
                continue
            key = (exp_id, tp)
            if key in seen:
                duplicates.append(f"Row {idx + 2}: duplicate ({exp_id}, {tp})")
            seen.add(key)

        if duplicates:
            return 0, 0, [
                "File contains duplicate (experiment_id, time_point) pairs. "
                "Resolve duplicates and re-upload.",
                *duplicates,
            ], []

        # --- Process rows ----------------------------------------------------
        for idx, row in df.iterrows():
            row_num = idx + 2  # 1-based, header on row 1
            exp_id = str(row.get(exp_col) or "").strip()
            tp_raw = row.get(tp_col)
            # pd.isna guard: pandas reads a blank cell as float('nan'), which is
            # truthy, so `str(cell or "")` stored the literal text 'nan' (the
            # same defect fix_nan_text_fields_019.py cleaned up for the Master
            # sheet). An overwrite row with a blank cell must CLEAR, not write
            # 'nan' -- and the typed-note mirror below must agree with it.
            _mod_raw = row.get(mod_col)
            if _mod_raw is None or (isinstance(_mod_raw, float) and pd.isna(_mod_raw)):
                modification = ""
            else:
                modification = str(_mod_raw).strip()

            if not exp_id:
                skipped += 1
                continue
            if tp_raw is None or (isinstance(tp_raw, float) and pd.isna(tp_raw)):
                skipped += 1
                continue
            try:
                tp = float(tp_raw)
            except Exception:
                errors.append(f"Row {row_num}: invalid time_point '{tp_raw}'")
                continue

            # Per-row overwrite flag (file column) takes precedence over global param
            row_overwrite = overwrite_existing
            if ow_col:
                ow_val = row.get(ow_col)
                if ow_val is not None and not (isinstance(ow_val, float) and pd.isna(ow_val)):
                    row_overwrite = _parse_bool(ow_val)

            # --- Resolve experiment (fuzzy: case-insensitive, symbols stripped) ---
            # All matches, not .first(): two stored IDs can share a normalized key,
            # and picking one silently attached the modification to the wrong
            # experiment. Name both so the researcher can use the exact ID.
            matches = find_experiment_matches(db, exp_id)
            if len(matches) > 1:
                candidates = ", ".join(sorted(e.experiment_id for e in matches))
                errors.append(
                    f"Row {row_num}: experiment '{exp_id}' is ambiguous - it matches "
                    f"{len(matches)} experiments: {candidates}. Use the exact experiment_id."
                )
                continue
            if not matches:
                errors.append(f"Row {row_num}: experiment '{exp_id}' not found")
                continue
            experiment = matches[0]
            canonical_exp_id = experiment.experiment_id

            # --- Find matching timepoint row ---
            candidates = find_timepoint_candidates(db, experiment.id, tp)
            if not candidates:
                errors.append(
                    f"Row {row_num}: no result row found for experiment='{canonical_exp_id}' "
                    f"time_point={tp}"
                )
                continue

            target: ExperimentalResults = candidates[0]

            # --- Overwrite guard: any existing modification note, any author ---
            existing_notes = _modification_notes(db, target)
            if existing_notes and not row_overwrite:
                skipped += 1
                feedbacks.append({
                    "row": row_num,
                    "experiment_id": canonical_exp_id,
                    "time_point": tp,
                    "status": "skipped",
                    "reason": "a modification note already exists on this timepoint; "
                              "pass overwrite_existing=true to write yours",
                })
                continue

            # --- Apply: this caller's own slot only; other authors' notes stay ---
            old_text = next((n.note_text for n in existing_notes if n.created_by == modified_by), None)
            new_text = modification or None
            sync_result_note(db, target, NoteType.modification, new_text, created_by=modified_by)

            db.add(ModificationsLog(
                experiment_id=canonical_exp_id,
                experiment_fk=experiment.id,
                modified_by=modified_by,
                modification_type="update",
                modified_table="experiment_notes",
                old_values={"result_id": target.id, "note_text": old_text},
                new_values={"result_id": target.id, "note_text": new_text},
            ))
            updated += 1
            feedbacks.append({
                "row": row_num,
                "experiment_id": canonical_exp_id,
                "time_point": tp,
                "status": "updated",
                "result_id": target.id,
            })

        return updated, skipped, errors, feedbacks

    @staticmethod
    def generate_template_bytes() -> bytes:
        """Return a downloadable Excel template for timepoint modifications."""
        import openpyxl  # noqa: PLC0415
        from openpyxl.styles import PatternFill, Font, Alignment  # noqa: PLC0415

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Template"

        headers = [
            "experiment_id",
            "time_point",
            "modification_description",
            "overwrite_existing",
        ]
        required = {"experiment_id", "time_point", "modification_description"}
        req_fill = PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid")
        opt_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")

        for col, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True)
            cell.fill = req_fill if h in required else opt_fill
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[cell.column_letter].width = 28

        # Example row
        ws.cell(row=2, column=1, value="HPHT_001")
        ws.cell(row=2, column=2, value=7.0)
        ws.cell(row=2, column=3, value="Added 5 g Mg(OH)2 after sampling")
        ws.cell(row=2, column=4, value="FALSE")

        # Instructions sheet
        instr = wb.create_sheet("INSTRUCTIONS")
        rows = [
            ["Timepoint Modifications — Upload Instructions"],
            [""],
            ["Column", "Required", "Description"],
            ["experiment_id", "Yes",
             "Experiment identifier (e.g. HPHT_001). Must exist in the database."],
            ["time_point", "Yes",
             "Time post-reaction in days (float). Matched with ±0.0001 day tolerance."],
            ["modification_description", "Yes",
             "Free text stored as a modification note on this timepoint (shows the MOD badge)."],
            ["overwrite_existing", "No",
             "Set TRUE to write your own note when a modification note by anyone already exists (other authors' notes are never changed). Default: FALSE."],
            [""],
            ["Notes:"],
            ["- Yellow headers are required. Green headers are optional."],
            ["- If the timepoint already has a modification note (by anyone),"],
            ["  the row is skipped unless overwrite_existing=TRUE; overwrite only"],
            ["  writes or replaces your own note, never someone else's."],
            ["- Duplicate (experiment_id, time_point) pairs in a single file are rejected."],
        ]
        for r in rows:
            instr.append(r)
        instr.column_dimensions["A"].width = 30
        instr.column_dimensions["B"].width = 12
        instr.column_dimensions["C"].width = 70

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
