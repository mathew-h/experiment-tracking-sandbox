"""Sample-related service functions for pXRF reading normalization and data lookups."""
from __future__ import annotations

import re

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.analysis import ExternalAnalysis, PXRFReading
from database.models.characterization import ElementalAnalysis
from database.models.enums import AnalysisType
from database.models.xrd import XRDAnalysis

log = structlog.get_logger(__name__)


def normalize_pxrf_reading_no(raw: str) -> str:
    """Normalize a pXRF reading number for consistent storage and lookup.

    Strips surrounding whitespace and converts integer-like floats
    (e.g. '1.0', '12.00') to plain integers to match legacy
    split_normalized_pxrf_readings behaviour.

    Args:
        raw: The raw pXRF reading number string.

    Returns:
        The normalized reading number as a string.

    Examples:
        >>> normalize_pxrf_reading_no("  42  ")
        "42"
        >>> normalize_pxrf_reading_no("1.0")
        "1"
        >>> normalize_pxrf_reading_no("ABC-01")
        "ABC-01"
    """
    v = raw.strip()
    if re.fullmatch(r"\d+\.0+", v):
        v = str(int(float(v)))
    return v


def evaluate_characterized(db: Session, sample_id: str) -> bool:
    """Return True if the sample meets at least one characterization criterion."""
    # 1. XRD type with a linked XRDAnalysis record
    has_xrd = db.execute(
        select(ExternalAnalysis.id)
        .join(XRDAnalysis, XRDAnalysis.external_analysis_id == ExternalAnalysis.id)
        .where(
            ExternalAnalysis.sample_id == sample_id,
            ExternalAnalysis.analysis_type == AnalysisType.XRD.value,
        )
        .limit(1)
    ).first() is not None
    if has_xrd:
        return True

    # 2. Elemental or Titration with at least one ElementalAnalysis row
    has_elemental = db.execute(
        select(ExternalAnalysis.id)
        .join(ElementalAnalysis, ElementalAnalysis.external_analysis_id == ExternalAnalysis.id)
        .where(
            ExternalAnalysis.sample_id == sample_id,
            ExternalAnalysis.analysis_type.in_(
                [AnalysisType.ELEMENTAL.value, AnalysisType.TITRATION.value]
            ),
        )
        .limit(1)
    ).first() is not None
    if has_elemental:
        return True

    # 3. pXRF linked to an existing PXRFReading row
    pxrf_readings = db.execute(
        select(ExternalAnalysis.pxrf_reading_no)
        .where(
            ExternalAnalysis.sample_id == sample_id,
            ExternalAnalysis.analysis_type == AnalysisType.PXRF.value,
            ExternalAnalysis.pxrf_reading_no.isnot(None),
        )
    ).scalars().all()
    for readings_str in pxrf_readings:
        for raw in readings_str.split(","):
            normalized = normalize_pxrf_reading_no(raw)
            if normalized and db.get(PXRFReading, normalized) is not None:
                return True

    return False


def log_sample_modification(
    db: Session,
    *,
    sample_id: str,
    modified_by: str,
    modification_type: str,
    modified_table: str,
    old_values: dict | None = None,
    new_values: dict | None = None,
) -> None:
    """Write a ModificationsLog entry for a sample-related change.

    NOTE: Requires ModificationsLog.sample_id column (added by Task 3 migration).
    Will fail if called before that migration is applied.
    """
    # lazy import to avoid circular dependency
    from database.models.experiments import ModificationsLog

    db.add(ModificationsLog(
        sample_id=sample_id,  # sample_id column added in Task 3 migration
        modified_by=modified_by,
        modification_type=modification_type,
        modified_table=modified_table,
        old_values=old_values or {},
        new_values=new_values or {},
    ))
