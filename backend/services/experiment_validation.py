"""
Experiment ID validation and parsing service.

This module provides validation and parsing for experiment IDs following either format:
- ExperimentType_ResearcherInitials_Index (e.g., Serum_MH_101) - 3-part format
- ExperimentType_Index (e.g., HPHT_001) - 2-part format

Both formats support optional sequential (-NUMBER) and treatment (_TEXT) suffixes.

Format Examples:
- Base (3-part): Serum_MH_101
- Base (2-part): HPHT_001
- Sequential (3-part): Serum_MH_101-2 (2nd run)
- Sequential (2-part): HPHT_001-2 (2nd run)
- Treatment (3-part): Serum_MH_101_Desorption (treatment variant)
- Treatment (2-part): HPHT_001_Desorption (treatment variant)
- Combined (3-part): Serum_MH_101-2_Desorption (treatment on 2nd run)
- Combined (2-part): HPHT_001-2_Desorption (treatment on 2nd run)
"""

from typing import Optional, Tuple, List
import re

from database.experiment_id_parser import (
    EXPERIMENT_TYPE_ABBREVIATIONS,
    ParsedExperimentID,
    classify_base_id,
    get_experiment_type_from_id,
)

__all__ = [
    "EXPERIMENT_TYPE_ABBREVIATIONS",
    "ParsedExperimentID",
    "get_experiment_type_from_id",
    "extract_lineage_info",
    "parse_experiment_id",
    "validate_experiment_id",
    "format_validation_warning",
]


def extract_lineage_info(experiment_id: str) -> Tuple[str, Optional[int], Optional[str], Optional[str]]:
    """
    LEGACY lineage extraction — frozen, pinned behavior (issue #70 P5).

    The canonical experiment ID grammar lives in
    database/experiment_id_parser.py::parse_lineage_fields. This function is
    retained verbatim because its algorithm diverges from the canonical
    grammar on shapes that locked callers depend on
    (backend/services/bulk_uploads/new_experiments.py::find_parent_for_copy
    and the parsed.sequential_number warning gate in the same file):

    1. Naive trailing "-N": ANY trailing hyphen-number is treated as a
       sequential number, so extract_lineage_info("CF-015") returns
       ("CF", 15, None, None) while the canonical grammar treats CF-015 as
       a standalone base experiment.
    2. Combined "-N_Treatment" suffixes (pre-existing bug, predates issue
       #69): the hyphen-NUMBER match requires the entire tail after the
       last hyphen to be purely digits, so the sequential number is never
       extracted and stays glued to base_id:
       extract_lineage_info("HPHT_001-2_Desorption") returns
       ("HPHT_001-2", None, "Desorption", None), NOT ("HPHT_001", 2, ...).

    Both divergences are pinned by
    tests/services/test_experiment_validation_replicates.py
    (TestLegacyLineageDivergencesPinned and test_existing_combined_unaffected).
    Do not modify this function's behavior without an explicit product
    decision covering every caller.

    Returns:
        Tuple of (base_id, sequential_number, treatment_variant, replicate_label)

    Examples:
        >>> extract_lineage_info("Serum_MH_101")
        ("Serum_MH_101", None, None, None)
        >>> extract_lineage_info("HPHT_001")
        ("HPHT_001", None, None, None)
        >>> extract_lineage_info("Serum_MH_101-2")
        ("Serum_MH_101", 2, None, None)
        >>> extract_lineage_info("HPHT_001-2")
        ("HPHT_001", 2, None, None)
        >>> extract_lineage_info("Serum_MH_101_Desorption")
        ("Serum_MH_101", None, "Desorption", None)
        >>> extract_lineage_info("HPHT_001_Desorption")
        ("HPHT_001", None, "Desorption", None)
        >>> extract_lineage_info("Serum_MH_101-2_Desorption")
        ("Serum_MH_101-2", None, "Desorption", None)
        # Known pre-existing limitation (predates issue #69, not fixed here): the
        # hyphen-NUMBER match requires the entire tail after the last hyphen to be
        # purely digits, so a combined "-N_Treatment" suffix never matches and the
        # sequential number is not extracted; see test_existing_combined_unaffected.
        >>> extract_lineage_info("HPHT_001-2_Desorption")
        ("HPHT_001-2", None, "Desorption", None)
        >>> extract_lineage_info("SERUM_001a")
        ("SERUM_001", None, None, "a")
        >>> extract_lineage_info("Serum_MH_101a")
        ("Serum_MH_101", None, None, "a")
        >>> extract_lineage_info("SERUM_001a-2")
        ("SERUM_001", 2, None, "a")
    """
    if not experiment_id:
        return "", None, None, None

    treatment_variant = None
    sequential_number = None
    replicate_label = None
    base_id = experiment_id

    # First, extract sequential number (hyphen-NUMBER pattern from the end)
    # This must be done before treatment detection to avoid confusion
    if '-' in experiment_id:
        hyphen_parts = experiment_id.rsplit('-', 1)
        if len(hyphen_parts) == 2 and hyphen_parts[-1].isdigit():
            sequential_number = int(hyphen_parts[-1])
            base_id = hyphen_parts[0]

    # Extract the replicate letter bound to the numeric index (e.g. "101a" -> "101" + "a").
    # Must run before treatment detection below, or a letter-suffixed index would be
    # mistaken for a treatment name (e.g. "Serum_MH_101a" -> base "Serum_MH", treatment "101a").
    parts = base_id.split('_')
    letter_match = re.match(r'^(\d+)([a-z])$', parts[-1])
    if letter_match:
        replicate_label = letter_match.group(2)
        parts[-1] = letter_match.group(1)
        base_id = '_'.join(parts)

    # Now check for treatment variant in the remaining base_id
    # Split by underscore to detect if last part is a treatment
    parts = base_id.split('_')

    # Determine expected base format by checking part count
    # After removing sequential, we should have:
    # - 2 parts for TYPE_INDEX format (e.g., HPHT_001)
    # - 3 parts for TYPE_INITIALS_INDEX format (e.g., Serum_MH_101)
    # If we have more parts than expected, the last part is likely a treatment
    
    if len(parts) > 2:
        # Could be 2-part format with treatment, or 3-part format (with or without treatment)
        potential_treatment = parts[-1]
        
        # Check if last part looks like a treatment (not all numeric)
        if not potential_treatment.isdigit():
            # Last part is not numeric, likely a treatment
            # But we need to distinguish between:
            # - HPHT_001_Desorption (2-part + treatment, len=3)
            # - Serum_MH_101_Desorption (3-part + treatment, len=4)
            # - Serum_MH_101 (3-part base, len=3)
            
            # If we have exactly 3 parts and last is non-numeric, it could be:
            # - TYPE_INDEX + treatment (HPHT_001_Desorption)
            # - TYPE_INITIALS_INDEX base (Serum_MH_101) - but 101 is numeric, so this won't match
            
            # If we have 4+ parts, definitely a treatment (TYPE_INITIALS_INDEX + treatment)
            # If we have 3 parts and last is non-numeric, it's TYPE_INDEX + treatment
            if len(parts) >= 3:
                treatment_variant = potential_treatment
                base_id = '_'.join(parts[:-1])
        # If last part is numeric and we have exactly 3 parts, it's TYPE_INITIALS_INDEX base format
        # If last part is numeric and we have exactly 2 parts, it's TYPE_INDEX base format

    return base_id, sequential_number, treatment_variant, replicate_label


