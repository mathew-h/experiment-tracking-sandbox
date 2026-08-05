# Fuzzy Experiment-ID Matching: Stop Silently Guessing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop bulk uploads from silently attaching results to the wrong experiment — fix `normalize_id`'s lossy key (which collapses 13 real experiment pairs and 3 sample pairs in the dev DB) and make the finders refuse to guess when more than one row matches.

**Architecture:** Two independent defects sit on top of each other in `backend/services/bulk_uploads/_id_match.py`. `normalize_id` deletes every separator *and* strips leading zeros, so `SERUM_JW_010-2` and `SERUM_JW_102` both become `serumjw102`; then `fuzzy_find_experiment` returns `.first()` of whatever it finds, so the loser is picked arbitrarily and nothing is reported. This plan fixes both layers: normalization becomes **run-delimited** (split into alpha/digit runs, strip leading zeros per digit run, join with `_`), which is a strict refinement — it never merges anything the old key kept apart — and the finders gain an all-matches API so callers can report ambiguity instead of resolving it by luck.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x ORM, `re`, pytest, structlog. No new dependencies.

## Global Constraints

- **Locked files touched — user sign-off obtained 2026-08-05.** `backend/services/bulk_uploads/_id_match.py` (Tasks 1-2) and `backend/services/bulk_uploads/timepoint_modifications.py` (Task 4) are locked per `.claude/CLAUDE.md` §5. Do not touch any other file under `backend/services/bulk_uploads/`. `backend/services/scalar_results_service.py` (Task 3) is **not** locked.
- **No new third-party packages.** `rapidfuzz` is already a dependency and already imported in `_id_match.py`.
- **Never run two pytest processes at once.** `experiments_test` is one shared PostgreSQL schema; concurrent runs corrupt it and an interrupted run leaves a stale schema `create_all` cannot repair.
- **Test-suite baseline:** `tests/test_pg_backup_restore.py` has **3 pre-existing failures** on `develop`. Full-suite expectation is `3 failed, 1332 passed, 4 skipped`. Three failures = clean.
- **Commands use the venv prefix:** `.venv/Scripts/python`, `.venv/Scripts/pytest`.
- **Branch:** `fix/id-match-ambiguity`, cut from `develop`. PRs always `gh pr create --base develop`.
- **Commit format (inline task — no issue number):** `[fix] <imperative, <50 chars, no trailing period>` then a body with `- Tests added: yes/no` and `- Docs updated: yes/no`.
- **No schema change, no migration.** This is pure matching logic.
- **This plan changes matching leniency on purpose.** Some ID pairs that used to match will stop matching (see "Accepted leniency losses" below). That is the fix, not a regression — a clean "not found" row error is strictly better than a silent wrong attachment. Do not widen the normalizer back to make an old test pass.

---

## Background an implementer needs

**The defect, concretely.** `normalize_id("SERUM_JW_010-2")` and `normalize_id("SERUM_JW_102")` both return `"serumjw102"`. Both experiments exist in the dev DB. When a workbook names one in a format that is not a byte-exact match to the stored string, `fuzzy_find_experiment` falls through to a normalized scan and returns `.first()` — an arbitrary one of the two. Results then land on the wrong experiment with no warning anywhere.

**Measured against the dev DB (1009 experiments, 680 samples), 2026-08-05:**

| Key | Experiment collisions | Sample collisions |
|---|---|---|
| Current `normalize_id` | **13 groups** | **3 groups** |
| Run-delimited key (this plan) | **0** | **0** |

The 13 experiment groups, all of one shape:

```
serumjw92  -> SERUM_JW_092  / SERUM_JW_009-2
serumjw102 -> SERUM_JW_102  / SERUM_JW_010-2
serumjw112 -> SERUM_JW_112  / SERUM_JW_011-2
serumjw122 -> SERUM_JW_122  / SERUM_JW_012_2
serumjw123 -> SERUM_JW_123  / SERUM_JW_012_3
serumjw132 -> SERUM_JW_132  / SERUM_JW_013_2
serumjw133 -> SERUM_JW_133  / SERUM_JW_013-3
serumjw142 -> SERUM_JW_142  / SERUM_JW_014_2
serumjw143 -> SERUM_JW_143  / SERUM_JW_014-3
serumjw152 -> SERUM_JW_152  / SERUM_JW_015_2
serumjw153 -> SERUM_JW_153  / SERUM_JW_015-3
serumjw162 -> SERUM_JW_162  / SERUM_JW_016_2
serumjw163 -> SERUM_JW_163  / SERUM_JW_016-3
```

The 3 sample groups (same root cause, not previously recorded anywhere):
`23UM042 / 23UM004.2`, `23UM052 / 23UM005.2`, `202505255? / 20250525_5`.

