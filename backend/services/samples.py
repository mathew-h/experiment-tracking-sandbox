"""Sample-related service functions for pXRF reading normalization and data lookups."""
from __future__ import annotations

import re
import structlog
from sqlalchemy.orm import Session

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
