"""Shared fuzzy-ID helpers for bulk-upload services.

Normalization rules (applied in order):
  1. Lowercase
  2. Strip all non-alphanumeric characters
  3. Strip leading zeros from each numeric segment

Examples:
  "20250502_2A"  → "202505022a"   (no leading zeros)
  "20250502-2A"  → "202505022a"
  "HPHT_001"     → "hpht1"        (leading zeros stripped)
  "HPHT-001"     → "hpht1"
  "HPHT_1"       → "hpht1"
  "HPHT_100"     → "hpht100"      (100 has no leading zeros)

Both ``fuzzy_find_sample`` and ``fuzzy_find_experiment`` try an exact DB match
first (single indexed query), then fall back to loading all rows and comparing
normalized IDs in Python. The exact-match fast path means the fallback scan is
only needed when the file's ID format differs from the stored one.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from database import Experiment, SampleInfo


def normalize_id(raw: str) -> str:
    """Lowercase, strip all non-alphanumeric chars, then strip leading zeros.

    Leading-zero stripping targets sequences of zeros that are preceded by a
    non-digit (or start of string) and followed by at least one more digit.
    This means:
      - "001" → "1"
      - "100" → "100"  (the 1 is not a leading zero)
      - "0"   → "0"    (lone zero, nothing follows)
    """
    s = re.sub(r"[^a-z0-9]", "", raw.lower())
    s = re.sub(r"(?<!\d)0+(?=\d)", "", s)
    return s


def fuzzy_find_sample(db: Session, raw_id: str) -> Optional[SampleInfo]:
    """Return the SampleInfo whose sample_id matches ``raw_id`` after normalization.

    Tries exact match first; falls back to normalized scan if not found.
    """
    sample = db.query(SampleInfo).filter(SampleInfo.sample_id == raw_id).first()
    if sample:
        return sample
    target = normalize_id(raw_id)
    for s in db.query(SampleInfo).all():
        if normalize_id(s.sample_id) == target:
            return s
    return None


def fuzzy_find_experiment(db: Session, raw_id: str) -> Optional[Experiment]:
    """Return the Experiment whose experiment_id matches ``raw_id`` after normalization.

    Tries exact match first; falls back to normalized scan if not found.
    """
    exp = db.query(Experiment).filter(Experiment.experiment_id == raw_id).first()
    if exp:
        return exp
    target = normalize_id(raw_id)
    for e in db.query(Experiment).all():
        if normalize_id(e.experiment_id) == target:
            return e
    return None
