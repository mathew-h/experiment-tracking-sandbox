# Issue #12 — Sample Analyses Not Consistently Populating

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three gaps in `backend/api/routers/samples.py` that cause pXRF elemental data, XRD mineral phases, and elemental composition results to be missing or inconsistent in the sample detail API.

**Architecture:** All fixes are in one file (`samples.py`). Extract the duplicated pXRF-map-building logic into a private helper `_build_pxrf_map`, then apply it to every endpoint that calls `_to_analysis_response`. Fix `list_analyses` to eagerly load `xrd_analysis`. Fix `get_sample` to fetch elemental results via a JOIN on `external_analysis_id` rather than relying on the nullable `ElementalAnalysis.sample_id` column (which is unset on records created before the column was backfilled).

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x, pytest against a real PostgreSQL test DB (`experiments_test`).

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Modify | `backend/api/routers/samples.py` | Add `_build_pxrf_map`, fix `list_analyses`, fix `get_sample`, fix `create_analysis` |
| Modify | `tests/api/test_samples.py` | 4 new tests covering the three bugs |

No schema changes. No new packages. No locked components touched.

---

## Background: the three bugs

### Bug A — `list_analyses` returns null `pxrf_data` and `xrd_data`

`GET /api/samples/{id}/analyses` (lines 521–536) calls `_to_analysis_response(r)` with no `pxrf_map`, so `pxrf_data` is always `null`. It also never `selectinload`s the `xrd_analysis` relationship, so `xrd_data` is always `null`.

### Bug B — `get_sample` misses elemental results when `ElementalAnalysis.sample_id` is NULL

`get_sample` loads elemental results via the ORM relationship `SampleInfo.elemental_results`, which joins on `ElementalAnalysis.sample_id`. That column is nullable. Records created without a `sample_id` value (possible in historical imports) are silently excluded. The fix: query via `ElementalAnalysis.external_analysis_id → ExternalAnalysis.id WHERE ExternalAnalysis.sample_id = ?` — covers all rows regardless of whether `sample_id` is set.

### Bug C — `create_analysis` POST response has null `pxrf_data`

