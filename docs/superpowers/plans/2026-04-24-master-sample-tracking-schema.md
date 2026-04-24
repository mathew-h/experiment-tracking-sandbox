# Master Sample Tracking Schema + Upload Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 new fields to `SampleInfo` (well_name, core_lender, core_interval_ft, on_loan_return_date), teach the Rock Inventory bulk uploader to accept the Master Sample Tracking.xlsx column headers directly, and update templates, schemas, and docs.

**Architecture:** Purely additive migration — 4 nullable String/Date columns on `sample_info`. `RockInventoryService` gains column-alias normalization so the file can be uploaded as-is. Pydantic schemas and the download template are updated to match.

**Tech Stack:** SQLAlchemy + Alembic, pandas + openpyxl, Pydantic v2, FastAPI, pytest

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `database/models/samples.py` | Modify | Add 4 fields to `SampleInfo` |
| `alembic/versions/<hash>_add_core_loan_fields_to_sample_info.py` | Create (generated) | Additive migration |
| `backend/services/bulk_uploads/rock_inventory.py` | Modify | Column-alias normalization + new field handling |
| `backend/api/schemas/samples.py` | Modify | Pydantic: add 4 fields to Create/Update/Response/Detail |
| `backend/api/routers/bulk_uploads.py` | Modify | Template generator: add 4 columns + INSTRUCTIONS |
| `docs/MODELS.md` | Modify | Document new fields |

---

## Context: What the Excel File Looks Like

`Master Sample Tracking.xlsx` has 498 data rows and these 13 columns (raw headers):

| Excel header | Normalized (lowercased) | Maps to |
|---|---|---|
| `sample_id` | `sample_id` | `SampleInfo.sample_id` |
| `latitude` | `latitude` | `SampleInfo.latitude` |
| `longitude` | `longitude` | `SampleInfo.longitude` |
| `Description` | `description` | `SampleInfo.description` |
| `pXRF Reading No` | `pxrf reading no` | → `ExternalAnalysis(pXRF)` (needs alias) |
| `Mag. Suscept. [SI*1e3]` | `mag. suscept. [si*1e3]` | → `ExternalAnalysis(Magnetic Susceptibility)` (needs alias) |
| `State` | `state` | `SampleInfo.state` |
| `country` | `country` | `SampleInfo.country` |
| `Locality` | `locality` | `SampleInfo.locality` |
| `Well Name` | `well name` | `SampleInfo.well_name` (**new**) |
| `Core Lender` | `core lender` | `SampleInfo.core_lender` (**new**) |
| `Core Interval (ft)` | `core interval (ft)` | `SampleInfo.core_interval_ft` (**new**, String, e.g. `"895'"`) |
| `On Loan Return Date` | `on loan return date` | `SampleInfo.on_loan_return_date` (**new**, Date) |

The 4 new fields are sparsely populated (21 / 498 rows). All 4 are nullable.

---

## Task 1: Add Fields to SampleInfo Model

**Files:**
- Modify: `database/models/samples.py`
- Test: `tests/services/bulk_uploads/test_rock_inventory.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/services/bulk_uploads/test_rock_inventory.py`:

```python
import datetime as dt


def test_sample_info_has_core_loan_fields(db_session):
    """SampleInfo accepts and persists the 4 new fields."""
    sample = SampleInfo(
        sample_id="TESTCORE001",
        well_name="Tuscarora Project CT-3",
        core_lender="Geologica",
        core_interval_ft="895'",
        on_loan_return_date=dt.date(2026, 7, 9),
    )
    db_session.add(sample)
    db_session.flush()

    found = db_session.query(SampleInfo).filter_by(sample_id="TESTCORE001").first()
    assert found.well_name == "Tuscarora Project CT-3"
    assert found.core_lender == "Geologica"
    assert found.core_interval_ft == "895'"
    assert found.on_loan_return_date == dt.date(2026, 7, 9)
```

- [ ] **Step 2: Run test to verify it fails**

```
cd <project root>
pytest tests/services/bulk_uploads/test_rock_inventory.py::test_sample_info_has_core_loan_fields -v
```

Expected: `FAILED` — `AttributeError: 'SampleInfo' object has no attribute 'well_name'` (or similar)

- [ ] **Step 3: Add the 4 fields to SampleInfo**

In `database/models/samples.py`, change the import line and add 4 fields:

