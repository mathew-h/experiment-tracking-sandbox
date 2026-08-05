"""Shared fuzzy-ID helpers for bulk-upload services.

Normalization rules (applied in order):
  1. Lowercase
  2. Split into maximal alphabetic and numeric runs, discarding every
     non-alphanumeric character
  3. Strip leading zeros inside each numeric run (an all-zero run becomes "0")
  4. Join the runs with a single "_"

Examples:
  "20250502_2A"  -> "20250502_2_a"
  "20250502-2A"  -> "20250502_2_a"
  "HPHT_001"     -> "hpht_1"
  "HPHT-001"     -> "hpht_1"
  "HPHT_1"       -> "hpht_1"
  "HPHT001"      -> "hpht_1"       (missing separator is inserted)
  "HPHT_100"     -> "hpht_100"     (100 has no leading zeros)

Why runs are DELIMITED rather than concatenated
-----------------------------------------------
The previous key deleted every separator before stripping leading zeros, so a
sequential re-run collapsed onto an unrelated experiment: "SERUM_JW_010-2" and
"SERUM_JW_102" both became "serumjw102". 13 real experiment pairs and 3 sample
pairs in the dev DB were affected (measured 2026-08-05), and the finders below
resolved the collision by returning an arbitrary one of the two -- silently
attaching bulk-uploaded results to the wrong experiment.

Keeping a delimiter between runs is a strict refinement: equal new keys imply
identical run sequences, which imply equal old keys, so this can only split an
old equivalence class, never merge two. Both keys collapse separator style and
zero padding, which is the leniency the finders exist for. Two documented
equivalences are deliberately lost -- "HPHT_0014B" no longer matches
"HPHT_001_4B" -- because they were guesses.

Both ``fuzzy_find_sample`` and ``fuzzy_find_experiment`` try an exact DB match
first (single indexed query), then fall back to loading all rows and comparing
normalized IDs in Python. The exact-match fast path means the fallback scan is
only needed when the file's ID format differs from the stored one. Neither ever
resolves an ambiguous key -- see ``find_experiment_matches``.
"""
from __future__ import annotations

import re
from typing import Optional, TypedDict

from sqlalchemy.orm import Session

from database import Experiment, SampleInfo


_RUN_RE = re.compile(r"[0-9]+|[a-z]+")


def normalize_id(raw: str) -> str:
    """Lowercase, split into alpha/digit runs, unpad each digit run, join with "_".

    Runs keep a delimiter between them so that a numeric boundary cannot be
    erased. "SERUM_JW_010-2" -> "serum_jw_10_2" while "SERUM_JW_102" ->
    "serum_jw_102": distinct, where the old concatenating key made them equal.
    An all-zero run collapses to "0" ("HPHT_00" -> "hpht_0").
    """
    runs: list[str] = []
    for run in _RUN_RE.findall(raw.lower()):
        if run.isdigit():
            run = run.lstrip("0") or "0"
        runs.append(run)
    return "_".join(runs)


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


class SimilarSampleMatch(TypedDict):
    sample_id: str
    similarity: float  # 0.0–1.0


def find_similar_samples(
    db: Session,
    incoming_ids: list[str],
    threshold: float = 0.90,
) -> dict[str, list[SimilarSampleMatch]]:
    """For each incoming_id with NO exact normalized match, return existing
    SampleInfo records whose normalized IDs score >= threshold via rapidfuzz WRatio.

    IDs that have an exact normalized match are silently excluded — they are
    auto-resolved by the caller, not conflicts.

    Returns dict mapping incoming_id -> sorted-desc list of SimilarSampleMatch.
    Only IDs with >= 1 candidate are included.
    """
    from rapidfuzz.fuzz import WRatio  # noqa: PLC0415

    all_samples = db.query(SampleInfo).all()
    # Build normalized lookup once to avoid N+1 full-table scans
    norm_to_sample = {normalize_id(s.sample_id): s for s in all_samples}

    conflicts: dict[str, list[SimilarSampleMatch]] = {}

    for raw in incoming_ids:
        # Skip IDs that have an exact normalized match (auto-resolved upstream)
        if norm_to_sample.get(normalize_id(raw)) is not None:
            continue

        # Score remaining candidates using normalized strings so that
        # punctuation/case differences are collapsed before comparison
        target = normalize_id(raw)
        candidates: list[SimilarSampleMatch] = []
        for s in all_samples:
            score = WRatio(target, normalize_id(s.sample_id)) / 100.0
            if score >= threshold:
                candidates.append(SimilarSampleMatch(sample_id=s.sample_id, similarity=round(score, 4)))

        if candidates:
            conflicts[raw] = sorted(candidates, key=lambda c: c["similarity"], reverse=True)

    return conflicts
