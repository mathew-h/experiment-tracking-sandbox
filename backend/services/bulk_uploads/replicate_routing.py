"""Replicate-column routing for bulk uploads (issue #70 P3).

Rows in results uploads may carry a base experiment ID (e.g. "SERUM_001") plus
a separate replicate column ("a", "b", ...). This module combines the two into
the full lettered sibling ID ("SERUM_001a") at parse time, so every downstream
step (fuzzy lookup, upsert, rollup) behaves exactly as if the row had carried
the full replicate ID. Pure string-level: no DB access — existence checks and
fuzzy matching stay in ScalarResultsService.
"""
from __future__ import annotations

import math
from typing import Any

from database.lineage_utils import parse_experiment_id


def combine_replicate_id(experiment_id: Any, replicate: Any) -> Any:
    """Return the effective experiment ID for a row's (experiment_id, replicate) pair.

    Rules (issue #70 locked decisions 1-2):
      - blank replicate (None/NaN/"") -> experiment_id returned unchanged
      - 0 (int, float, or "0") -> experiment_id unchanged (bare base = replicate 0)
      - single letter a-z (any case) -> appended to the ID's numeric index
      - the ID may already carry the same letter (no-op); a different letter,
        a derivation suffix (-2), a treatment suffix (_Desorption), or an ID
        shape that cannot carry a letter (e.g. CF-015) raises ValueError

    Raises:
        ValueError: with a user-facing, per-row message on any malformed or
            conflicting combination.
    """
    # Blank / replicate-0 spellings: pass the ID through untouched so rows
    # without a usable replicate value keep byte-identical behavior.
    if replicate is None:
        return experiment_id
    if isinstance(replicate, float) and math.isnan(replicate):
        return experiment_id
    if (
        isinstance(replicate, (int, float))
        and not isinstance(replicate, bool)
        and replicate == 0
    ):
        return experiment_id

    rep = str(replicate).strip().lower()
    if rep in ("", "0", "0.0"):
        return experiment_id

    if len(rep) != 1 or not ("a" <= rep <= "z"):
        raise ValueError(
            f"Replicate must be a single letter a-z (or 0 for the group parent), "
            f"got '{replicate}'."
        )

    if experiment_id is None or str(experiment_id).strip() == "":
        raise ValueError("Replicate letter given without an Experiment ID.")

    exp_id = str(experiment_id).strip()
    base_id, derivation_num, treatment_variant, replicate_label = parse_experiment_id(exp_id)

    if replicate_label == rep:
        return exp_id
    if replicate_label is not None:
        raise ValueError(
            f"Replicate column '{rep}' conflicts with the replicate letter "
            f"already in '{exp_id}'."
        )
    if derivation_num is not None or treatment_variant is not None:
        raise ValueError(
            f"Replicate column cannot be combined with a derivation or treatment "
            f"suffix ('{exp_id}') - put the full replicate ID in the Experiment ID "
            f"column instead."
        )

    candidate = f"{base_id}{rep}"
    # Round-trip guard: some ID shapes (e.g. "CF-015", whose index is not an
    # underscore-delimited numeric segment) cannot carry a replicate letter
    # under the P1 grammar. Refuse rather than write an ID the lineage
    # listener would misclassify.
    if parse_experiment_id(candidate) != (base_id, None, None, rep):
        raise ValueError(
            f"'{exp_id}' cannot take a replicate letter - only IDs ending in a "
            f"numeric index (e.g. SERUM_001) support the replicate column."
        )
    return candidate
