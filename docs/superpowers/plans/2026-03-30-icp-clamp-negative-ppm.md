# ICP Negative PPM Clamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clamp all ICP element ppm values to zero on upload (negative readings are instrument noise below detection limit) and back-fill existing negative values in the database.

**Architecture:** Two-part fix — (1) a one-line guard in `ICPService.process_icp_dataframe` prevents negative values from ever reaching the database on future uploads; (2) an Alembic data migration back-fills all 27 fixed ICP element columns in `icp_results` by setting any existing negative float to 0. A merge migration is needed first because the migration chain currently has two open heads.

**Tech Stack:** Python 3, SQLAlchemy, Alembic, PostgreSQL, pytest

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Modify | `backend/services/icp_service.py` | Line 351 — `max(0.0, ...)` clamp in `process_icp_dataframe` |
| Create | `alembic/versions/<hash>_merge_heads_before_icp_clamp.py` | Merge migration joining the two current heads |
| Create | `alembic/versions/<hash>_clamp_negative_icp_ppm_to_zero.py` | Data migration — UPDATE rows with negative element values |
| Modify | `tests/test_icp_service.py` | Add a test for negative-value clamping in `process_icp_dataframe` |

---

### Task 1: Add negative-value test to `test_icp_service.py`

**Files:**
- Modify: `tests/test_icp_service.py`

- [ ] **Step 1: Append the failing test**

Add this function to the bottom of `tests/test_icp_service.py`:

```python
def test_negative_concentration_clamped_to_zero():
    """Negative ICP concentrations (instrument noise) must be stored as 0, not negative."""
    test_data = {
        'Label': ['Serum_MH_011_Day5_5x'],
        'Type': ['SAMP'],
        'Element Label': ['Fe 238.204'],
        'Concentration': [-0.003],   # negative — below detection limit
        'Intensity': [1.2],
    }

    df = pd.DataFrame(test_data)
    processed_data, errors = ICPService.process_icp_dataframe(df)

    assert not errors, f"Unexpected errors: {errors}"
    assert len(processed_data) == 1
    fe_val = processed_data[0].get('fe')
    assert fe_val == 0.0, f"Expected 0.0 for negative concentration, got {fe_val}"
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /c/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox
.venv/Scripts/python -m pytest tests/test_icp_service.py::test_negative_concentration_clamped_to_zero -v
```

Expected: **FAIL** — the test asserts `fe == 0.0` but the current code stores the raw negative value.

---

### Task 2: Apply the clamp in `ICPService.process_icp_dataframe`

**Files:**
- Modify: `backend/services/icp_service.py` (line 351)

- [ ] **Step 1: Apply the one-line fix**

In `backend/services/icp_service.py`, find line 351 (inside `process_icp_dataframe`, the pivot loop):

```python
# BEFORE
concentration_val = float(concentration) if pd.notna(concentration) else 0.0
```

Replace with:

```python
# AFTER
concentration_val = max(0.0, float(concentration)) if pd.notna(concentration) else 0.0
```

- [ ] **Step 2: Run the test to confirm it passes**

```bash
.venv/Scripts/python -m pytest tests/test_icp_service.py::test_negative_concentration_clamped_to_zero -v
```

Expected: **PASS**

- [ ] **Step 3: Run the broader ICP test suite to check for regressions**

```bash
.venv/Scripts/python -m pytest tests/test_icp_service.py tests/test_icp_parsing.py tests/test_icp_handling.py -v
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/services/icp_service.py tests/test_icp_service.py
git commit -m "[fix] clamp negative ICP ppm values to zero on upload

- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Create a merge migration for the two open Alembic heads

There are currently two open heads (`a1b2c3d4e5f6` and `fe62b69c6571`). A new migration cannot be appended until these are merged.

**Files:**
- Create: `alembic/versions/<generated_hash>_merge_heads_before_icp_clamp.py`

- [ ] **Step 1: Generate the merge migration**

```bash
.venv/Scripts/alembic merge a1b2c3d4e5f6 fe62b69c6571 -m "merge heads before icp clamp"
```

Alembic prints the path of the new file, e.g.:
`alembic/versions/abcd1234_merge_heads_before_icp_clamp.py`

- [ ] **Step 2: Verify the generated file**

Open the generated file. It should look like:

```python
"""merge heads before icp clamp

Revision ID: <generated>
Revises: a1b2c3d4e5f6, fe62b69c6571
Create Date: <date>

"""
from typing import Sequence, Union

revision: str = '<generated>'
down_revision: Union[str, None] = ('a1b2c3d4e5f6', 'fe62b69c6571')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
```

`down_revision` must be the tuple `('a1b2c3d4e5f6', 'fe62b69c6571')`. No other changes are needed.

- [ ] **Step 3: Confirm single head**

```bash
.venv/Scripts/alembic heads
```

Expected: one head (the merge migration's revision ID).

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "[chore] merge alembic heads before icp clamp migration

- Tests added: no
- Docs updated: no"
```

