"""Unified XRD upload: auto-detects Aeris vs ActLabs format and routes accordingly."""
from __future__ import annotations

import io
import re
from typing import List, Tuple

import pandas as pd
from sqlalchemy.orm import Session

# Aeris Sample ID pattern: DATE_ExperimentID-dDAYS_SCAN
# e.g. 20260218_HPHT070-d19_02
_AERIS_SAMPLE_RE = re.compile(r"^\d{8}_.+?-d\d+_\d+$")


def _detect_format(file_bytes: bytes) -> str | None:
    """
    Inspect the first sheet of the file to detect XRD format.
    Returns 'aeris', 'actlabs', or None (unrecognised).
    """
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), nrows=6)
    except Exception:
        return None

    columns = [str(c).strip() for c in df.columns]

    # Find column whose header is 'sample_id' or 'sample id'
    sample_col = None
    for c in columns:
        if c.lower() in ("sample_id", "sample id"):
            sample_col = c
            break

    if sample_col is None:
        return None

    # Check first few non-empty values against Aeris regex
    for val in df[sample_col].dropna().head(5):
        if _AERIS_SAMPLE_RE.match(str(val).strip()):
            return "aeris"

    return "actlabs"


class XRDAutoDetectService:
    @staticmethod
    def upload(db: Session, file_bytes: bytes) -> Tuple[int, int, int, List[str]]:
        """
        Auto-detect XRD format (Aeris or ActLabs) and delegate to the
        appropriate parser.

        Returns (created, updated, skipped, errors).
        """
        fmt = _detect_format(file_bytes)

        if fmt == "aeris":
            from backend.services.bulk_uploads.aeris_xrd import AerisXRDUploadService  # noqa: PLC0415
            return AerisXRDUploadService.bulk_upsert_from_excel(db, file_bytes)

        if fmt == "actlabs":
            from backend.services.bulk_uploads.actlabs_xrd_report import XRDUploadService  # noqa: PLC0415
            # XRDUploadService returns 8-tuple; normalise to 4-tuple
            (
                created_ext, updated_ext,
                created_json, updated_json,
                created_phase, updated_phase,
                skipped, errors,
            ) = XRDUploadService.bulk_upsert_from_excel(db, file_bytes)
            # Expose phase counts (mineral phases) as the primary user-visible metric;
            # external analysis + JSON sub-records are implementation details.
            created = created_phase + created_ext
            updated = updated_phase + updated_ext
            return created, updated, skipped, errors

        return 0, 0, 0, [
            "Unable to detect XRD file format. "
            "Expected Aeris format (Sample ID values like '20260218_HPHT070-d19_02') "
            "or ActLabs format (first column 'sample_id' with plain sample identifiers)."
        ]

    @staticmethod
    def generate_template_bytes() -> bytes:
        """
        Return a downloadable ActLabs-format XRD template as Excel bytes.
        (Aeris files are instrument exports — no template needed for that format.)
        """
        import openpyxl  # noqa: PLC0415
        from openpyxl.styles import PatternFill, Font, Alignment  # noqa: PLC0415

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "XRD Template"

        headers = ["sample_id", "Quartz", "Calcite", "Dolomite", "Feldspar", "Pyrite", "Other"]
        req_fill = PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid")
        opt_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")

        for col, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True)
            cell.fill = req_fill if h == "sample_id" else opt_fill
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[cell.column_letter].width = 18

        # Example row
        ws.cell(row=2, column=1, value="S001")
        ws.cell(row=2, column=2, value=45.2)
        ws.cell(row=2, column=3, value=20.1)
        ws.cell(row=2, column=4, value=15.0)
        ws.cell(row=2, column=5, value=10.5)
        ws.cell(row=2, column=6, value=5.2)
        ws.cell(row=2, column=7, value=4.0)

        # Instructions
        instr = wb.create_sheet("INSTRUCTIONS")
        rows = [
            ["XRD Mineralogy Upload — Instructions"],
            [""],
            ["This template is for ActLabs-format XRD reports."],
            ["For Aeris instrument exports, upload the file directly — no template needed."],
            [""],
            ["Column", "Description"],
            ["sample_id (required)", "Must match an existing sample in the database."],
            ["[mineral name]",
             "Mineral weight percent (0–100). Add or remove columns as needed."],
            [""],
            ["Format auto-detection:"],
            ["  Aeris  — Sample ID column values match pattern YYYYMMDD_ExpID-dDAYS_SCAN"],
            ["  ActLabs — sample_id column with plain sample identifiers (e.g. S001)"],
            [""],
            ["Notes:"],
            ["- Leave cells blank for minerals not detected"],
            ["- Column headers become mineral phase names in the database"],
            ["- Replace example mineral columns with your actual phases"],
        ]
        for r in rows:
            instr.append(r)
        instr.column_dimensions["A"].width = 35
        instr.column_dimensions["B"].width = 60

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
