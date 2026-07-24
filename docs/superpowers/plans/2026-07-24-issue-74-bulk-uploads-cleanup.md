# Bulk Uploads Page Cleanup (Issue #74) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the broken Master Results Sync button (replace with drag-and-drop-only upload), reorder the Bulk Uploads page so the six active widgets sit on top at increased prominence, and collapse the six low-use widgets into a "Less-used uploads" accordion.

**Architecture:** The drag-and-drop ingestion path already exists and is identical to sync — `MasterBulkUploadService.sync_from_path()` and `.from_bytes()` both delegate to the same `_process_bytes()` (verified in `backend/services/bulk_uploads/master_bulk_upload.py:258,268`), so removing sync loses no parsing capability. Work is: (1) backend — make `file` required on `POST /master-results` and delete the now-dead `/master-results/config` endpoints; (2) frontend — delete all sync UI/API code, rewrite the master widget copy, add a `prominent` variant to `UploadRow`, reorder the page, and wrap demoted rows in a collapsed section; (3) update e2e specs and docs.

**Tech Stack:** FastAPI + pytest (backend); React 18 + TypeScript + Tailwind + React Query + Vitest/Testing Library + Playwright (frontend).

## Global Constraints

- **Branch:** `feat/issue-74-bulk-uploads-cleanup` (already created from `develop`). PRs use `--base develop`.
- **Locked component — zero edits:** `backend/services/bulk_uploads/master_bulk_upload.py`. `sync_from_path()` stays in the file as API-unreachable code; its service-level test `tests/services/bulk_uploads/test_master_bulk_upload.py::test_sync_from_path_file_not_found_returns_error` stays too. Do not touch either.
- **Exact instructional copy** must include this path verbatim: `01_R&D\02_Results\Master_Reactor_Sampling_Tracker_v2.xlsx`
- **Active widget order (top of page, prominent), verbatim from the issue:** Master Results Sync, ICP-OES Data, XRD Mineralogy, New Experiments, Experiment Status Update, ActLabs Rock Analysis.
- **Demoted widgets (collapsed section, bottom, in current relative order):** Solution Chemistry, Timepoint Modifications, Rock Inventory, Chemical Inventory, Sample Chemical Composition, pXRF Readings.
- The collapsed section's toggle button is labeled exactly **`Less-used uploads`** — e2e specs and unit tests select on this text.
- Design tokens only (`text-ink-*`, `bg-surface-*`, etc.) — never hardcode hex values. Tailwind utility classes only, no inline styles. No `console.log`.
- **Never start, stop, or restart** the uvicorn server (port 8000) or the Vite dev server (port 5173/5174).
- No new dependencies. Do not touch `frontend/package.json` / `package-lock.json`.
- Commit format (issue task): subject `[#74] <imperative, ≤50 chars>` + body lines `- Tests added: yes/no`, `- Docs updated: yes/no`.
- Docs written under `docs/` are auto-copied to `docs/project_context/` by a PostToolUse hook — **never write to `docs/project_context/` directly**.
- Frontend test commands run from `frontend/`: `npx vitest run src`, `npx eslint src --ext .ts,.tsx`, `npx tsc --noEmit`. Backend: `pytest tests/api/test_bulk_uploads.py -v` from repo root using `.venv`.

**Scope interpretations (user-confirmed 2026-07-24):**
1. `GET/PATCH /api/bulk-uploads/master-results/config` are removed — they exist solely to configure the sync source path and are dead once sync is gone. *(confirmed)*
2. The locked parser file keeps `sync_from_path()` as dead code rather than being edited. *(confirmed)*
3. Solution Chemistry is demoted per the issue's explicit active-list (it is not in the top-six list).

---

### Task 1: Backend — remove sync mode and config endpoints

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py:263-295` (master-results endpoint) and `:630-682` (config block)
- Test: `tests/api/test_bulk_uploads.py:178-188` (sync-mode test), `:695-744` (config tests)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `POST /api/bulk-uploads/master-results` now requires `file` (422 without it); the `GET/PATCH /api/bulk-uploads/master-results/config` routes are no longer registered (verified via the route registry — HTTP-level 404 assertions are off-limits because the SPA catch-all in `backend/api/main.py` answers unknown paths and must not be modified; plan amendment 2026-07-24). Task 2's frontend change (removing `triggerMasterSync`) depends on this contract.

- [ ] **Step 1: Replace the sync-mode test and delete the config tests (write failing tests)**

In `tests/api/test_bulk_uploads.py`, replace `test_master_results_sync_no_file_returns_response_shape` (lines 178-188) with:

```python
def test_master_results_no_file_returns_422(client):
    """POST to master-results without a file is rejected — sync mode removed (issue #74)."""
    resp = client.post("/api/bulk-uploads/master-results")
    assert resp.status_code == 422


def test_master_results_config_endpoints_removed():
    """The /master-results/config routes were removed with the sync feature (issue #74).

    Asserted against the route registry, not via HTTP status codes: the SPA
    catch-all in backend/api/main.py answers unknown paths, so HTTP-level
    404 assertions would require changing app-wide routing semantics
    (plan amendment 2026-07-24, user-confirmed).
    """
    from backend.api.main import app

    config_paths = [
        r.path for r in app.routes if "master-results/config" in getattr(r, "path", "")
    ]
    assert config_paths == []