```python
# Change:
from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Text, Boolean
# To:
from sqlalchemy import Column, Integer, String, DateTime, Date, Float, ForeignKey, Text, Boolean
```

Add after the `characterized` field (line ~32):

```python
    # Core loan tracking
    well_name = Column(String, nullable=True)
    core_lender = Column(String, nullable=True)
    core_interval_ft = Column(String, nullable=True)  # stored as string, e.g. "895'"
    on_loan_return_date = Column(Date, nullable=True)
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/services/bulk_uploads/test_rock_inventory.py::test_sample_info_has_core_loan_fields -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add database/models/samples.py tests/services/bulk_uploads/test_rock_inventory.py
git commit -m "[fix] add well_name, core_lender, core_interval_ft, on_loan_return_date to SampleInfo

- Tests added: yes
- Docs updated: no"
```

---

## Task 2: Generate and Apply Migration

**Files:**
- Create: `alembic/versions/<hash>_add_core_loan_fields_to_sample_info.py` (generated)

- [ ] **Step 1: Generate the migration**

```bash
cd <project root>
alembic revision --autogenerate -m "add_core_loan_fields_to_sample_info"
```

Expected output: `Generating .../alembic/versions/<hash>_add_core_loan_fields_to_sample_info.py ... done`

- [ ] **Step 2: Review the generated migration**

Open the new file. Verify `upgrade()` contains exactly these 4 `add_column` calls and nothing else:

```python
def upgrade() -> None:
    op.add_column('sample_info', sa.Column('well_name', sa.String(), nullable=True))
    op.add_column('sample_info', sa.Column('core_lender', sa.String(), nullable=True))
    op.add_column('sample_info', sa.Column('core_interval_ft', sa.String(), nullable=True))
    op.add_column('sample_info', sa.Column('on_loan_return_date', sa.Date(), nullable=True))
```

Verify `downgrade()` drops them in reverse order:

```python
def downgrade() -> None:
    op.drop_column('sample_info', 'on_loan_return_date')
    op.drop_column('sample_info', 'core_interval_ft')
    op.drop_column('sample_info', 'core_lender')
    op.drop_column('sample_info', 'well_name')
```

If autogenerate added anything else (unlikely but check), remove the extras — this migration should be purely additive.

- [ ] **Step 3: Apply the migration**

```bash
alembic upgrade head
```

Expected: no errors.

- [ ] **Step 4: Verify downgrade works cleanly**

```bash
alembic downgrade -1
alembic upgrade head
```

Both should succeed without errors.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "[fix] migration: add core/loan fields to sample_info

- Tests added: no
- Docs updated: no"
```

---

## Task 3: Update RockInventoryService

**Files:**
- Modify: `backend/services/bulk_uploads/rock_inventory.py`
- Test: `tests/services/bulk_uploads/test_rock_inventory.py`

Three categories of changes:
1. Alias `pXRF Reading No` → `pxrf_reading_no` (currently not detected)
2. Extend mag susc aliases for `Mag. Suscept. [SI*1e3]` (currently not detected)
3. Map and persist the 4 new fields, with date parsing + overwrite clearing

- [ ] **Step 1: Write the failing tests**

Add these 4 tests to `tests/services/bulk_uploads/test_rock_inventory.py`:

```python
from database.models.analysis import ExternalAnalysis


def test_pxrf_reading_no_alias_recognized(db_session):
    """'pXRF Reading No' column header creates a pXRF ExternalAnalysis record."""
    xlsx = make_excel(
        ["sample_id", "pXRF Reading No"],
        [["TESTALIAS-PXRF1", "708"]],
    )
    created, updated, _imgs, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )
    assert errors == [], f"Unexpected errors: {errors}"
    ea = (
        db_session.query(ExternalAnalysis)
        .filter_by(sample_id="TESTALIAS-PXRF1", analysis_type="pXRF")
        .first()
    )
    assert ea is not None, "Expected pXRF ExternalAnalysis record"
    assert ea.pxrf_reading_no == "708"


def test_mag_susc_alias_recognized(db_session):
    """'Mag. Suscept. [SI*1e3]' column header creates a Magnetic Susceptibility record."""
    xlsx = make_excel(
        ["sample_id", "Mag. Suscept. [SI*1e3]"],
        [["TESTALIAS-MAG1", "23-41"]],
    )
    created, updated, _imgs, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )
    assert errors == [], f"Unexpected errors: {errors}"
    ea = (
        db_session.query(ExternalAnalysis)
        .filter_by(sample_id="TESTALIAS-MAG1", analysis_type="Magnetic Susceptibility")
        .first()
    )
    assert ea is not None, "Expected Magnetic Susceptibility ExternalAnalysis record"
    assert ea.magnetic_susceptibility == "23-41"


