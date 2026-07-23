"""Tests for replicate-letter support in experiment_validation (issue #69)."""
from backend.services.experiment_validation import (
    extract_lineage_info, parse_experiment_id,
)


class TestExtractLineageInfoReplicateGrammar:
    def test_bare_stem(self):
        assert extract_lineage_info("HPHT_001") == ("HPHT_001", None, None, None)

    def test_replicate_letter_two_part(self):
        assert extract_lineage_info("SERUM_001a") == ("SERUM_001", None, None, "a")

    def test_replicate_letter_three_part(self):
        assert extract_lineage_info("Serum_MH_101a") == ("Serum_MH_101", None, None, "a")

    def test_replicate_letter_plus_sequential(self):
        assert extract_lineage_info("SERUM_001a-2") == ("SERUM_001", 2, None, "a")

    def test_existing_sequential_unaffected(self):
        assert extract_lineage_info("HPHT_001-2") == ("HPHT_001", 2, None, None)

    def test_existing_treatment_unaffected(self):
        assert extract_lineage_info("HPHT_001_Desorption") == ("HPHT_001", None, "Desorption", None)

    def test_existing_combined_unaffected(self):
        # NOTE: this documents a pre-existing bug in extract_lineage_info that predates
        # issue #69 (present unmodified since the initial project commit, b69b24f): the
        # hyphen-NUMBER extraction only matches when the text after the last hyphen is
        # purely digits, so a combined "-N_Treatment" suffix fails the sequential-number
        # match entirely and falls through to the treatment branch, which then strips
        # "_Treatment" but leaves the "-N" attached to base_id. The correct/desired
        # tuple would be ("Serum_MH_101", 2, "Desorption", None); actual (unchanged)
        # behavior is asserted here so this test documents reality rather than going red
        # for a bug outside this task's scope (adding replicate-letter recognition only;
        # no reordering of the existing sequential/treatment extraction logic per brief).
        assert extract_lineage_info("Serum_MH_101-2_Desorption") == ("Serum_MH_101-2", None, "Desorption", None)

    def test_empty(self):
        assert extract_lineage_info("") == ("", None, None, None)


class TestParseExperimentIdReplicateLabel:
    def test_two_part_replicate_is_valid(self):
        result = parse_experiment_id("SERUM_001a")
        assert result.is_valid is True
        assert result.replicate_label == "a"
        assert result.index == "001"
        assert result.experiment_type is not None

    def test_three_part_replicate_does_not_degrade_to_wrong_treatment(self):
        result = parse_experiment_id("Serum_MH_101a")
        assert result.is_valid is True
        assert result.replicate_label == "a"
        assert result.index == "101"
        assert result.researcher_initials == "MH"
        assert result.base_id == "Serum_MH_101"

    def test_non_replicate_id_has_null_replicate_label(self):
        result = parse_experiment_id("HPHT_001")
        assert result.replicate_label is None

    def test_invalid_id_has_null_replicate_label(self):
        result = parse_experiment_id("")
        assert result.replicate_label is None
