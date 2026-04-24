# pXRF Upload Audit — Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three bugs uncovered by auditing `niton_xrf_download_20260106.csv` against the `PXRFUploadService` parser, and replace stale unit tests that target a legacy module.

**Architecture:** All changes are in one service class (`PXRFUploadService`), one router endpoint (`/api/bulk-uploads/pxrf`), and two test files. The service return signature gains one field (`warnings`) which must be propagated through to the router response simultaneously to avoid a runtime unpack error.

**Tech Stack:** Python 3.x, pandas, SQLAlchemy, FastAPI, pytest / SQLite in-memory

---

## Audit Summary

### What will work as-is
- CSV format parsed correctly via the pandas fallback in `_load_excel_from_bytes()`
- All required element columns (`Fe`, `Mg`, `Si`, `Ni`, `Cu`, `Mo`, `Co`, `Al`, `Ca`, `K`, `Au`) are present in the file
- `<LOD` and other null equivalents → `0.0`
- `Reading No` integer normalization (`1.0` → `"1"`)
- Insert / skip / update logic

### Bugs found

| # | Severity | Issue |
|---|----------|-------|
| 1 | **Critical** | **Mixed units**: rows 1–3 have `Units = "%"` (weight percent); all other rows use `ppm`. Parser ignores the `Units` column entirely — Fe gets stored as `32.94` instead of `329,403` for those rows. Silent data corruption. |
| 2 | Data loss | **Zn silently discarded**: model has `zn` column; CSV has `Zn` data; `Zn` is absent from `PXRF_REQUIRED_COLUMNS` so parser never reads it. |
| 3 | Minor | **CSV reverse-match broken**: router uses `openpyxl.load_workbook()` to extract reading numbers for post-upload characterized-status re-evaluation. `openpyxl` cannot read CSV files and fails silently, so no reverse-match runs for CSV uploads. |
| 4 | Test debt | **`test_ingest_pxrf.py` tests legacy code**: tests import `database.ingest_pxrf.ingest_pxrf_data` (old Streamlit module, not `PXRFUploadService`). Tests cannot run against the current stack and provide zero coverage. |

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Rewrite | `tests/test_ingest_pxrf.py` | Replace legacy module tests with `PXRFUploadService.ingest_from_bytes()` tests including units and Zn |
| Modify | `backend/services/bulk_uploads/pxrf_data.py` | `_clean_dataframe()` returns 3-tuple + adds % conversion + Zn cleaning; `_upsert_dataframe()` optionally maps Zn; `ingest_from_bytes()` returns 5-tuple |
| Modify | `backend/api/routers/bulk_uploads.py` | Unpack 5-tuple; pass `warnings` to response; add CSV fallback in reading_no extraction block |
| Modify | `tests/api/test_bulk_uploads.py` | Update `ingest_from_bytes` mock return values from 4-tuple to 5-tuple |

---

## Task 1: Rewrite `tests/test_ingest_pxrf.py`

**Files:**
- Rewrite: `tests/test_ingest_pxrf.py`

These tests will fail until Tasks 2 and 3 are complete. That's correct — write them first so the implementation is driven by the test contract.

- [ ] **Step 1: Replace the entire file content**

