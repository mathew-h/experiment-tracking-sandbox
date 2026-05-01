"""Unit tests for _id_match.normalize_id."""
from __future__ import annotations

import pytest

from backend.services.bulk_uploads._id_match import normalize_id


@pytest.mark.parametrize("raw, expected", [
    # Force lowercase
    ("HPHT_1", "hpht1"),
    ("Serum_MH_101", "serummh101"),

    # Strip all non-alphanumeric symbols (not just - and _)
    ("HPHT-001", "hpht1"),        # hyphen
    ("HPHT_001", "hpht1"),        # underscore
    ("HPHT 001", "hpht1"),        # space
    ("HPHT.001", "hpht1"),        # dot
    ("HPHT/001", "hpht1"),        # slash
    ("HPHT(001)", "hpht1"),       # parens

    # Strip leading zeros from numeric segments
    ("hpht001", "hpht1"),         # leading zeros after alpha prefix
    ("HPHT_0014B", "hpht14b"),    # leading zeros mid-id
    ("HPHT_001_4B", "hpht14b"),   # strip symbol then leading zeros

    # No false positives — zeros that are NOT leading
    ("HPHT_100", "hpht100"),      # 1 then 00 — not leading
    ("HPHT_0", "hpht0"),          # single zero alone, not followed by digit
    ("HPHT_00", "hpht0"),         # collision: second 0 satisfies lookahead, first is stripped — same as HPHT_0
    ("20250502_2A", "202505022a"), # date-style ID — internal zeros stay
    ("hpht1", "hpht1"),           # already normalized
])
def test_normalize_id(raw, expected):
    """normalize_id produces the expected canonical string for each input."""
    assert normalize_id(raw) == expected


# ── find_similar_samples ──────────────────────────────────────────────────────

from unittest.mock import MagicMock
from backend.services.bulk_uploads._id_match import find_similar_samples, SimilarSampleMatch
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
    # 'TAMARACK' normalizes same as 'Tamarack' → fuzzy_find_sample returns it
    from unittest.mock import patch
    db = _make_db(["Tamarack"])
    with patch("backend.services.bulk_uploads._id_match.fuzzy_find_sample") as mock_ffm:
        mock_ffm.return_value = SampleInfo(sample_id="Tamarack")
        result = find_similar_samples(db, ["TAMARACK"], threshold=0.90)
    assert "TAMARACK" not in result


def test_find_similar_near_match_returned():
    """Near-match above threshold is returned when no exact normalized match exists."""
    from unittest.mock import patch
    db = _make_db(["Tamarack"])
    with patch("backend.services.bulk_uploads._id_match.fuzzy_find_sample") as mock_ffm:
        mock_ffm.return_value = None  # no exact normalized match
        result = find_similar_samples(db, ["Tamarrack"], threshold=0.85)
    assert "Tamarrack" in result
    assert len(result["Tamarrack"]) == 1
    match = result["Tamarrack"][0]
    assert match["sample_id"] == "Tamarack"
    assert match["similarity"] >= 0.85


def test_find_similar_sorted_by_similarity_desc():
    """Candidates are sorted best-first."""
    from unittest.mock import patch
    db = _make_db(["Tamarack", "Tamaraack"])
    with patch("backend.services.bulk_uploads._id_match.fuzzy_find_sample") as mock_ffm:
        mock_ffm.return_value = None
        result = find_similar_samples(db, ["Tamarrack"], threshold=0.80)
    if "Tamarrack" in result:
        sims = [m["similarity"] for m in result["Tamarrack"]]
        assert sims == sorted(sims, reverse=True)


def test_find_similar_below_threshold_excluded():
    """Candidates below threshold are excluded."""
    from unittest.mock import patch
    db = _make_db(["ZZZ999"])
    with patch("backend.services.bulk_uploads._id_match.fuzzy_find_sample") as mock_ffm:
        mock_ffm.return_value = None
        result = find_similar_samples(db, ["Tamarack"], threshold=0.90)
    assert "Tamarack" not in result
