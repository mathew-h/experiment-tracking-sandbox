"""Unit tests for _id_match.normalize_id."""
from __future__ import annotations

import pytest

from backend.services.bulk_uploads._id_match import normalize_id


@pytest.mark.parametrize("raw, expected", [
    # Force lowercase; runs are joined with a single underscore
    ("HPHT_1", "hpht_1"),
    ("Serum_MH_101", "serum_mh_101"),

    # Every separator collapses to the canonical delimiter
    ("HPHT-001", "hpht_1"),        # hyphen
    ("HPHT_001", "hpht_1"),        # underscore
    ("HPHT 001", "hpht_1"),        # space
    ("HPHT.001", "hpht_1"),        # dot
    ("HPHT/001", "hpht_1"),        # slash
    ("HPHT(001)", "hpht_1"),       # parens

    # A missing separator is inserted at the alpha/digit boundary, so an
    # unseparated file ID still matches the stored separated one
    ("hpht001", "hpht_1"),
    ("HPHT001", "hpht_1"),

    # Leading zeros are stripped inside each digit run, not across runs
    ("HPHT_0014B", "hpht_14_b"),
    ("HPHT_001_4B", "hpht_1_4_b"),  # NOT equal to the line above -- see below

    # No false positives — zeros that are NOT leading
    ("HPHT_100", "hpht_100"),      # 1 then 00 — not leading
    ("HPHT_0", "hpht_0"),          # lone zero survives
    ("HPHT_00", "hpht_0"),         # all-zero run collapses to a single 0
    ("20250502_2A", "20250502_2_a"),  # date-style ID — internal zeros stay

    # Idempotent: normalizing an already-normalized key is a no-op
    ("hpht_1", "hpht_1"),
])
def test_normalize_id(raw, expected):
    """normalize_id produces the expected canonical string for each input."""
    assert normalize_id(raw) == expected


# ── Regression: the 13 real experiment pairs the old key conflated ────────────
#
# The old key deleted separators AND stripped leading zeros, so a sequential
# re-run (SERUM_JW_010-2) collapsed onto an unrelated experiment (SERUM_JW_102).
# fuzzy_find_experiment then returned .first() of the two, so a bulk upload could
# attach results to the wrong experiment silently. All 13 pairs below exist in
# the dev DB (measured 2026-08-05).

_CONFLATED_PAIRS = [
    ("SERUM_JW_092", "SERUM_JW_009-2"),
    ("SERUM_JW_102", "SERUM_JW_010-2"),
    ("SERUM_JW_112", "SERUM_JW_011-2"),
    ("SERUM_JW_122", "SERUM_JW_012_2"),
    ("SERUM_JW_123", "SERUM_JW_012_3"),
    ("SERUM_JW_132", "SERUM_JW_013_2"),
    ("SERUM_JW_133", "SERUM_JW_013-3"),
    ("SERUM_JW_142", "SERUM_JW_014_2"),
    ("SERUM_JW_143", "SERUM_JW_014-3"),
    ("SERUM_JW_152", "SERUM_JW_015_2"),
    ("SERUM_JW_153", "SERUM_JW_015-3"),
    ("SERUM_JW_162", "SERUM_JW_016_2"),
    ("SERUM_JW_163", "SERUM_JW_016-3"),
]


@pytest.mark.parametrize("left, right", _CONFLATED_PAIRS)
def test_real_experiment_pairs_no_longer_collide(left, right):
    """Two distinct real experiments must never share a normalized key."""
    assert normalize_id(left) != normalize_id(right), (
        f"{left} and {right} both normalize to {normalize_id(left)!r}"
    )


_CONFLATED_SAMPLE_PAIRS = [
    ("23UM042", "23UM004.2"),
    ("23UM052", "23UM005.2"),
    ("202505255?", "20250525_5"),
]


@pytest.mark.parametrize("left, right", _CONFLATED_SAMPLE_PAIRS)
def test_real_sample_pairs_no_longer_collide(left, right):
    """The same defect reached fuzzy_find_sample; 3 real dev-DB pairs."""
    assert normalize_id(left) != normalize_id(right), (
        f"{left} and {right} both normalize to {normalize_id(left)!r}"
    )


@pytest.mark.parametrize("left, right", [
    ("HPHT_001", "hpht1"),      # separator present vs absent
    ("HPHT-001", "HPHT_1"),     # different separator, padded vs unpadded
    ("20250502_2A", "20250502-2a"),
])
def test_intended_equivalences_survive(left, right):
    """The leniency the finders actually rely on must not be lost."""
    assert normalize_id(left) == normalize_id(right)


# ── find_similar_samples ──────────────────────────────────────────────────────

from unittest.mock import MagicMock
from backend.services.bulk_uploads._id_match import find_similar_samples
from database import SampleInfo


def _make_db(sample_ids: list[str]):
    """Build a mock Session whose query().all() returns SampleInfo stubs."""
    samples = [SampleInfo(sample_id=sid) for sid in sample_ids]
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # no exact match
    db.query.return_value.all.return_value = samples
    return db


def test_find_similar_no_near_matches():
    """Returns empty dict when no sample is similar enough."""
    db = _make_db(["Granite", "Basalt"])
    result = find_similar_samples(db, ["QRTZ9999"], threshold=0.90)
    assert result == {}


def test_find_similar_exact_normalized_excluded():
    """Exact normalized match (auto-resolved) must NOT appear in conflicts."""
    db = _make_db(["Tamarack"])
    result = find_similar_samples(db, ["TAMARACK"], threshold=0.90)
    assert "TAMARACK" not in result


def test_find_similar_near_match_returned():
    """Near-match above threshold is returned when no exact normalized match exists."""
    db = _make_db(["Tamarack"])
    result = find_similar_samples(db, ["Tamarrack"], threshold=0.85)
    assert "Tamarrack" in result
    assert len(result["Tamarrack"]) == 1
    match = result["Tamarrack"][0]
    assert match["sample_id"] == "Tamarack"
    assert match["similarity"] >= 0.85


def test_find_similar_sorted_by_similarity_desc():
    """Candidates are sorted best-first."""
    db = _make_db(["Tamarack", "Tamaraack"])
    result = find_similar_samples(db, ["Tamarrack"], threshold=0.80)
    assert "Tamarrack" in result
    sims = [m["similarity"] for m in result["Tamarrack"]]
    assert sims == sorted(sims, reverse=True)


def test_find_similar_below_threshold_excluded():
    """Candidates below threshold are excluded."""
    db = _make_db(["ZZZ999"])
    result = find_similar_samples(db, ["Tamarack"], threshold=0.90)
    assert "Tamarack" not in result
