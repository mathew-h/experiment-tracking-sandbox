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
    ("20250502_2A", "202505022a"), # date-style ID — internal zeros stay
    ("hpht1", "hpht1"),           # already normalized
])
def test_normalize_id(raw, expected):
    assert normalize_id(raw) == expected
