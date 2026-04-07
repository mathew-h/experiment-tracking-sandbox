# Issue #31: Map Sampled Solution Volume (mL) in Master Results Sync Parser

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Map the `Sampled Solution Volume (mL)` column in the Master Results Sync parser to `ScalarResults.sampling_volume_mL`.

**Architecture:** Single-function change in the `_process_bytes` function — add a case-insensitive column-name normalisation step and parse the new column via the existing `_parse_float` helper. All other service, schema, view, and calculation-engine code is untouched. Tests are added to the existing unit test file plus a new integration test module.

**Tech Stack:** Python 3.11, pandas, SQLAlchemy 2.x, pytest, openpyxl (test fixtures)

---

## Pre-flight: field existence check

Before writing any code, confirm the target field exists:

```bash
grep -n "sampling_volume_mL" database/models/results.py
```

Expected output (line number may differ):
```
83:    sampling_volume_mL = Column(Float, nullable=True) # in mL
```

If the field is absent, **stop and flag to the user — do not add it.**

---

## Files

| Action | Path |
|--------|------|
| Modify | `backend/services/bulk_uploads/master_bulk_upload.py` |
| Modify | `tests/services/bulk_uploads/test_master_bulk_upload.py` |
| Create | `tests/integration/conftest.py` (if absent) |
| Create | `tests/integration/test_master_results_sync_endpoint.py` |
| Modify | `docs/specs/master_results_sync.md` |
| Modify | `docs/user_guide/BULK_UPLOADS.md` |

---

## Task 1: Write failing unit tests

**Files:**
- Modify: `tests/services/bulk_uploads/test_master_bulk_upload.py`

- [ ] **Step 1.1 — Add the four new unit tests at the end of the file**

Append after the last existing test (`test_from_bytes_matches_experiment_with_leading_zeros_and_symbols`):

```python
# ---------------------------------------------------------------------------
# Sampled Solution Volume tests (Issue #31)
# ---------------------------------------------------------------------------

def test_sampled_solution_volume_parsed(db_session: Session):
    """Sampled Solution Volume (mL) cell with a value is saved to sampling_volume_mL."""
    _seed_experiment(db_session, "HPHT_VOL001", 8001)

    headers = [
        "Experiment ID", "Duration (Days)", "Description", "Sample Date",
        "NMR Run Date", "ICP Run Date", "GC Run Date",
        "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
        "Sample pH", "Sample Conductivity (mS/cm)",
        "Sampled Solution Volume (mL)",
        "Modification", "Overwrite",
    ]
    xlsx = make_excel_multisheet({"Dashboard": (headers, [
        ["HPHT_VOL001", 7.0, "Day 7", None, None, None, None,
         None, None, None, None, 7.0, None, 15.5, None, "FALSE"],
    ])})
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_VOL001")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    assert result.scalar_data.sampling_volume_mL == pytest.approx(15.5)


def test_sampled_solution_volume_blank(db_session: Session):
    """Blank Sampled Solution Volume cell → sampling_volume_mL is None; row not skipped."""
    _seed_experiment(db_session, "HPHT_VOL002", 8002)

    headers = [
        "Experiment ID", "Duration (Days)", "Description", "Sample Date",
        "NMR Run Date", "ICP Run Date", "GC Run Date",
        "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
        "Sample pH", "Sample Conductivity (mS/cm)",
        "Sampled Solution Volume (mL)",
        "Modification", "Overwrite",
    ]
    xlsx = make_excel_multisheet({"Dashboard": (headers, [
        ["HPHT_VOL002", 7.0, "Day 7", None, None, None, None,
         None, None, None, None, 7.0, None, None, None, "FALSE"],
    ])})
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1, "Row must not be skipped when volume cell is blank"

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_VOL002")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    assert result.scalar_data.sampling_volume_mL is None


def test_sampled_solution_volume_column_absent(db_session: Session):
    """Legacy file without Sampled Solution Volume column processes without KeyError."""
    _seed_experiment(db_session, "HPHT_VOL003", 8003)

    # _master_excel() does NOT include the new column — simulates an older Dashboard file
    xlsx = _master_excel([
        ["HPHT_VOL003", 7.0, "Day 7", None, None, None, None,
         None, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1


def test_sampled_solution_volume_case_insensitive(db_session: Session):
    """Lowercase header 'sampled solution volume (ml)' is normalised and parsed correctly."""
    _seed_experiment(db_session, "HPHT_VOL004", 8004)

    headers = [
        "Experiment ID", "Duration (Days)", "Description", "Sample Date",
        "NMR Run Date", "ICP Run Date", "GC Run Date",
        "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
        "Sample pH", "Sample Conductivity (mS/cm)",
        "sampled solution volume (ml)",  # intentionally lowercase
        "Modification", "Overwrite",
    ]
    xlsx = make_excel_multisheet({"Dashboard": (headers, [
        ["HPHT_VOL004", 7.0, "Day 7", None, None, None, None,
         None, None, None, None, 7.0, None, 20.0, None, "FALSE"],
    ])})
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_VOL004")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    assert result.scalar_data.sampling_volume_mL == pytest.approx(20.0)
```