`POST /api/samples/{id}/analyses` calls `_to_analysis_response(ea)` with no `pxrf_map`, so the returned `analysis.pxrf_data` is always `null` even when the pXRF reading exists. (The UI refetches the full sample after creation, so this doesn't break the tab display — but the POST response is wrong and will break any caller that depends on it.)

---

## Task 1: Write failing tests for all three bugs

**Files:**
- Modify: `tests/api/test_samples.py`

These tests must fail against the current code. Run them to confirm before touching `samples.py`.

- [ ] **Step 1: Add four tests at the bottom of `tests/api/test_samples.py`**

```python
# ── Issue #12 regression tests ────────────────────────────────────────────

def test_list_analyses_returns_pxrf_data(client, db_session):
    """Bug A: list_analyses must populate pxrf_data when the reading exists."""
    from database.models.analysis import PXRFReading, ExternalAnalysis
    _make_sample(db_session, "BUG_A_S01")
    db_session.add(PXRFReading(reading_no="77", fe=25.0, mg=10.0, si=30.0,
                               ni=0.5, cu=0.1, co=0.05, mo=0.02, al=5.0,
                               ca=1.0, k=0.3, au=0.0, zn=0.1))
    db_session.add(ExternalAnalysis(sample_id="BUG_A_S01", analysis_type="pXRF",
                                    pxrf_reading_no="77"))
    db_session.commit()
    resp = client.get("/api/samples/BUG_A_S01/analyses")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["pxrf_data"] is not None, "pxrf_data must not be null"
    assert items[0]["pxrf_data"]["fe"] == pytest.approx(25.0)


def test_list_analyses_returns_xrd_data(client, db_session):
    """Bug A: list_analyses must populate xrd_data when an XRDAnalysis record exists."""
    from database.models.analysis import ExternalAnalysis
    from database.models.xrd import XRDAnalysis
    _make_sample(db_session, "BUG_A_S02")
    ea = ExternalAnalysis(sample_id="BUG_A_S02", analysis_type="XRD")
    db_session.add(ea)
    db_session.flush()
    db_session.add(XRDAnalysis(
        external_analysis_id=ea.id,
        mineral_phases={"lizardite": 65.0, "magnetite": 35.0},
    ))
    db_session.commit()
    resp = client.get("/api/samples/BUG_A_S02/analyses")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["xrd_data"] is not None, "xrd_data must not be null"
    assert items[0]["xrd_data"]["mineral_phases"]["lizardite"] == pytest.approx(65.0)


def test_get_sample_elemental_results_when_sample_id_null(client, db_session):
    """Bug B: elemental_results must appear even when ElementalAnalysis.sample_id is NULL."""
    from database.models.analysis import ExternalAnalysis
    from database.models.characterization import ElementalAnalysis, Analyte
    _make_sample(db_session, "BUG_B_S01")
    analyte = Analyte(analyte_symbol="FeO", unit="%")
    db_session.add(analyte)
    db_session.flush()
    ea = ExternalAnalysis(sample_id="BUG_B_S01", analysis_type="Elemental")
    db_session.add(ea)
    db_session.flush()
    # Deliberately leave sample_id=None to reproduce the historical data pattern
    db_session.add(ElementalAnalysis(
        external_analysis_id=ea.id,
        sample_id=None,
        analyte_id=analyte.id,
        analyte_composition=12.5,
    ))
    db_session.commit()
    resp = client.get("/api/samples/BUG_B_S01")
    assert resp.status_code == 200
    results = resp.json()["elemental_results"]
    assert len(results) == 1, "elemental_results must include rows where sample_id is NULL"
    assert results[0]["analyte_symbol"] == "FeO"
    assert results[0]["analyte_composition"] == pytest.approx(12.5)


def test_create_analysis_response_includes_pxrf_data(client, db_session):
    """Bug C: POST /analyses response must include pxrf_data when the reading exists."""
    from database.models.analysis import PXRFReading
    _make_sample(db_session, "BUG_C_S01")
    db_session.add(PXRFReading(reading_no="88", fe=18.0, mg=8.0, si=28.0,
                               ni=0.4, cu=0.2, co=0.03, mo=0.01, al=4.0,
                               ca=0.8, k=0.2, au=0.0, zn=0.05))
    db_session.commit()
    resp = client.post(
        "/api/samples/BUG_C_S01/analyses",
        json={"analysis_type": "pXRF", "pxrf_reading_no": "88"},
    )
    assert resp.status_code == 201
    analysis = resp.json()["analysis"]
    assert analysis["pxrf_data"] is not None, "pxrf_data must not be null in POST response"
    assert analysis["pxrf_data"]["fe"] == pytest.approx(18.0)
```

- [ ] **Step 2: Add `import pytest` at the top of `tests/api/test_samples.py`** (if not already present — check first)

The file currently does not import `pytest`. Add it as the first import:

```python
import pytest
import io
# ... rest of file unchanged
```

- [ ] **Step 3: Run the four new tests to confirm they fail**

```bash
cd C:/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox
.venv/Scripts/pytest tests/api/test_samples.py::test_list_analyses_returns_pxrf_data tests/api/test_samples.py::test_list_analyses_returns_xrd_data tests/api/test_samples.py::test_get_sample_elemental_results_when_sample_id_null tests/api/test_samples.py::test_create_analysis_response_includes_pxrf_data -v 2>&1 | tail -20
```

Expected: 3–4 FAILs (Bug B may pass if `sample_id=None` raises a FK constraint; in that case note the actual failure reason and adjust the test to match what the constraint allows).

---

## Task 2: Add `_build_pxrf_map` helper and fix `list_analyses`

**Files:**
- Modify: `backend/api/routers/samples.py`

- [ ] **Step 1: Add `_build_pxrf_map` directly above `_avg_pxrf` (around line 243)**

Replace the block starting at line 243:

```python
_PXRF_ELEMENTS = ["fe", "mg", "ni", "cu", "si", "co", "mo", "al", "ca", "k", "au", "zn"]


def _build_pxrf_map(
    analyses: "list[ExternalAnalysis]",
    db: Session,
) -> "dict[str, PXRFReading]":
    """Return a {reading_no: PXRFReading} map for all pXRF analyses in the list."""
    reading_nos: set[str] = set()
    for a in analyses:
        if a.analysis_type == "pXRF" and a.pxrf_reading_no:
            for raw in a.pxrf_reading_no.split(","):
                normed = normalize_pxrf_reading_no(raw)
                if normed:
                    reading_nos.add(normed)
    if not reading_nos:
        return {}
    rows = db.execute(
        select(PXRFReading).where(PXRFReading.reading_no.in_(reading_nos))
    ).scalars().all()
    return {r.reading_no: r for r in rows}
```

- [ ] **Step 2: Simplify the pXRF map block in `get_sample` (around line 183–197) to use the new helper**

Replace the inline pXRF-map building block:

```python
    # Before: ~15 lines of inline pXRF map building
    # After:
    pxrf_map = _build_pxrf_map(list(sample.external_analyses), db)
```

The `all_reading_nos` variable and the `if all_reading_nos:` block are removed; `_build_pxrf_map` handles the empty-set short-circuit internally.

- [ ] **Step 3: Fix `list_analyses` to eager-load `xrd_analysis` and use `_build_pxrf_map`**

Replace the full `list_analyses` function (lines 521–536):

```python
@router.get("/{sample_id}/analyses", response_model=list[ExternalAnalysisResponse])
def list_analyses(
    sample_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ExternalAnalysisResponse]:
    from database.models.analysis import ExternalAnalysis as EA
    from sqlalchemy.orm import selectinload as sl

    rows = db.execute(
        select(EA)
        .where(EA.sample_id == sample_id)
        .options(sl(EA.analysis_files), sl(EA.xrd_analysis))
        .order_by(EA.analysis_date)
    ).scalars().all()
    pxrf_map = _build_pxrf_map(list(rows), db)
    return [_to_analysis_response(r, pxrf_map) for r in rows]
```

- [ ] **Step 4: Run the Bug A tests to confirm they pass**

```bash
.venv/Scripts/pytest tests/api/test_samples.py::test_list_analyses_returns_pxrf_data tests/api/test_samples.py::test_list_analyses_returns_xrd_data -v 2>&1 | tail -15
```

Expected: both PASS.

- [ ] **Step 5: Run the full samples test suite to confirm no regressions**

```bash
.venv/Scripts/pytest tests/api/test_samples.py -v 2>&1 | tail -25
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/samples.py tests/api/test_samples.py
git commit -m "[#12] Extract _build_pxrf_map; fix list_analyses pXRF+XRD

- Add _build_pxrf_map helper to deduplicate reading-number lookup
- Replace inline map-building in get_sample with helper call
- Fix list_analyses: add xrd_analysis selectinload, call _build_pxrf_map
- Tests: test_list_analyses_returns_pxrf_data, test_list_analyses_returns_xrd_data

- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Fix `get_sample` elemental results query (Bug B)

**Files:**
- Modify: `backend/api/routers/samples.py`

The `SampleInfo.elemental_results` ORM relationship joins on `ElementalAnalysis.sample_id`, which is nullable. Switch to a JOIN query that finds all `ElementalAnalysis` rows whose parent `ExternalAnalysis` belongs to this sample — regardless of whether `ElementalAnalysis.sample_id` is set.

- [ ] **Step 1: In `get_sample`, remove `selectinload(SampleInfo.elemental_results)` from the query options**

The `.options(...)` block currently includes:
```python
selectinload(SampleInfo.elemental_results).selectinload(ElementalAnalysis.analyte),
```
Remove that line. The elemental results will be fetched separately below.

Also add the necessary imports at the top of `get_sample` (they are local imports, so add them to the existing `from database.models...` block inside the function):

```python
    from database.models.conditions import ExperimentalConditions
    from database.models.characterization import ElementalAnalysis, Analyte
    from database.models.analysis import PXRFReading
    from database.models.xrd import XRDAnalysis
```

(`Analyte` and `ElementalAnalysis` are already imported via `from database.models.characterization import ElementalAnalysis`; add `Analyte` if not present.)

- [ ] **Step 2: After the `pxrf_map = _build_pxrf_map(...)` line, add the elemental results query**

```python
    # Fetch elemental results via the external_analysis join to catch rows
    # where ElementalAnalysis.sample_id is NULL (historical import pattern).
    from database.models.characterization import ElementalAnalysis
    elemental_rows = db.execute(
        select(ElementalAnalysis)
        .join(ExternalAnalysis, ElementalAnalysis.external_analysis_id == ExternalAnalysis.id)
        .where(ExternalAnalysis.sample_id == sample_id)
        .options(selectinload(ElementalAnalysis.analyte))
    ).scalars().all()
```

- [ ] **Step 3: Replace `sample.elemental_results` with `elemental_rows` in the `SampleDetail(...)` constructor**

Change:
```python
        elemental_results=[
            ElementalAnalysisItem(
                analyte_symbol=r.analyte.analyte_symbol,
                unit=r.analyte.unit,
                analyte_composition=r.analyte_composition,
            )
            for r in sample.elemental_results
            if r.analyte
        ],
```
To:
```python
        elemental_results=[
            ElementalAnalysisItem(
                analyte_symbol=r.analyte.analyte_symbol,
                unit=r.analyte.unit,
                analyte_composition=r.analyte_composition,
            )
            for r in elemental_rows
            if r.analyte
        ],
```

- [ ] **Step 4: Run Bug B test**

```bash
.venv/Scripts/pytest tests/api/test_samples.py::test_get_sample_elemental_results_when_sample_id_null -v 2>&1 | tail -15
```

Expected: PASS. If it fails with a FK constraint error (PostgreSQL enforces `NOT NULL` on `sample_id` at the DB level), the test needs to be adjusted — skip setting `sample_id=None` and instead verify the JOIN path works for the normal case. Report the actual failure.

- [ ] **Step 5: Run full samples test suite**

```bash
.venv/Scripts/pytest tests/api/test_samples.py -v 2>&1 | tail -25
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/samples.py tests/api/test_samples.py
git commit -m "[#12] Fix get_sample elemental_results to use JOIN query

- Remove selectinload(SampleInfo.elemental_results) from options
- Query ElementalAnalysis via ExternalAnalysis.sample_id JOIN instead
- Catches rows where ElementalAnalysis.sample_id is NULL
- Tests: test_get_sample_elemental_results_when_sample_id_null

- Tests added: yes
- Docs updated: no"
```

---

## Task 4: Fix `create_analysis` POST response (Bug C)

**Files:**
- Modify: `backend/api/routers/samples.py`

- [ ] **Step 1: In `create_analysis`, build pXRF map after `db.refresh(ea)` and pass it to `_to_analysis_response`**

The current return block (around lines 513–517):
```python
    db.commit()
    db.refresh(ea)
    return ExternalAnalysisWithWarnings(
        analysis=_to_analysis_response(ea), warnings=warnings
    )
```

Replace with:
```python
    db.commit()
    db.refresh(ea)
    pxrf_map = _build_pxrf_map([ea], db)
    return ExternalAnalysisWithWarnings(
        analysis=_to_analysis_response(ea, pxrf_map), warnings=warnings
    )
```

- [ ] **Step 2: Run Bug C test**

```bash
.venv/Scripts/pytest tests/api/test_samples.py::test_create_analysis_response_includes_pxrf_data -v 2>&1 | tail -15
```

Expected: PASS.

- [ ] **Step 3: Run full samples test suite**

```bash
.venv/Scripts/pytest tests/api/test_samples.py -v 2>&1 | tail -25
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/api/routers/samples.py tests/api/test_samples.py
git commit -m "[#12] Fix create_analysis POST response to include pxrf_data

- Call _build_pxrf_map([ea], db) after refresh
- Pass map to _to_analysis_response so pxrf_data is populated in response
- Tests: test_create_analysis_response_includes_pxrf_data

- Tests added: yes
- Docs updated: no"
```

---

## Task 5: Browser verification with Chrome DevTools

Verify the three fixes are visible in the running app.

- [ ] **Step 1: Navigate to the Samples list**

Navigate to `http://localhost:5173/samples`. Take a screenshot and confirm the page loads.

- [ ] **Step 2: Open a sample that has pXRF data (check the Analyses tab)**

Click a sample with `has_pxrf: true` (shown by the pXRF badge in the list). Navigate to its detail page. Click the **Analyses** tab. Take a screenshot — the pXRF analysis rows should show elemental data (Fe, Mg, Si, etc.) with values, not blank.

- [ ] **Step 3: Check a sample with XRD data**

Click a sample with `has_xrd: true`. In the Analyses tab, the XRD analysis row should show mineral phases (e.g., "Mineral phases (wt%)" table). Take a screenshot.

- [ ] **Step 4: Check a sample with elemental composition**

Open a sample that has elemental data. In the **Overview** tab, the "Elemental Composition" table should appear with analyte rows. Take a screenshot.

- [ ] **Step 5: Inspect the network request for `GET /api/samples/{id}/analyses`**

Open DevTools → Network → filter XHR. Navigate to the Analyses tab. Find the `analyses` request and check the response body — confirm `pxrf_data` and `xrd_data` are non-null for the relevant analyses.

---

## Self-Review

**Spec coverage:**
- Bug A (list_analyses missing pXRF + XRD) → Task 2 ✓
- Bug B (elemental_results missing when sample_id NULL) → Task 3 ✓
- Bug C (create_analysis response missing pXRF) → Task 4 ✓
- Tests for all three → Task 1 ✓
- Browser verification → Task 5 ✓

**Placeholder scan:** None. All code blocks are complete and self-contained.

**Type consistency:**
- `_build_pxrf_map(analyses: list[ExternalAnalysis], db: Session) -> dict[str, PXRFReading]` — defined in Task 2, called in Task 2 (`list_analyses`), Task 2 (`get_sample`), and Task 4 (`create_analysis`). Name is consistent across all tasks.
- `_to_analysis_response(a, pxrf_map)` — existing function signature already accepts `pxrf_map` as second arg. Tasks 2 and 4 both pass it correctly.
- `elemental_rows` — introduced in Task 3 Step 2, consumed in Task 3 Step 3. Consistent.