def parse_experiment_id(experiment_id: str) -> ParsedExperimentID:
    """
    Parse and validate an experiment ID.
    
    Supports two formats:
    - ExperimentType_ResearcherInitials_Index[-Sequential][_Treatment] (3-part, e.g., Serum_MH_101)
    - ExperimentType_Index[-Sequential][_Treatment] (2-part, e.g., HPHT_001)
    
    Args:
        experiment_id: The experiment ID to parse
        
    Returns:
        ParsedExperimentID object with parsed components and validation warnings
        
    Examples:
        >>> result = parse_experiment_id("Serum_MH_101")
        >>> result.experiment_type
        ExperimentType.SERUM
        >>> result.researcher_initials
        'MH'
        >>> result.index
        '101'
        >>> result = parse_experiment_id("HPHT_001")
        >>> result.experiment_type
        ExperimentType.HPHT
        >>> result.researcher_initials
        None
        >>> result.index
        '001'

    Lineage fields use the legacy extraction (see extract_lineage_info);
    classification is shared with database/experiment_id_parser.py.
    """
    warnings = []

    if not experiment_id or not isinstance(experiment_id, str):
        return ParsedExperimentID(
            experiment_type=None,
            researcher_initials=None,
            index=None,
            sequential_number=None,
            treatment_variant=None,
            base_id="",
            original_id=experiment_id or "",
            is_valid=False,
            warnings=["Experiment ID is empty or invalid"]
        )

    original_id = experiment_id.strip()

    # Extract lineage info first — NOTE: intentionally the LEGACY extraction,
    # not the canonical grammar; see extract_lineage_info's docstring.
    base_id, sequential_number, treatment_variant, replicate_label = extract_lineage_info(original_id)

    # Classification (type / initials / index / validity) is shared with the
    # canonical parser module.
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


def validate_experiment_id(experiment_id: str) -> Tuple[bool, List[str]]:
    """
    Validate an experiment ID and return warnings.
    
    This is a convenience function that returns just the validation status and warnings.
    
    Args:
        experiment_id: The experiment ID to validate
        
    Returns:
        Tuple of (is_valid, warnings_list)
        
    Example:
        >>> is_valid, warnings = validate_experiment_id("Serum_MH_101")
        >>> is_valid
        True
        >>> warnings
        []
    """
    parsed = parse_experiment_id(experiment_id)
    return parsed.is_valid, parsed.warnings


def format_validation_warning(warnings: List[str]) -> str:
    """
    Format validation warnings into a user-friendly message.
    
    Args:
        warnings: List of warning messages
        
    Returns:
        Formatted warning string
    """
    if not warnings:
        return ""
    
    if len(warnings) == 1:
        return f"⚠️ {warnings[0]}"
    
    return "⚠️ Validation warnings:\n" + "\n".join(f"  • {w}" for w in warnings)

