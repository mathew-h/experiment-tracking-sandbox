# pXRF Upload HTTP 500 Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-step. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix HTTP 500 on `/api/bulk-uploads/pxrf` caused by a top-level `from utils.storage import get_file` in `pxrf_data.py` failing at runtime because `utils.storage` does not exist in the project.

**Architecture:** Move the `utils.storage` import inside `ingest_from_source` (the only method that calls `get_file`). `ingest_from_bytes` — the method the API uses — has never needed it. The test suite stubs `utils.storage` via `conftest.py`, masking the bug in CI.

**Tech Stack:** Python, FastAPI, pytest

---

## Root Cause Summary

`backend/services/bulk_uploads/pxrf_data.py` line 12:
```python
from utils.storage import get_file
```

`utils/storage.py` does not exist anywhere in the project. `conftest.py` stubs it with `MagicMock` (lines 15–16), so all tests pass. In production, the first request to `/api/bulk-uploads/pxrf` triggers the lazy import of `PXRFUploadService` (route line 124), which imports `pxrf_data.py`, which hits this line → `ModuleNotFoundError` → unhandled → FastAPI returns HTTP 500.

`get_file` is only used in `ingest_from_source` (lines 149–153 of `pxrf_data.py`), not in `ingest_from_bytes`.

---

## File Map

| File | Change |
|------|--------|
| `backend/services/bulk_uploads/pxrf_data.py` | Remove top-level import; add lazy import inside `ingest_from_source` |
| `tests/api/test_bulk_uploads.py` | Add regression test: module import succeeds without `utils.storage` stub |

---

### Task 1: Add failing regression test

**Files:**
- Modify: `tests/api/test_bulk_uploads.py`

- [ ] **Step 1: Add the failing test to `tests/api/test_bulk_uploads.py`**

  Append this test. It temporarily removes `utils.storage` and `utils` from `sys.modules` and re-imports `pxrf_data` to confirm that the module-level import fails before the fix.

```python
def test_pxrf_data_importable_without_utils_storage():
    """pxrf_data must not require utils.storage at import time.

    The API uses ingest_from_bytes; utils.storage is only needed by
    ingest_from_source (legacy file-path loader). A top-level import
    causes ModuleNotFoundError in production → HTTP 500 on first upload.
    """
    import sys
    import importlib

    keys_to_evict = [
        "utils",
        "utils.storage",
        "backend.services.bulk_uploads.pxrf_data",
    ]
    saved = {k: sys.modules.pop(k) for k in keys_to_evict if k in sys.modules}

    try:
        import backend.services.bulk_uploads.pxrf_data  # must not raise
    except ModuleNotFoundError as exc:
        raise AssertionError(
            f"pxrf_data raised ModuleNotFoundError on import: {exc}\n"
            "Move 'from utils.storage import get_file' inside ingest_from_source."
        ) from exc
    finally:
        for k, v in saved.items():
            sys.modules[k] = v
        # Re-import with stubs restored so other tests are unaffected
        importlib.import_module("backend.services.bulk_uploads.pxrf_data")
```

- [ ] **Step 2: Run the test to confirm it fails**

  ```
  pytest tests/api/test_bulk_uploads.py::test_pxrf_data_importable_without_utils_storage -v
  ```

  Expected output: `FAILED` with `AssertionError: pxrf_data raised ModuleNotFoundError on import`

---

### Task 2: Apply the fix

**Files:**
- Modify: `backend/services/bulk_uploads/pxrf_data.py`

- [ ] **Step 1: Remove the top-level import and add a lazy import**

  In `backend/services/bulk_uploads/pxrf_data.py`:

  **Remove line 12** (top of file):
  ```python
  from utils.storage import get_file
  ```

  **Replace the body of `ingest_from_source`** (currently lines 146–153) with a lazy import:
  ```python
  @classmethod
  def ingest_from_source(
      cls, db: Session, file_source: str, update_existing: bool = False
  ) -> Tuple[int, int, int, List[str], List[str]]:
      from utils.storage import get_file  # noqa: PLC0415
      try:
          file_bytes = get_file(file_source)
      except Exception as e:
          return 0, 0, 0, [f"Error fetching file '{file_source}': {e}"], []
      return cls.ingest_from_bytes(db, file_bytes, update_existing)
  ```

  The full updated imports block at the top of the file should be:
  ```python
  from __future__ import annotations

  import io
  from typing import List, Tuple

  import pandas as pd
  from sqlalchemy import select
  from sqlalchemy.orm import Session

  from database import PXRFReading
  from frontend.config.variable_config import PXRF_REQUIRED_COLUMNS
  ```

- [ ] **Step 2: Run the regression test — expect PASS**

  ```
  pytest tests/api/test_bulk_uploads.py::test_pxrf_data_importable_without_utils_storage -v
  ```

  Expected: `PASSED`

- [ ] **Step 3: Run the full pXRF test suite — expect all pass**

  ```
  pytest tests/api/test_bulk_uploads.py -v -k pxrf
  ```

  Expected: `7 passed` (or 8 passed including the new test)

- [ ] **Step 4: Run the full test suite to check for regressions**

  ```
  pytest tests/ -v --tb=short 2>&1 | tail -20
  ```

  Expected: no new failures

- [ ] **Step 5: Commit**

  ```bash
  git add backend/services/bulk_uploads/pxrf_data.py tests/api/test_bulk_uploads.py
  git commit -m "[fix] make utils.storage import lazy in pxrf_data

  - Tests: yes
  - Docs updated: no"
  ```