```python
import pytest
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, PXRFReading
from backend.services.bulk_uploads.pxrf_data import PXRFUploadService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED = ["Reading No", "Fe", "Mg", "Ni", "Cu", "Si", "Co", "Mo", "Al", "Ca", "K", "Au"]


def _csv_bytes(data: dict) -> bytes:
    """Serialize dict-of-lists to in-memory CSV bytes."""
    return pd.DataFrame(data).to_csv(index=False).encode()


def _row(**overrides) -> dict:
    """One-row data dict with all required columns zeroed, reading_no='1'."""
    base = {col: [0.0] for col in _REQUIRED}
    base["Reading No"] = ["1"]
    for k, v in overrides.items():
        base[k] = [v]
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    s = Sess()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# Basic insert
# ---------------------------------------------------------------------------

def test_ingest_new_reading(db):
    data = _row(Fe=10.0, Ca=1.5, Au=0.005)
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data)
    )
    assert errors == []
    assert inserted == 1
    r = db.query(PXRFReading).filter_by(reading_no="1").first()
    assert r is not None
    assert r.fe == pytest.approx(10.0)
    assert r.ca == pytest.approx(1.5)
    assert r.au == pytest.approx(0.005)


def test_null_equivalents_become_zero(db):
    data = {
        "Reading No": ["5"],
        "Fe": ["<LOD"], "Mg": ["ND"], "Ni": ["N/A"],
        "Cu": [""], "Si": ["LOD"], "Co": ["n.d."],
        "Mo": ["n/a"], "Al": [None], "Ca": [0.0], "K": [0.0], "Au": [0.0],
    }
    PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    r = db.query(PXRFReading).filter_by(reading_no="5").first()
    assert r.fe == pytest.approx(0.0)
    assert r.ni == pytest.approx(0.0)
    assert r.co == pytest.approx(0.0)


def test_reading_no_float_normalized(db):
    """Excel stores ints as floats; '1.0' should become reading_no='1'."""
    data = _row(Fe=5.0)
    data["Reading No"] = ["1.0"]
    PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    assert db.query(PXRFReading).filter_by(reading_no="1").first() is not None


def test_empty_reading_no_rows_dropped(db):
    data = {col: [0.0, 0.0, 0.0, 0.0] for col in _REQUIRED}
    data["Reading No"] = ["1", "", None, "4"]
    data["Fe"] = [10.0, 20.0, 30.0, 40.0]
    inserted, *_ = PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    assert inserted == 2
    assert db.query(PXRFReading).filter_by(reading_no="1").first() is not None
    assert db.query(PXRFReading).filter_by(reading_no="4").first() is not None


# ---------------------------------------------------------------------------
# Skip / update logic
# ---------------------------------------------------------------------------

def _seed_reading(db, reading_no: str = "10", fe: float = 1.0) -> PXRFReading:
    r = PXRFReading(reading_no=reading_no, fe=fe, mg=0.0, ni=0.0, cu=0.0,
                    si=0.0, co=0.0, mo=0.0, al=0.0, ca=0.0, k=0.0, au=0.0)
    db.add(r)
    db.commit()
    return r


def test_skip_existing_when_update_false(db):
    _seed_reading(db, "10", fe=1.0)
    data = {col: [0.0, 0.0] for col in _REQUIRED}
    data["Reading No"] = ["10", "11"]
    data["Fe"] = [99.0, 5.0]
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data), update_existing=False
    )
    assert inserted == 1
    assert skipped == 1
    assert db.query(PXRFReading).filter_by(reading_no="10").first().fe == pytest.approx(1.0)


def test_update_existing_when_flag_true(db):
    _seed_reading(db, "20", fe=1.0)
    data = _row(Fe=99.9)
    data["Reading No"] = ["20"]
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data), update_existing=True
    )
    assert updated == 1
    assert inserted == 0
    assert db.query(PXRFReading).filter_by(reading_no="20").first().fe == pytest.approx(99.9)


def test_missing_required_column_returns_error(db):
    data = {"Reading No": ["1"], "Fe": [10.0]}  # missing Mg, Ni, Cu, Si, Co, Mo, Al, Ca, K, Au
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data)
    )
    assert inserted == 0
    assert any("Missing required columns" in e for e in errors)


# ---------------------------------------------------------------------------
# Bug 1: % → ppm normalization
# ---------------------------------------------------------------------------

def test_percent_rows_converted_to_ppm(db):
    """Niton exports in weight-% for some scan modes; parser must × 10,000."""
    data = {
        "Reading No": ["20", "21"],
        "Units": ["%", "ppm"],
        "Fe": [30.0, 300_000.0],
        "Mg": [0.0, 0.0], "Ni": [0.0, 0.0], "Cu": [0.0, 0.0],
        "Si": [0.0, 0.0], "Co": [0.0, 0.0], "Mo": [0.0, 0.0],
        "Al": [0.0, 0.0], "Ca": [0.0, 0.0], "K": [0.0, 0.0], "Au": [0.0, 0.0],
    }
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data)
    )
    assert inserted == 2
    assert errors == []
    assert len(warnings) == 1
    assert "converted" in warnings[0].lower()
    r20 = db.query(PXRFReading).filter_by(reading_no="20").first()
    assert r20.fe == pytest.approx(300_000.0)   # 30.0 × 10,000
    r21 = db.query(PXRFReading).filter_by(reading_no="21").first()
    assert r21.fe == pytest.approx(300_000.0)   # already ppm, unchanged


def test_no_warning_when_all_ppm(db):
    data = _row(Fe=5000.0)
    data["Units"] = ["ppm"]
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data)
    )
    assert warnings == []


def test_no_warning_when_no_units_column(db):
    """Older exports omit the Units column entirely; no warning expected."""
    data = _row(Fe=5000.0)
    # No "Units" key in data
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data)
    )
    assert warnings == []


# ---------------------------------------------------------------------------
# Bug 2: Zn optional import
# ---------------------------------------------------------------------------

def test_zn_imported_when_column_present(db):
    data = _row(Fe=10.0)
    data["Zn"] = [42.5]
    PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    r = db.query(PXRFReading).filter_by(reading_no="1").first()
    assert r.zn == pytest.approx(42.5)


def test_zn_lod_becomes_zero(db):
    data = _row(Fe=10.0)
    data["Zn"] = ["<LOD"]
    PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    r = db.query(PXRFReading).filter_by(reading_no="1").first()
    assert r.zn == pytest.approx(0.0)


def test_zn_not_required_upload_succeeds_without_it(db):
    """Upload without Zn column must succeed; zn field stays None."""
    data = _row(Fe=10.0)
    assert "Zn" not in data
    inserted, *_ = PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    assert inserted == 1
    r = db.query(PXRFReading).filter_by(reading_no="1").first()
    assert r.zn is None
```