```

Delete the whole "D2: Master Results config endpoints" section (the section comment at lines 695-697 and the four tests `test_get_master_results_config_returns_path`, `test_patch_master_results_config_invalid_path`, `test_patch_master_results_config_valid_path`, `test_patch_master_results_config_persists_to_get`, lines 699-744). Do NOT delete the AppConfig model tests above that section.

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/api/test_bulk_uploads.py -k "master_results_no_file or config_endpoints_removed" -v`
Expected: both FAIL — `test_master_results_no_file_returns_422` gets 200 (sync branch still active), `test_master_results_config_endpoints_removed` finds the config routes still registered (non-empty `config_paths`).

- [ ] **Step 3: Rewrite the master-results endpoint and delete the config block**

In `backend/api/routers/bulk_uploads.py`, replace the whole `upload_master_results` function (lines 263-295) with:

```python
@router.post("/master-results", response_model=UploadResponse)
async def upload_master_results(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """
    Master Results upload — parse the uploaded master tracker file.

    The former no-file SharePoint sync mode was removed (issue #74);
    a file is now required.
    """
    from backend.services.bulk_uploads.master_bulk_upload import MasterBulkUploadService  # noqa: PLC0415
    try:
        file_bytes = await file.read()
        created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(db, file_bytes)
        db.commit()
    except Exception as exc:
        db.rollback()
        log.error("master_results_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    log.info("master_results", created=created, updated=updated, user=current_user.email)
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        feedbacks=feedbacks,
        message=f"Master Results: {created} created, {updated} updated, {skipped} skipped",
    )
```

Note the `Optional` wrapper and `File(None)` are gone, along with the `mode` variable and the `sync_from_path` call.

Then delete the entire Master Results config block (lines 630-682): the `from pydantic import BaseModel as _PydanticBase` import, `MasterResultsConfigResponse`, `MasterResultsConfigUpdate`, `_MASTER_RESULTS_CONFIG_KEY`, `get_master_results_config`, and `update_master_results_config`. Before deleting, grep the file for other uses of `_PydanticBase` — if (unexpectedly) used elsewhere, keep the import; otherwise remove it. Keep the section divider comment structure tidy (remove the now-empty section header comment too).

If `Optional` is now unused in the file's imports, remove it from the `typing` import; run `flake8 backend/api/routers/bulk_uploads.py --select=F401` to check.

- [ ] **Step 4: Run the full API bulk-uploads test file**

Run: `pytest tests/api/test_bulk_uploads.py -v`
Expected: all PASS, including the two new tests and the existing `test_master_results_upload_returns_response_shape` (upload-with-file path unchanged).

Also run the master parser service tests to prove the locked file is untouched:
Run: `pytest tests/services/bulk_uploads/test_master_bulk_upload.py -v`
Expected: all PASS.
Run: `git status --porcelain backend/services/bulk_uploads/`
Expected: no output (locked directory untouched).

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/bulk_uploads.py tests/api/test_bulk_uploads.py
git commit -m "[#74] Remove master results sync mode from API

- POST /master-results now requires a file; sync branch deleted
- GET/PATCH /master-results/config endpoints removed (sync-only config)
- Locked parser backend/services/bulk_uploads/master_bulk_upload.py untouched
- Tests added: yes
- Docs updated: no"
```

---

### Task 2: Frontend — remove sync feature and rewrite master widget copy

**Files:**
- Modify: `frontend/src/api/bulkUploads.ts:64-70`
- Modify: `frontend/src/pages/BulkUploadRow.tsx` (remove `IconRefresh`, `syncFn`, `syncMutation`, sync button block)
- Modify: `frontend/src/pages/BulkUploads.tsx:192-203` (master widget props)
- Create: `frontend/src/pages/__tests__/BulkUploads.test.tsx`

**Interfaces:**
- Consumes: Task 1's contract (`POST /master-results` file-required) — no code dependency, behavior only.
- Produces: `UploadRowProps` **without** `syncFn`; `bulkUploadsApi` **without** `triggerMasterSync`. Task 3 modifies the same three frontend files and extends the same test file — it assumes these removals are done.

- [ ] **Step 1: Write the failing unit test**

Create `frontend/src/pages/__tests__/BulkUploads.test.tsx`:

```tsx
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/bulkUploads', () => ({
  bulkUploadsApi: {
    getNextIds: vi.fn().mockResolvedValue({ HPHT: 1, Serum: 1, CF: 1, Autoclave: 1 }),
    uploadMasterResults: vi.fn(),
    uploadIcpOes: vi.fn(),
    uploadXrdMineralogy: vi.fn(),
    uploadScalarResults: vi.fn(),
    uploadNewExperiments: vi.fn(),
    uploadTimepointModifications: vi.fn(),
    uploadRockInventory: vi.fn(),
    uploadChemicalInventory: vi.fn(),
    uploadElementalComposition: vi.fn(),
    uploadActlabsRock: vi.fn(),
    uploadExperimentStatus: vi.fn(),
    uploadPXRF: vi.fn(),
    downloadTemplate: vi.fn(),
  },
  isConflictCheckResult: (r: unknown) => (r as { status?: string })?.status === 'warnings',
}))

