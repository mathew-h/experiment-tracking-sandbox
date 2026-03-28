from __future__ import annotations

import io
import re
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Experiment
from database.models import XRDPhase


# Pattern: DATE_ExperimentID-dDAYS_SCAN
# e.g. 20260218_HPHT070-d19_02
_AERIS_SAMPLE_RE = re.compile(
    r"^(\d{8})_(.+?)-d(\d+)_\d+$"
)


def _parse_aeris_sample_id(raw: str) -> Optional[Tuple[datetime, str, int]]:
    """
    Extract (measurement_date, experiment_id_raw, days_post_reaction) from an
    Aeris-format Sample ID like ``20260218_HPHT070-d19_02``.

    Returns None if the string doesn't match.
    """
    m = _AERIS_SAMPLE_RE.match(raw.strip())
    if not m:
        return None
    date_str, exp_id_raw, days_str = m.groups()
    try:
        measurement_date = datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        return None
    return measurement_date, exp_id_raw, int(days_str)


def _normalize_id(raw: str) -> str:
    """Strip delimiters and lowercase for fuzzy experiment-ID matching."""
    return "".join(ch for ch in raw.lower() if ch not in ("-", "_", " "))


def _find_experiment(db: Session, exp_id_raw: str) -> Optional[Experiment]:
    """
    Look up an Experiment using delimiter-insensitive matching so that
    ``HPHT070`` resolves to ``HPHT_070`` etc.
    """
    norm = _normalize_id(exp_id_raw)
    return (
        db.query(Experiment)
        .filter(
            func.lower(
                func.replace(
                    func.replace(
                        func.replace(Experiment.experiment_id, "-", ""),
                        "_", "",
                    ),
                    " ", "",
                )
            )
            == norm
        )
        .first()
    )


def _clean_mineral_name(col: str) -> str:
    """Strip trailing ``[%]`` or ``(%)`` and whitespace from a column header."""
    col = re.sub(r"\s*[\[\(]%[\]\)]\s*$", "", col)
    return col.strip()


class AerisXRDUploadService:
    """Bulk-upload handler for Aeris XRD time-series mineral-phase data."""

    @staticmethod
    def bulk_upsert_from_excel(
        db: Session, file_bytes: bytes, overwrite: bool = False
    ) -> Tuple[int, int, int, List[str]]:
        """
        Parse an Aeris XRD Excel file and upsert ``XRDPhase`` rows keyed by
        (experiment_id, time_post_reaction_days, mineral_name).

        When overwrite=False: upserts XRDPhase rows keyed on
        (experiment_id, time_post_reaction_days, mineral_name).
        When overwrite=True: deletes ALL existing XRDPhase rows for each
        (experiment_id, time_post_reaction_days) key before inserting the new
        set, so only the uploaded phases survive.

        Returns (created, updated, skipped, errors).
        """
        created = updated = skipped = 0
        errors: List[str] = []

        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return 0, 0, 0, [f"Failed to read Excel: {e}"]

        if df.shape[1] < 3:
            return 0, 0, 0, [
                "Excel must contain at least Sample ID, Rwp, "
                "and one mineral column."
            ]

        cols = [str(c).strip() for c in df.columns]
        df.columns = cols

        # Identify fixed columns (case-insensitive)
        col_lower = {c.lower(): c for c in cols}
        sample_col = col_lower.get("sample id") or col_lower.get("sample_id")
        rwp_col = col_lower.get("rwp")

        if not sample_col:
            return 0, 0, 0, ["Could not find a 'Sample ID' column."]

        skip_cols = {
            (sample_col or "").lower(),
            (rwp_col or "").lower(),
            "scan number",
            "scan_number",
        }
        mineral_cols = [c for c in cols if c.lower() not in skip_cols]
        if not mineral_cols:
            return 0, 0, 0, ["No mineral-phase columns detected."]

        # Cache experiment lookups per raw ID to avoid repeated queries
        exp_cache: dict[str, Optional[Experiment]] = {}
        # Track (experiment_id, days) pairs already cleared in overwrite mode
        cleared_keys: set[tuple[str, float]] = set()

        for idx, row in df.iterrows():
            row_num = idx + 2  # 1-indexed header + 1-indexed row
            raw_sample = str(row.get(sample_col, "")).strip()
            if not raw_sample:
                skipped += 1
                continue

            parsed = _parse_aeris_sample_id(raw_sample)
            if parsed is None:
                errors.append(
                    f"Row {row_num}: Sample ID '{raw_sample}' does not match "
                    f"expected format DATE_ExperimentID-dDAYS_SCAN "
                    f"(e.g. 20260218_HPHT070-d19_02)."
                )
                continue

            measurement_date, exp_id_raw, days = parsed

            # Resolve experiment (with cache)
            if exp_id_raw not in exp_cache:
                exp_cache[exp_id_raw] = _find_experiment(db, exp_id_raw)
            experiment = exp_cache[exp_id_raw]

            if experiment is None:
                errors.append(
                    f"Row {row_num}: Experiment '{exp_id_raw}' not found in "
                    f"database (tried delimiter-insensitive match)."
                )
                continue

            exp_id_db = experiment.experiment_id
            exp_fk = experiment.id

            # Parse Rwp
            rwp_val: Optional[float] = None
            if rwp_col:
                raw_rwp = row.get(rwp_col)
                try:
                    if raw_rwp is not None and not (
                        isinstance(raw_rwp, float) and pd.isna(raw_rwp)
                    ):
                        rwp_val = float(raw_rwp)
                except (ValueError, TypeError):
                    pass

            # When overwrite=True, delete all existing phases for this
            # (experiment, timepoint) once per unique key within this file
            # before inserting the new set.
            if overwrite:
                clear_key = (exp_id_db, float(days))
                if clear_key not in cleared_keys:
                    (
                        db.query(XRDPhase)
                        .filter(
                            XRDPhase.experiment_id == exp_id_db,
                            XRDPhase.time_post_reaction_days == days,
                        )
                        .delete(synchronize_session=False)
                    )
                    db.flush()
                    cleared_keys.add(clear_key)

            # Upsert one XRDPhase per mineral column
            for mcol in mineral_cols:
                raw_val = row.get(mcol)
                try:
                    if raw_val is None or (
                        isinstance(raw_val, float) and pd.isna(raw_val)
                    ):
                        continue
                    amount_val = float(raw_val)
                except (ValueError, TypeError):
                    continue

                mineral_name = _clean_mineral_name(mcol)

                if overwrite:
                    db.add(XRDPhase(
                        experiment_fk=exp_fk,
                        experiment_id=exp_id_db,
                        time_post_reaction_days=days,
                        mineral_name=mineral_name,
                        amount=amount_val,
                        rwp=rwp_val,
                        measurement_date=measurement_date,
                    ))
                    created += 1
                else:
                    phase = (
                        db.query(XRDPhase)
                        .filter(
                            XRDPhase.experiment_id == exp_id_db,
                            XRDPhase.time_post_reaction_days == days,
                            XRDPhase.mineral_name == mineral_name,
                        )
                        .first()
                    )
                    if phase:
                        phase.amount = amount_val
                        phase.rwp = rwp_val
                        phase.measurement_date = measurement_date
                        phase.experiment_fk = exp_fk
                        updated += 1
                    else:
                        db.add(XRDPhase(
                            experiment_fk=exp_fk,
                            experiment_id=exp_id_db,
                            time_post_reaction_days=days,
                            measurement_date=measurement_date,
                            rwp=rwp_val,
                            mineral_name=mineral_name,
                            amount=amount_val,
                        ))
                        created += 1

        return created, updated, skipped, errors
