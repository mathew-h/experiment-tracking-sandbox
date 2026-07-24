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


class TestLegacyLineageDivergencesPinned:
    """P5 (issue #70): extract_lineage_info is retained as a frozen legacy shim.

    Its algorithm diverges from the canonical grammar
    (database.experiment_id_parser.parse_lineage_fields) on two shapes, both of
    which are consumed by locked code (new_experiments.py's find_parent_for_copy
    and its parsed.sequential_number warning gate), so the divergent outputs are
    pinned here as KNOWN ISSUES rather than fixed. Do not "fix" these without an
    explicit product decision.
    """

    def test_naive_trailing_dash_number_cf_shape(self):
        # Canonical grammar: ("CF-015", None, None, None). Legacy: any trailing
        # -N is sequential, regardless of the prefix shape.
        assert extract_lineage_info("CF-015") == ("CF", 15, None, None)

    def test_naive_trailing_dash_number_hyphenated_shape(self):
        # Canonical grammar: ("TEST-SAMPLE-001", None, None, None).
        assert extract_lineage_info("TEST-SAMPLE-001") == ("TEST-SAMPLE", 1, None, None)

    def test_combined_suffix_bug_two_part(self):
        # Same pre-existing bug as test_existing_combined_unaffected, 2-part shape.
        # Canonical grammar: ("HPHT_001", 2, "Desorption", None).
        assert extract_lineage_info("HPHT_001-2_Desorption") == ("HPHT_001-2", None, "Desorption", None)

    def test_parsed_dataclass_pins_cf_shape(self):
        result = parse_experiment_id("CF-015")
        assert result.sequential_number == 15
        assert result.base_id == "CF"
        assert result.is_valid is False
        assert result.replicate_label is None

    def test_parsed_dataclass_pins_combined_shape(self):
        result = parse_experiment_id("Serum_MH_101-2_Desorption")
        assert result.sequential_number is None
        assert result.treatment_variant == "Desorption"
        assert result.base_id == "Serum_MH_101-2"
        assert result.index == "101-2"
        assert result.researcher_initials == "MH"
        assert result.is_valid is True

    def test_valid_id_warning_text_unchanged(self):
        # Warning strings surface verbatim in bulk-upload feedback; pin one.
        result = parse_experiment_id("XYZ_001")
        assert result.is_valid is False
        assert any("Unknown experiment type 'XYZ'" in w for w in result.warnings)


class TestTimepointOnValidationSurface:
    """Issue #81: the validation surface pre-strips '-t<days>' before the
    FROZEN extract_lineage_info, so legacy lineage semantics apply to the stem."""

    def test_timepoint_surfaced(self):
        parsed = parse_experiment_id("SERUM_001a-t7")
        assert parsed.timepoint_days == 7.0
        assert parsed.replicate_label == "a"
        assert parsed.base_id == "SERUM_001"
        assert parsed.is_valid is True

    def test_decimal_timepoint_surfaced(self):
        assert parse_experiment_id("SERUM_001a-t0.5").timepoint_days == 0.5

    def test_no_token_means_none(self):
        assert parse_experiment_id("SERUM_001a").timepoint_days is None
        assert parse_experiment_id("CF-015").timepoint_days is None

    def test_legacy_divergences_apply_to_stem(self):
        # CF-015-t3: strip token -> 'CF-015' -> legacy naive rule still fires
        # exactly as pinned for the bare shape.
        parsed = parse_experiment_id("CF-015-t3")
        assert parsed.timepoint_days == 3.0
        assert parsed.base_id == "CF"
        assert parsed.sequential_number == 15

    def test_frozen_function_untouched_by_token(self):
        # extract_lineage_info itself never sees/strips tokens (frozen body).
        assert extract_lineage_info("SERUM_001a-t7") == ("SERUM_001a-t7", None, None, None)
