from __future__ import annotations

import io
from typing import List, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from database import SampleInfo, ExternalAnalysis, XRDAnalysis
from database.models import XRDPhase


class XRDUploadService:
    @staticmethod
    def bulk_upsert_from_excel(db: Session, file_bytes: bytes) -> Tuple[int, int, int, int, int, int, int, List[str]]:
        """
        Upsert XRD mineralogy per sample from an Excel file.
        Returns (
          created_ext, updated_ext, created_json, updated_json, created_phase, updated_phase, skipped_rows, errors
        ).
        """
        created_ext = updated_ext = created_json = updated_json = created_phase = updated_phase = skipped = 0
        errors: List[str] = []

        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return 0, 0, 0, 0, 0, 0, 0, [f"Failed to read Excel: {e}"]

        if df.shape[1] < 2:
            return 0, 0, 0, 0, 0, 0, 0, ["Template must include 'sample_id' and at least one mineral column."]

        normalized = [str(c).strip() for c in df.columns]
        df.columns = normalized

        # Resolve sample_id column (case-insensitive match)
        sample_col = None
        for c in df.columns:
            if c.lower() == "sample_id":
                sample_col = c
                break
        if not sample_col:
            return 0, 0, 0, 0, 0, 0, 0, ["First column must be 'sample_id'."]

        mineral_cols = [c for c in df.columns if c != sample_col]
        if not mineral_cols:
            return 0, 0, 0, 0, 0, 0, 0, ["No mineral columns detected."]

        for idx, row in df.iterrows():
            try:
                sample_id = str(row.get(sample_col) or '').strip()
                if not sample_id:
                    skipped += 1
                    continue

                # Validate sample exists
                sample = db.query(SampleInfo).filter(SampleInfo.sample_id == sample_id).first()
                if not sample:
                    errors.append(f"Row {idx+2}: sample_id '{sample_id}' not found")
                    continue

                # Build mineral dict from columns, skipping blanks and non-numeric
                mineral_data = {}
                for mcol in mineral_cols:
                    val = row.get(mcol)
                    try:
                        if val is None or (isinstance(val, float) and pd.isna(val)):
                            continue
                        fval = float(val)
                    except Exception:
                        continue
                    mineral_data[mcol.strip().lower()] = fval

                # Find or create ExternalAnalysis for this sample/type
                ext = (
                    db.query(ExternalAnalysis)
                    .filter(
                        ExternalAnalysis.sample_id == sample_id,
                        ExternalAnalysis.analysis_type == "XRD",
                    )
                    .first()
                )
                if not ext:
                    ext = ExternalAnalysis(sample_id=sample_id, analysis_type="XRD")
                    db.add(ext)
                    db.flush()
                    created_ext += 1
                else:
                    updated_ext += 1

                # Upsert JSON model
                xrd = db.query(XRDAnalysis).filter(XRDAnalysis.external_analysis_id == ext.id).first()
                if xrd:
                    xrd.mineral_phases = mineral_data or None
                    updated_json += 1
                else:
                    xrd = XRDAnalysis(external_analysis_id=ext.id, mineral_phases=mineral_data or None)
                    db.add(xrd)
                    created_json += 1

                # Upsert normalized phases per mineral
                for mcol in mineral_cols:
                    display_name = str(mcol).strip()
                    key = display_name.lower()
                    if key not in mineral_data:
                        continue
                    amount_val = mineral_data[key]

                    phase = (
                        db.query(XRDPhase)
                        .filter(
                            XRDPhase.sample_id == sample_id,
                            XRDPhase.mineral_name == display_name,
                        )
                        .first()
                    )
                    if phase:
                        phase.amount = amount_val
                        if phase.external_analysis_id is None:
                            phase.external_analysis_id = ext.id
                        updated_phase += 1
                    else:
                        phase = XRDPhase(
                            sample_id=sample_id,
                            external_analysis_id=ext.id,
                            mineral_name=display_name,
                            amount=amount_val,
                        )
                        db.add(phase)
                        created_phase += 1

            except Exception as e:
                errors.append(f"Row {idx+2}: {e}")

        return created_ext, updated_ext, created_json, updated_json, created_phase, updated_phase, skipped, errors


