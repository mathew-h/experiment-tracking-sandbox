# Issue #13: Sample Description in Table View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Description column to the sample inventory table and expose description in the list API response so the existing description search works end-to-end.

**Architecture:** The backend search already filters on `description` (router line 124–126). The gap is that `SampleListItem` (schema + router) omits `description`, so it never reaches the frontend. Fix is: add the field to the Pydantic schema, populate it in the router, add it to the TS interface, and add a table column.

**Tech Stack:** FastAPI + Pydantic v2 (backend), React 18 + TypeScript + TanStack Query v5 + Tailwind (frontend), pytest (backend tests), Playwright (e2e)

---

## File Map

| File | Change |
|------|--------|
| `backend/api/schemas/samples.py` | Add `description: Optional[str] = None` to `SampleListItem` |
| `backend/api/routers/samples.py` | Populate `description` in the `SampleListItem` list comprehension |
| `frontend/src/api/samples.ts` | Add `description: string \| null` to `SampleListItem` interface |
| `frontend/src/pages/Samples.tsx` | Add Description column header + cell to the table |
| `tests/api/test_samples.py` | Add 2 new tests: description in list response, search-by-description |
| `frontend/e2e/journeys/11-sample-management.spec.ts` | Add 1 test: description column visible in table |

---

## Task 1: Add `description` to backend `SampleListItem` schema

**Files:**
- Modify: `backend/api/schemas/samples.py:49-63`
- Test: `tests/api/test_samples.py`

- [ ] **Step 1: Write the failing test**

Add these two tests at the end of `tests/api/test_samples.py`:

```python
def test_list_samples_description_in_response(client, db_session):
    s = SampleInfo(sample_id="DESC_S01", description="Olivine-rich dunite from Oman")
    db_session.add(s)
    db_session.commit()
    resp = client.get("/api/samples")
    assert resp.status_code == 200
    item = next(i for i in resp.json()["items"] if i["sample_id"] == "DESC_S01")
    assert item["description"] == "Olivine-rich dunite from Oman"


def test_list_samples_search_by_description(client, db_session):
    s = SampleInfo(sample_id="DESC_S02", description="Serpentinite with magnetite veins")
    db_session.add(s)
    db_session.commit()
    resp = client.get("/api/samples", params={"search": "magnetite veins"})
    assert resp.status_code == 200
    ids = [i["sample_id"] for i in resp.json()["items"]]
    assert "DESC_S02" in ids
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/api/test_samples.py::test_list_samples_description_in_response tests/api/test_samples.py::test_list_samples_search_by_description -v
```

Expected: FAIL — `KeyError: 'description'` on the first test.

- [ ] **Step 3: Add `description` to `SampleListItem` schema**

In `backend/api/schemas/samples.py`, update `SampleListItem` (currently lines 49–63):

```python
class SampleListItem(BaseModel):
    """Flat projection for the inventory table — no nested objects."""
    model_config = ConfigDict(from_attributes=True)

    sample_id: str
    rock_classification: Optional[str] = None
    locality: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    description: Optional[str] = None
    characterized: bool
    experiment_count: int = 0
    has_pxrf: bool = False
    has_xrd: bool = False
    has_elemental: bool = False
    created_at: datetime
```

- [ ] **Step 4: Populate `description` in the list router**

In `backend/api/routers/samples.py`, update the `items` list comprehension (currently lines 137–152):

```python
    items = [
        SampleListItem(
            sample_id=r.SampleInfo.sample_id,
            rock_classification=r.SampleInfo.rock_classification,
            locality=r.SampleInfo.locality,
            state=r.SampleInfo.state,
            country=r.SampleInfo.country,
            description=r.SampleInfo.description,
            characterized=r.SampleInfo.characterized,
            created_at=r.SampleInfo.created_at,
            experiment_count=r.experiment_count,
            has_pxrf=r.pxrf_count > 0,
            has_xrd=r.xrd_count > 0,
            has_elemental=r.elemental_count > 0,
        )
        for r in rows
    ]
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
pytest tests/api/test_samples.py -v
```

Expected: All tests pass, including the 2 new ones.

- [ ] **Step 6: Commit**

```bash
git add backend/api/schemas/samples.py backend/api/routers/samples.py tests/api/test_samples.py
git commit -m "[#13] Add description to SampleListItem schema and router

- Tests added: yes
- Docs updated: no"
```

---

## Task 2: Add `description` to frontend `SampleListItem` type and table

**Files:**
- Modify: `frontend/src/api/samples.ts:19-31`
- Modify: `frontend/src/pages/Samples.tsx`

- [ ] **Step 1: Add `description` to `SampleListItem` TS interface**

In `frontend/src/api/samples.ts`, update `SampleListItem` (currently lines 19–31):

