"""Tests for the canonical experiment ID parser (issue #70 P5).

parse_lineage_fields / parse_experiment_id_full encode the final replicate
ruleset (P1 grammar). The legacy divergent surface (extract_lineage_info)
is pinned separately in tests/services/test_experiment_validation_replicates.py.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.experiment_id_parser import (
    ParsedExperimentID,
    classify_base_id,
    get_experiment_type_from_id,
    parse_experiment_id_full,
    parse_lineage_fields,
)
from database.models.enums import ExperimentType


class TestParseLineageFields:
    """Byte-identical to the pre-P5 lineage_utils.parse_experiment_id grammar."""

    def test_bare_stems(self):
        assert parse_lineage_fields("HPHT_MH_001") == ("HPHT_MH_001", None, None, None)
        assert parse_lineage_fields("LEACH_TEST") == ("LEACH_TEST", None, None, None)
        assert parse_lineage_fields("SERUM_001") == ("SERUM_001", None, None, None)

    def test_sequential(self):
        assert parse_lineage_fields("HPHT_MH_001-2") == ("HPHT_MH_001", 2, None, None)
        assert parse_lineage_fields("HPHT_MH_001-10") == ("HPHT_MH_001", 10, None, None)
        assert parse_lineage_fields("HPHT_001-2") == ("HPHT_001", 2, None, None)

    def test_type_prefixed_ids_are_standalone(self):
        assert parse_lineage_fields("CF-015") == ("CF-015", None, None, None)
        assert parse_lineage_fields("CF-12") == ("CF-12", None, None, None)
        assert parse_lineage_fields("CF-04") == ("CF-04", None, None, None)
        assert parse_lineage_fields("CF-015-2") == ("CF-015", 2, None, None)

    def test_hyphenated_non_derivations(self):
        assert parse_lineage_fields("COMPLEX-ID-TEST-3") == ("COMPLEX-ID-TEST-3", None, None, None)
        assert parse_lineage_fields("TEST-SAMPLE-001") == ("TEST-SAMPLE-001", None, None, None)
        assert parse_lineage_fields("TEST-SAMPLE-ABC") == ("TEST-SAMPLE-ABC", None, None, None)
        assert parse_lineage_fields("HPHT-HIGH-TEMP") == ("HPHT-HIGH-TEMP", None, None, None)

    def test_treatment(self):
        assert parse_lineage_fields("HPHT_MH_001_Desorption") == ("HPHT_MH_001", None, "Desorption", None)
        assert parse_lineage_fields("Serum_MH_101_Annealing") == ("Serum_MH_101", None, "Annealing", None)

    def test_combined_sequential_treatment(self):
        assert parse_lineage_fields("HPHT_MH_001-2_Desorption") == ("HPHT_MH_001", 2, "Desorption", None)
        assert parse_lineage_fields("Serum_MH_101-3_Annealing") == ("Serum_MH_101", 3, "Annealing", None)

    def test_explicit_parent_spellings(self):
        assert parse_lineage_fields("HPHT_MH_001-0") == ("HPHT_MH_001", 0, None, None)
        assert parse_lineage_fields("HPHT_MH_001-1") == ("HPHT_MH_001", 1, None, None)

    def test_replicate_letters(self):
        assert parse_lineage_fields("SERUM_001a") == ("SERUM_001", None, None, "a")
        assert parse_lineage_fields("Serum_MH_101a") == ("Serum_MH_101", None, None, "a")
        assert parse_lineage_fields("SERUM_001a-2") == ("SERUM_001", 2, None, "a")

    def test_empty_and_none(self):
        assert parse_lineage_fields("") == (None, None, None, None)
        assert parse_lineage_fields(None) == (None, None, None, None)
        assert parse_lineage_fields("   ") == (None, None, None, None)


class TestLineageUtilsDelegation:
    """lineage_utils.parse_experiment_id must remain the same public surface."""

    def test_wrapper_matches_canonical_on_corpus(self):
        from database.lineage_utils import parse_experiment_id
        corpus = [
            "HPHT_MH_001", "LEACH_TEST", "SERUM_001", "HPHT_MH_001-2",
            "HPHT_001-2", "CF-015", "CF-015-2", "TEST-SAMPLE-001",
            "HPHT-HIGH-TEMP", "HPHT_MH_001_Desorption",
            "HPHT_MH_001-2_Desorption", "SERUM_001-0", "SERUM_001-1",
            "SERUM_001a", "Serum_MH_101a", "SERUM_001a-2",
            "SERUM_001a-2_Desorption", "", None, "   ",
        ]
        for exp_id in corpus:
            assert parse_experiment_id(exp_id) == parse_lineage_fields(exp_id), exp_id


class TestClassifyBaseId:
    def test_three_part(self):
        etype, initials, index, is_valid, warnings = classify_base_id("Serum_MH_101", "Serum_MH_101")
        assert etype == ExperimentType.SERUM
        assert initials == "MH"
        assert index == "101"
        assert is_valid is True
        assert warnings == []

    def test_two_part(self):
        etype, initials, index, is_valid, warnings = classify_base_id("HPHT_001", "HPHT_001")
        assert etype == ExperimentType.HPHT
        assert initials is None
        assert index == "001"
        assert is_valid is True
        assert warnings == []

    def test_one_part_invalid(self):
        etype, initials, index, is_valid, warnings = classify_base_id("CF-015", "CF-015")
        assert etype is None and initials is None and index is None
        assert is_valid is False
        assert len(warnings) == 1
        assert "Got: CF-015" in warnings[0]

    def test_unknown_type_warning(self):
        etype, initials, index, is_valid, warnings = classify_base_id("XYZ_001", "XYZ_001")
        assert etype is None
        assert index == "001"
        assert is_valid is False
        assert any("Unknown experiment type 'XYZ'" in w for w in warnings)


class TestParseExperimentIdFull:
    def test_replicate_full_parse(self):
        result = parse_experiment_id_full("Serum_MH_101a-2")
        assert isinstance(result, ParsedExperimentID)
        assert result.experiment_type == ExperimentType.SERUM
        assert result.researcher_initials == "MH"
        assert result.index == "101"
        assert result.replicate_label == "a"
        assert result.sequential_number == 2
        assert result.treatment_variant is None
        assert result.base_id == "Serum_MH_101"
        assert result.original_id == "Serum_MH_101a-2"
        assert result.is_valid is True
        assert result.warnings == []

    def test_combined_sequential_treatment_uses_canonical_grammar(self):
        # Unlike the legacy validation surface, the canonical full parse
        # extracts BOTH the sequential number and the treatment.
        result = parse_experiment_id_full("HPHT_001-2_Desorption")
        assert result.sequential_number == 2
        assert result.treatment_variant == "Desorption"
        assert result.base_id == "HPHT_001"
        assert result.index == "001"

    def test_cf_shape_is_standalone_and_invalid_format(self):
        result = parse_experiment_id_full("CF-015")
        assert result.sequential_number is None
        assert result.base_id == "CF-015"
        assert result.is_valid is False

    def test_empty_is_invalid(self):
        for bad in ("", None, "   "):
            result = parse_experiment_id_full(bad)
            assert result.is_valid is False
            assert result.warnings == ["Experiment ID is empty or invalid"]
            assert result.replicate_label is None

    def test_type_map(self):
        assert get_experiment_type_from_id("ac") == ExperimentType.AUTOCLAVE
        assert get_experiment_type_from_id("CF") == ExperimentType.CF
        assert get_experiment_type_from_id("nonsense") is None
