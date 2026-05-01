# Issue #54: Fix parse_experiment_id Misclassification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `parse_experiment_id` so that `TYPE-NNN` style IDs like `CF-015`, `CF-04`, and `CF-12` are recognised as standalone base experiments, not sequential derivations of a phantom parent.

**Architecture:** The fix restructures the two-step parsing in `parse_experiment_id`: (1) strip treatment variant first (underscore-TEXT suffix), then (2) apply a prefix-rule gate before accepting a trailing `-N` as a sequential derivation — the prefix must itself end in `_digits` or `-digits` to confirm it already carries a numeric index. Two stale test assertions are updated to reflect real naming conventions, and the pre-existing test failure for `HPHT_MH_001-2_Desorption` is resolved as a side-effect. After deploying the fix, `establish_experiment_lineage_006.py` must be re-run on the live database to repair the corrupted lineage records.

**Tech Stack:** Python 3.x, SQLAlchemy, pytest, regex (`re` stdlib)

---

## File Map

| File | Change |
|------|--------|
| `database/lineage_utils.py` | Restructure lines 70-104 of `parse_experiment_id`; add `import re` |
| `tests/test_lineage_migration.py` | Update 2 stale assertions (lines 130, 133); fix 1 pre-existing failure (line 144); add 5 new assertions |

No migrations, no schema changes, no new packages.

---

### Task 1: Update tests to reflect new expectations (write failing tests first)

**Files:**
- Modify: `tests/test_lineage_migration.py:121-150`

The `test_parse_experiment_id` method is a pure unit test with no DB fixture. It currently has three problems:
- Line 130 (`COMPLEX-ID-TEST-3 → ("COMPLEX-ID-TEST", 3, None)`) expects a synthetic pattern that real experiment IDs don't follow
- Line 133 (`TEST-SAMPLE-001 → ("TEST-SAMPLE", 1, None)`) same synthetic pattern  
- Line 144 (`HPHT_MH_001-2_Desorption → ("HPHT_MH_001", 2, "Desorption")`) already **fails** against current code

Replace the entire `test_parse_experiment_id` method body with the version below. The five new CF assertions and the corrected combined-sequential-treatment assertion are the ones that will **fail** until Task 2 is done.

- [ ] **Step 1: Replace the test method**

In `tests/test_lineage_migration.py`, replace the full body of `test_parse_experiment_id` (lines 122–150) with:

```python
    def test_parse_experiment_id(self):
        """Test parsing of experiment IDs to identify derivations and treatments."""
        # Base experiments — underscore-index format
        assert parse_experiment_id("HPHT_MH_001") == ("HPHT_MH_001", None, None)
        assert parse_experiment_id("LEACH_TEST") == ("LEACH_TEST", None, None)

        # Sequential derivations — prefix must end in _digits or -digits
        assert parse_experiment_id("HPHT_MH_001-2") == ("HPHT_MH_001", 2, None)
        assert parse_experiment_id("HPHT_MH_001-10") == ("HPHT_MH_001", 10, None)
        assert parse_experiment_id("HPHT_001-2") == ("HPHT_001", 2, None)

        # CF-style IDs: TYPE-NNN — the prefix ("CF") does NOT end in digits,
        # so these are standalone base experiments, not derivations.
        assert parse_experiment_id("CF-015") == ("CF-015", None, None)
        assert parse_experiment_id("CF-12") == ("CF-12", None, None)
        assert parse_experiment_id("CF-04") == ("CF-04", None, None)

        # CF-015-2 IS a derivation because its prefix "CF-015" ends in -015 (digits)
        assert parse_experiment_id("CF-015-2") == ("CF-015", 2, None)

        # Former synthetic test cases — now recognised as base experiments
        # (their prefixes don't end in digits, so trailing -N is not a derivation)
        assert parse_experiment_id("COMPLEX-ID-TEST-3") == ("COMPLEX-ID-TEST-3", None, None)
        assert parse_experiment_id("TEST-SAMPLE-001") == ("TEST-SAMPLE-001", None, None)

        # Non-derivations with hyphens (last part is NOT numeric)
        assert parse_experiment_id("TEST-SAMPLE-ABC") == ("TEST-SAMPLE-ABC", None, None)
        assert parse_experiment_id("HPHT-HIGH-TEMP") == ("HPHT-HIGH-TEMP", None, None)

        # Treatment variants (underscore-TEXT suffix)
        assert parse_experiment_id("HPHT_MH_001_Desorption") == ("HPHT_MH_001", None, "Desorption")
        assert parse_experiment_id("Serum_MH_101_Annealing") == ("Serum_MH_101", None, "Annealing")

        # Combined sequential + treatment — treatment stripped first, then sequential detected
        assert parse_experiment_id("HPHT_MH_001-2_Desorption") == ("HPHT_MH_001", 2, "Desorption")
        assert parse_experiment_id("Serum_MH_101-3_Annealing") == ("Serum_MH_101", 3, "Annealing")

        # Edge cases
        assert parse_experiment_id("") == (None, None, None)
        assert parse_experiment_id(None) == (None, None, None)
        assert parse_experiment_id("   ") == (None, None, None)
```