```typescript
export interface SampleListItem {
  sample_id: string
  rock_classification: string | null
  locality: string | null
  state: string | null
  country: string | null
  description: string | null
  characterized: boolean
  experiment_count: number
  has_pxrf: boolean
  has_xrd: boolean
  has_elemental: boolean
  created_at: string
}
```

- [ ] **Step 2: Add Description column header to the table**

In `frontend/src/pages/Samples.tsx`, update the `<TableHead>` block (currently lines 111–120):

```tsx
          <TableHead>
            <tr>
              <Th>Sample ID</Th>
              <Th>Classification</Th>
              <Th>Description</Th>
              <Th>Location</Th>
              <Th>Characterized</Th>
              <Th>Analyses</Th>
              <Th>Experiments</Th>
              <Th></Th>
            </tr>
          </TableHead>
```

- [ ] **Step 3: Add Description cell to each table row**

In `frontend/src/pages/Samples.tsx`, update each `<TableRow>` inside `data.items.map(...)` (currently lines 129–160). Add the Description `<Td>` after the Classification cell:

```tsx
                  <TableRow
                    key={s.sample_id}
                    onClick={() => navigate(`/samples/${s.sample_id}`)}
                    className="cursor-pointer"
                  >
                    <Td className="font-mono-data text-ink-primary">{s.sample_id}</Td>
                    <Td>{s.rock_classification ?? <span className="text-ink-muted">—</span>}</Td>
                    <Td className="max-w-xs">
                      {s.description
                        ? <span className="block truncate text-ink-secondary" title={s.description}>{s.description}</span>
                        : <span className="text-ink-muted">—</span>}
                    </Td>
                    <Td className="text-ink-muted">
                      {[s.locality, s.state, s.country].filter(Boolean).join(', ') || '—'}
                    </Td>
                    <Td>
                      <Badge variant={s.characterized ? 'success' : 'default'}>
                        {s.characterized ? 'Yes' : 'No'}
                      </Badge>
                    </Td>
                    <Td>
                      <div className="flex gap-1">
                        {s.has_pxrf && <Badge variant="default">pXRF</Badge>}
                        {s.has_xrd && <Badge variant="default">XRD</Badge>}
                        {s.has_elemental && <Badge variant="default">Elem</Badge>}
                      </div>
                    </Td>
                    <Td className="tabular-nums">{s.experiment_count}</Td>
                    <Td onClick={(e) => e.stopPropagation()}>
                      <button
                        className="text-xs text-red-400 hover:text-red-300"
                        onClick={() => setDeleteTarget(s.sample_id)}
                      >
                        Delete
                      </button>
                    </Td>
                  </TableRow>
```

Also update the `colSpan` on the "No samples found" empty row from `7` to `8`:

```tsx
                <Td colSpan={8} className="text-center py-8 text-ink-muted">No samples found</Td>
```

- [ ] **Step 4: Run ESLint to verify zero warnings**

```bash
cd frontend && npx eslint src/api/samples.ts src/pages/Samples.tsx --ext .ts,.tsx
```

Expected: no errors or warnings.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/samples.ts frontend/src/pages/Samples.tsx
git commit -m "[#13] Add Description column to sample list table

- Tests added: no
- Docs updated: no"
```

---

## Task 3: Add e2e test for description column

**Files:**
- Modify: `frontend/e2e/journeys/11-sample-management.spec.ts`

- [ ] **Step 1: Add a test that verifies the description column header is present**

Append this test to `frontend/e2e/journeys/11-sample-management.spec.ts`:

```typescript
test('sample list table has Description column header', async ({ page }) => {
  await page.goto('/samples')
  await expect(page.locator('thead')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByRole('columnheader', { name: /description/i })).toBeVisible()
})
```

- [ ] **Step 2: Run the new e2e test**

```bash
cd frontend && npx playwright test e2e/journeys/11-sample-management.spec.ts --grep "Description column" --reporter=line
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/journeys/11-sample-management.spec.ts
git commit -m "[#13] Add e2e test for description column header

- Tests added: yes
- Docs updated: no"
```

---

## Self-Review

**Spec coverage:**
- ✅ Description visible in table view → Task 2 (column header + cell)
- ✅ Description searchable → Already implemented in backend (`SampleInfo.description.ilike(pattern)` at router line 124–126); frontend search placeholder already reads "Search by ID or description…". The only gap was the field not appearing in the list response — fixed in Task 1.

**Placeholder scan:** No TBDs, TODOs, or "similar to Task N" references — all code shown explicitly.

**Type consistency:**
- `description: Optional[str] = None` in Pydantic `SampleListItem` ↔ `description: string | null` in TS `SampleListItem` ✅
- `r.SampleInfo.description` populated in router ↔ field added to schema ✅
- `s.description` accessed in `Samples.tsx` ↔ field in TS interface ✅
- `colSpan` updated from 7 → 8 to match new column count ✅