- [ ] **Step 2: Run the tests to verify they all fail**

```
cd C:\Users\MathewHearl\Documents\0x_Software\database_sandbox\experiment_tracking_sandbox
pytest tests/test_ingest_pxrf.py -v 2>&1 | head -60
```

Expected: most tests fail — either import errors (old module gone), unpack errors (wrong tuple length), or assertion failures.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_ingest_pxrf.py
git commit -m "[fix] rewrite pxrf unit tests targeting PXRFUploadService

- Tests: yes
- Docs updated: no"
```

---

## Task 2: Update `PXRFUploadService` in `pxrf_data.py`

**Files:**
- Modify: `backend/services/bulk_uploads/pxrf_data.py`

- [ ] **Step 1: Replace the file with the updated implementation**

```python
from __future__ import annotations

import io
from typing import List, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from database import PXRFReading
from frontend.config.variable_config import PXRF_REQUIRED_COLUMNS
from utils.storage import get_file


NULL_EQUIVALENTS = ['', '<LOD', 'LOD', 'ND', 'n.d.', 'n/a', 'N/A', None]


class PXRFUploadService:
    @staticmethod
    def _load_excel_from_bytes(file_bytes: bytes) -> Tuple[pd.DataFrame, List[str]]:
        errors: List[str] = []
        try:
            df = pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl')
        except Exception:
            try:
                df = pd.read_csv(io.BytesIO(file_bytes))
            except Exception as e:
                return pd.DataFrame(), [f"Failed to read file: {e}"]

        missing = PXRF_REQUIRED_COLUMNS - set(df.columns)
        if missing:
            errors.append("Missing required columns: " + ", ".join(sorted(missing)))
            return pd.DataFrame(), errors
        return df, errors

    @staticmethod
    def _clean_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str], List[str]]:
        """Clean and normalise the dataframe.

        Returns (df, errors, warnings).
        errors: non-empty means processing should halt.
        warnings: informational messages to surface in the upload response.
        """
        errors: List[str] = []
        warnings: List[str] = []
        try:
            # Normalize Reading No: convert to string and remove .0 suffix from floats.
            # Excel stores integers as floats (1 becomes 1.0), so "1.0" should become "1".
            df['Reading No'] = df['Reading No'].apply(
                lambda x: str(int(float(x))) if pd.notna(x) and str(x).replace('.', '', 1).replace('-', '', 1).isdigit() else str(x)
            ).str.strip()

            # Drop empty Reading No rows
            df = df.dropna(subset=['Reading No'])
            df = df[df['Reading No'] != '']

            # Clean required numeric columns
            for col in PXRF_REQUIRED_COLUMNS - {'Reading No'}:
                df[col] = df[col].replace(NULL_EQUIVALENTS, 0)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            # Optional: clean Zn if present (model supports it; not required in all Niton exports)
            if 'Zn' in df.columns:
                df['Zn'] = df['Zn'].replace(NULL_EQUIVALENTS, 0)
                df['Zn'] = pd.to_numeric(df['Zn'], errors='coerce').fillna(0)

            # Unit normalisation: Niton XRF can export in weight-percent mode.
            # Convert % → ppm (× 10,000) so all readings share the same unit before storage.
            if 'Units' in df.columns:
                pct_mask = df['Units'].astype(str).str.strip() == '%'
                pct_count = int(pct_mask.sum())
                if pct_count > 0:
                    element_cols = [c for c in PXRF_REQUIRED_COLUMNS if c != 'Reading No']
                    if 'Zn' in df.columns:
                        element_cols.append('Zn')
                    df.loc[pct_mask, element_cols] = df.loc[pct_mask, element_cols] * 10_000
                    warnings.append(
                        f"{pct_count} row(s) exported in weight-% and were converted to ppm (× 10,000)."
                    )
        except Exception as e:
            errors.append(f"Error cleaning data: {e}")
        return df, errors, warnings

    @staticmethod
    def _upsert_dataframe(db: Session, df: pd.DataFrame, update_existing: bool) -> Tuple[int, int, int, List[str]]:
        inserted = updated = skipped = 0
        errors: List[str] = []
        has_zn = 'Zn' in df.columns
        try:
            existing_reading_nos = set(row[0] for row in db.query(PXRFReading.reading_no).all())
            for _, row in df.iterrows():
                reading_no = row['Reading No']
                reading_data = {
                    'reading_no': reading_no,
                    'fe': row['Fe'],
                    'mg': row['Mg'],
                    'ni': row['Ni'],
                    'cu': row['Cu'],
                    'si': row['Si'],
                    'co': row['Co'],
                    'mo': row['Mo'],
                    'al': row['Al'],
                    'ca': row['Ca'],
                    'k': row['K'],
                    'au': row['Au'],
                }
                if has_zn:
                    reading_data['zn'] = row['Zn']

                if reading_no in existing_reading_nos:
                    if update_existing:
                        existing = db.query(PXRFReading).filter(PXRFReading.reading_no == reading_no).first()
                        for k, v in reading_data.items():
                            if k != 'reading_no':
                                setattr(existing, k, v)
                        updated += 1
                    else:
                        skipped += 1
                else:
                    db.add(PXRFReading(**reading_data))
                    inserted += 1
        except Exception as e:
            errors.append(f"Error during database upsert: {e}")
        return inserted, updated, skipped, errors

    @classmethod
    def ingest_from_bytes(
        cls, db: Session, file_bytes: bytes, update_existing: bool = False
    ) -> Tuple[int, int, int, List[str], List[str]]:
        """Ingest pXRF data from file bytes.

        Returns (inserted, updated, skipped, errors, warnings).
        """
        df, errors = cls._load_excel_from_bytes(file_bytes)
        if errors:
            return 0, 0, 0, errors, []
        df, clean_errors, warnings = cls._clean_dataframe(df)
        if clean_errors:
            return 0, 0, 0, clean_errors, []
        inserted, updated, skipped, upsert_errors = cls._upsert_dataframe(db, df, update_existing)
        return inserted, updated, skipped, upsert_errors, warnings

    @classmethod
    def ingest_from_source(
        cls, db: Session, file_source: str, update_existing: bool = False
    ) -> Tuple[int, int, int, List[str], List[str]]:
        try:
            file_bytes = get_file(file_source)
        except Exception as e:
            return 0, 0, 0, [f"Error fetching file '{file_source}': {e}"], []
        return cls.ingest_from_bytes(db, file_bytes, update_existing)