- [ ] **Step 2: Run the test to confirm failures**

```bash
cd experiment_tracking_sandbox
.venv/Scripts/python -m pytest tests/test_lineage_migration.py::TestExperimentLineageMigration::test_parse_experiment_id -v
```

Expected: **FAILED** — assertions for `CF-015`, `CF-12`, `CF-04`, `CF-015-2`, `COMPLEX-ID-TEST-3`, `TEST-SAMPLE-001`, and `HPHT_MH_001-2_Desorption` will fail against the current implementation.

---

### Task 2: Fix `parse_experiment_id` logic

**Files:**
- Modify: `database/lineage_utils.py:1-104`

The existing logic runs sequential-extraction before treatment-extraction, which breaks combined IDs like `HPHT_MH_001-2_Desorption` (the `-2_Desorption` suffix fails `.isdigit()` so sequential is missed). It also has no prefix guard, so `CF-015` is wrongly treated as `base='CF', deriv=15`.

The fix does two things:
1. Extracts treatment first (underscore-TEXT suffix), then checks for sequential.
2. Gates sequential detection: only accept trailing `-N` when the prefix itself ends in `[_-]\d+` (confirming a numeric index already exists in the name).

- [ ] **Step 3: Add `import re` and rewrite `parse_experiment_id`**

In `database/lineage_utils.py`, add `import re` after the `from __future__ import annotations` line, then replace the body of `parse_experiment_id` (lines 63–104) with:

```python
    if not experiment_id or not isinstance(experiment_id, str):
        return None, None, None

    experiment_id = experiment_id.strip()
    if not experiment_id:
        return None, None, None

    treatment_variant = None
    derivation_num = None
    base_id = experiment_id

    # Step 1: Extract treatment variant (trailing _TEXT segment).
    # A trailing underscore segment is a treatment only when:
    #   - it contains no hyphens (so "001-2" is not mistaken for a treatment)
    #   - it is not all digits (so "001" index segments are left alone)
    #   - removing it still leaves a structured ID with ≥ 2 underscore-segments
    #     (prevents "CF_Desorption" from stripping "Desorption" off a 1-part base)
    parts = experiment_id.split('_')
    if len(parts) >= 2:
        last = parts[-1]
        if not last.isdigit() and '-' not in last:
            remaining = '_'.join(parts[:-1])
            if len(remaining.split('_')) >= 2:
                treatment_variant = last
                base_id = remaining

    # Step 2: Extract sequential derivation number (trailing -N).
    # Only treat -N as a derivation when the prefix already ends in _NNN or -NNN,
    # confirming it carries a numeric index (e.g. HPHT_MH_001, CF-015).
    # This prevents TYPE-NNN IDs like CF-015 from being parsed as deriv=15 of "CF".
    if '-' in base_id:
        prefix, _, suffix = base_id.rpartition('-')
        if suffix.isdigit() and re.search(r'[_-]\d+$', prefix):
            derivation_num = int(suffix)
            base_id = prefix

    return base_id, derivation_num, treatment_variant
```

The full updated imports block at the top of `database/lineage_utils.py` should be:

```python
from __future__ import annotations

import re
from typing import Optional, Tuple, TYPE_CHECKING
from sqlalchemy.orm import Session
from sqlalchemy import func
```

Also update the docstring examples in `parse_experiment_id` to add the CF cases and remove the stale `TEST-SAMPLE-001` example:

```python
    """
    Parse an experiment ID to extract the base ID, derivation number, and treatment variant.

    Uses hybrid delimiter system:
    - Hyphen-NUMBER for sequential lineage (e.g., -2, -3), but ONLY when the prefix
      itself ends in a numeric segment (_NNN or -NNN).
    - Underscore-TEXT for treatment variants (e.g., _Desorption).

    TYPE-NNN IDs (e.g., CF-015, CF-04) are treated as standalone base experiments
    because their prefix ("CF") does not end in digits.

    Args:
        experiment_id: The experiment ID to parse

    Returns:
        A tuple of (base_experiment_id, derivation_number, treatment_variant)

    Examples:
        >>> parse_experiment_id("CF-015")
        ("CF-015", None, None)
        >>> parse_experiment_id("CF-015-2")
        ("CF-015", 2, None)
        >>> parse_experiment_id("HPHT_MH_001-2")
        ("HPHT_MH_001", 2, None)
        >>> parse_experiment_id("HPHT_MH_001-2_Desorption")
        ("HPHT_MH_001", 2, "Desorption")
        >>> parse_experiment_id("HPHT_MH_001")
        ("HPHT_MH_001", None, None)
        >>> parse_experiment_id("HPHT_MH_001_Desorption")
        ("HPHT_MH_001", None, "Desorption")
    """
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/Scripts/python -m pytest tests/test_lineage_migration.py::TestExperimentLineageMigration::test_parse_experiment_id -v
```

