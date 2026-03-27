# Issue #14: Fuzzy Matching for Master Result Upload Sync

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply full fuzzy experiment-ID matching (force lowercase, strip all symbols, strip leading zeros) to the Master Results bulk upload sync, which currently uses an incomplete normalization that misses symbols other than `-`/`_` and doesn't strip leading zeros.

**Architecture:** Two-layer fix — (1) extend `normalize_id` in the shared `_id_match.py` helper to add leading-zero stripping, then (2) replace `ScalarResultsService._find_experiment`'s hand-rolled SQL normalization with a call to the shared `fuzzy_find_experiment`. No new files; no schema changes.

**Tech Stack:** Python 3.x, SQLAlchemy ORM, pytest, PostgreSQL (test DB at `postgresql://experiments_user:password@localhost:5432/experiments_test`)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/services/bulk_uploads/_id_match.py` | Modify | Add leading-zero stripping to `normalize_id`; update module docstring examples |
| `backend/services/scalar_results_service.py` | Modify | Replace `_find_experiment`'s custom SQL normalization with `fuzzy_find_experiment` |
| `tests/services/bulk_uploads/test_id_match.py` | Create | Unit tests for `normalize_id` (all three normalization rules) |
| `tests/services/bulk_uploads/test_master_bulk_upload.py` | Modify | Add integration tests for fuzzy-matched experiment IDs in master upload |

---

## Task 1: Unit-test `normalize_id` (currently missing tests)

**Files:**
- Create: `tests/services/bulk_uploads/test_id_match.py`

These tests are pure Python — no DB required. Run them in any environment.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/bulk_uploads/test_id_match.py`:

```python
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
```

- [ ] **Step 2: Run to confirm tests fail**

```
pytest tests/services/bulk_uploads/test_id_match.py -v
```

Expected: several cases FAIL because `normalize_id` currently produces `"hpht001"` not `"hpht1"` for leading-zero inputs.

---

## Task 2: Implement leading-zero stripping in `normalize_id`

**Files:**
- Modify: `backend/services/bulk_uploads/_id_match.py`

- [ ] **Step 1: Update `normalize_id` and the module docstring**

Replace the entire module header and `normalize_id` function (lines 1–28) with:

```python
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
```

Leave `fuzzy_find_sample` and `fuzzy_find_experiment` unchanged — they call `normalize_id` so they inherit the new behaviour automatically.

- [ ] **Step 2: Run the Task 1 tests to confirm they now pass**

```
pytest tests/services/bulk_uploads/test_id_match.py -v
```

Expected: all parametrize cases PASS.

- [ ] **Step 3: Run full bulk-upload test suite to check for regressions**

```
pytest tests/services/bulk_uploads/ -v
```

Expected: all existing tests PASS (no regressions from the stricter normalization).

- [ ] **Step 4: Commit**

```bash
git add backend/services/bulk_uploads/_id_match.py \
        tests/services/bulk_uploads/test_id_match.py
git commit -m "[#14] Add leading-zero stripping to normalize_id

- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Write failing integration tests for master upload fuzzy matching

**Files:**
- Modify: `tests/services/bulk_uploads/test_master_bulk_upload.py`

These tests expose the second bug: `ScalarResultsService._find_experiment` uses
its own partial normalization and doesn't call `fuzzy_find_experiment`, so the
master upload can't resolve IDs with symbols other than `-`/`_` or leading zeros.

- [ ] **Step 1: Add three new test functions at the bottom of the file**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
# ---------------------------------------------------------------------------
# Fuzzy-matching tests (Issue #14)
# ---------------------------------------------------------------------------

def test_from_bytes_matches_experiment_with_leading_zeros(db_session: Session):
    """DB stores 'HPHT_1'; spreadsheet contains 'HPHT_001' — should match."""
    _seed_experiment(db_session, "HPHT_1", 7801)

    xlsx = _master_excel([
        ["HPHT_001", 5.0, "Day 5", None, None, None, None,
         3.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert feedbacks[0]["action"] == "created"


def test_from_bytes_matches_experiment_with_dot_separator(db_session: Session):
    """DB stores 'Serum_MH_101'; spreadsheet contains 'Serum.MH.101' — should match."""
    _seed_experiment(db_session, "Serum_MH_101", 7802)

    xlsx = _master_excel([
        ["Serum.MH.101", 10.0, "Day 10", None, None, None, None,
         None, None, None, None, 6.8, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert feedbacks[0]["action"] == "created"


def test_from_bytes_matches_experiment_with_leading_zeros_and_symbols(db_session: Session):
    """Combined: DB stores 'HPHT_14B'; spreadsheet uses 'HPHT-014B' — should match."""
    _seed_experiment(db_session, "HPHT_14B", 7803)

    xlsx = _master_excel([
        ["HPHT-014B", 3.0, "Day 3", None, None, None, None,
         None, None, None, None, 7.5, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert feedbacks[0]["action"] == "created"
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```
pytest tests/services/bulk_uploads/test_master_bulk_upload.py::test_from_bytes_matches_experiment_with_leading_zeros \
       tests/services/bulk_uploads/test_master_bulk_upload.py::test_from_bytes_matches_experiment_with_dot_separator \
       tests/services/bulk_uploads/test_master_bulk_upload.py::test_from_bytes_matches_experiment_with_leading_zeros_and_symbols \
       -v