def test_master_sample_tracking_new_fields(db_session):
    """Well Name, Core Lender, Core Interval (ft), On Loan Return Date are persisted."""
    import datetime as dt
    xlsx = make_excel(
        ["sample_id", "Well Name", "Core Lender", "Core Interval (ft)", "On Loan Return Date"],
        [["TESTCORE-NEW1", "Tuscarora CT-3", "Geologica", "895'", dt.datetime(2026, 7, 9)]],
    )
    created, updated, _imgs, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )
    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    # service uppercases + removes underscores/spaces from sample_id
    sample = (
        db_session.query(SampleInfo)
        .filter_by(sample_id="TESTCORE-NEW1")
        .first()
    )
    assert sample is not None
    assert sample.well_name == "Tuscarora CT-3"
    assert sample.core_lender == "Geologica"
    assert sample.core_interval_ft == "895'"
    assert sample.on_loan_return_date == dt.date(2026, 7, 9)


def test_overwrite_clears_core_loan_fields(db_session):
    """overwrite=TRUE clears all 4 new fields when no replacement value is given."""
    import datetime as dt
    existing = SampleInfo(
        sample_id="TESTOVERWRITE-CL1",
        well_name="Old Well",
        core_lender="Old Lender",
        core_interval_ft="100'",
        on_loan_return_date=dt.date(2025, 1, 1),
    )
    db_session.add(existing)
    db_session.flush()

    xlsx = make_excel(
        ["sample_id", "overwrite"],
        [["TESTOVERWRITE-CL1", "TRUE"]],
    )
    RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    db_session.refresh(existing)

    assert existing.well_name is None
    assert existing.core_lender is None
    assert existing.core_interval_ft is None
    assert existing.on_loan_return_date is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/services/bulk_uploads/test_rock_inventory.py::test_pxrf_reading_no_alias_recognized tests/services/bulk_uploads/test_rock_inventory.py::test_mag_susc_alias_recognized tests/services/bulk_uploads/test_rock_inventory.py::test_master_sample_tracking_new_fields tests/services/bulk_uploads/test_rock_inventory.py::test_overwrite_clears_core_loan_fields -v