---

### Task 4: Write and apply the data migration

**Files:**
- Create: `alembic/versions/<generated_hash>_clamp_negative_icp_ppm_to_zero.py`

- [ ] **Step 1: Generate an empty migration**

```bash
.venv/Scripts/alembic revision -m "clamp negative icp ppm to zero"
```

Alembic prints the path, e.g.:
`alembic/versions/bbbb2222_clamp_negative_icp_ppm_to_zero.py`

- [ ] **Step 2: Write the upgrade and downgrade functions**

Open the generated file and replace the `upgrade` and `downgrade` stubs with:

```python
# All 27 fixed ICP element columns in icp_results (ppm, must be >= 0)
_ICP_ELEMENT_COLUMNS = [
    'fe', 'si', 'ni', 'cu', 'mo', 'zn', 'mn', 'ca', 'cr', 'co', 'mg', 'al',
    'sr', 'y', 'nb', 'sb', 'cs', 'ba', 'nd', 'gd', 'pt', 'rh', 'ir',
    'pd', 'ru', 'os', 'tl',
]


def upgrade() -> None:
    """Set any negative ICP element ppm values to 0. NULLs are left untouched."""
    for col in _ICP_ELEMENT_COLUMNS:
        op.execute(
            f'UPDATE icp_results SET "{col}" = 0 WHERE "{col}" < 0'
        )


def downgrade() -> None:
    # Original negative values are not recoverable after this migration.
    # Downgrade is intentionally a no-op.
    pass
```

- [ ] **Step 3: Apply the migration against the dev database**

```bash
.venv/Scripts/alembic upgrade head
```

Expected: `Running upgrade <merge_head> -> <new_rev>, clamp negative icp ppm to zero`
No errors.

- [ ] **Step 4: Verify the migration worked (spot check)**

```bash
.venv/Scripts/python -c "
from database import engine
with engine.connect() as conn:
    from sqlalchemy import text
    cols = ['fe','si','ni','cu','mo','mg','al','ca','cr','co','zn','mn']
    for col in cols:
        result = conn.execute(text(f'SELECT COUNT(*) FROM icp_results WHERE \"{col}\" < 0')).scalar()
        print(f'{col}: {result} negative rows remaining')
"
```

Expected: all columns show `0 negative rows remaining`.

- [ ] **Step 5: Test the downgrade/upgrade cycle**

```bash
.venv/Scripts/alembic downgrade -1 && .venv/Scripts/alembic upgrade head
```

Expected: clean run with no errors. Downgrade is a no-op so data is unchanged.

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/
git commit -m "[fix] back-fill negative ICP ppm values to zero

- Tests added: no
- Docs updated: no"
```

---

### Task 5: Final validation

- [ ] **Step 1: Run all ICP-related tests**

```bash
.venv/Scripts/python -m pytest tests/test_icp_service.py tests/test_icp_parsing.py tests/test_icp_handling.py -v
```

Expected: all pass.

- [ ] **Step 2: Run the full migration chain on a fresh test DB**

```bash
.venv/Scripts/python -c "
from sqlalchemy import create_engine
from database import Base
engine = create_engine('postgresql://experiments_user:password@localhost:5432/experiments_test')
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
print('Fresh DB ready')
"
.venv/Scripts/alembic -x db=postgresql://experiments_user:password@localhost:5432/experiments_test upgrade head
```

Expected: clean upgrade from base to head with no errors.

- [ ] **Step 3: Confirm branch is clean and push**

```bash
git status
git log --oneline develop..HEAD
```

Expected: 3 commits on this branch:
1. `[fix] clamp negative ICP ppm values to zero on upload`
2. `[chore] merge alembic heads before icp clamp migration`
3. `[fix] back-fill negative ICP ppm values to zero`

---

## Self-Review

**Spec coverage:**
- ✅ Negative values set to 0 in existing data → Task 4 migration
- ✅ Future uploads clamp negatives → Task 2 service fix
- ✅ Test coverage for upload-path clamp → Task 1 + 2
- ✅ Two open Alembic heads handled → Task 3 merge migration

**Placeholder scan:** None found. All steps include exact commands, code, and expected output.

**Type consistency:** `ICP_FIXED_ELEMENT_FIELDS` from `variable_config.py` is reproduced inline in the migration (as `_ICP_ELEMENT_COLUMNS`) so the migration has no runtime import dependency. The 27-element list matches exactly: `fe, si, ni, cu, mo, zn, mn, ca, cr, co, mg, al, sr, y, nb, sb, cs, ba, nd, gd, pt, rh, ir, pd, ru, os, tl`.
