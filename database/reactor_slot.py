"""Canonical reactor slot identity.

A physical reactor slot is a *pair*: the series (HPHT vessel vs. Core Flood rig)
and the number within it. `R01` and `CF01` are two different pieces of hardware
that happen to share the number 1. Since issue #147 HPHT has two series: the
Yushen/Tan vessels `R01`-`R16` (the default) and the Parr vessels `P01`-`P06`,
chosen by `experimental_conditions.reactor_series = 'P'`. Before issue #97 that label was re-derived
from `(reactor_number, experiment_type == "Core Flood")` in three separate
places, and every occupancy query keyed on the bare integer — so setting a Core
Flood to ONGOING could auto-complete the HPHT sitting in R01.

This module is the ONLY definition of that mapping. It is imported by:
  - database/event_listeners.py  (keeps experimental_conditions.reactor_slot current)
  - backend/services/bulk_uploads/experiment_status.py
  - backend/services/bulk_uploads/new_experiments.py
  - backend/api/routers/experiments.py, conditions.py, dashboard.py

It deliberately imports nothing from `database.models` or `backend` so any layer
can use it. The Alembic backfill in
`alembic/versions/<rev>_add_reactor_slot_to_conditions.py` re-expresses these
rules in SQL (and the #147 migration adds the Parr series to the view);
`tests/models/test_reactor_slot_column.py` pins the two together.

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


# Non-default series an HPHT experiment may name in reactor_series. NULL means the
# type's default series above. The DB CHECK `ck_conditions_reactor_series` allows
# exactly these values; adding a series means a migration that widens it.
PARR_SERIES = "P"
_HPHT_SERIES = ("R", PARR_SERIES)
ALLOWED_REACTOR_SERIES = frozenset({PARR_SERIES})


def is_hpht_series(prefix: str | None) -> bool:
    """True for the HPHT slot prefixes ('R' Yushen/Tan, 'P' Parr)."""
    return prefix in _HPHT_SERIES


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


def reactor_series_error(experiment_type: object | None, reactor_series: object | None) -> str | None:
    """Why `reactor_series` is invalid for this type, or None when it is fine.

    NULL/blank is always fine (the type's default series). 'P' is HPHT-only.
    """
    if reactor_series is None or str(reactor_series).strip() == "":
        return None
    value = str(reactor_series).strip().upper()
    if value not in ALLOWED_REACTOR_SERIES:
        return f"Unknown reactor series '{reactor_series}'; allowed: {', '.join(sorted(ALLOWED_REACTOR_SERIES))}"
    if series_prefix(experiment_type) != "R":
        return f"Reactor series '{value}' (Parr) is only valid for HPHT experiments"
    return None


def derive_reactor_slot(
    reactor_number: object | None,
    experiment_type: object | None,
    reactor_series: object | None = None,
) -> str | None:
    """Build the canonical slot label, or None when there is no slot.

    None is returned when: the type is not occupancy-bearing, the number is
    missing or unparseable, the number is <= 0, or `reactor_series` is not valid
    for the type (a Parr series on a Core Flood holds no slot). Zero is not a slot — the eight
    `R00` rows in the 2026-07-28 prod audit exist only because `0` is falsy in
    Python and slipped past `if conditions.reactor_number`.
    """
    prefix = series_prefix(experiment_type)
    if prefix is None:
        return None
    if reactor_series is not None and str(reactor_series).strip() != "":
        if reactor_series_error(experiment_type, reactor_series) is not None:
            return None
        prefix = str(reactor_series).strip().upper()
    if reactor_number is None:
        return None
    try:
        number = int(reactor_number)
    except (TypeError, ValueError):
        return None
    return _format_slot(prefix, number)


_LABEL_RE = re.compile(r"^(CF|R|P)\s*0*(\d+)$", re.IGNORECASE)


def parse_reactor_cell(value: object) -> tuple[int, str | None]:
    """Read a bulk-upload reactor cell as (number, label prefix or None).

    A plain number (7, 7.0, "7") gives (7, None): the series is not stated.
    A slot label ("R07", "cf2", "P01") gives (number, "R"/"CF"/"P").
    Raises ValueError for anything else. Whether the prefix suits the row's
    experiment type is `series_for_label`'s job.
    """
    if isinstance(value, str):
        text = value.strip()
        match = _LABEL_RE.match(text)
        if match:
            return int(match.group(2)), match.group(1).upper()
        return int(text), None
    return int(value), None


def series_for_label(prefix: str, experiment_type: object | None) -> str | None:
    """reactor_series to store for a labelled reactor cell; ValueError on a mismatch.

    The type's own default prefix ('R' on HPHT, 'CF' on Core Flood) stores NULL;
    'P' stores 'P' on HPHT and is an error on any other type.
    """
    default = series_prefix(experiment_type)
    if prefix == PARR_SERIES:
        error = reactor_series_error(experiment_type, prefix)
        if error is not None:
            raise ValueError(error)
        return PARR_SERIES
    if prefix != default:
        raise ValueError(
            f"Reactor label prefix '{prefix}' does not match experiment type "
            f"'{experiment_type}' (expected '{default or 'no reactor'}')"
        )
    return None
