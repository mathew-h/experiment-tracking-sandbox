"""
Canonical experiment ID parser (issue #70 P5).

Single source of truth for the experiment ID grammar:

- ``TYPE_INDEX`` (2-part, e.g. ``HPHT_001``) or ``TYPE_INITIALS_INDEX``
  (3-part, e.g. ``Serum_MH_101``) base stems
- ``-N`` sequential derivations (only when the prefix ends in a numeric
  segment, so ``CF-015`` stays standalone); ``-0``/``-1`` are explicit
  "group parent" spellings (see lineage_utils.update_experiment_lineage)
- ``_Text`` treatment variants (e.g. ``_Desorption``)
- a single trailing lowercase letter bound to the numeric index for
  replicates (e.g. ``SERUM_001a``), issue #69/#70 grammar

Consumers:
- ``database.lineage_utils.parse_experiment_id`` delegates to
  :func:`parse_lineage_fields` (4-tuple surface used by lineage, event
  listeners, replicate routing, and the data-migration script).
- ``backend.services.experiment_validation.parse_experiment_id`` delegates
  its classification half to :func:`classify_base_id` but keeps its OWN
  legacy lineage extraction (``extract_lineage_info``), whose divergent
  behavior is pinned — see that function's docstring.
- :func:`parse_experiment_id_full` returns the complete parse in one call.

This module must not import anything from ``backend``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from database.models.enums import ExperimentType


# Mapping of common abbreviations to ExperimentType enum values
EXPERIMENT_TYPE_ABBREVIATIONS: Dict[str, ExperimentType] = {
    # Full names (case-insensitive)
    "serum": ExperimentType.SERUM,
    "autoclave": ExperimentType.AUTOCLAVE,
    "hpht": ExperimentType.HPHT,
    "coreflood": ExperimentType.CF,
    "core flood": ExperimentType.CF,
    "cf": ExperimentType.CF,
    "other": ExperimentType.OTHER,
    # Common abbreviations
    "ac": ExperimentType.AUTOCLAVE,
}


@dataclass
class ParsedExperimentID:
    """Result of parsing an experiment ID."""
    experiment_type: Optional[ExperimentType]
    researcher_initials: Optional[str]
    index: Optional[str]
    sequential_number: Optional[int]
    treatment_variant: Optional[str]
    base_id: str  # The ID without sequential/treatment suffixes
    original_id: str
    is_valid: bool
    warnings: List[str]
    replicate_label: Optional[str] = None  # "a", "b", "c"; None = not a replicate


_REPLICATE_LETTER_RE = re.compile(r'^(\d+)([a-z])$')
_REPLICATE_GUARD_RE = re.compile(r'^\d+[a-z]$')


def get_experiment_type_from_id(type_text: str) -> Optional[ExperimentType]:
    """
    Map experiment type text (abbreviation or full name) to ExperimentType enum.

    Args:
        type_text: The type portion from experiment ID (case-insensitive)

    Returns:
        ExperimentType enum value if found, None otherwise
    """
    if not type_text:
        return None

    normalized = type_text.strip().lower()
    return EXPERIMENT_TYPE_ABBREVIATIONS.get(normalized)


def parse_lineage_fields(experiment_id: str) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]:
    """
    Parse an experiment ID to extract the base ID, derivation number, treatment variant,
    and replicate label.

    Uses hybrid delimiter system:
    - Hyphen-NUMBER for sequential lineage (e.g., -2, -3), but ONLY when the prefix
      itself ends in a numeric segment (_NNN or -NNN, optionally letter-suffixed).
    - Underscore-TEXT for treatment variants (e.g., _Desorption).
    - A single trailing lowercase letter bound to the numeric index for replicates
      (e.g., _001a). Extracted last so a letter-suffixed index is never mistaken
      for a treatment name.

    TYPE-NNN IDs (e.g., CF-015, CF-04) are treated as standalone base experiments
    because their prefix ("CF") does not end in digits.

    -0 and -1 are valid derivation numbers (they denote the explicit "group parent"
    spelling of a replicate set — see database/lineage_utils.py::update_experiment_lineage).

    Args:
        experiment_id: The experiment ID to parse

    Returns:
        A tuple of (base_experiment_id, derivation_number, treatment_variant, replicate_label)

    Examples:
        >>> parse_lineage_fields("CF-015")
        ("CF-015", None, None, None)
        >>> parse_lineage_fields("CF-015-2")
        ("CF-015", 2, None, None)
        >>> parse_lineage_fields("HPHT_MH_001-2")
        ("HPHT_MH_001", 2, None, None)
        >>> parse_lineage_fields("HPHT_MH_001-2_Desorption")
        ("HPHT_MH_001", 2, "Desorption", None)
        >>> parse_lineage_fields("HPHT_MH_001")
        ("HPHT_MH_001", None, None, None)
        >>> parse_lineage_fields("HPHT_MH_001_Desorption")
        ("HPHT_MH_001", None, "Desorption", None)
        >>> parse_lineage_fields("SERUM_001-0")
        ("SERUM_001", 0, None, None)
        >>> parse_lineage_fields("SERUM_001a")
        ("SERUM_001", None, None, "a")
        >>> parse_lineage_fields("Serum_MH_101a")
        ("Serum_MH_101", None, None, "a")
        >>> parse_lineage_fields("SERUM_001a-2")
        ("SERUM_001", 2, None, "a")
    """
    if not experiment_id or not isinstance(experiment_id, str):
        return None, None, None, None

    experiment_id = experiment_id.strip()
    if not experiment_id:
        return None, None, None, None

    treatment_variant = None
    derivation_num = None
    replicate_label = None
    base_id = experiment_id

    # Step 1: Extract treatment variant (trailing _TEXT segment).
    # A trailing underscore segment is a treatment only when:
    #   - it is not a letter-suffixed numeric index (e.g. "101a") — replicate guard
    #   - it contains no hyphens (so "001-2" is not mistaken for a treatment)
    #   - it is not all digits (so "001" index segments are left alone)
    #   - removing it still leaves a structured ID with >= 2 underscore-segments
    #     (prevents "CF_Desorption" from stripping "Desorption" off a 1-part base)
    parts = experiment_id.split('_')
    if len(parts) >= 2:
        last = parts[-1]
        if not _REPLICATE_GUARD_RE.match(last) and not last.isdigit() and '-' not in last:
            remaining = '_'.join(parts[:-1])
            if len(remaining.split('_')) >= 2:
                treatment_variant = last
                base_id = remaining

    # Step 2: Extract sequential derivation number (trailing -N).
    # Only treat -N as a derivation when the prefix already ends in _NNN or -NNN
    # (optionally letter-suffixed, e.g. "_001a"), confirming it carries a numeric index.
    # This prevents TYPE-NNN IDs like CF-015 from being parsed as deriv=15 of "CF".
    # -0 and -1 are valid derivation numbers (see docstring).
    if '-' in base_id:
        prefix, _, suffix = base_id.rpartition('-')
        if suffix.isdigit() and re.search(r'[_-]\d+[a-z]?$', prefix):
            derivation_num = int(suffix)
            base_id = prefix

    # Step 3: Extract the replicate letter bound to the numeric index and rebuild
    # base_id with the numeric-only index (e.g. "SERUM_001a" -> "SERUM_001").
    id_parts = base_id.split('_')
    letter_match = _REPLICATE_LETTER_RE.match(id_parts[-1])
    if letter_match:
        replicate_label = letter_match.group(2)
        id_parts[-1] = letter_match.group(1)
        base_id = '_'.join(id_parts)

    return base_id, derivation_num, treatment_variant, replicate_label


def classify_base_id(
    base_id: str, original_id: str
) -> Tuple[Optional[ExperimentType], Optional[str], Optional[str], bool, List[str]]:
    """
    Classify a base stem into (experiment_type, researcher_initials, index,
    is_valid, warnings).

    Supports both 2-part (TYPE_INDEX) and 3-part (TYPE_INITIALS_INDEX) formats.
    ``original_id`` is only used in warning text. Warning strings are pinned —
    they surface verbatim in bulk-upload row feedback.
    """
    warnings: List[str] = []

    parts = base_id.split('_')

    experiment_type = None
    researcher_initials = None
    index = None

    if len(parts) < 2:
        warnings.append(
            f"Expected format: ExperimentType_Index or ExperimentType_ResearcherInitials_Index "
            f"(e.g., HPHT_001 or Serum_MH_101). Got: {original_id}"
        )
        is_valid = False
    elif len(parts) == 2:
        # 2-part format: TYPE_INDEX
        type_text = parts[0]
        index = parts[1]
        researcher_initials = None  # Not present in 2-part format

        # Validate experiment type
        experiment_type = get_experiment_type_from_id(type_text)
        if not experiment_type:
            warnings.append(
                f"Unknown experiment type '{type_text}'. Expected one of: "
                f"{', '.join(sorted(set(EXPERIMENT_TYPE_ABBREVIATIONS.keys())))}"
            )

        # Validate index (should be numeric or alphanumeric)
        if not index:
            warnings.append("Index portion is missing (e.g., 001, 101)")

        is_valid = len(warnings) == 0
    else:
        # 3-part format: TYPE_INITIALS_INDEX
        type_text = parts[0]
        researcher_initials = parts[1]
        index = parts[2]

        # Validate experiment type
        experiment_type = get_experiment_type_from_id(type_text)
        if not experiment_type:
            warnings.append(
                f"Unknown experiment type '{type_text}'. Expected one of: "
                f"{', '.join(sorted(set(EXPERIMENT_TYPE_ABBREVIATIONS.keys())))}"
            )

        # Validate researcher initials (basic check)
        if not researcher_initials or not researcher_initials.isalnum():
            warnings.append(
                f"Researcher initials '{researcher_initials}' should be alphanumeric (e.g., MH, JD)"
            )

        # Validate index (should be numeric or alphanumeric)
        if not index:
            warnings.append("Index portion is missing (e.g., 101, 001)")

        is_valid = len(warnings) == 0

    return experiment_type, researcher_initials, index, is_valid, warnings


def parse_experiment_id_full(experiment_id: str) -> ParsedExperimentID:
    """
    Full canonical parse: replicate-grammar lineage fields plus base-stem
    classification and validity, in one ParsedExperimentID.

    Note: this uses the CANONICAL grammar (parse_lineage_fields). The legacy
    validation surface (backend.services.experiment_validation.parse_experiment_id)
    intentionally differs on two pinned shapes — combined "-N_Treatment"
    suffixes and naive trailing "-N" (e.g. CF-015). See that module.
    """
    if not experiment_id or not isinstance(experiment_id, str) or not experiment_id.strip():
        return ParsedExperimentID(
            experiment_type=None,
            researcher_initials=None,
            index=None,
            sequential_number=None,
            treatment_variant=None,
            base_id="",
            original_id=experiment_id if isinstance(experiment_id, str) else "",
            is_valid=False,
            warnings=["Experiment ID is empty or invalid"],
        )

    original_id = experiment_id.strip()
    base_id, sequential_number, treatment_variant, replicate_label = parse_lineage_fields(original_id)
    experiment_type, researcher_initials, index, is_valid, warnings = classify_base_id(base_id, original_id)

    return ParsedExperimentID(
        experiment_type=experiment_type,
        researcher_initials=researcher_initials,
        index=index,
        sequential_number=sequential_number,
        treatment_variant=treatment_variant,
        base_id=base_id,
        original_id=original_id,
        is_valid=is_valid,
        warnings=warnings,
        replicate_label=replicate_label,
    )
