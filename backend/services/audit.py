"""JSON-safe values for ModificationsLog payloads (issue #190, D-08).

``old_values`` and ``new_values`` are JSONB columns, so every value written to
them must be something JSON can hold. This is the one conversion; every writer
of a ModificationsLog row must use it. See docs/working/decisions.md
(2026-11-13).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


def audit_jsonable(value: Any) -> Any:
    """Coerce one column value to something JSONB can hold.

    None, bool, int, float and str pass through. Dates, datetimes and pandas
    Timestamps become ISO strings; this check runs before the Enum check
    because a pandas Timestamp also has a ``.value`` attribute (its integer
    nanoseconds). An Enum member becomes its value. Anything else becomes
    ``str(value)``.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)


def audit_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """``audit_jsonable`` applied to every value of an old/new values mapping."""
    return {key: audit_jsonable(value) for key, value in values.items()}