**Why run-delimited is safe.** The new key is the old key with delimiters inserted at every alpha↔digit boundary and every original separator. Two strings with equal new keys therefore have identical run sequences, which implies equal old keys — so the new key can only ever *split* an old equivalence class, never merge two. Every equivalence documented in `_id_match.py`'s module docstring survives, including the un-separated case: `HPHT001`, `HPHT_001`, `HPHT-001` and `HPHT_1` all map to `hpht_1`. Verified by script (Task 1, Step 5).

**Accepted leniency losses.** Two documented pairs stop matching, both of them cases where the old key was guessing:
- `HPHT_0014B` → `hpht_14_b` vs `HPHT_001_4B` → `hpht_1_4_b` (was: both `hpht14b`).
- The 13 pairs and 3 sample pairs above — that is the entire point.

A workbook ID that no longer matches produces the existing "experiment not found" row error, which the researcher can fix by using the exact ID.

**Where ambiguity must NOT degrade to "not found".** `backend/services/scalar_results_service.py:91-101`: when `_find_experiment` returns `None`, the create path calls `auto_create_treatment_experiment` and may **create a brand-new experiment**. An ambiguous ID silently returning `None` there would fabricate a row. So ambiguity has to be a distinct signal, not a `None` (Task 3).

**Sibling finders are out of scope and verified clean.** `backend/services/icp_service.py:757`, `backend/services/bulk_uploads/aeris_xrd.py:46` and `backend/services/bulk_uploads/xrd_upload.py:63` each hand-roll their own delimiter-stripping lookup and each end in `.first()`. They do **not** strip leading zeros, so they do not have the 13-pair defect — a collision check across all 1009 dev experiment IDs on a delimiter-only key returns **0 groups**. They keep the latent `.first()` habit; recorded in Task 5, not fixed here.

---

### Task 1: Run-delimited `normalize_id` (LOCKED FILE)

**Files:**
- Modify: `backend/services/bulk_uploads/_id_match.py:1-43` (module docstring + `normalize_id`)
- Modify: `tests/services/bulk_uploads/test_id_match.py:9-36` (the parametrized expectations all change)

**Interfaces:**
- Consumes: nothing.
- Produces: `normalize_id(raw: str) -> str` — same signature, new output format (`"hpht_1"` not `"hpht1"`). Task 2's matchers and `find_similar_samples` both consume it.

**This file is locked.** Keep the diff to the module docstring, the `normalize_id` body, and one new module-level regex constant. Do not touch `fuzzy_find_sample`, `fuzzy_find_experiment` or `find_similar_samples` in this task — Task 2 owns those.

- [ ] **Step 1: Write the failing test**

Replace the parametrized block at `tests/services/bulk_uploads/test_id_match.py:9-36` with the following. Leave everything from `# ── find_similar_samples ──` down (line 39 onward) exactly as it is — those tests use alpha-only IDs and are unaffected.

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_id_match.py -v
```

Expected: the `test_normalize_id` cases fail (`"hpht1" != "hpht_1"`) and all 16 `no_longer_collide` cases fail (both sides still equal). `test_intended_equivalences_survive` passes already.

- [ ] **Step 3: Rewrite `normalize_id`**

In `backend/services/bulk_uploads/_id_match.py`, replace the module docstring (lines 1-20) with:

```python
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
```

Then replace `normalize_id` (the current lines 31-43) with:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_id_match.py -v
```

Expected: all pass, including the `find_similar_samples` tests further down the file (they use alpha-only IDs, so their keys are unchanged).

- [ ] **Step 5: Prove zero collisions against the dev DB**

```bash
.venv/Scripts/python -c "
import collections
from database import get_db, Experiment, SampleInfo
from backend.services.bulk_uploads._id_match import normalize_id
db = next(get_db())
for model, col in ((Experiment,'experiment_id'), (SampleInfo,'sample_id')):
    ids = [getattr(r, col) for r in db.query(model).all()]
    g = collections.defaultdict(list)
    for i in ids: g[normalize_id(i)].append(i)
    dups = {k:v for k,v in g.items() if len(v)>1}
    print(f'{model.__name__}.{col}: n={len(ids)} colliding groups={len(dups)}', list(dups.values())[:5])
"
```

Expected, exactly:
```
Experiment.experiment_id: n=1009 colliding groups=0 []
SampleInfo.sample_id: n=680 colliding groups=0 []
```

`n` may have grown if experiments were added since 2026-08-05; **`colliding groups` must be 0 for both**. If it is not, stop and report the groups — a collision the new key still has means the key needs another rule, and that is a design decision for the user.