```

Expected: all 4 `FAILED`.

- [ ] **Step 3: Implement the changes in rock_inventory.py**

**3a. Add `import datetime` at the top of the file** (after `import io`):

```python
import datetime
```

**3b. Add `_parse_date` static method** to `RockInventoryService` (after `_parse_bool`):

```python
@staticmethod
def _parse_date(val) -> Optional[datetime.date]:
    """Parse a date-like value to datetime.date. Returns None if unparseable."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    # pd.Timestamp and other objects with a .date() callable
    if hasattr(val, "date") and callable(val.date):
        try:
            return val.date()
        except Exception:
            pass
    if isinstance(val, str):
        stripped = val.strip()
        if not stripped:
            return None
        parsed = pd.to_datetime(stripped, errors="coerce")
        return None if pd.isna(parsed) else parsed.date()
    return None
```

**3c. In `bulk_upsert_samples`, after the header normalization line**, add pXRF alias normalization:

```python
# Normalize headers
df.columns = [str(c).strip().lower() for c in df.columns]

# Rename pXRF column alias to canonical name before field_map lookup
_PXRF_ALIASES = {"pxrf reading no", "pxrf reading no."}
_pxrf_raw = next((c for c in df.columns if c in _PXRF_ALIASES), None)
if _pxrf_raw:
    df = df.rename(columns={_pxrf_raw: "pxrf_reading_no"})
```

**3d. Extend `_MAG_SUSC_ALIASES`** — change the existing line to:

```python
_MAG_SUSC_ALIASES = {
    "magnetic_susceptibility",
    "magnetic susceptibility",
    "mag_susc",
    "mag susc",
    "mag. suscept. [si*1e3]",   # Master Sample Tracking header
    "mag. suscept.",            # short form
}
```

**3e. Extend `field_map`** — add the 8 new entries (natural-language and underscore variants):

```python
field_map = {
    "rock_classification": "rock_classification",
    "state": "state",
    "country": "country",
    "locality": "locality",
    "latitude": "latitude",
    "longitude": "longitude",
    "description": "description",
    "characterized": "characterized",
    # Core / loan fields — both Master Sample Tracking and template-style headers
    "well name": "well_name",
    "well_name": "well_name",
    "core lender": "core_lender",
    "core_lender": "core_lender",
    "core interval (ft)": "core_interval_ft",
    "core_interval_ft": "core_interval_ft",
    "on loan return date": "on_loan_return_date",
    "on_loan_return_date": "on_loan_return_date",
    "overwrite": "overwrite",
}
```

**3f. Add date handling inside the field-update loop** — in the section that processes each `col, attr` pair, add an `elif` for `on_loan_return_date` alongside the existing `latitude`/`longitude`/`characterized` branches:

```python
if attr in {"latitude", "longitude"}:
    try:
        val = float(val) if val is not None else None
    except Exception:
        val = None
elif attr == "characterized":
    parsed = RockInventoryService._parse_bool(val)
    if parsed is not None:
        val = parsed
    else:
        current = getattr(sample, attr)
        val = current if current is not None else False
elif attr == "on_loan_return_date":
    val = RockInventoryService._parse_date(val)
```

**3g. Add new fields to the overwrite clearing list** — extend the existing `for attr in [...]` block:

```python
if overwrite_mode and not is_new:
    for attr in [
        "rock_classification",
        "state",
        "country",
        "locality",
        "latitude",
        "longitude",
        "description",
        "characterized",
        "well_name",
        "core_lender",
        "core_interval_ft",
        "on_loan_return_date",
    ]:
        if attr == "characterized":
            setattr(sample, attr, False)
        else:
            setattr(sample, attr, None)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/services/bulk_uploads/test_rock_inventory.py::test_pxrf_reading_no_alias_recognized tests/services/bulk_uploads/test_rock_inventory.py::test_mag_susc_alias_recognized tests/services/bulk_uploads/test_rock_inventory.py::test_master_sample_tracking_new_fields tests/services/bulk_uploads/test_rock_inventory.py::test_overwrite_clears_core_loan_fields -v
```

Expected: all 4 `PASSED`.

- [ ] **Step 5: Run full rock inventory test suite to verify no regressions**

```
pytest tests/services/bulk_uploads/test_rock_inventory.py -v
```

Expected: all `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add backend/services/bulk_uploads/rock_inventory.py \
        tests/services/bulk_uploads/test_rock_inventory.py
git commit -m "[fix] teach rock_inventory to handle Master Sample Tracking columns

- Alias 'pXRF Reading No' → pxrf_reading_no
- Alias 'Mag. Suscept. [SI*1e3]' for magnetic susceptibility
- Map Well Name, Core Lender, Core Interval (ft), On Loan Return Date
- Parse On Loan Return Date to datetime.date
- Clear new fields in overwrite mode
- Tests added: yes
- Docs updated: no"
```

---

## Task 4: Update Pydantic Schemas

**Files:**
- Modify: `backend/api/schemas/samples.py`

- [ ] **Step 1: Add `date` to the datetime import**

Change:
```python
from datetime import datetime
```
To:
```python
from datetime import date, datetime
```

- [ ] **Step 2: Add the 4 new fields to `SampleCreate`**

```python
class SampleCreate(BaseModel):
    sample_id: str
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    well_name: Optional[str] = None
    core_lender: Optional[str] = None
    core_interval_ft: Optional[str] = None
    on_loan_return_date: Optional[date] = None
```

- [ ] **Step 3: Add the 4 new fields to `SampleUpdate`**

```python
class SampleUpdate(BaseModel):
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    characterized: Optional[bool] = None
    well_name: Optional[str] = None
    core_lender: Optional[str] = None
    core_interval_ft: Optional[str] = None
    on_loan_return_date: Optional[date] = None
```

- [ ] **Step 4: Add the 4 new fields to `SampleResponse`**

```python
class SampleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sample_id: str
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    characterized: bool
    well_name: Optional[str] = None
    core_lender: Optional[str] = None
    core_interval_ft: Optional[str] = None
    on_loan_return_date: Optional[date] = None
    created_at: datetime
```

- [ ] **Step 5: Add the 4 new fields to `SampleDetail`**

```python
class SampleDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sample_id: str
    rock_classification: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    characterized: bool
    well_name: Optional[str] = None
    core_lender: Optional[str] = None
    core_interval_ft: Optional[str] = None
    on_loan_return_date: Optional[date] = None
    created_at: datetime
    photos: list[SamplePhotoResponse] = []
    analyses: list[ExternalAnalysisResponse] = []
    elemental_results: list[ElementalAnalysisItem] = []
    experiments: list[LinkedExperiment] = []
```

- [ ] **Step 6: Run the API test suite to verify no regressions**

```
pytest tests/api/test_samples.py -v
```

Expected: all `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add backend/api/schemas/samples.py
git commit -m "[fix] add core/loan fields to sample Pydantic schemas

- Tests added: no
- Docs updated: no"
```

---

## Task 5: Update Rock Inventory Download Template

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py`

The rock-inventory template is built inline in `_get_template_bytes`. Find the `if upload_type == "rock-inventory":` block (around line 685).

- [ ] **Step 1: Update headers list, example row, and INSTRUCTIONS sheet**

Replace the existing `headers` list and `example_row`:

```python
headers = [
    "sample_id", "rock_classification", "state", "country",
    "locality", "latitude", "longitude", "description",
    "characterized", "pxrf_reading_no", "magnetic_susceptibility",
    "well_name", "core_lender", "core_interval_ft", "on_loan_return_date",
    "overwrite",
]
example_row = [
    "S001", "Basalt", "BC", "Canada", "Vancouver Island",
    49.5, -125.0, "Fresh olivine basalt", "FALSE", "", "",
    "", "", "", "",
    "FALSE",
]
```

Add 4 new rows to the `instructions` list (after the `magnetic_susceptibility` entry):

```python
(
    "well_name",
    "Well or borehole name (e.g. Tuscarora Project CT-3). Applies to core samples only.",
),
(
    "core_lender",
    "Organization lending the core (e.g. Geologica). Applies to core samples only.",
),
(
    "core_interval_ft",
    "Depth interval in feet as a string (e.g. 895'). Applies to core samples only.",
),
(
    "on_loan_return_date",
    "Date core must be returned to lender (YYYY-MM-DD). Applies to core samples only.",
),
```

- [ ] **Step 2: Manually verify the template downloads correctly**

With the dev server running, download the template from:
`GET /api/bulk-uploads/templates/rock-inventory`

Open in Excel and confirm:
- 16 columns present (sample_id through overwrite)
- New 4 columns appear with green optional fill
- INSTRUCTIONS sheet has entries for all 4 new columns

- [ ] **Step 3: Commit**

```bash
git add backend/api/routers/bulk_uploads.py
git commit -m "[fix] add core/loan fields to rock-inventory download template

- Tests added: no
- Docs updated: no"
```

---

## Task 6: Update MODELS.md

**Files:**
- Modify: `docs/MODELS.md`

- [ ] **Step 1: Find the SampleInfo section** (search for `### \`SampleInfo\``)

- [ ] **Step 2: Add the 4 new fields to the Fields list**

In the `### \`SampleInfo\`` section, under `**Fields**:`, add after `description`:

```
  - `well_name` (String, nullable): Well or borehole name for core samples (e.g. "Tuscarora Project CT-3").
  - `core_lender` (String, nullable): Organization lending the core sample (e.g. "Geologica").
  - `core_interval_ft` (String, nullable): Depth interval stored as a string (e.g. "895'").
  - `on_loan_return_date` (Date, nullable): Date the core must be returned to the lender.
```

- [ ] **Step 3: Commit**

```bash
git add docs/MODELS.md
git commit -m "[fix] document well_name, core_lender, core_interval_ft, on_loan_return_date in MODELS.md

- Tests added: no
- Docs updated: yes"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|---|---|
| `Well Name` → `well_name` on SampleInfo | Task 1, 3 |
| `Core Lender` → `core_lender` on SampleInfo | Task 1, 3 |
| `Core Interval (ft)` → `core_interval_ft` (String) | Task 1, 3 |
| `On Loan Return Date` → `on_loan_return_date` (Date) | Task 1, 3 |
| `pXRF Reading No` alias → existing pXRF EA path | Task 3 |
| `Mag. Suscept. [SI*1e3]` alias → existing mag susc EA path | Task 3 |
| Overwrite clears new fields | Task 3 |
| Migration is purely additive | Task 2 |
| API schemas expose new fields (create/update/response/detail) | Task 4 |
| Template download includes new columns | Task 5 |
| MODELS.md updated | Task 6 |

**No gaps found.**
