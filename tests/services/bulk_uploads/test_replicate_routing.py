"""Unit tests for combine_replicate_id (issue #70 P3). Pure — no DB."""
from __future__ import annotations

import pytest

from backend.services.bulk_uploads.replicate_routing import combine_replicate_id


def test_blank_values_pass_through():
    assert combine_replicate_id("SERUM_001", None) == "SERUM_001"
    assert combine_replicate_id("SERUM_001", float("nan")) == "SERUM_001"
    assert combine_replicate_id("SERUM_001", "") == "SERUM_001"
    assert combine_replicate_id("SERUM_001", "  ") == "SERUM_001"


def test_zero_means_group_parent():
    assert combine_replicate_id("SERUM_001", 0) == "SERUM_001"
    assert combine_replicate_id("SERUM_001", 0.0) == "SERUM_001"
    assert combine_replicate_id("SERUM_001", "0") == "SERUM_001"


def test_letter_appends_to_numeric_index():
    assert combine_replicate_id("SERUM_001", "a") == "SERUM_001a"
    assert combine_replicate_id("SERUM_001", "B") == "SERUM_001b"
    assert combine_replicate_id(" SERUM_001 ", " c ") == "SERUM_001c"
    assert combine_replicate_id("Serum_MH_101", "a") == "Serum_MH_101a"


def test_same_letter_in_id_is_noop():
    assert combine_replicate_id("SERUM_001a", "a") == "SERUM_001a"


def test_conflicting_letter_raises():
    with pytest.raises(ValueError, match="conflicts"):
        combine_replicate_id("SERUM_001a", "b")


def test_derivation_or_treatment_suffix_raises():
    with pytest.raises(ValueError, match="derivation or treatment"):
        combine_replicate_id("SERUM_001-2", "b")
    with pytest.raises(ValueError, match="derivation or treatment"):
        combine_replicate_id("HPHT_MH_001_Desorption", "b")
    # Explicit parent spellings parse as derivation 0/1 — same strict rule.
    with pytest.raises(ValueError, match="derivation or treatment"):
        combine_replicate_id("SERUM_001-0", "b")


def test_id_without_numeric_index_raises():
    # "CF-015" has no underscore-delimited numeric index; "CF-015b" would not
    # round-trip through parse_experiment_id as a replicate.
    with pytest.raises(ValueError, match="cannot take a replicate letter"):
        combine_replicate_id("CF-015", "b")


def test_malformed_replicate_values_raise():
    for bad in ("ab", "2", 2.0, "b2", True):
        with pytest.raises(ValueError, match="single letter"):
            combine_replicate_id("SERUM_001", bad)


def test_replicate_without_experiment_id_raises():
    with pytest.raises(ValueError, match="without an Experiment ID"):
        combine_replicate_id(None, "a")
    with pytest.raises(ValueError, match="without an Experiment ID"):
        combine_replicate_id("   ", "a")