```

- [ ] **Step 2: Run the unit tests**

```
pytest tests/test_ingest_pxrf.py -v
```

Expected: all tests pass. If any fail, diagnose before continuing.

- [ ] **Step 3: Commit**

```bash
git add backend/services/bulk_uploads/pxrf_data.py
git commit -m "[fix] pXRF parser: % → ppm conversion, Zn import, 5-tuple return

- Detects Units column; converts weight-% rows to ppm (× 10,000)
- Optionally imports Zn column when present in file
- _clean_dataframe() now returns (df, errors, warnings)
- ingest_from_bytes() now returns 5-tuple including warnings
- Tests: yes
- Docs updated: no"
```

---

## Task 3: Update the router and API test mocks

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py` (lines 127–152, 221–222)
- Modify: `tests/api/test_bulk_uploads.py` (all `ingest_from_bytes.return_value` occurrences)

The router currently unpacks 4 values from `ingest_from_bytes`; after Task 2 it returns 5, causing a runtime unpack error. Fix both in this task.

- [ ] **Step 1: Find all mock return values to update in `test_bulk_uploads.py`**

```
grep -n "ingest_from_bytes.return_value" tests/api/test_bulk_uploads.py
```

Every line that looks like `return_value = (N, N, N, [])` needs a fifth element `[]` appended: `return_value = (N, N, N, [], [])`.