- [ ] **Step 6: Run every suite that consumes the key**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/ -q
```

Expected: green. `test_actlabs_conflicts.py`, `test_master_bulk_upload.py`, `test_scalar_results_replicates.py` and `test_timepoint_modifications.py` all reach `normalize_id` through the finders. If one fails on a hardcoded `"hpht1"`-style expectation, update the expectation. If one fails because two IDs it *wanted* matched no longer do, report it — that is an accepted-leniency-loss decision, not a silent fix.

- [ ] **Step 7: Commit**

```bash
git add backend/services/bulk_uploads/_id_match.py tests/services/bulk_uploads/test_id_match.py
git commit -m "$(cat <<'EOF'
[fix] Delimit runs in normalize_id to stop ID collisions

- 13 real experiment pairs and 3 sample pairs no longer share a key
- Strict refinement: never merges what the old key kept apart
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Finders that refuse to guess (LOCKED FILE)

**Files:**
- Modify: `backend/services/bulk_uploads/_id_match.py` (`fuzzy_find_sample`, `fuzzy_find_experiment`; add two matchers and one exception)
- Test: `tests/services/bulk_uploads/test_id_match_ambiguity.py` (create)

**Interfaces:**
- Consumes: `normalize_id` from Task 1.
- Produces — Tasks 3 and 4 both import from `backend.services.bulk_uploads._id_match`:
  ```python
  class AmbiguousExperimentIdError(ValueError):
      def __init__(self, raw_id: str, candidates: list[str]) -> None: ...
      raw_id: str
      candidates: list[str]          # sorted stored experiment_id strings

  def find_experiment_matches(db: Session, raw_id: str) -> list[Experiment]: ...
  def find_sample_matches(db: Session, raw_id: str) -> list[SampleInfo]: ...
  def fuzzy_find_experiment(db: Session, raw_id: str) -> Optional[Experiment]: ...  # None on 0 or >1
  def fuzzy_find_sample(db: Session, raw_id: str) -> Optional[SampleInfo]: ...      # None on 0 or >1
  ```

`fuzzy_find_*` keep their exact current signature so no caller breaks; the only change is that an ambiguous key now yields `None` plus a `structlog` warning instead of an arbitrary row.

- [ ] **Step 1: Write the failing test**

Create `tests/services/bulk_uploads/test_id_match_ambiguity.py`:

```python
"""The finders must never resolve an ambiguous ID to an arbitrary row.

Task 1 removed every collision present in the dev DB, but the guard is what
makes a future collision loud instead of silent. `GUARD_AMB_1` and
`GUARD_AMB_001` are two distinct legal experiment_id strings that share the
normalized key `guard_amb_1` under any zero-stripping scheme.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Experiment, SampleInfo
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads._id_match import (
    AmbiguousExperimentIdError,
    find_experiment_matches,
    find_sample_matches,
    fuzzy_find_experiment,
    fuzzy_find_sample,
    normalize_id,
)


@pytest.fixture()
def two_colliding_experiments(db_session: Session) -> Session:
    db_session.add_all([
        Experiment(experiment_id="GUARD_AMB_1", experiment_number=8804001,
                   status=ExperimentStatus.ONGOING),
        Experiment(experiment_id="GUARD_AMB_001", experiment_number=8804002,
                   status=ExperimentStatus.ONGOING),
    ])
    db_session.flush()
    return db_session


def test_the_fixture_really_collides():
    assert normalize_id("GUARD_AMB_1") == normalize_id("GUARD_AMB_001")


def test_exact_match_wins_over_ambiguity(two_colliding_experiments: Session):
    """A byte-exact ID is never ambiguous, even when its normalized key is."""
    exp = fuzzy_find_experiment(two_colliding_experiments, "GUARD_AMB_001")
    assert exp is not None
    assert exp.experiment_id == "GUARD_AMB_001"


def test_find_experiment_matches_returns_both(two_colliding_experiments: Session):
    matches = find_experiment_matches(two_colliding_experiments, "guard-amb-01")
    assert {m.experiment_id for m in matches} == {"GUARD_AMB_1", "GUARD_AMB_001"}


def test_fuzzy_find_experiment_refuses_to_guess(two_colliding_experiments: Session):
    """The whole point: no arbitrary .first() on an ambiguous key."""
    assert fuzzy_find_experiment(two_colliding_experiments, "guard-amb-01") is None


def test_unambiguous_lookup_still_resolves(db_session: Session):
    db_session.add(Experiment(
        experiment_id="GUARD_SOLO_007", experiment_number=8804003,
        status=ExperimentStatus.ONGOING,
    ))
    db_session.flush()
    exp = fuzzy_find_experiment(db_session, "guard-solo-7")
    assert exp is not None and exp.experiment_id == "GUARD_SOLO_007"


def test_missing_experiment_still_returns_none(db_session: Session):
    assert fuzzy_find_experiment(db_session, "GUARD_NOPE_999") is None


def test_ambiguous_error_carries_the_candidates():
    err = AmbiguousExperimentIdError("guard-amb-01", ["GUARD_AMB_001", "GUARD_AMB_1"])
    assert isinstance(err, ValueError)
    assert err.raw_id == "guard-amb-01"
    assert err.candidates == ["GUARD_AMB_001", "GUARD_AMB_1"]
    assert "GUARD_AMB_001" in str(err) and "GUARD_AMB_1" in str(err)


def test_sample_finder_also_refuses_to_guess(db_session: Session):
    db_session.add_all([
        SampleInfo(sample_id="GUARD_SMP_1"),
        SampleInfo(sample_id="GUARD_SMP_001"),
    ])
    db_session.flush()
    assert len(find_sample_matches(db_session, "guard-smp-01")) == 2
    assert fuzzy_find_sample(db_session, "guard-smp-01") is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_id_match_ambiguity.py -v
```