import { BulkUploadsPage } from '../BulkUploads'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 0 },
    mutations: { retry: false },
  },
})

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  queryClient.clear()
})

describe('BulkUploadsPage — master results widget (issue #74)', () => {
  it('shows drag-and-drop instructions with the master tracker path and no sync button', async () => {
    render(<BulkUploadsPage />, { wrapper })

    await userEvent.click(screen.getByRole('button', { name: /Master Results Sync/i }))

    expect(
      screen.getByText(/01_R&D\\02_Results\\Master_Reactor_Sampling_Tracker_v2\.xlsx/)
    ).toBeInTheDocument()
    expect(screen.queryByText('Sync from SharePoint')).toBeNull()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `npx vitest run src/pages/__tests__/BulkUploads.test.tsx`
Expected: FAIL — the tracker path text is not found (and "Sync from SharePoint" is present).

- [ ] **Step 3: Remove `triggerMasterSync` from the API client**

In `frontend/src/api/bulkUploads.ts`, replace lines 64-70:

```ts
export const bulkUploadsApi = {
  // Card 1 — Master Results (drag-and-drop upload of the master tracker file)
  uploadMasterResults: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/master-results', fileForm(file)),
```

(i.e. delete the `triggerMasterSync` entry and its comment line; keep everything else in the object unchanged.)

- [ ] **Step 4: Remove all sync code from `UploadRow`**

In `frontend/src/pages/BulkUploadRow.tsx`:

1. Delete the `IconRefresh` function (lines 31-42).
2. In `UploadRowProps`, delete the `syncFn` doc comment and field (lines 56-57).
3. Remove `syncFn,` from the destructured props in the `UploadRow` function signature.
4. Delete the entire `syncMutation` declaration (lines 112-121).
5. Change the `isPending` line to:

```ts
  const isPending = uploadMutation.isPending
```

6. Delete the sync button block — the `{/* Sync button row (Master Results only) */}` comment and the whole `{syncFn && ( ... )}` JSX block (lines 169-183).

- [ ] **Step 5: Update the master widget in `BulkUploads.tsx`**

Replace the Master Results `UploadRow` (lines 192-203) with:

```tsx
        {/* 1 — Master Results Sync (drag-and-drop; the broken SharePoint sync was removed, issue #74) */}
        <UploadRow
          id="master-results"
          title="Master Results Sync"
          description="Drag and drop the master tracker spreadsheet to push updates"
          helpText={
            'Drag and drop the master results file into the zone below to push updates: ' +
            '01_R&D\\02_Results\\Master_Reactor_Sampling_Tracker_v2.xlsx — ' +
            "reads the 'Dashboard' sheet. Required columns: Experiment ID, Duration (Days). " +
            'Replicates: either write the full lettered ID (SERUM_001a) in Experiment ID, or put the base ID there and the letter (a, b, c) in the optional Replicate column — 0 or blank means the group parent.'
          }
          accept=".xlsx,.xls"
          uploadFn={(file) => bulkUploadsApi.uploadMasterResults(file)}
          isOpen={isOpen('master-results')}
          onToggle={() => toggle('master-results')}
        />
```

(The `helpText` is a JS string expression, so `\\` renders as a single backslash.)

- [ ] **Step 6: Run tests, lint, and type check**

Run (from `frontend/`):
- `npx vitest run src` — Expected: all PASS including the new test.
- `npx eslint src/api/bulkUploads.ts src/pages/BulkUploadRow.tsx src/pages/BulkUploads.tsx src/pages/__tests__/BulkUploads.test.tsx --ext .ts,.tsx` — Expected: zero errors/warnings.
- `npx tsc --noEmit` — Expected: clean (this is what catches any lingering `syncFn`/`triggerMasterSync` reference).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/bulkUploads.ts frontend/src/pages/BulkUploadRow.tsx frontend/src/pages/BulkUploads.tsx frontend/src/pages/__tests__/BulkUploads.test.tsx
git commit -m "[#74] Replace master sync button with drag-and-drop

- triggerMasterSync, syncFn prop, sync mutation and button removed
- Master widget copy now instructs drag-and-drop of the tracker file
- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Frontend — prominence variant, widget reorder, less-used accordion

**Files:**
- Modify: `frontend/src/pages/BulkUploadRow.tsx` (export `IconChevron`, add `prominent` prop)
- Modify: `frontend/src/pages/ActlabsUploadRow.tsx` (pass-through `prominent` prop)
- Modify: `frontend/src/pages/BulkUploads.tsx` (reorder + accordion)
- Test: `frontend/src/pages/__tests__/BulkUploads.test.tsx` (extend)

**Interfaces:**
- Consumes: Task 2's state of the same files (`syncFn` already gone; test file and wrapper already exist).
- Produces: `UploadRowProps.prominent?: boolean`; `ActlabsUploadRowProps.prominent?: boolean`; exported `IconChevron({ open: boolean })` from `BulkUploadRow.tsx`; a page-level toggle button labeled `Less-used uploads` that conditionally renders the six demoted rows. Task 4's e2e specs rely on that exact label.

- [ ] **Step 1: Write the failing layout tests**

Append to `frontend/src/pages/__tests__/BulkUploads.test.tsx` (inside the file, after the existing describe block):

```tsx
describe('BulkUploadsPage — layout (issue #74)', () => {
  const ACTIVE_TITLES = [
    'Master Results Sync',
    'ICP-OES Data',
    'XRD Mineralogy',
    'New Experiments',
    'Experiment Status Update',
    'ActLabs Rock Analysis',
  ]

  it('renders the six active widgets in order before the less-used section', () => {
    render(<BulkUploadsPage />, { wrapper })

    const labels = screen.getAllByRole('button').map((b) => b.textContent ?? '')
    const positions = [...ACTIVE_TITLES, 'Less-used uploads'].map((t) =>
      labels.findIndex((l) => l.includes(t))
    )
    expect(positions.every((p) => p >= 0)).toBe(true)
    expect(positions).toEqual([...positions].sort((a, b) => a - b))
  })

  it('hides demoted widgets until the less-used section is expanded', async () => {
    render(<BulkUploadsPage />, { wrapper })

    expect(screen.queryByText('Solution Chemistry')).toBeNull()
    expect(screen.queryByText('Timepoint Modifications')).toBeNull()
    expect(screen.queryByText('Rock Inventory')).toBeNull()
    expect(screen.queryByText('Chemical Inventory')).toBeNull()
    expect(screen.queryByText('Sample Chemical Composition')).toBeNull()
    expect(screen.queryByText('pXRF Readings')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: /Less-used uploads/i }))

    expect(screen.getByText('Solution Chemistry')).toBeInTheDocument()
    expect(screen.getByText('pXRF Readings')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx vitest run src/pages/__tests__/BulkUploads.test.tsx`
Expected: both new tests FAIL (no `Less-used uploads` button exists; demoted titles render immediately). The Task 2 test still PASSES.

- [ ] **Step 3: Add the `prominent` variant to `UploadRow` and export `IconChevron`**

In `frontend/src/pages/BulkUploadRow.tsx`:

1. Change `function IconChevron(` to `export function IconChevron(`.
2. Add to `UploadRowProps` (after `topContent`):

```ts
  /** Larger header treatment for the six active widgets at the top of the page */
  prominent?: boolean
```

3. Add `prominent = false,` to the destructured props.
4. Replace the header `<button>` className with:

```tsx
        className={`w-full flex items-center justify-between ${prominent ? 'px-5 py-4' : 'px-4 py-3'} bg-surface-primary hover:bg-surface-secondary transition-colors text-left`}
```

5. Replace the title span className with:

```tsx
          <span className={`${prominent ? 'text-base font-semibold' : 'text-sm font-medium'} text-ink-primary shrink-0`}>{title}</span>
```

6. Replace the description span className with:

```tsx
          <span className={`${prominent ? 'text-sm' : 'text-xs'} text-ink-muted truncate hidden sm:block`}>{description}</span>
```

- [ ] **Step 4: Pass `prominent` through `ActlabsUploadRow`**

In `frontend/src/pages/ActlabsUploadRow.tsx`:

```tsx
interface ActlabsUploadRowProps {
  isOpen: boolean
  onToggle: () => void
  /** Larger header treatment — passed through to UploadRow */
  prominent?: boolean
}

export function ActlabsUploadRow({ isOpen, onToggle, prominent = false }: ActlabsUploadRowProps) {
```

and add `prominent={prominent}` to the inner `<UploadRow>` props (after `accept`).

- [ ] **Step 5: Reorder the page and add the accordion**

In `frontend/src/pages/BulkUploads.tsx`:

1. Import `IconChevron`: change the UploadRow import line to

```tsx
import { UploadRow, IconChevron } from './BulkUploadRow'
```

2. Add state next to the other `useState` calls in `BulkUploadsPage`:

```tsx
  const [showInactive, setShowInactive] = useState(false)
```

3. Replace the entire `<div className="space-y-2">…</div>` widget list with the block below. Every `UploadRow`/`ActlabsUploadRow` keeps its exact existing props (only `prominent` is added to the top six; the master row keeps the Task 2 copy); the six demoted rows move inside the conditional block unchanged.

```tsx
      <div className="space-y-2">

        {/* ── Active uploads — most-used, full prominence ─────────────────── */}

        {/* 1 — Master Results Sync (drag-and-drop; the broken SharePoint sync was removed, issue #74) */}
        <UploadRow
          id="master-results"
          title="Master Results Sync"
          description="Drag and drop the master tracker spreadsheet to push updates"
          helpText={
            'Drag and drop the master results file into the zone below to push updates: ' +
            '01_R&D\\02_Results\\Master_Reactor_Sampling_Tracker_v2.xlsx — ' +
            "reads the 'Dashboard' sheet. Required columns: Experiment ID, Duration (Days). " +
            'Replicates: either write the full lettered ID (SERUM_001a) in Experiment ID, or put the base ID there and the letter (a, b, c) in the optional Replicate column — 0 or blank means the group parent.'
          }
          accept=".xlsx,.xls"
          uploadFn={(file) => bulkUploadsApi.uploadMasterResults(file)}
          prominent
          isOpen={isOpen('master-results')}
          onToggle={() => toggle('master-results')}
        />

        {/* 2 — ICP-OES Data */}
        <UploadRow
          id="icp-oes"
          title="ICP-OES Data"
          description="Upload ICP-OES elemental analysis CSV"
          helpText="Instrument CSV export from the ICP-OES. Multi-element, multi-timepoint files supported. Blank rows are filtered. Duplicate spectral lines resolved by best intensity."
          accept=".csv"
          uploadFn={(file) => bulkUploadsApi.uploadIcpOes(file, icpOverwrite)}
          topContent={<IcpOverwriteToggle checked={icpOverwrite} onChange={setIcpOverwrite} />}
          prominent
          isOpen={isOpen('icp-oes')}
          onToggle={() => toggle('icp-oes')}
        />

        {/* 3 — XRD Mineralogy */}
        <UploadRow
          id="xrd-mineralogy"
          title="XRD Mineralogy"
          description="Upload XRD mineral phase data — auto-detects format from column names"
          helpText={
            xrdMode === 'experiment'
              ? "Experiment+Timepoint format: include 'Experiment ID' and 'Time (days)' columns plus one column per mineral phase. The format is auto-detected on upload."
              : "Sample-based format: include a 'sample_id' column plus one column per mineral phase. Aeris instrument exports (sample IDs like '20260218_HPHT070-d19_02') are also accepted."
          }
          accept=".xlsx,.xls,.csv"
          uploadFn={(file) => bulkUploadsApi.uploadXrdMineralogy(file, xrdOverwrite)}
          templateType="xrd-mineralogy"
          templateMode={xrdMode}
          topContent={
            <>
              <XrdModeToggle mode={xrdMode} onChange={setXrdMode} />
              <XrdOverwriteToggle checked={xrdOverwrite} onChange={setXrdOverwrite} />
            </>
          }
          skippedMessage={
            !xrdOverwrite
              ? "Some rows were skipped because data already exists for these timepoints. Enable 'Replace existing results' to overwrite."
              : undefined
          }
          prominent
          isOpen={isOpen('xrd-mineralogy')}
          onToggle={() => toggle('xrd-mineralogy')}
        />

        {/* 4 — New Experiments */}
        <UploadRow
          id="new-experiments"
          title="New Experiments"
          description="Bulk-create experiments from a structured Excel template"
          helpText="Use the template for correct column formatting. The file must have an 'experiments' sheet; a 'conditions' sheet is optional. Replicates: write a lowercase letter after the number (SERUM_001a, _001b, _001c) — the bare SERUM_001 (or SERUM_001-0) is replicate 0, the group parent."
          accept=".xlsx,.xls"
          uploadFn={(file) => bulkUploadsApi.uploadNewExperiments(file)}
          templateType="new-experiments"
          topContent={<NextIdChips data={nextIds} />}
          prominent
          isOpen={isOpen('new-experiments')}
          onToggle={() => toggle('new-experiments')}
        />

        {/* 5 — Experiment Status Update */}
        <UploadRow
          id="experiment-status"
          title="Experiment Status Update"
          description="Bulk-set experiment status (ONGOING / COMPLETED / QUEUED / CANCELLED)"
          helpText="Required columns: experiment_id, status. Optional: reactor_number, date (start date). Setting an HPHT or Core Flood experiment to ONGOING with a reactor_number auto-completes an older experiment in the same reactor; a newer-or-equal-dated occupant triggers a warning instead of a completion."
          accept=".xlsx,.xls,.csv"
          uploadFn={(file) => bulkUploadsApi.uploadExperimentStatus(file)}
          templateType="experiment-status"
          prominent
          isOpen={isOpen('experiment-status')}
          onToggle={() => toggle('experiment-status')}
        />

        {/* 6 — ActLabs Rock Analysis */}
        <ActlabsUploadRow
          prominent
          isOpen={isOpen('actlabs-rock')}
          onToggle={() => toggle('actlabs-rock')}
        />

        {/* ── Less-used uploads — collapsed by default ────────────────────── */}
        <div className="pt-4">
          <button
            className="w-full flex items-center justify-between px-4 py-2.5 rounded-lg border border-surface-border bg-surface-primary hover:bg-surface-secondary transition-colors text-left"
            onClick={() => setShowInactive((v) => !v)}
            aria-expanded={showInactive}
          >
            <span className="text-xs font-medium text-ink-secondary">Less-used uploads</span>
            <IconChevron open={showInactive} />
          </button>

          {showInactive && (
            <div className="mt-2 space-y-2">

              {/* 7 — Solution Chemistry */}
              <UploadRow
                id="scalar-results"
                title="Solution Chemistry"
                description="Upload solution chemistry measurements (pH, NH₄, H₂, conductivity)"
                helpText="Required columns: Experiment ID, Time (days). All other fields are optional. Set Overwrite=TRUE to replace existing values. Replicates: either write the full lettered ID (SERUM_001a) in Experiment ID, or put the base ID there and the letter (a, b, c) in the optional Replicate column — 0 or blank means the group parent."
                accept=".xlsx,.xls,.csv"
                uploadFn={(file) => bulkUploadsApi.uploadScalarResults(file)}
                templateType="scalar-results"
                isOpen={isOpen('scalar-results')}
                onToggle={() => toggle('scalar-results')}
              />

              {/* 8 — Timepoint Modifications */}
              <UploadRow
                id="timepoint-modifications"
                title="Timepoint Modifications"
                description="Bulk-set modification descriptions on existing result rows"
                helpText="Required columns: experiment_id, time_point, modification_description. Set overwrite_existing=TRUE to replace existing descriptions. Time is matched with ±0.0001 day tolerance."
                accept=".xlsx,.xls,.csv"
                uploadFn={(file) => bulkUploadsApi.uploadTimepointModifications(file)}
                templateType="timepoint-modifications"
                isOpen={isOpen('timepoint-modifications')}
                onToggle={() => toggle('timepoint-modifications')}
              />

              {/* 9 — Rock Inventory */}
              <UploadRow
                id="rock-inventory"
                title="Rock Inventory"
                description="Upload or update rock sample metadata"
                helpText="Required column: sample_id. Optional: rock_classification, state, country, locality, latitude, longitude, description, characterized."
                accept=".xlsx,.xls,.csv"
                uploadFn={(file) => bulkUploadsApi.uploadRockInventory(file)}
                templateType="rock-inventory"
                isOpen={isOpen('rock-inventory')}
                onToggle={() => toggle('rock-inventory')}
              />

              {/* 10 — Chemical Inventory */}
              <UploadRow
                id="chemical-inventory"
                title="Chemical Inventory"
                description="Upload or update chemical reagent records"
                helpText="Required column: name. Optional: formula, cas_number, molecular_weight, density, hazard_class, supplier, catalog_number, notes."
                accept=".xlsx,.xls,.csv"
                uploadFn={(file) => bulkUploadsApi.uploadChemicalInventory(file)}
                templateType="chemical-inventory"
                isOpen={isOpen('chemical-inventory')}
                onToggle={() => toggle('chemical-inventory')}
              />

              {/* 11 — Sample Chemical Composition */}
              <UploadRow
                id="elemental-composition"
                title="Sample Chemical Composition"
                description="Wide-format Excel with sample_id + analyte columns"
                helpText="First column must be sample_id. Remaining columns are analyte symbols (e.g. SiO2, Al2O3). Cells contain numeric values. Unknown analytes are auto-created with the selected default unit."
                accept=".xlsx,.xls"
                uploadFn={(file) => bulkUploadsApi.uploadElementalComposition(file, elemDefaultUnit)}
                templateType="elemental-composition"
                topContent={
                  <DefaultUnitField value={elemDefaultUnit} onChange={setElemDefaultUnit} />
                }
                isOpen={isOpen('elemental-composition')}
                onToggle={() => toggle('elemental-composition')}
              />

              {/* 12 — pXRF Readings */}
              <UploadRow
                id="pxrf"
                title="pXRF Readings"
                description="Upload portable XRF scan data"
                helpText="Instrument CSV or Excel export from the portable XRF. Each row is one scan. Instrument format — no template needed."
                accept=".csv,.xlsx,.xls"
                uploadFn={(file) => bulkUploadsApi.uploadPXRF(file)}
                isOpen={isOpen('pxrf')}
                onToggle={() => toggle('pxrf')}
              />

            </div>
          )}
        </div>

      </div>
```

- [ ] **Step 6: Run tests, lint, type check, and production build**

Run (from `frontend/`):
- `npx vitest run src` — Expected: all PASS (including both new layout tests and the Task 2 test).
- `npx eslint src/pages/BulkUploads.tsx src/pages/BulkUploadRow.tsx src/pages/ActlabsUploadRow.tsx src/pages/__tests__/BulkUploads.test.tsx --ext .ts,.tsx` — Expected: zero errors/warnings.
- `npx tsc --noEmit` — Expected: clean.
- `npm run build` — Expected: clean production build.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/BulkUploads.tsx frontend/src/pages/BulkUploadRow.tsx frontend/src/pages/ActlabsUploadRow.tsx frontend/src/pages/__tests__/BulkUploads.test.tsx
git commit -m "[#74] Reorder bulk upload widgets by usage

- Six active widgets on top with prominent header treatment
- Six low-use widgets collapsed under Less-used uploads accordion
- Tests added: yes
- Docs updated: no"
```

---

### Task 4: E2E spec updates

**Files:**
- Delete: `frontend/e2e/journeys/07-master-results-sync.spec.ts`
- Create: `frontend/e2e/journeys/07-bulk-uploads-layout.spec.ts`
- Modify: `frontend/e2e/journeys/08-solution-chemistry.spec.ts:15`
- Modify: `frontend/e2e/journeys/09-elemental-composition.spec.ts:16`
- Modify: `frontend/e2e/journeys/11-sample-management.spec.ts:195`
- Modify: `frontend/e2e/journeys/13-master-bulk-upload.spec.ts:95`

**Interfaces:**
- Consumes: the `Less-used uploads` toggle label and page layout from Task 3.
- Produces: nothing downstream.

- [ ] **Step 1: Replace the sync spec with a layout spec**

Delete `frontend/e2e/journeys/07-master-results-sync.spec.ts` (`git rm frontend/e2e/journeys/07-master-results-sync.spec.ts`) and create `frontend/e2e/journeys/07-bulk-uploads-layout.spec.ts`:

```ts
import { test, expect } from '../fixtures/auth'

test('master results widget shows drag-and-drop instructions, no sync button', async ({ page }) => {
  await page.goto('/bulk-uploads')
  await page.getByRole('button', { name: /Master Results Sync/i }).click()

  await expect(page.getByText(/Master_Reactor_Sampling_Tracker_v2\.xlsx/)).toBeVisible({ timeout: 5_000 })
  await expect(page.getByRole('button', { name: 'Sync from SharePoint', exact: true })).toHaveCount(0)
})

test('active widgets on top; demoted widgets collapsed into less-used section', async ({ page }) => {
  await page.goto('/bulk-uploads')

  for (const title of [
    'Master Results Sync',
    'ICP-OES Data',
    'XRD Mineralogy',
    'New Experiments',
    'Experiment Status Update',
    'ActLabs Rock Analysis',
  ]) {
    await expect(page.getByRole('button', { name: new RegExp(title, 'i') })).toBeVisible()
  }

  // Demoted rows hidden until the accordion is expanded
  await expect(page.getByRole('button', { name: /Solution Chemistry/i })).toHaveCount(0)
  await page.getByRole('button', { name: /Less-used uploads/i }).click()
  await expect(page.getByRole('button', { name: /Solution Chemistry/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /pXRF Readings/i })).toBeVisible()
})
```

- [ ] **Step 2: Expand the accordion in specs that use demoted widgets**

In each file below, insert one line immediately after `await page.goto('/bulk-uploads')` (and any wait that follows it), **before** the row-header click:

```ts
  await page.getByRole('button', { name: /Less-used uploads/i }).click()
```

- `08-solution-chemistry.spec.ts` — before the `Solution Chemistry` click at line 15.
- `09-elemental-composition.spec.ts` — before the `Sample Chemical Composition` click at line 16.
- `11-sample-management.spec.ts` — before the `rock inventory` click at line 195.
- `13-master-bulk-upload.spec.ts` — before the `Solution Chemistry` click at line 95 (the master-results and ActLabs tests in this file target active widgets — leave them unchanged).

- [ ] **Step 3: Verify Playwright still collects all specs**

Run (from `frontend/`): `npx playwright test --list`
Expected: all journey specs listed, including `07-bulk-uploads-layout.spec.ts`; no parse errors. (Do not run the suite — it requires the live app and login; runtime verification happens at review time on the running lab setup.)

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/journeys/
git commit -m "[#74] Update e2e specs for reorganized uploads page

- 07 sync spec replaced with layout + drag-drop copy spec
- Demoted-widget specs expand Less-used uploads first
- Tests added: yes
- Docs updated: no"
```

---

### Task 5: Documentation update

**Files:**
- Modify: `docs/user_guide/BULK_UPLOADS.md:1-33`
- Modify: `docs/api/API_REFERENCE.md:379`
- Modify: `docs/developer/ADDING_UPLOAD_TYPE.md:178`
- Modify: `docs/deployment/PRODUCTION_DEPLOYMENT.md:140-150`
- Modify: `docs/specs/master_results_sync.md` (Overview, UI Behaviour, API Endpoint sections)

**Interfaces:**
- Consumes: final behavior from Tasks 1-3.
- Produces: nothing downstream. The PostToolUse hook auto-syncs each file to `docs/project_context/` — do not write there directly.

- [ ] **Step 1: Update the user guide**

In `docs/user_guide/BULK_UPLOADS.md`:

1. Append to the intro paragraph (after "...Only one row can be open at a time."):

```markdown
The six most-used upload types appear at the top of the page at full size; the
remaining low-use types are collapsed under a **Less-used uploads** section at
the bottom — click it to expand them.
```

2. Replace the §1 lead-in and "Two modes" block (lines 25-32, from "Reads the team's shared Excel tracker..." through "...SharePoint path is unavailable.") with:

```markdown
Drag and drop the team's master tracker spreadsheet to push updates:

`01_R&D\02_Results\Master_Reactor_Sampling_Tracker_v2.xlsx`

Download the file from SharePoint (or use a synced local copy) and drop it into
the upload zone. The former "Sync from SharePoint" button was removed (issue #74)
— the file is now always uploaded manually, and the `file` field is required on
the endpoint.
```

Keep the "Expected sheet: Dashboard" table and the Replicates paragraph unchanged.

- [ ] **Step 2: Update the API reference**

In `docs/api/API_REFERENCE.md` line 379, change the description's first two sentences from:

`Master Results sync. `file` optional — if omitted, reads from configured SharePoint path. Runs calc engine on affected ScalarResults.`

to:

`Master Results upload. `file` required — the no-file SharePoint sync mode and the GET/PATCH /master-results/config endpoints were removed (issue #74). Runs calc engine on affected ScalarResults.`

Keep the rest of the row (replicate-handling text) unchanged.

- [ ] **Step 3: Update the developer guide**

In `docs/developer/ADDING_UPLOAD_TYPE.md`, replace the `syncFn` row of the props table (line 178) with:

```markdown
| `prominent` | `boolean` | | Larger header/title treatment — used by the six active widgets at the top of the page |
```

- [ ] **Step 4: Update the deployment guide**

In `docs/deployment/PRODUCTION_DEPLOYMENT.md`, delete the whole "Configuring the Master Results Path" section (lines 142-149 plus its preceding `---` divider at line 140) — the config endpoints no longer exist. Replace it with nothing (Troubleshooting follows directly).

- [ ] **Step 5: Update the master results spec**

In `docs/specs/master_results_sync.md`:

1. Replace the second Overview paragraph (lines 16-18, "Because the file lives on the same LAN machine...") with:

```markdown
As of issue #74 the upload is **drag-and-drop only**: the user downloads or syncs
the tracker locally (`01_R&D\02_Results\Master_Reactor_Sampling_Tracker_v2.xlsx`)
and drops it onto the Master Results widget. The former server-side
read-from-configured-path sync mode was removed.
```

2. Replace the whole "UI Behaviour" section body (lines 92-129, keeping the `## UI Behaviour` heading but simplifying its parenthetical) with:

```markdown
## UI Behaviour

The Master Results card is a standard drag-and-drop upload row (the largest,
topmost widget on the page). Its help text instructs users to drop
`01_R&D\02_Results\Master_Reactor_Sampling_Tracker_v2.xlsx`.

After upload the card shows Created / Updated / Skipped counts, a collapsible
warning list (experiment IDs not found in DB), and prominent red errors for
unexpected exceptions.
```

3. Replace the "API Endpoint" section body (lines 135-149) with the following (the `POST` line stays inside its own triple-backtick code fence, as it is today):

````markdown
```
POST /api/bulk-uploads/master-results
```

- `file` (multipart) is **required** — the endpoint parses the uploaded workbook
- Returns `UploadResult`
- Requires Firebase auth

The former `GET`/`PATCH /api/bulk-uploads/master-results/config` endpoints were
removed with the sync mode (issue #74).
````

4. In "Backend Implementation Notes", delete the first two bullets (the `AppConfig` path-storage bullet and the read-lock bullet) and the `PermissionError` bullet; keep the final bullet ("Parsing is delegated entirely to the existing `master_bulk_upload.py` parser; do not modify its logic").

- [ ] **Step 6: Verify hook sync and commit**

Run: `git status --porcelain docs/`
Expected: the five edited files **plus** their auto-synced copies under `docs/project_context/` (the hook fires on each Write/Edit; `docs/specs/` → `docs/project_context/master_results_sync.md`, etc.).

```bash
git add docs/
git commit -m "[#74] Update docs for drag-and-drop master upload

- User guide, API reference, spec, developer + deployment guides
- project_context copies synced by hook
- Tests added: no
- Docs updated: yes"
```

---

## Verification (whole branch, before PR)

- Backend: `pytest tests/api/test_bulk_uploads.py tests/services/bulk_uploads/test_master_bulk_upload.py -v` — all pass.
- Full backend suite: `pytest` — expect the 3 known pre-existing `tests/test_pg_backup_restore.py` failures (local pg_dump toolchain gap, predates this branch) and nothing else failing.
- Frontend: `npx vitest run src`, `npx eslint src --ext .ts,.tsx` (only the 5 known pre-existing errors in untouched files), `npx tsc --noEmit`, `npm run build` — all clean.
- `git status --porcelain backend/services/bulk_uploads/ database/models/` — empty (locked components untouched).
- Acceptance criteria from issue #74:
  1. Sync button removed; drag-and-drop instructions reference `01_R&D\02_Results\Master_Reactor_Sampling_Tracker_v2.xlsx` ✓ (Task 2 + unit test + e2e)
  2. Drag-and-drop upload updates records — same parser as sync (`_process_bytes`), covered by existing `13-master-bulk-upload.spec.ts` e2e journey and `test_master_results_upload_returns_response_shape` ✓
  3. Six active widgets first, at increased size ✓ (Task 3 + tests)
  4. Other widgets demoted to lower-prominence collapsed section ✓ (Task 3 + tests)
  5. No regression in existing upload functionality — demoted rows keep identical props/endpoints; full suites run ✓