Expected: **PASSED** — all assertions green.

- [ ] **Step 5: Commit**

```bash
git add database/lineage_utils.py tests/test_lineage_migration.py
git commit -m "[#54] fix parse_experiment_id prefix-check for TYPE-NNN IDs

- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Update issue log and prepare data migration notes

**Files:**
- Modify: `docs/working/issue-log.md`

- [ ] **Step 6: Append to issue log**

Append this entry to `docs/working/issue-log.md`:

```markdown
## 2026-04-30 | issue #54 — Fix parse_experiment_id misclassification of TYPE-NNN IDs
- **Files changed:**
  - `database/lineage_utils.py` — restructured `parse_experiment_id`: treatment extracted before sequential check; sequential gate now requires prefix to end in `[_-]\d+`; `import re` added
  - `tests/test_lineage_migration.py` — updated 2 stale assertions (COMPLEX-ID-TEST-3, TEST-SAMPLE-001); added 5 new assertions (CF-015, CF-12, CF-04, CF-015-2, HPHT_001-2); fixed pre-existing failure for HPHT_MH_001-2_Desorption
- **Tests added:** yes — 5 new assertions in test_parse_experiment_id
- **Decision logged:** no
- **⚠ Data migration required:** Re-run `establish_experiment_lineage_006.py` on the live database to correct corrupted parent-child links for CF-015, CF-04, CF-12 and any other TYPE-NNN experiments. See Task 4 below.
```

- [ ] **Step 7: Commit**

```bash
git add docs/working/issue-log.md
git commit -m "[#54] update issue log"
```

---

### Task 4: Re-run lineage migration on the live database

**Files:** none (runtime only)

This task corrects the corrupted lineage records already in the database. It uses the existing idempotent migration script — now that `parse_experiment_id` is fixed, running it again will overwrite the wrong `base_experiment_id` and `parent_experiment_fk` values with correct ones.

> **When to run:** After this branch is merged to `develop` and deployed to the lab PC via `update.ps1`.

- [ ] **Step 8: Dry-run the migration (confirm what will change)**

From the lab PC (or any machine pointing at the live DB):

```bash
cd experiment_tracking_sandbox
.venv/Scripts/python database/data_migrations/establish_experiment_lineage_006.py --dry-run
```

Expected output will list experiments being re-linked. Look for lines like:
```
  CF-015 -> base: CF-015   (corrected from base: CF)
  CF-04  -> base: CF-04    (corrected from base: CF)
  CF-12  -> base: CF-12    (corrected from base: CF)
```
These should now show as base experiments (no "Found derivation:" prefix).

- [ ] **Step 9: Run the migration**

```bash
.venv/Scripts/python database/data_migrations/establish_experiment_lineage_006.py
```

Expected summary:
- `Experiments scanned`: total count of all experiments
- `Derivations found`: should be lower than before (CF-style IDs no longer counted as derivations)
- `Errors: 0`

- [ ] **Step 10: Verify specific experiments**

```bash
.venv/Scripts/python -c "
from database import SessionLocal
from database.models import Experiment
db = SessionLocal()
for exp_id in ['CF-015', 'CF-04', 'CF-12']:
    e = db.query(Experiment).filter_by(experiment_id=exp_id).first()
    if e:
        print(f'{exp_id}: base={e.base_experiment_id}, parent_fk={e.parent_experiment_fk}')
    else:
        print(f'{exp_id}: not found in DB')
db.close()
"
```

Expected for each: `base_experiment_id == exp_id` and `parent_experiment_fk == None`.

---

## Self-Review

**Spec coverage:**
- ✅ `CF-015` / `CF-12` / `CF-04` → base: covered in Task 1 (test) + Task 2 (fix)
- ✅ `CF-015-2` → sequential base=CF-015: covered in Task 1 + Task 2
- ✅ `HPHT_001-2` → sequential base=HPHT_001: covered in Task 1 + Task 2
- ✅ Test cases for COMPLEX-ID-TEST-3 and TEST-SAMPLE-001 updated: Task 1
- ✅ DB lineage re-migration: Task 4
- ✅ Pre-existing failure for HPHT_MH_001-2_Desorption fixed as side-effect of new algorithm: Task 1 + Task 2

**Placeholder scan:** None found.

**Type consistency:** `parse_experiment_id` signature unchanged (`Tuple[Optional[str], Optional[int], Optional[str]]`). All callers (`get_or_find_parent_experiment`, `update_experiment_lineage`, `auto_create_treatment_experiment`, `event_listeners.py`) destructure the same 3-tuple — no changes needed.