Expected: collection error — `ImportError: cannot import name 'AmbiguousExperimentIdError'`.

- [ ] **Step 3: Add the matchers, the exception, and the guard**

In `backend/services/bulk_uploads/_id_match.py`, add `import structlog` next to `import re` and a module-level logger after the imports:

```python
log = structlog.get_logger(__name__)
```

Add the exception directly below `normalize_id`:

```python
class AmbiguousExperimentIdError(ValueError):
    """More than one stored experiment matches one normalized ID.

    Raised by callers that must not fall through to a "not found" path --
    `ScalarResultsService._find_experiment`'s caller auto-CREATES an experiment
    when the lookup returns None, so a silent None on an ambiguous ID would
    fabricate a row.
    """

    def __init__(self, raw_id: str, candidates: list[str]) -> None:
        self.raw_id = raw_id
        self.candidates = candidates
        super().__init__(
            f"Experiment ID '{raw_id}' is ambiguous - it matches "
            f"{len(candidates)} experiments: {', '.join(candidates)}. "
            f"Use the exact experiment_id."
        )
```

Replace `fuzzy_find_sample` and `fuzzy_find_experiment` with the four functions below (same file position, keeping `find_similar_samples` after them):

```python
def find_sample_matches(db: Session, raw_id: str) -> list[SampleInfo]:
    """Every SampleInfo matching ``raw_id``. Exact match short-circuits to one.

    A list, not an Optional, so a caller can tell "no match" from "several" --
    the distinction the old .first() destroyed.
    """
    sample = db.query(SampleInfo).filter(SampleInfo.sample_id == raw_id).first()
    if sample:
        return [sample]
    target = normalize_id(raw_id)
    return [s for s in db.query(SampleInfo).all() if normalize_id(s.sample_id) == target]


def find_experiment_matches(db: Session, raw_id: str) -> list[Experiment]:
    """Every Experiment matching ``raw_id``. Exact match short-circuits to one."""
    exp = db.query(Experiment).filter(Experiment.experiment_id == raw_id).first()
    if exp:
        return [exp]
    target = normalize_id(raw_id)
    return [e for e in db.query(Experiment).all() if normalize_id(e.experiment_id) == target]


def fuzzy_find_sample(db: Session, raw_id: str) -> Optional[SampleInfo]:
    """The SampleInfo matching ``raw_id``, or None if none or several match.

    Never picks one of several: an arbitrary choice attaches data to the wrong
    sample with no trace.
    """
    matches = find_sample_matches(db, raw_id)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        log.warning(
            "ambiguous_sample_id",
            raw_id=raw_id,
            normalized=normalize_id(raw_id),
            candidates=sorted(s.sample_id for s in matches),
        )
    return None


def fuzzy_find_experiment(db: Session, raw_id: str) -> Optional[Experiment]:
    """The Experiment matching ``raw_id``, or None if none or several match.

    Returns None rather than raising so existing callers keep working. Callers
    that must distinguish ambiguity from absence should use
    ``find_experiment_matches`` and raise ``AmbiguousExperimentIdError``.
    """
    matches = find_experiment_matches(db, raw_id)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        log.warning(
            "ambiguous_experiment_id",
            raw_id=raw_id,
            normalized=normalize_id(raw_id),
            candidates=sorted(e.experiment_id for e in matches),
        )
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_id_match_ambiguity.py tests/services/bulk_uploads/test_id_match.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the locked-parser suite**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/ -q
```

Expected: green. If a test fails because it relied on `.first()` resolving a collision, that test was asserting the bug — report it before changing it.

- [ ] **Step 6: Commit**