- [ ] **Step 1.2 — Run the tests to confirm they fail**

```bash
pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "sampled_solution_volume" -v
```

Expected: 4 tests collected, all **FAILED** (the parser doesn't know about the column yet).

---

## Task 2: Implement the parser change

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py:94-136`

- [ ] **Step 2.1 — Add case-normalisation for the new column header**

In `_process_bytes`, find line 94:

```python
    df.columns = [str(c).strip() for c in df.columns]
```

Replace it with:

```python
    df.columns = [str(c).strip() for c in df.columns]
    # Normalise the optional volume column header to canonical casing.
    df.columns = [
        "Sampled Solution Volume (mL)" if c.lower() == "sampled solution volume (ml)" else c
        for c in df.columns
    ]
```

- [ ] **Step 2.2 — Parse the new field in the per-row loop**

Find (around line 134):

```python
        conductivity = _parse_float(row.get("Sample Conductivity (mS/cm)"))
        modification = str(row.get("Modification") or "").strip() or None
```

Insert the new line between them:

```python
        conductivity = _parse_float(row.get("Sample Conductivity (mS/cm)"))
        sampling_vol_ml = _parse_float(row.get("Sampled Solution Volume (mL)"))
        modification = str(row.get("Modification") or "").strip() or None
```

- [ ] **Step 2.3 — Add the field to result_data**

Find (around line 138):

```python
        result_data: Dict[str, Any] = {
            ...
            "final_ph": ph,
            "final_conductivity_mS_cm": conductivity,
            "_overwrite": overwrite,
        }
```

Add `"sampling_volume_mL": sampling_vol_ml,` before `"_overwrite"`:

```python
        result_data: Dict[str, Any] = {
            "time_post_reaction": time_post_reaction,
            "description": description or f"Master upload — day {time_post_reaction}",
            "measurement_date": sample_date,
            "nmr_run_date": nmr_run_date,
            "icp_run_date": icp_run_date,
            "gc_run_date": gc_run_date,
            "gross_ammonium_concentration_mM": nh4_mm,
            "h2_concentration": h2_ppm,
            "h2_concentration_unit": "ppm" if h2_ppm is not None else None,
            "gas_sampling_volume_ml": gas_vol_ml,
            "gas_sampling_pressure_MPa": gas_mpa,
            "final_ph": ph,
            "final_conductivity_mS_cm": conductivity,
            "sampling_volume_mL": sampling_vol_ml,
            "_overwrite": overwrite,
        }
```

> **Why None-stripping already handles absent/blank cells:** The line below result_data strips all `None` values (except `_overwrite`). When the column is absent or blank, `_parse_float` returns `None`, which is stripped, so the service creates `ScalarResults` without setting this field — the DB column defaults to `NULL`. No extra guard needed.

- [ ] **Step 2.4 — Update the module docstring to include the new column**

Find the top-of-file docstring:

```python
"""
Master Results bulk upload — reads from fixed SharePoint path or uploaded bytes.

Dashboard sheet column spec:
  Experiment ID | Duration (Days) | Description | Sample Date | NMR Run Date |
  ICP Run Date  | GC Run Date     | NH4 (mM)    | H2 (ppm)    | Gas Volume (mL) |
  Gas Pressure (psi) | Sample pH | Sample Conductivity (mS/cm) | Modification | Overwrite
"""
```

Replace with:

```python
"""
Master Results bulk upload — reads from fixed SharePoint path or uploaded bytes.

Dashboard sheet column spec:
  Experiment ID | Duration (Days) | Description | Sample Date | NMR Run Date |
  ICP Run Date  | GC Run Date     | NH4 (mM)    | H2 (ppm)    | Gas Volume (mL) |
  Gas Pressure (psi) | Sample pH | Sample Conductivity (mS/cm) |
  Sampled Solution Volume (mL) | Modification | Overwrite
"""
```

---

## Task 3: Run unit tests and commit

- [ ] **Step 3.1 — Run the four new unit tests**

```bash
pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "sampled_solution_volume" -v
```

Expected: 4 tests **PASSED**.

- [ ] **Step 3.2 — Run the full unit test suite for this module**

```bash
pytest tests/services/bulk_uploads/test_master_bulk_upload.py -v
```

Expected: all existing tests **PASSED** (no regressions).

- [ ] **Step 3.3 — Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py \
        tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "[#31] map Sampled Solution Volume (mL) in master parser

- Tests added: yes
- Docs updated: no"
```

---

## Task 4: Create integration test conftest (if absent)

**Files:**
- Create: `tests/integration/conftest.py`

- [ ] **Step 4.1 — Check whether `tests/integration/conftest.py` exists**

```bash
ls tests/integration/
```

If `conftest.py` is already present and provides a `db_session` fixture against the Postgres test DB, skip to Task 5. If it is absent (only `__init__.py`), continue.

- [ ] **Step 4.2 — Create `tests/integration/conftest.py`**

```python
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from database import Base  # noqa: F401 — registers all models

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
_test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=_test_engine)


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """Create all tables once for this test session."""
    Base.metadata.create_all(bind=_test_engine)
    yield


@pytest.fixture()
def db_session(create_test_tables) -> Session:
    """Per-test DB session wrapped in a transaction; rolls back after each test."""
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = _TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```

---

## Task 5: Write and run integration tests

**Files:**
- Create: `tests/integration/test_master_results_sync_endpoint.py`

- [ ] **Step 5.1 — Create the integration test file**

```python
"""Integration tests for Master Results Sync — Sampled Solution Volume (Issue #31)."""
from __future__ import annotations

import io

import openpyxl
import pytest
from sqlalchemy.orm import Session

from database import Base, Experiment, ExperimentalResults
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.master_bulk_upload import MasterBulkUploadService


def _seed_experiment(db: Session, experiment_id: str, exp_num: int) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    return exp


def _make_xlsx(headers: list[str], rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dashboard"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_HEADERS_WITH_VOL = [
    "Experiment ID", "Duration (Days)", "Description", "Sample Date",
    "NMR Run Date", "ICP Run Date", "GC Run Date",
    "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
    "Sample pH", "Sample Conductivity (mS/cm)",
    "Sampled Solution Volume (mL)",
    "Modification", "Overwrite",
]

_HEADERS_LEGACY = [
    "Experiment ID", "Duration (Days)", "Description", "Sample Date",
    "NMR Run Date", "ICP Run Date", "GC Run Date",
    "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
    "Sample pH", "Sample Conductivity (mS/cm)",
    "Modification", "Overwrite",
]


def test_sync_writes_sampled_solution_volume(db_session: Session):
    """Full service round-trip: column present → ScalarResults.sampling_volume_mL persisted."""
    _seed_experiment(db_session, "CF_INT001", 9001)

    xlsx = _make_xlsx(_HEADERS_WITH_VOL, [
        ["CF_INT001", 14.0, "Day 14", None, None, None, None,
         None, None, None, None, 7.1, None, 42.5, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "CF_INT001")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    assert result.scalar_data.sampling_volume_mL == pytest.approx(42.5)


def test_sync_without_sampled_solution_volume_column(db_session: Session):
    """Legacy file without the column → sync succeeds, sampling_volume_mL is None."""
    _seed_experiment(db_session, "CF_INT002", 9002)

    xlsx = _make_xlsx(_HEADERS_LEGACY, [
        ["CF_INT002", 14.0, "Day 14", None, None, None, None,
         None, None, None, None, 7.1, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "CF_INT002")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    assert result.scalar_data.sampling_volume_mL is None
```

- [ ] **Step 5.2 — Run the integration tests**

```bash
pytest tests/integration/test_master_results_sync_endpoint.py -v
```

Expected: 2 tests **PASSED**.

- [ ] **Step 5.3 — Commit**

```bash
git add tests/integration/conftest.py \
        tests/integration/test_master_results_sync_endpoint.py
git commit -m "[#31] add integration tests for sampling volume sync

- Tests added: yes
- Docs updated: no"
```

---

## Task 6: Update documentation

**Files:**
- Modify: `docs/specs/master_results_sync.md:30-47`
- Modify: `docs/user_guide/BULK_UPLOADS.md:36-53`

- [ ] **Step 6.1 — Add the new row to `docs/specs/master_results_sync.md`**

Find the Column Definitions table. After the row for `Sample Conductivity (mS/cm)`:

```markdown
| `Sample Conductivity (mS/cm)` | No | `ScalarResults.final_conductivity_mS_cm` | Float |
```

Insert:

```markdown
| `Sampled Solution Volume (mL)` | No | `ScalarResults.sampling_volume_mL` | Float; mL; optional; absent column treated as blank |
```

The full updated table block should look like:

```markdown
| Column Header | Required | Maps To | Notes |
|---|---|---|---|
| `Experiment ID` | Yes | `Experiment.experiment_id` | Must exist in DB |
| `Duration (Days)` | Yes | `ExperimentalResults.time_post_reaction_days` | Numeric; `0` = pre-reaction baseline |
| `Description` | No | `ExperimentalResults` description field | Free text |
| `Sample Date` | No | `ScalarResults.measurement_date` | Date; see parsing rules |
| `NH4 (mM)` | No | `ScalarResults.gross_ammonium_concentration_mM` | Float |
| `H2 (ppm)` | No | `ScalarResults.h2_concentration` | Float |
| `Gas Volume (mL)` | No | `ScalarResults.gas_sampling_volume_ml` | Float |
| `Gas Pressure (psi)` | No | `ScalarResults.gas_sampling_pressure_MPa` | Converted: × 0.00689476 |
| `Sample pH` | No | `ScalarResults.final_ph` | Float |
| `Sample Conductivity (mS/cm)` | No | `ScalarResults.final_conductivity_mS_cm` | Float |
| `Sampled Solution Volume (mL)` | No | `ScalarResults.sampling_volume_mL` | Float; mL; optional; absent column treated as blank |
| `Modification` | No | `ExperimentalResults.brine_modification_description` | Free text |
| `NMR Run Date` | No | Stored as metadata on result | Date |
| `ICP Run Date` | No | Stored as metadata on result | Date |
| `GC Run Date` | No | Stored as metadata on result | Date |
| `OVERWRITE` | No | Per-row overwrite flag | `TRUE`/`FALSE`; default `FALSE` |
| `Standard` | No | Ignored by parser | Informational column for lab use only |
```

- [ ] **Step 6.2 — Add the new row to `docs/user_guide/BULK_UPLOADS.md`**

Find the Master Results Sync column table (section 1). After the row for `Sample Conductivity (mS/cm)`:

```markdown
| Sample Conductivity (mS/cm) | | |
```

Insert:

```markdown
| Sampled Solution Volume (mL) | | Volume of production fluid collected at this timepoint (mL) |
```

- [ ] **Step 6.3 — Commit**

```bash
git add docs/specs/master_results_sync.md \
        docs/user_guide/BULK_UPLOADS.md
git commit -m "[#31] update docs with Sampled Solution Volume column

- Tests added: no
- Docs updated: yes"
```

---

## Task 7: Final verification

- [ ] **Step 7.1 — Run the full bulk-upload unit test suite**

```bash
pytest tests/services/bulk_uploads/test_master_bulk_upload.py -v
```

Expected: all tests **PASSED** (no regressions to existing tests).

- [ ] **Step 7.2 — Run integration tests**

```bash
pytest tests/integration/test_master_results_sync_endpoint.py -v
```

Expected: 2 tests **PASSED**.

---

## Acceptance Criteria Checklist

- [ ] `master_bulk_upload.py` maps `Sampled Solution Volume (mL)` (case-insensitive) via `_parse_float`
- [ ] A populated cell saves the correct float value (mL) to the DB
- [ ] A blank / missing cell produces `None` without skipping or erroring the row
- [ ] A file without the column at all processes without `KeyError`
- [ ] `master_results_sync.md` column table updated with the new row
- [ ] `BULK_UPLOADS.md` Master Results Sync table updated with the new row

---

## Notes

- The issue body references `_parse_numeric`, but the parser only defines `_parse_float`. The implementation uses `_parse_float` — the existing function that covers all numeric cell types (float, int, string). No new helper is needed.
- `gas_sampling_pressure_MPa` uses a unit conversion; `sampling_volume_mL` does not — mL is stored directly.
- Do **not** modify `ScalarResultsService`, `scalar_results.py`, `event_listeners.py`, or any SQL view. The field flows through the existing service path unchanged.