```

Expected: all three FAIL with errors like `"Experiment with ID 'HPHT_001' not found"`.

---

## Task 4: Fix `ScalarResultsService._find_experiment` to use `fuzzy_find_experiment`

**Files:**
- Modify: `backend/services/scalar_results_service.py:319-338`

The current `_find_experiment` builds its own SQL normalization that only strips
hyphens and underscores. Replace it with a call to the shared `fuzzy_find_experiment`.
The `joinedload(conditions)` eager-load is dropped — conditions are not accessed
during scalar result creation, so lazy-loading is fine.

- [ ] **Step 1: Replace the `_find_experiment` method body**

In `backend/services/scalar_results_service.py`, find the `_find_experiment` static
method (around line 319) and replace it entirely with:

```python
@staticmethod
def _find_experiment(db: Session, experiment_id: str) -> Optional[Experiment]:
    """Find an experiment by ID using full fuzzy normalization.

    Delegates to ``fuzzy_find_experiment`` from ``_id_match``, which normalizes
    by lowercasing, stripping all non-alphanumeric characters, and stripping
    leading zeros from numeric segments.
    """
    from backend.services.bulk_uploads._id_match import fuzzy_find_experiment  # noqa: PLC0415
    return fuzzy_find_experiment(db, experiment_id)
```

The `func` import at the top of the file (line 3: `from sqlalchemy import func`) can
now be removed **only if** nothing else in the file uses it. Check with:

```bash
grep -n "func\." backend/services/scalar_results_service.py
```

If the only match was inside the old `_find_experiment`, remove the `func` import.
If other usages exist, leave the import.

- [ ] **Step 2: Run the three new tests to confirm they now pass**

```
pytest tests/services/bulk_uploads/test_master_bulk_upload.py::test_from_bytes_matches_experiment_with_leading_zeros \
       tests/services/bulk_uploads/test_master_bulk_upload.py::test_from_bytes_matches_experiment_with_dot_separator \
       tests/services/bulk_uploads/test_master_bulk_upload.py::test_from_bytes_matches_experiment_with_leading_zeros_and_symbols \
       -v
```

Expected: all three PASS.

- [ ] **Step 3: Run the full test suite for affected areas**

```
pytest tests/services/bulk_uploads/ tests/services/ -v
```

Expected: all existing and new tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/services/scalar_results_service.py \
        tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "[#14] Wire _find_experiment to fuzzy_find_experiment

- Tests added: yes
- Docs updated: no"
```

---

## Task 5: Log in issue-log and close the GitHub issue

**Files:**
- Modify: `docs/working/issue-log.md`

- [ ] **Step 1: Append entry to issue-log**

Append to the bottom of `docs/working/issue-log.md`:

```markdown
## 2026-03-27 | issue #14 — Fuzzy matching for master result upload sync
- **Files changed:**
  - `backend/services/bulk_uploads/_id_match.py` — added leading-zero stripping step to `normalize_id`; updated module docstring examples
  - `backend/services/scalar_results_service.py` — replaced `_find_experiment`'s hand-rolled SQL normalization with `fuzzy_find_experiment` from `_id_match`
  - `tests/services/bulk_uploads/test_id_match.py` — created: 15 parametrized unit tests for `normalize_id` (force lower, strip symbols, strip leading zeros)
  - `tests/services/bulk_uploads/test_master_bulk_upload.py` — added 3 integration tests for fuzzy-matched IDs in master upload
- **Tests added:** yes
- **Decision logged:** no
```

- [ ] **Step 2: Commit**

```bash
git add docs/working/issue-log.md
git commit -m "[#14] Log issue-14 fix in issue-log

- Tests added: no
- Docs updated: yes"
```

- [ ] **Step 3: Open a PR targeting `develop`**

```bash
gh pr create \
  --base develop \
  --title "[#14] Fuzzy matching for master result upload sync" \
  --body "## Summary
- Extends \`normalize_id\` in \`_id_match.py\` to strip leading zeros from numeric segments (e.g. \`HPHT_001\` → \`hpht1\`).
- Replaces \`ScalarResultsService._find_experiment\`'s partial SQL normalization with the shared \`fuzzy_find_experiment\`, matching the pattern already used by \`timepoint_modifications.py\`.
- Adds 15 unit tests for \`normalize_id\` and 3 integration tests for master upload fuzzy matching.

Closes #14"
```

---

## Self-Review

**Spec coverage:**
- ✅ Force lowercase — covered by existing `normalize_id`; tested in Task 1
- ✅ Remove symbols (all non-alphanumeric, not just `-`/`_`) — covered by existing regex; tested with dot, slash, parens in Task 1
- ✅ Remove leading zeros — added in Task 2; tested in Task 1 (unit) and Task 3 (integration)
- ✅ Master upload sync uses the fuzzy matching — fixed in Task 4; integration tests in Task 3 prove it

**Placeholder scan:** No TBD/TODO. All code blocks are complete.

**Type consistency:**
- `normalize_id(raw: str) -> str` — consistent across Tasks 1 and 2
- `fuzzy_find_experiment(db: Session, raw_id: str) -> Optional[Experiment]` — unchanged signature, used correctly in Task 4
- `_find_experiment(db: Session, experiment_id: str) -> Optional[Experiment]` — return type preserved

**Edge case: `"20250502_2A"` normalization**

The regex `(?<!\d)0+(?=\d)` will NOT incorrectly strip zeros from date-style IDs like `"20250502_2A"`:
- After symbol strip: `"202505022a"`
- The `0` in position 4 is preceded by `5` (a digit) → lookbehind `(?<!\d)` does NOT match → zero preserved ✓
- Result: `"202505022a"` — correct, matches the module docstring example.
