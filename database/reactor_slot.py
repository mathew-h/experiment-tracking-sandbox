"""Canonical reactor slot identity.

A physical reactor slot is a *pair*: the series (HPHT vessel vs. Core Flood rig)
and the number within it. `R01` and `CF01` are two different pieces of hardware
that happen to share the number 1. Before issue #97 that label was re-derived
from `(reactor_number, experiment_type == "Core Flood")` in three separate
places, and every occupancy query keyed on the bare integer — so setting a Core
Flood to ONGOING could auto-complete the HPHT sitting in R01.

This module is the ONLY definition of that mapping. It is imported by:
  - database/event_listeners.py  (keeps experimental_conditions.reactor_slot current)
  - backend/services/bulk_uploads/experiment_status.py
  - backend/services/bulk_uploads/new_experiments.py
  - backend/api/routers/experiments.py, dashboard.py
  - backend/services/notion_sync/import_.py

It deliberately imports nothing from `database.models` or `backend` so any layer
can use it. The Alembic backfill in
`alembic/versions/<rev>_add_reactor_slot_to_conditions.py` re-expresses these
rules in SQL; `tests/models/test_reactor_slot_column.py` pins the two together.

`derive_reactor_slot` returns None for anything that does not occupy a physical
slot. That is load-bearing: an occupancy query filtered on `reactor_slot` cannot
see a Serum vial even if the calling code forgot to check the type.
"""
from __future__ import annotations

import re

# Occupancy-bearing types only. Autoclave is deliberately absent — decided
# 2026-07-29 after the audit found AUTO_JW_022-024 carrying historical HPHT
# vessel numbers (all COMPLETED, so inert). If the team later confirms autoclave
# runs occupy the numbered vessels, add "autoclave": "R" here and to the
# dashboard's experiment_type filters; nothing else needs to change.
#
# Keys are the output of normalize_experiment_type, so every casing variant in
# production data (`SERUM`, `CF`, `Core  Flood`) resolves through one lookup.
_SERIES_BY_TYPE: dict[str, str] = {
    "hpht": "R",
    "core flood": "CF",
    "coreflood": "CF",
    "cf": "CF",
}

_SLOT_LABEL_RE = re.compile(r"(CF|R)0*(\d+)", re.IGNORECASE)


def normalize_experiment_type(experiment_type: object | None) -> str:
    """Lowercase + collapse whitespace so 'HPHT ', 'Core  Flood', 'SERUM' compare cleanly.

    Tolerates enum instances as well as strings: `experiment_type` is a String
    column, but the ID parser hands back `ExperimentType` members.
    """
    if experiment_type is None:
        return ""
    raw = experiment_type.value if hasattr(experiment_type, "value") else str(experiment_type)
    return " ".join(raw.strip().lower().split())


def series_prefix(experiment_type: object | None) -> str | None:
    """Return the slot-label prefix ('R' or 'CF') for a type, or None if it holds no slot."""
    return _SERIES_BY_TYPE.get(normalize_experiment_type(experiment_type))


def is_occupancy_type(experiment_type: object | None) -> bool:
    """True for HPHT / Core Flood — the types with physical reactor occupancy."""
    return series_prefix(experiment_type) is not None


def _format_slot(prefix: str, number: int) -> str | None:
    """Render a canonical slot label, or None if the number is not a slot.

    Zero and negatives are rejected here rather than at each call site so the
    guard and the padding width live in one place.
    """
    if number <= 0:
        return None
    return f"{prefix}{number:02d}"


def derive_reactor_slot(
    reactor_number: object | None,
    experiment_type: object | None,
) -> str | None:
    """Build the canonical slot label, or None when there is no slot.

    None is returned when: the type is not occupancy-bearing, the number is
    missing or unparseable, or the number is <= 0. Zero is not a slot — the eight
    `R00` rows in the 2026-07-28 prod audit exist only because `0` is falsy in
    Python and slipped past `if conditions.reactor_number`.
    """
    prefix = series_prefix(experiment_type)
    if prefix is None:
        return None
    if reactor_number is None:
        return None
    try:
        number = int(reactor_number)
    except (TypeError, ValueError):
        return None
    return _format_slot(prefix, number)


def canonical_slot_label(label: str | None) -> str | None:
    """Normalize an externally supplied label ('r5', 'CF1') to canonical form ('R05', 'CF01').

    Used on the Notion sync path, where the reactor label comes from a Notion
    page title and is not guaranteed to be zero-padded or upper-cased.
    """
    if not label:
        return None
    match = _SLOT_LABEL_RE.fullmatch(label.strip())
    if match is None:
        return None
    return _format_slot(match.group(1).upper(), int(match.group(2)))