- [ ] **Step 2: Update every mock in `test_bulk_uploads.py`**

For each line found above, change `(N, N, N, [])` → `(N, N, N, [], [])`.

For example, line 126:
```python
# Before
mock_pxrf.ingest_from_bytes.return_value = (3, 0, 0, [])
# After
mock_pxrf.ingest_from_bytes.return_value = (3, 0, 0, [], [])
```

Line 571:
```python
# Before
fake_mod.PXRFUploadService.ingest_from_bytes.return_value = (1, 0, 0, [])
# After
fake_mod.PXRFUploadService.ingest_from_bytes.return_value = (1, 0, 0, [], [])
```

Apply the same change to any other occurrences found by grep.

- [ ] **Step 3: Update the router — unpack 5 values and pass warnings to response**

In `backend/api/routers/bulk_uploads.py`, find line 152:
```python
created, updated, skipped, errors = PXRFUploadService.ingest_from_bytes(db, file_bytes)
```
Replace with:
```python
created, updated, skipped, errors, svc_warnings = PXRFUploadService.ingest_from_bytes(db, file_bytes)
```

Find the final `return UploadResponse(...)` for this endpoint (around line 221):
```python
return UploadResponse(created=created, updated=updated, skipped=skipped, errors=errors,
                      message=message)
```
Replace with:
```python
return UploadResponse(created=created, updated=updated, skipped=skipped, errors=errors,
                      message=message, warnings=svc_warnings)
```

- [ ] **Step 4: Run the full pXRF test suite**

```
pytest tests/test_ingest_pxrf.py tests/api/test_bulk_uploads.py -v -k pxrf
```

Expected: all pXRF tests pass.

- [ ] **Step 5: Run the full test suite to check for regressions**

```
pytest --tb=short -q
```

Expected: all passing (or same failures as before this branch).

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/bulk_uploads.py tests/api/test_bulk_uploads.py
git commit -m "[fix] propagate pXRF upload warnings to router response; update test mocks