```bash
git add backend/services/bulk_uploads/_id_match.py tests/services/bulk_uploads/test_id_match_ambiguity.py
git commit -m "$(cat <<'EOF'
[fix] Refuse to resolve an ambiguous experiment ID

- find_experiment_matches / find_sample_matches expose all matches
- fuzzy_find_* return None + structlog warning instead of .first()
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Make ambiguity loud in the scalar-results path

**Files:**
- Modify: `backend/services/scalar_results_service.py:347-356` (`_find_experiment`) and `:441-443` (`get_scalar_results_for_experiment`)
- Test: `tests/services/bulk_uploads/test_scalar_results_ambiguity.py` (create)

**Interfaces:**
- Consumes: `find_experiment_matches`, `AmbiguousExperimentIdError` from Task 2.
- Produces: `ScalarResultsService._find_experiment` now raises `AmbiguousExperimentIdError` instead of returning `None` when several rows match.

**Why this task is not optional.** `create_scalar_result_ex` at line 91-101 treats `None` as "maybe I should create this experiment" and calls `auto_create_treatment_experiment`. An ambiguous ID returning `None` would therefore create a spurious experiment row. Raising a `ValueError` subclass is what the per-row handlers already expect: `backend/services/bulk_uploads/scalar_results.py` and `master_bulk_upload.py` both catch `ValueError` and turn it into a row error string.

- [ ] **Step 1: Write the failing test**

Create `tests/services/bulk_uploads/test_scalar_results_ambiguity.py`:

```python
"""An ambiguous experiment ID must raise, never fall through to auto-create."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Experiment
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads._id_match import AmbiguousExperimentIdError
from backend.services.scalar_results_service import ScalarResultsService


@pytest.fixture()
def two_colliding_experiments(db_session: Session) -> Session:
    db_session.add_all([
        Experiment(experiment_id="AMBSCAL_1", experiment_number=8805001,
                   status=ExperimentStatus.ONGOING),
        Experiment(experiment_id="AMBSCAL_001", experiment_number=8805002,
                   status=ExperimentStatus.ONGOING),
    ])
    db_session.flush()
    return db_session


def test_find_experiment_raises_on_ambiguity(two_colliding_experiments: Session):
    with pytest.raises(AmbiguousExperimentIdError) as excinfo:
        ScalarResultsService._find_experiment(two_colliding_experiments, "ambscal-01")
    assert set(excinfo.value.candidates) == {"AMBSCAL_1", "AMBSCAL_001"}


def test_ambiguity_does_not_auto_create_an_experiment(two_colliding_experiments: Session):
    """The real hazard: None would send create_scalar_result_ex into
    auto_create_treatment_experiment and fabricate a row."""
    before = two_colliding_experiments.query(Experiment).count()
    with pytest.raises(ValueError):
        ScalarResultsService.create_scalar_result_ex(
            two_colliding_experiments,
            "ambscal-01",
            {"description": "amb", "gross_ammonium_concentration_mM": 1.0,
             "time_post_reaction": 7.0},
        )
    assert two_colliding_experiments.query(Experiment).count() == before, (
        "an experiment was auto-created for an ambiguous ID"
    )


def test_unambiguous_lookup_unaffected(db_session: Session):
    db_session.add(Experiment(
        experiment_id="AMBSCAL_SOLO_009", experiment_number=8805003,
        status=ExperimentStatus.ONGOING,
    ))
    db_session.flush()
    exp = ScalarResultsService._find_experiment(db_session, "ambscal-solo-9")
    assert exp is not None and exp.experiment_id == "AMBSCAL_SOLO_009"


def test_read_path_returns_empty_instead_of_raising(two_colliding_experiments: Session):
    """get_scalar_results_for_experiment is a read helper behind a GET; an
    ambiguous ID there must not become a 500."""
    assert ScalarResultsService.get_scalar_results_for_experiment(
        two_colliding_experiments, "ambscal-01"
    ) == []
```

The signature is `create_scalar_result_ex(db, experiment_id, result_data)` — three positionals, verified at `backend/services/scalar_results_service.py:69-71`. The assertion that matters is the experiment count: whatever else `create_scalar_result_ex` raises for a malformed payload, it must not have created a row.

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_scalar_results_ambiguity.py -v
```

Expected: `test_find_experiment_raises_on_ambiguity` FAILS with `DID NOT RAISE` (it returns `None` after Task 2), and `test_ambiguity_does_not_auto_create_an_experiment` FAILS either on the count or on a different exception type.

- [ ] **Step 3: Implement**

Replace `_find_experiment` (lines 347-356) with:

```python
    @staticmethod
    def _find_experiment(db: Session, experiment_id: str) -> Optional[Experiment]:
        """Find an experiment by ID using full fuzzy normalization.

        Raises ``AmbiguousExperimentIdError`` (a ValueError) when several stored
        experiments share the normalized key. Returning None there would be
        actively dangerous: ``create_scalar_result_ex`` treats None as "not
        found" and falls through to ``auto_create_treatment_experiment``, so an
        ambiguous ID would fabricate an experiment row. The per-row handlers in
        the scalar and master bulk parsers already catch ValueError and report
        it as a row error.
        """
        from backend.services.bulk_uploads._id_match import (  # noqa: PLC0415
            AmbiguousExperimentIdError,
            find_experiment_matches,
        )
        matches = find_experiment_matches(db, experiment_id)
        if len(matches) > 1:
            raise AmbiguousExperimentIdError(
                experiment_id, sorted(e.experiment_id for e in matches)
            )
        return matches[0] if matches else None
```

Then make the read helper tolerant. Replace lines 441-443 with:

```python
        from backend.services.bulk_uploads._id_match import (  # noqa: PLC0415
            AmbiguousExperimentIdError,
        )
        try:
            experiment = ScalarResultsService._find_experiment(db, experiment_id)
        except AmbiguousExperimentIdError:
            # Read helper behind a GET -- an ambiguous ID is an empty result,
            # not a 500. The warning is already logged in _id_match.
            return []
        if not experiment:
            return []
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_scalar_results_ambiguity.py -v
.venv/Scripts/pytest tests/services/bulk_uploads/test_master_bulk_upload.py tests/services/bulk_uploads/test_scalar_results_replicates.py tests/services/bulk_uploads/test_scalar_results_timepoints.py -q
```

Expected: the new file passes; the three existing scalar suites stay green.

- [ ] **Step 5: Commit**

```bash
git add backend/services/scalar_results_service.py tests/services/bulk_uploads/test_scalar_results_ambiguity.py
git commit -m "$(cat <<'EOF'
[fix] Raise on ambiguous ID before scalar auto-create

- Ambiguity no longer degrades to None and fabricates an experiment
- Read helper returns [] instead of surfacing a 500
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Report ambiguity as a row error in the timepoint-modifications parser (LOCKED FILE)

**Files:**
- Modify: `backend/services/bulk_uploads/timepoint_modifications.py:12` (import) and `:142-146` (the lookup)
- Test: `tests/services/bulk_uploads/test_timepoint_modifications.py` (append one test)

**Interfaces:**
- Consumes: `find_experiment_matches` from Task 2.
- Produces: nothing. Last code change.

**This file is locked.** The diff is one import line and five lines at the lookup. Nothing else.

Today this parser already handles `None` as `f"Row {row_num}: experiment '{exp_id}' not found"`, so after Task 2 an ambiguous ID is at least not a wrong attachment. This task upgrades the message so a researcher can act on it, instead of hunting for an ID they can see in the file.

- [ ] **Step 1: Write the failing test**

Append to `tests/services/bulk_uploads/test_timepoint_modifications.py`. It already imports `Experiment`, `ExperimentStatus`, `make_excel` and `TimepointModificationsService` at the top, and every existing test unpacks `bulk_set_from_bytes` as `updated, skipped, errors, feedbacks` — follow that convention exactly. It also has a `_seed_experiment_with_result` helper; this test needs two colliding experiments and reaches the ambiguity check before any timepoint lookup, so it seeds directly.

```python
def test_ambiguous_experiment_id_reports_candidates(db_session: Session):
    """An ambiguous ID must name both candidates, not just say 'not found'.

    AMBTPM_1 and AMBTPM_001 share the normalized key ambtpm_1, so .first() used
    to attach the modification to whichever row came back.
    """
    db_session.add_all([
        Experiment(experiment_id="AMBTPM_1", experiment_number=8806001,
                   status=ExperimentStatus.ONGOING),
        Experiment(experiment_id="AMBTPM_001", experiment_number=8806002,
                   status=ExperimentStatus.ONGOING),
    ])
    db_session.flush()

    xlsx = make_excel(
        ["experiment_id", "time_point", "modification_description"],
        [["ambtpm-01", 7.0, "swapped brine"]],
    )
    updated, skipped, errors, _ = TimepointModificationsService.bulk_set_from_bytes(
        db_session, xlsx
    )

    assert updated == 0
    assert any("ambiguous" in e.lower() for e in errors), errors
    assert any("AMBTPM_1" in e and "AMBTPM_001" in e for e in errors), errors
```

The three header names are all accepted aliases (`_EXPERIMENT_ID_ALIASES`, `_TIME_POINT_ALIASES`, `_MODIFICATION_ALIASES` at `timepoint_modifications.py:14-22`), so `_resolve_col` finds every column and the parser reaches the experiment lookup rather than short-circuiting on "Missing required columns".

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_timepoint_modifications.py -v -k ambiguous
```

Expected: FAIL — the error string reads `experiment 'ambtpm-01' not found`, with no candidates and no "ambiguous".

- [ ] **Step 3: Implement**

Change the import at line 12 from:

```python
from backend.services.bulk_uploads._id_match import fuzzy_find_experiment
```

to:

```python
from backend.services.bulk_uploads._id_match import find_experiment_matches
```

Replace lines 142-146:

```python
            # --- Resolve experiment (fuzzy: case-insensitive, symbols stripped) ---
            experiment = fuzzy_find_experiment(db, exp_id)
            if not experiment:
                errors.append(f"Row {row_num}: experiment '{exp_id}' not found")
                continue
```

with:

```python
            # --- Resolve experiment (fuzzy: case-insensitive, symbols stripped) ---
            # All matches, not .first(): two stored IDs can share a normalized key,
            # and picking one silently attached the modification to the wrong
            # experiment. Name both so the researcher can use the exact ID.
            matches = find_experiment_matches(db, exp_id)
            if len(matches) > 1:
                candidates = ", ".join(sorted(e.experiment_id for e in matches))
                errors.append(
                    f"Row {row_num}: experiment '{exp_id}' is ambiguous - it matches "
                    f"{len(matches)} experiments: {candidates}. Use the exact experiment_id."
                )
                continue
            if not matches:
                errors.append(f"Row {row_num}: experiment '{exp_id}' not found")
                continue
            experiment = matches[0]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_timepoint_modifications.py -v
```

Expected: all pass, new test included.

- [ ] **Step 5: Run the full backend suite**

```bash
.venv/Scripts/pytest -q
```

Expected: `3 failed, <N> passed, 4 skipped` where the 3 are `tests/test_pg_backup_restore.py`. One process only.

- [ ] **Step 6: Commit**

```bash
git add backend/services/bulk_uploads/timepoint_modifications.py tests/services/bulk_uploads/test_timepoint_modifications.py
git commit -m "$(cat <<'EOF'
[fix] Name both candidates on an ambiguous upload row

- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Record the new contract and the untouched siblings

**Files:**
- Create: `docs/issues/issue-fuzzy-experiment-id-conflation.md`
- Modify: `docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md` ("Out of scope" item 1)
- Modify: `.claude/rules/MODELS.md` (`Canonical ID parser` bullet under `Experiment`)

**Interfaces:**
- Consumes: everything shipped in Tasks 1-4.
- Produces: nothing. Documentation only, no test.

The `PostToolUse` hook copies anything written under `docs/` into `docs/project_context/` automatically. **Do not write there directly**; commit what appears.

- [ ] **Step 1: Write the issue record**

Create `docs/issues/issue-fuzzy-experiment-id-conflation.md`:

```markdown
# bug: `normalize_id` conflated real experiments, and the finders resolved it by guessing

> **Status 2026-08-05 — FIXED.** Branch `fix/id-match-ambiguity`. Found during
> the issue #109 investigation and recorded there as out of scope; this is the
> follow-through.

## Root cause

`backend/services/bulk_uploads/_id_match.py::normalize_id` deleted every
non-alphanumeric character **and** stripped leading zeros from numeric
segments, so a sequential re-run collapsed onto an unrelated experiment:
`SERUM_JW_010-2` and `SERUM_JW_102` both became `serumjw102`.
`fuzzy_find_experiment` then returned `.first()` of the normalized scan — an
arbitrary one of the two, with nothing logged. A bulk upload could attach
results to the wrong experiment silently.

Measured against the dev DB, 2026-08-05:

- **13 experiment pairs** collided (1009 experiments): `SERUM_JW_092/009-2`,
  `102/010-2`, `112/011-2`, `122/012_2`, `123/012_3`, `132/013_2`, `133/013-3`,
  `142/014_2`, `143/014-3`, `152/015_2`, `153/015-3`, `162/016_2`, `163/016-3`.
- **3 sample pairs** collided (680 samples), via the same key through
  `fuzzy_find_sample`: `23UM042/23UM004.2`, `23UM052/23UM005.2`,
  `202505255?/20250525_5`. Not previously recorded anywhere.

## What shipped

1. **Run-delimited `normalize_id`.** Split into maximal alpha/digit runs, strip
   leading zeros inside each digit run, join with `_`. `SERUM_JW_010-2` ->
   `serum_jw_10_2`, `SERUM_JW_102` -> `serum_jw_102`.
   This is a **strict refinement**: equal new keys imply identical run
   sequences, which imply equal old keys, so it can only split an old
   equivalence class, never merge two. Collision count on the dev DB is now
   **0 for experiments and 0 for samples**.
   Every equivalence the finders rely on survives, including the missing
   separator: `HPHT001`, `HPHT_001`, `HPHT-001`, `HPHT_1` all -> `hpht_1`.
2. **The finders no longer guess.** `find_experiment_matches` /
   `find_sample_matches` return **all** matches; `fuzzy_find_experiment` /
   `fuzzy_find_sample` return `None` on 0 **or** >1 and log a structlog
   warning (`ambiguous_experiment_id` / `ambiguous_sample_id`) naming the
   candidates. Signatures unchanged, so no caller broke.
3. **`ScalarResultsService._find_experiment` raises
   `AmbiguousExperimentIdError`** (a `ValueError`) instead of returning `None`.
   This one is load-bearing: `create_scalar_result_ex` treats `None` as "not
   found" and falls through to `auto_create_treatment_experiment`, so a silent
   `None` would have **fabricated an experiment row**.
   `get_scalar_results_for_experiment` (a read helper behind a GET) catches it
   and returns `[]` rather than 500ing.
4. **`timepoint_modifications.py` reports both candidates** in its row error
   instead of "not found".

## Accepted leniency losses

Two documented equivalences are gone on purpose, both cases where the old key
was guessing:

- `HPHT_0014B` (`hpht_14_b`) no longer matches `HPHT_001_4B` (`hpht_1_4_b`).
- The 13 experiment pairs and 3 sample pairs above.

A workbook ID that no longer matches gets the existing "not found" row error,
which a researcher fixes by using the exact ID. A clean failure beats a silent
wrong attachment.

## Out of scope — recorded, not fixed

**Three sibling finders still end in `.first()`.**
`backend/services/icp_service.py:757`,
`backend/services/bulk_uploads/aeris_xrd.py:46` and
`backend/services/bulk_uploads/xrd_upload.py:63` each hand-roll their own
delimiter-stripping SQL lookup. None of them strips leading zeros, so **none
has the 13-pair defect** — a collision check on a delimiter-only key across all
1009 dev experiment IDs returns **0 groups** (verified 2026-08-05). They keep
the latent habit: a future ID pair differing only in separators would resolve
arbitrarily. Consolidating them onto `find_experiment_matches` would touch two
more locked parsers and their suites, so it needs its own `/start-task`.
```

- [ ] **Step 2: Close the out-of-scope item in the #109 doc**

In `docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md`, replace out-of-scope item 1 (`**`_id_match.py::normalize_id` conflates 13 real experiment pairs.**` …) with:

```markdown
1. **`_id_match.py::normalize_id` conflated 13 real experiment pairs — FIXED
   2026-08-05** on branch `fix/id-match-ambiguity`. `normalize_id` is now
   run-delimited (0 collisions on the dev DB, experiments and samples), and the
   finders return all matches rather than `.first()`, so an ambiguous ID is
   reported instead of resolved by luck. Full record:
   `docs/issues/issue-fuzzy-experiment-id-conflation.md`.
```

- [ ] **Step 3: Note the new key in `.claude/rules/MODELS.md`**

Append to the `**Canonical ID parser:**` bullet under `Experiment`:

```markdown
    Separate from the parser, `backend/services/bulk_uploads/_id_match.py::normalize_id`
    is the canonical **fuzzy match key** used to resolve a workbook's ID spelling
    against a stored one. It is run-delimited (alpha/digit runs, leading zeros
    stripped per digit run, joined with `_`) — deliberately *not* a plain
    strip-and-concatenate, which collapsed `SERUM_JW_010-2` onto `SERUM_JW_102`
    (13 real pairs). The finders return **all** matches; nothing resolves an
    ambiguous key. See `docs/issues/issue-fuzzy-experiment-id-conflation.md`.
```

- [ ] **Step 4: Verify the hook synced project_context**

```bash
git status --short docs/project_context/
```

Expected: the new issue doc and the #109 doc appear there as new/modified. If not, re-run the `Edit`/`Write` on the `docs/` original — never write into `project_context/` by hand.

- [ ] **Step 5: Commit**

```bash
git add docs/issues/ .claude/rules/MODELS.md docs/project_context/
git commit -m "$(cat <<'EOF'
[fix] Record the ID-conflation fix and its contract

- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Definition of done

- [ ] `.venv/Scripts/pytest -q` → `3 failed` and they are all `tests/test_pg_backup_restore.py`
- [ ] `.venv/Scripts/pytest tests/services/bulk_uploads/ -q` → fully green
- [ ] The Task 1 Step 5 collision script prints `colliding groups=0` for both experiments and samples
- [ ] No `.first()` remains in `_id_match.py` outside the exact-match fast paths — `grep -n "first()" backend/services/bulk_uploads/_id_match.py` shows only the two `== raw_id` queries
- [ ] No file under `backend/services/bulk_uploads/` other than `_id_match.py` and `timepoint_modifications.py` changed
- [ ] Follow `docs/GIT_WORKFLOW.md`, then `/complete-task`. PR with `gh pr create --base develop`
