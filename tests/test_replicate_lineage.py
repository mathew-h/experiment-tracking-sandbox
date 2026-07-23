"""Tests for replicate-letter support in experiment ID lineage parsing (issue #69)."""
import pytest

from database.lineage_utils import parse_experiment_id


class TestParseExperimentIdReplicateGrammar:
    """4-tuple (base_experiment_id, derivation_num, treatment_variant, replicate_label)."""

    def test_bare_stem(self):
        assert parse_experiment_id("SERUM_001") == ("SERUM_001", None, None, None)

    def test_explicit_parent_dash_0(self):
        assert parse_experiment_id("SERUM_001-0") == ("SERUM_001", 0, None, None)

    def test_explicit_parent_dash_1(self):
        assert parse_experiment_id("SERUM_001-1") == ("SERUM_001", 1, None, None)

    def test_replicate_letter_two_part(self):
        assert parse_experiment_id("SERUM_001a") == ("SERUM_001", None, None, "a")

    def test_replicate_letter_three_part(self):
        assert parse_experiment_id("Serum_MH_101a") == ("Serum_MH_101", None, None, "a")

    def test_replicate_letter_does_not_degrade_to_treatment(self):
        # Regression guard: must NOT parse as base="Serum_MH", treatment="101a"
        result = parse_experiment_id("Serum_MH_101a")
        assert result[0] == "Serum_MH_101"
        assert result[2] is None

    def test_replicate_letter_plus_sequential(self):
        assert parse_experiment_id("SERUM_001a-2") == ("SERUM_001", 2, None, "a")

    def test_type_prefixed_id_unaffected(self):
        assert parse_experiment_id("CF-015") == ("CF-015", None, None, None)

    def test_existing_sequential_unaffected(self):
        assert parse_experiment_id("HPHT_MH_001-2") == ("HPHT_MH_001", 2, None, None)

    def test_existing_treatment_unaffected(self):
        assert parse_experiment_id("HPHT_MH_001_Desorption") == ("HPHT_MH_001", None, "Desorption", None)

    def test_existing_combined_sequential_treatment_unaffected(self):
        assert parse_experiment_id("HPHT_MH_001-2_Desorption") == ("HPHT_MH_001", 2, "Desorption", None)

    def test_empty_and_none(self):
        assert parse_experiment_id("") == (None, None, None, None)
        assert parse_experiment_id(None) == (None, None, None, None)
        assert parse_experiment_id("   ") == (None, None, None, None)
