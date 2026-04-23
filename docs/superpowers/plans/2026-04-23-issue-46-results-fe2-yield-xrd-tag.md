# Issue #46: Fe²⁺ Yield Columns + XRD Run Date Tag — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the already-calculated `ferrous_iron_yield_h2_pct`/`ferrous_iron_yield_nh3_pct` values in the Results tab table, add `xrd_run_date` to the database and bulk upload parser, and render a `• XRD` badge alongside the existing `• ICP` badge on result rows.

**Architecture:** Part 1 (Fe²⁺ columns) is pure API plumbing — values are already calculated and stored on `ScalarResults`; they just need to flow through `ResultWithFlagsResponse` → router → `ResultWithFlags` TypeScript interface → table render. Part 2 (XRD date) adds a new nullable `DateTime` column to `ScalarResults`, creates a migration, wires the column through the same API pipeline, extends the master bulk upload parser to read an `XRD Run Date` Excel column, and renders the badge in the ICP cell.

**Tech Stack:** Python 3.11 / SQLAlchemy / Alembic, FastAPI / Pydantic v2, React 18 / TypeScript / Tailwind CSS, pytest / Vitest

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `database/models/results.py` | Add `xrd_run_date` column to `ScalarResults` (after `gc_run_date`) |
| Create | `alembic/versions/<rev>_add_xrd_run_date_to_scalar_results.py` | Additive migration: add + drop `xrd_run_date` |
| Modify | `backend/services/bulk_uploads/master_bulk_upload.py` | Parse `XRD Run Date` column and map to `xrd_run_date` |
| Modify | `docs/specs/master_results_sync.md` | Add `XRD Run Date` row to column definitions table |
| Modify | `backend/api/schemas/results.py` | Add `ferrous_iron_yield_h2_pct`, `ferrous_iron_yield_nh3_pct`, `xrd_run_date` to `ResultWithFlagsResponse` |
| Modify | `backend/api/routers/experiments.py` | Populate three new fields in `get_experiment_results` serializer |
| Modify | `frontend/src/api/experiments.ts` | Extend `ResultWithFlags` interface with three new fields |
| Modify | `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` | Add `fmtPct`, update `GRID` (12→14 cols), insert two column headers/cells, add XRD badge |
| Modify | `tests/api/test_results.py` | Add three tests for new fields in the results endpoint |
| Modify | `tests/services/bulk_uploads/test_master_bulk_upload.py` | Add test for XRD Run Date parsing |
| Create | `frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx` | Vitest tests: new columns render, `fmtPct` formatting, XRD badge |

---

## Task 1: Add `xrd_run_date` to `ScalarResults` and create the migration

**Files:**
- Modify: `database/models/results.py` (around line 85 — immediately after `gc_run_date`)
- Create: `alembic/versions/<generated>_add_xrd_run_date_to_scalar_results.py`

- [ ] **Step 1: Write failing test**

Add at the bottom of `tests/api/test_results.py`:

```python
def test_scalar_results_has_xrd_run_date_field():
    """ScalarResults model must have an xrd_run_date column."""
    from database.models.results import ScalarResults
    assert hasattr(ScalarResults, 'xrd_run_date'), "xrd_run_date column missing from ScalarResults"
```

- [ ] **Step 2: Run test to confirm it fails**

Run from project root (`experiment_tracking_sandbox/`):
```
python -m pytest tests/api/test_results.py::test_scalar_results_has_xrd_run_date_field -v
```
Expected: `FAILED — AssertionError: xrd_run_date column missing from ScalarResults`

- [ ] **Step 3: Add `xrd_run_date` to `database/models/results.py`**

Locate lines 85–87 (the `nmr_run_date` / `icp_run_date` / `gc_run_date` block in `ScalarResults`). Insert one line after `gc_run_date`:

```python
    nmr_run_date = Column(DateTime(timezone=True), nullable=True)
    icp_run_date = Column(DateTime(timezone=True), nullable=True)
    gc_run_date = Column(DateTime(timezone=True), nullable=True)
    xrd_run_date = Column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Confirm test passes**

```
python -m pytest tests/api/test_results.py::test_scalar_results_has_xrd_run_date_field -v
```
Expected: `PASSED`

- [ ] **Step 5: Generate migration**

```bash
alembic revision --autogenerate -m "add xrd_run_date to scalar_results"
```

Open the newest file in `alembic/versions/`. Verify it contains exactly these two functions (edit manually if autogenerate missed it):

```python
def upgrade() -> None:
    op.add_column('scalar_results', sa.Column('xrd_run_date', sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column('scalar_results', 'xrd_run_date')
```

The `down_revision` must be `'ad32def91adc'` (current head before this change).

- [ ] **Step 6: Apply and round-trip the migration**

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```
Expected: all three commands complete without errors.

- [ ] **Step 7: Commit**

```bash
git add database/models/results.py alembic/versions/
git commit -m "[#46] add xrd_run_date column to scalar_results

- Tests added: yes
- Docs updated: no"
```

---

## Task 2: Extend the Master Results Sync parser to read `XRD Run Date`

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (lines ~135-156)
- Modify: `docs/specs/master_results_sync.md` (column table, around line 44–46)
- Modify: `tests/services/bulk_uploads/test_master_bulk_upload.py` (add test at the bottom)

- [ ] **Step 1: Write failing test**

Add at the bottom of `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
def test_xrd_run_date_parsed_and_stored(db_session: Session):
    """Master upload stores xrd_run_date when 'XRD Run Date' column is present."""
    from database.models.experiments import Experiment
    from database.models.results import ExperimentalResults, ScalarResults
    from tests.services.bulk_uploads.excel_helpers import make_excel_multisheet

    _seed_experiment(db_session, "HPHT_XRD001", 7780)

    xrd_headers = [
        "Experiment ID", "Duration (Days)", "Description", "Sample Date",
        "NMR Run Date", "ICP Run Date", "GC Run Date", "XRD Run Date",
        "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
        "Sample pH", "Sample Conductivity (mS/cm)",
        "Sampled Solution Volume (mL)", "Modification", "Overwrite",
    ]
    xlsx = make_excel_multisheet({"Dashboard": (xrd_headers, [
        ["HPHT_XRD001", 7.0, "Day 7 XRD", None, None, None, None, "2026-04-15",
         5.0, None, None, None, 7.1, None, None, None, "FALSE"],
    ])})

    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    exp = db_session.execute(
        select(Experiment).where(Experiment.experiment_id == "HPHT_XRD001")
    ).scalar_one()
    er = db_session.execute(
        select(ExperimentalResults).where(ExperimentalResults.experiment_fk == exp.id)
    ).scalar_one()
    scalar = db_session.execute(
        select(ScalarResults).where(ScalarResults.result_id == er.id)
    ).scalar_one()

    assert scalar.xrd_run_date is not None
    assert scalar.xrd_run_date.year == 2026
    assert scalar.xrd_run_date.month == 4
    assert scalar.xrd_run_date.day == 15
```

The `select` import is already present at the top of the test file (`from sqlalchemy import select` — if missing, add it).

- [ ] **Step 2: Run test to confirm it fails**

```
python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py::test_xrd_run_date_parsed_and_stored -v
```
Expected: `FAILED` — `scalar.xrd_run_date is not None` fails because the parser doesn't map the column yet.

- [ ] **Step 3: Update the parse block in `master_bulk_upload.py`**

Locate lines ~135–137 (nmr/icp/gc parsing) and add `xrd_run_date` immediately after:

```python
        nmr_run_date = _parse_date(row.get("NMR Run Date"))
        icp_run_date = _parse_date(row.get("ICP Run Date"))
        gc_run_date = _parse_date(row.get("GC Run Date"))
        xrd_run_date = _parse_date(row.get("XRD Run Date"))
```

Locate the `result_data` dict (lines ~152–156) and add `"xrd_run_date"` after `"gc_run_date"`:

```python
            "nmr_run_date": nmr_run_date,
            "icp_run_date": icp_run_date,
            "gc_run_date": gc_run_date,
            "xrd_run_date": xrd_run_date,
```

- [ ] **Step 4: Confirm new test passes**

```
python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py::test_xrd_run_date_parsed_and_stored -v
```
Expected: `PASSED`

- [ ] **Step 5: Run full master bulk upload test suite (regression check)**

```
python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -v
```
Expected: all tests pass. The existing tests use rows without an "XRD Run Date" column; `row.get("XRD Run Date")` returns `None` → `_parse_date(None)` → `None` → stripped from `result_data` by the existing `{k: v for k, v in result_data.items() if v is not None ...}` filter, so no existing row is affected.

- [ ] **Step 6: Update `docs/specs/master_results_sync.md`**

Find the table rows for NMR/ICP/GC Run Date (around line 44–46) and insert the XRD row:

```markdown
| `NMR Run Date` | No | Stored as metadata on result | Date |
| `ICP Run Date` | No | Stored as metadata on result | Date |
| `GC Run Date`  | No | Stored as metadata on result | Date |
| `XRD Run Date` | No | Stored as metadata on result | Date |
```

- [ ] **Step 7: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py \
        docs/specs/master_results_sync.md \
        tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "[#46] parse XRD Run Date in master bulk upload

- Tests added: yes
- Docs updated: yes"
```

---

## Task 3: Expose new fields in API schema and router

**Files:**
- Modify: `backend/api/schemas/results.py` (lines 105–129 — `ResultWithFlagsResponse`)
- Modify: `backend/api/routers/experiments.py` (lines 195–216 — `get_experiment_results`)

- [ ] **Step 1: Write failing tests**

Add to `tests/api/test_results.py` (add `import pytest` at the top of the file):

```python
import pytest

def test_results_endpoint_includes_ferrous_yield_columns(client, db_session):
    """GET /experiments/{id}/results returns ferrous_iron_yield_h2_pct and _nh3_pct."""
    exp, result = _seed(db_session)
    scalar = ScalarResults(
        result_id=result.id,
        ferrous_iron_yield_h2_pct=16.8,
        ferrous_iron_yield_nh3_pct=24.6,
    )
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["ferrous_iron_yield_h2_pct"] == pytest.approx(16.8)
    assert data[0]["ferrous_iron_yield_nh3_pct"] == pytest.approx(24.6)


def test_results_endpoint_includes_xrd_run_date(client, db_session):
    """GET /experiments/{id}/results returns xrd_run_date per row."""
    exp, result = _seed(db_session)
    scalar = ScalarResults(
        result_id=result.id,
        xrd_run_date=datetime(2026, 4, 15, tzinfo=timezone.utc),
    )
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["xrd_run_date"] is not None
    assert "2026-04-15" in data[0]["xrd_run_date"]


def test_results_endpoint_xrd_run_date_null_when_absent(client, db_session):
    """xrd_run_date is null in the response when not set on the scalar row."""
    exp, result = _seed(db_session)
    scalar = ScalarResults(result_id=result.id, gross_ammonium_concentration_mM=1.0)
    db_session.add(scalar)
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["xrd_run_date"] is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```
python -m pytest \
  tests/api/test_results.py::test_results_endpoint_includes_ferrous_yield_columns \
  tests/api/test_results.py::test_results_endpoint_includes_xrd_run_date \
  tests/api/test_results.py::test_results_endpoint_xrd_run_date_null_when_absent \
  -v
```
Expected: all three `FAILED` — the fields are not in the API response yet.

- [ ] **Step 3: Update `ResultWithFlagsResponse` in `backend/api/schemas/results.py`**

Replace the `ResultWithFlagsResponse` class (lines 105–129) with:

```python
class ResultWithFlagsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_fk: int
    time_post_reaction_days: Optional[float] = None
    time_post_reaction_bucket_days: Optional[float] = None
    cumulative_time_post_reaction_days: Optional[float] = None
    is_primary_timepoint_result: bool
    description: str
    created_at: datetime
    has_scalar: bool = False
    has_icp: bool = False
    has_brine_modification: bool = False
    brine_modification_description: Optional[str] = None
    # Key scalar values for the list (None if no scalar)
    grams_per_ton_yield: Optional[float] = None
    h2_grams_per_ton_yield: Optional[float] = None
    h2_micromoles: Optional[float] = None
    gross_ammonium_concentration_mM: Optional[float] = None
    background_ammonium_concentration_mM: Optional[float] = None
    final_conductivity_mS_cm: Optional[float] = None
    final_ph: Optional[float] = None
    scalar_measurement_date: Optional[datetime] = None
    ferrous_iron_yield_h2_pct: Optional[float] = None
    ferrous_iron_yield_nh3_pct: Optional[float] = None
    xrd_run_date: Optional[datetime] = None
```

- [ ] **Step 4: Update the router serializer in `backend/api/routers/experiments.py`**

Replace the `out.append(ResultWithFlagsResponse(...))` call (lines ~195–216) with:

```python
        out.append(ResultWithFlagsResponse(
            id=r.id,
            experiment_fk=r.experiment_fk,
            time_post_reaction_days=r.time_post_reaction_days,
            time_post_reaction_bucket_days=r.time_post_reaction_bucket_days,
            cumulative_time_post_reaction_days=r.cumulative_time_post_reaction_days,
            is_primary_timepoint_result=r.is_primary_timepoint_result,
            description=r.description,
            created_at=r.created_at,
            has_scalar=scalar is not None,
            has_icp=icp is not None,
            has_brine_modification=r.has_brine_modification,
            brine_modification_description=r.brine_modification_description,
            grams_per_ton_yield=scalar.grams_per_ton_yield if scalar else None,
            h2_grams_per_ton_yield=scalar.h2_grams_per_ton_yield if scalar else None,
            h2_micromoles=scalar.h2_micromoles if scalar else None,
            gross_ammonium_concentration_mM=scalar.gross_ammonium_concentration_mM if scalar else None,
            background_ammonium_concentration_mM=scalar.background_ammonium_concentration_mM if scalar else None,
            final_conductivity_mS_cm=scalar.final_conductivity_mS_cm if scalar else None,
            final_ph=scalar.final_ph if scalar else None,
            scalar_measurement_date=scalar.measurement_date if scalar else None,
            ferrous_iron_yield_h2_pct=scalar.ferrous_iron_yield_h2_pct if scalar else None,
            ferrous_iron_yield_nh3_pct=scalar.ferrous_iron_yield_nh3_pct if scalar else None,
            xrd_run_date=scalar.xrd_run_date if scalar else None,
        ))
```

- [ ] **Step 5: Confirm the three new tests pass**

```
python -m pytest \
  tests/api/test_results.py::test_results_endpoint_includes_ferrous_yield_columns \
  tests/api/test_results.py::test_results_endpoint_includes_xrd_run_date \
  tests/api/test_results.py::test_results_endpoint_xrd_run_date_null_when_absent \
  -v
```
Expected: all three `PASSED`.

- [ ] **Step 6: Run full results + experiments test suite**

```
python -m pytest tests/api/test_results.py tests/api/test_experiments.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/api/schemas/results.py \
        backend/api/routers/experiments.py \
        tests/api/test_results.py
git commit -m "[#46] expose ferrous yield pct and xrd_run_date in results API

- Tests added: yes
- Docs updated: no"
```

---

## Task 4: Extend the TypeScript `ResultWithFlags` interface

**Files:**
- Modify: `frontend/src/api/experiments.ts` (lines 52–73 — `ResultWithFlags`)

- [ ] **Step 1: Replace `ResultWithFlags` in `frontend/src/api/experiments.ts`**

Replace the interface (lines 52–73) with:

```typescript
export interface ResultWithFlags {
  id: number
  experiment_fk: number
  time_post_reaction_days: number | null
  time_post_reaction_bucket_days: number | null
  cumulative_time_post_reaction_days: number | null
  is_primary_timepoint_result: boolean
  description: string
  created_at: string
  has_scalar: boolean
  has_icp: boolean
  has_brine_modification: boolean
  brine_modification_description: string | null
  grams_per_ton_yield: number | null
  h2_grams_per_ton_yield: number | null
  h2_micromoles: number | null
  gross_ammonium_concentration_mM: number | null
  background_ammonium_concentration_mM: number | null
  final_conductivity_mS_cm: number | null
  final_ph: number | null
  scalar_measurement_date: string | null
  ferrous_iron_yield_h2_pct: number | null
  ferrous_iron_yield_nh3_pct: number | null
  xrd_run_date: string | null
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend
npx tsc --noEmit
```
Expected: 0 errors. (If you see errors referencing `ferrous_iron_yield_h2_pct` or `xrd_run_date` missing in `ResultsTab.tsx`, that's expected — fix in Task 5.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/experiments.ts
git commit -m "[#46] extend ResultWithFlags with ferrous yield and xrd_run_date

- Tests added: no
- Docs updated: no"
```

---

## Task 5: Update the Results tab UI — new columns and XRD badge

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`

Changes:
1. Add `fmtPct` formatter after `fmtDate`
2. Expand `GRID` from 12 to 14 columns
3. Insert two header cells: `Fe²⁺ NH₃ (%)` after `NH₄ (g/t)`, `Fe²⁺ H₂ (%)` after `H₂ (g/t)`
4. Insert two data cells using `fmtPct`
5. Extend the ICP cell to also render `• XRD` when `xrd_run_date` is set

- [ ] **Step 1: Write failing frontend tests**

Create `frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ResultsTab } from '../ResultsTab'
import type { ResultWithFlags } from '@/api/experiments'
import * as experimentsApiModule from '@/api/experiments'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getResults: vi.fn(),
    updateBackgroundAmmonium: vi.fn(),
  },
}))

vi.mock('@/api/results', () => ({
  resultsApi: {
    getScalar: vi.fn(),
    getIcp: vi.fn(),
  },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const baseResult: ResultWithFlags = {
  id: 1,
  experiment_fk: 10,
  time_post_reaction_days: 7,
  time_post_reaction_bucket_days: 7,
  cumulative_time_post_reaction_days: 7,
  is_primary_timepoint_result: true,
  description: 'T7',
  created_at: '2026-04-01T00:00:00Z',
  has_scalar: false,
  has_icp: false,
  has_brine_modification: false,
  brine_modification_description: null,
  grams_per_ton_yield: null,
  h2_grams_per_ton_yield: null,
  h2_micromoles: null,
  gross_ammonium_concentration_mM: null,
  background_ammonium_concentration_mM: null,
  final_conductivity_mS_cm: null,
  final_ph: null,
  scalar_measurement_date: null,
  ferrous_iron_yield_h2_pct: null,
  ferrous_iron_yield_nh3_pct: null,
  xrd_run_date: null,
}

describe('ResultsTab — new columns', () => {
  it('renders Fe²⁺ NH₃ (%) column header', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('Fe²⁺ NH₃ (%)')).toBeInTheDocument()
  })

  it('renders Fe²⁺ H₂ (%) column header', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('Fe²⁺ H₂ (%)')).toBeInTheDocument()
  })

  it('renders 24.6% for ferrous_iron_yield_nh3_pct = 24.6', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, ferrous_iron_yield_nh3_pct: 24.6 },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('24.6%')).toBeInTheDocument()
  })

  it('renders 16.8% for ferrous_iron_yield_h2_pct = 16.8', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, ferrous_iron_yield_h2_pct: 16.8 },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('16.8%')).toBeInTheDocument()
  })

  it('renders XRD badge when xrd_run_date is set', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, xrd_run_date: '2026-04-15T00:00:00Z' },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    expect(await screen.findByText('XRD')).toBeInTheDocument()
  })

  it('does not render XRD badge when xrd_run_date is null', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([baseResult])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    await screen.findByText('T+7')
    expect(screen.queryByText('XRD')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd frontend
npx vitest run src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx
```
Expected: failures on column headers and badge assertions.

- [ ] **Step 3: Add `fmtPct` and update `GRID` in `ResultsTab.tsx`**

After the `fmtDate` function (line 17), insert:

```typescript
function fmtPct(n: number | null | undefined, decimals = 1) {
  return n != null ? `${n.toFixed(decimals)}%` : '—'
}
```

Replace the `GRID` constant (line 19):

```typescript
const GRID = 'grid-cols-[1.5rem_5rem_6rem_5rem_5rem_4.5rem_5rem_5rem_4.5rem_4rem_6rem_5rem_minmax(0,1fr)_1.5rem]'
```

Column mapping (left to right, 14 cols):
`[★ | Time(d) | SampleDate | GrossNH₄(mM) | NH₄(g/t) | Fe²⁺NH₃(%) | H₂(µmol) | H₂(g/t) | Fe²⁺H₂(%) | pH | Cond | ICP+XRD | SamplingMod | ▼]`

- [ ] **Step 4: Update the header row in `ResultsTab.tsx`**

Replace the header `<div>` (lines ~184–197) with:

```tsx
          <div className={`grid ${GRID} gap-2 px-4 py-2 border-b border-surface-border text-xs text-ink-muted`}>
            <span></span>
            <span>Time (d)</span>
            <span>Sample Date</span>
            <span>Gross NH₄ (mM)</span>
            <span>NH₄ (g/t)</span>
            <span>Fe²⁺ NH₃ (%)</span>
            <span>H₂ (µmol)</span>
            <span>H₂ (g/t)</span>
            <span>Fe²⁺ H₂ (%)</span>
            <span>pH</span>
            <span>Cond. (mS/cm)</span>
            <span>ICP</span>
            <span>Sampling Mod</span>
            <span></span>
          </div>
```

- [ ] **Step 5: Update the data row in `ResultsTab.tsx`**

Replace the data `<div>` inside `results.map` (lines ~200–225):

```tsx
              <div
                className={`grid ${GRID} gap-2 px-4 py-2 border-b border-surface-border/50 hover:bg-surface-raised cursor-pointer items-center`}
                onClick={() => toggle(r.id)}
              >
                <span className="text-xs text-ink-muted">{r.is_primary_timepoint_result ? '★' : ''}</span>
                <span className="font-mono-data text-sm text-ink-primary">T+{r.time_post_reaction_days ?? '?'}</span>
                <span className="font-mono-data text-xs text-ink-secondary">{fmtDate(r.scalar_measurement_date)}</span>
                <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.gross_ammonium_concentration_mM)}</span>
                <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.grams_per_ton_yield)}</span>
                <span className="font-mono-data text-xs text-ink-secondary">{fmtPct(r.ferrous_iron_yield_nh3_pct)}</span>
                <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.h2_micromoles)}</span>
                <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.h2_grams_per_ton_yield)}</span>
                <span className="font-mono-data text-xs text-ink-secondary">{fmtPct(r.ferrous_iron_yield_h2_pct)}</span>
                <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.final_ph, 1)}</span>
                <span className="font-mono-data text-xs text-ink-secondary">{fmt(r.final_conductivity_mS_cm)}</span>
                <span className="flex items-center gap-1">
                  {r.has_icp && <Badge variant="info" dot>ICP</Badge>}
                  {r.xrd_run_date && <Badge variant="info" dot>XRD</Badge>}
                </span>
                <span className="flex items-center gap-1 min-w-0">
                  {r.has_brine_modification && <Badge variant="warning" dot>MOD</Badge>}
                  {r.brine_modification_description && (
                    <span
                      className="truncate text-xs text-ink-secondary"
                      title={r.brine_modification_description}
                    >
                      {r.brine_modification_description}
                    </span>
                  )}
                </span>
                <span className="text-ink-muted text-xs">{expanded.has(r.id) ? '▲' : '▼'}</span>
              </div>
```

- [ ] **Step 6: Run frontend tests**

```bash
cd frontend
npx vitest run src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx
```
Expected: all 6 tests `PASSED`.

- [ ] **Step 7: TypeScript check**

```bash
cd frontend
npx tsc --noEmit
```
Expected: 0 errors.

- [ ] **Step 8: Run full frontend test suite**

```bash
cd frontend
npx vitest run
```
Expected: all tests pass, no regressions.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/ResultsTab.tsx \
        frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx
git commit -m "[#46] add Fe2+ yield columns and XRD badge to results table

- Tests added: yes
- Docs updated: no"
```

---

## Task 6: Full-suite verification and PR

- [ ] **Step 1: Run full backend suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -40
```
Expected: all pass. If `xrd_run_date` attribute errors appear, confirm `alembic upgrade head` was applied.

- [ ] **Step 2: Run full frontend suite**

```bash
cd frontend && npx vitest run
```
Expected: all pass.

- [ ] **Step 3: Open PR**

```bash
gh pr create \
  --base develop \
  --title "feat: Add Fe2+ yield columns and XRD run date tag to results table (#46)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `ferrous_iron_yield_nh3_pct` and `ferrous_iron_yield_h2_pct` columns to the Results tab table (values were already calculated/stored, just not surfaced)
- Adds `xrd_run_date` (nullable Date) to `ScalarResults` via additive migration
- Extends Master Results Sync parser to read `XRD Run Date` Excel column
- Renders `• XRD` badge alongside `• ICP` when `xrd_run_date` is set

Closes #46

## Test plan
- [ ] Run `python -m pytest tests/ -v` — all pass
- [ ] Run `cd frontend && npx vitest run` — all pass
- [ ] Upload a Master Results Sync file with `XRD Run Date` column; confirm `xrd_run_date` stored
- [ ] Open an experiment with scalar data that has `ferrous_iron_yield_h2_pct` set; confirm `16.8%`-style value appears in the table
- [ ] Confirm null values show `—` (not `0`, `null`, or blank)
- [ ] Confirm ICP badge still renders when `has_icp=true`
- [ ] Confirm XRD badge appears only when `xrd_run_date` is non-null

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|---|---|
| Fe²⁺ NH₃ (%) column after NH₄ (g/t) | Task 5 Step 4/5 |
| Fe²⁺ H₂ (%) column after H₂ (g/t) | Task 5 Step 4/5 |
| Null values render as `—` | Task 5 Step 3 (`fmtPct`) |
| 1 decimal place with % suffix | Task 5 Step 3 (`fmtPct`) |
| Both columns in API response | Task 3 Steps 3/4 |
| `xrd_run_date` migration (upgrade + downgrade) | Task 1 Step 5 |
| Master Results Sync parses `XRD Run Date` | Task 2 Step 3 |
| Rows without XRD date leave field unchanged | Task 2 Step 5 (existing `None`-filter) |
| `GET /experiments/{id}/results` returns `xrd_run_date` | Task 3 Steps 3/4 |
| `• XRD` badge on rows with `xrd_run_date` | Task 5 Step 5 |
| XRD badge style matches ICP badge | Task 5 Step 5 (`Badge variant="info" dot`) |
| ICP badge behavior unchanged | Task 5 Step 5 (unchanged `r.has_icp` check) |
| No regression on existing column order | Task 5 (full column list preserved, two inserted) |

**Placeholder scan:** None found. All code blocks are complete.

**Type consistency:** `fmtPct` defined in Task 5 Step 3, used in Step 5 in the same task. `xrd_run_date: string | null` defined in Task 4, consumed as `r.xrd_run_date` (string | null — truthy check works correctly) in Task 5 Step 5. `ferrous_iron_yield_h2_pct: Optional[float]` defined in Task 3 Step 3, populated in Step 4 using `scalar.ferrous_iron_yield_h2_pct` (matches `ScalarResults` column name confirmed at line 102 of `database/models/results.py`).