- Router unpacks 5-tuple from ingest_from_bytes and surfaces warnings field
- API test mocks updated for new 5-tuple return signature
- Tests: yes
- Docs updated: no"
```

---

## Task 4: Fix CSV reading-number extraction for reverse-match

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py` (lines 127–149)

The router uses `openpyxl.load_workbook()` to extract reading numbers before the reverse-match logic. `openpyxl` cannot read CSV files and raises an exception, which is silently caught. For CSV uploads, `_imported_reading_nos` stays empty and no characterized-status re-evaluation runs.

- [ ] **Step 1: Find the extraction block in the router**

The block starts at `_imported_reading_nos: set[str] = set()` (around line 127) and ends with `except Exception: pass` (around line 149). Read lines 124–152 of `backend/api/routers/bulk_uploads.py` to confirm exact bounds.

- [ ] **Step 2: Replace the extraction block**

Replace the entire block from `_imported_reading_nos: set[str] = set()` through the closing `except Exception: pass` with:

```python
_imported_reading_nos: set[str] = set()
try:
    from backend.services.samples import normalize_pxrf_reading_no as _norm  # noqa: PLC0415
    try:
        import openpyxl as _openpyxl  # noqa: PLC0415
        _wb = _openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        try:
            _ws = _wb.active
            _header_row = next(_ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
            if _header_row is not None:
                _rn_col = next(
                    (i for i, h in enumerate(_header_row) if str(h).strip() == "Reading No"), None
                )
                if _rn_col is not None:
                    for _row in _ws.iter_rows(min_row=2, values_only=True):
                        _v = _row[_rn_col] if _rn_col < len(_row) else None
                        if _v is not None:
                            _s = str(_v).strip()
                            if _s:
                                _imported_reading_nos.add(_norm(_s))
        finally:
            _wb.close()
    except Exception:
        # openpyxl failed (CSV file) — fall back to pandas
        import pandas as _pd  # noqa: PLC0415
        _df_rn = _pd.read_csv(io.BytesIO(file_bytes), usecols=["Reading No"], dtype=str)
        for _v in _df_rn["Reading No"].dropna():
            _s = str(_v).strip()
            if _s:
                _imported_reading_nos.add(_norm(_s))
except Exception:
    pass
```

- [ ] **Step 3: Run tests**

```
pytest tests/api/test_bulk_uploads.py -v -k pxrf
```

Expected: same pass/fail as before (this fix is exercised only in integration; unit tests mock the service).

- [ ] **Step 4: Commit**

```bash
git add backend/api/routers/bulk_uploads.py
git commit -m "[fix] CSV fallback for pXRF reading-no extraction in reverse-match

- openpyxl cannot parse CSV files; falls back to pandas read_csv
- Ensures post-upload characterized-status re-evaluation runs for CSV uploads
- Tests: no (integration-level behavior)
- Docs updated: no"
```

---

## Self-Review

### Spec coverage check

| Audit finding | Task that addresses it |
|---------------|----------------------|
| Mixed units (% vs ppm) — critical | Task 2 (`_clean_dataframe`) + Task 1 (test) |
| Zn silently discarded | Task 2 (`_clean_dataframe` + `_upsert_dataframe`) + Task 1 (test) |
| CSV reverse-match broken | Task 4 (router fallback) |
| Stale unit tests | Task 1 (full rewrite) |
| Return signature propagation | Task 2 (service) + Task 3 (router + mocks) |

### Placeholder scan
No TBDs, no "add validation later", no "similar to Task N" — all steps contain exact code.

### Type consistency
- `_clean_dataframe()` returns `Tuple[pd.DataFrame, List[str], List[str]]` in Task 2 step 1; called with `df, clean_errors, warnings = cls._clean_dataframe(df)` in `ingest_from_bytes()` in the same file. ✓
- `ingest_from_bytes()` returns 5-tuple in Task 2; router unpacks 5 in Task 3; mocks return 5-tuple in Task 3. ✓
- `_upsert_dataframe()` signature unchanged (still 4-tuple). ✓
- `ingest_from_source()` now also returns 5-tuple (matches `ingest_from_bytes`). ✓
