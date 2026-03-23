# M8 Design: Testing and Documentation Pass

**Date:** 2026-03-23
**Milestone:** M8 — Testing and Docs
**Branch:** `feature/m8-testing-docs`
**Status:** Approved

---

## 1. Overview

M8 covers three workstreams:

1. **Playwright E2E infrastructure** — browser automation against the live dev stack
2. **Upload testing and parser fixes** — test each upload type with real lab files; fix parsing bugs found
3. **New feature implementation** — specs in `docs/specs/` that are designed but not yet fully built (Master Results Sync server-side UI + mutable config store, `next-ids` endpoint fix, new `elemental_composition.py` parser)

After all uploads are verified, the final chunk completes the 6 original E2E journeys, the calculation regression test, and the documentation pass.

---

## 2. Playwright Setup

### Installation (already complete)
- `@playwright/test` added to `frontend/package.json` devDependencies (`--legacy-peer-deps`)
- Chromium binary downloaded to `%APPDATA%\Local\ms-playwright\chromium-1208`

### Configuration
**Location:** `frontend/playwright.config.ts`

Key settings:
- `baseURL: 'http://localhost:5173'` — connects to the already-running Vite dev server
- `testDir: './e2e/journeys'`
- `globalSetup: './e2e/fixtures/auth.ts'` — runs once before all tests; logs in and saves `storageState`
- `use.storageState: 'e2e/.auth/state.json'` — persisted Firebase session reused across tests
- `workers: 1` — sequential (live dev DB, no isolation)
- `projects: [{ name: 'chromium' }]` — Chromium only (Windows lab PC)
- No `webServer` config — assumes dev stack already running (Vite + FastAPI)

### `package.json` scripts
```json
"test:e2e": "playwright test",
"test:e2e:ui": "playwright test --ui"
```

### Directory structure
```
frontend/
├── e2e/
│   ├── .auth/
│   │   └── state.json          # gitignored — Firebase session token
│   ├── fixtures/
│   │   └── auth.ts             # authenticated Page fixture
│   ├── journeys/
│   │   ├── 01-create-experiment.spec.ts
│   │   ├── 02-bulk-upload-experiments.spec.ts
│   │   ├── 03-upload-icp.spec.ts
│   │   ├── 04-update-status-dashboard.spec.ts
│   │   ├── 05-upload-xrd.spec.ts
│   │   ├── 06-recalculate-derived-fields.spec.ts
│   │   ├── 07-master-results-sync.spec.ts
│   │   ├── 08-solution-chemistry.spec.ts
│   │   └── 09-elemental-composition.spec.ts
│   └── helpers/
│       └── forms.ts            # shared form-fill utilities
├── playwright.config.ts
└── package.json
```

### Auth strategy
- **Real Firebase credentials** — tests use `labpc@addisenergy.com` dev account
- **Global setup** (`e2e/fixtures/auth.ts`): logs in once via UI, saves `storageState` to `e2e/.auth/state.json`
- All spec files consume the saved state — no per-test login
- `e2e/.auth/` is gitignored (contains Firebase ID token)

### Test data strategy
- Tests **create data and leave it** in the live dev DB (no teardown)
- Each journey uses unique experiment IDs with a `E2E_` prefix to distinguish from real data
- Upload journeys use real files from `docs/sample_data/` via Playwright `setInputFiles()`

---

## 3. Chunk Breakdown

### Chunk A — Playwright Infrastructure
**Goal:** Working Playwright setup with authenticated smoke test.

Deliverables:
- Cut `feature/m8-testing-docs` from `infra/lab-pc-server-setup`
- `frontend/playwright.config.ts`
- `frontend/e2e/fixtures/auth.ts` — global setup that logs in and saves storage state
- `frontend/e2e/journeys/00-smoke.spec.ts` — verifies Playwright reaches `localhost:5173`, auth works, and dashboard loads
- `.gitignore` entry for `frontend/e2e/.auth/`

---

### Chunk B — New Experiments Upload
**Goal:** Test `new_experiments_template.xlsx` end-to-end; fix `next-ids` endpoint; add NextIdChips UI.

**Existing backend — requires fixes:**
- `GET /api/experiments/next-ids` already exists at `backend/api/routers/experiments.py`
- Two divergences from spec (`docs/specs/new_experiments_upload.md`) to fix:
  1. Remove Firebase auth requirement (spec says no auth — read-only, non-sensitive)
  2. Add `Autoclave` type to the response (current impl only returns HPHT, Serum, CF)

**New frontend work:**
- NextIdChips component on the New Experiments upload card (shows next available IDs per type)

**Test:**
- Upload `docs/sample_data/new_experiments_template.xlsx` via UI
- Verify experiments appear in the experiment list
- Fix any parser errors encountered
- E2E journey 2: `02-bulk-upload-experiments.spec.ts`

---

### Chunk C — ICP + Solution Chemistry
**Goal:** Test both ICP and solution chemistry uploads with real files; fix any parser issues.

**Files:**
- `docs/sample_data/icp_raw_data.csv` — ICP upload
- `docs/sample_data/solution chemistry upload.xlsx` — solution chemistry (scalar results)

**Test:**
- Upload each file via the Bulk Uploads UI
- Inspect `UploadResult` response (created/updated/skipped/errors)
- Fix any parser bugs found
- E2E journey 3: `03-upload-icp.spec.ts`
- E2E test: `08-solution-chemistry.spec.ts`

---

### Chunk D — Master Results Sync
**Goal:** Implement the server-side sync model from `docs/specs/master_results_sync.md`; test with `Master Reactor Sampling Tracker.xlsx`.

**What already exists:**
- `MasterBulkUploadService.sync_from_path()` in `master_bulk_upload.py` reads the file from `settings.master_results_path` (a pydantic-settings `.env` field)
- `POST /api/bulk-uploads/master-results` already calls `sync_from_path()` when no file body is provided
- `Standard` column — must verify the existing parser silently ignores it (spec requirement)

**What is genuinely new (backend):**
- Mutable config store for the file path — the current `.env` field is read-only at runtime; need a small `AppConfig` DB table (key-value) or equivalent writable store
- `GET /api/bulk-uploads/master-results/config` — read the configured path from the writable store
- `PATCH /api/bulk-uploads/master-results/config` — validate the path resolves to a readable `.xlsx`, then save
- Update `POST /api/bulk-uploads/master-results` to read from the writable store (not `.env`)
- `PermissionError` handling (file open in Excel → clear user message, not 500)

**New frontend work:**
- Redesign the Master Results card:
  - Gear icon → settings panel with file path input + "Test connection" button
  - Normal state: "Last synced: X" + `[Sync Now]` + `[View last sync log]` buttons
  - No drag-and-drop file picker (server-side read only)
- Parse spec: `Standard` column must be silently ignored

**Test:**
- Configure file path to `docs/sample_data/Master Reactor Sampling Tracker.xlsx`
- Trigger sync and verify `UploadResult`
- Fix any parser issues
- E2E test: `07-master-results-sync.spec.ts`

---

### Chunk E — XRD Mineralogy (Aeris format)
**Goal:** Test `XRD_result_070d19.xlsx` (Aeris instrument export); fix Aeris parser if issues found.

**File:** `docs/sample_data/XRD_result_070d19.xlsx`
**Format:** Aeris — `Sample ID` column with values like `20260218_HPHT070-d19_02`
**UI endpoint:** The XRD Mineralogy card in `BulkUploads.tsx` calls `POST /api/bulk-uploads/xrd-mineralogy`, which routes through `XRDAutoDetectService`. Auto-detection will classify this file as `"aeris"` format and delegate to `AerisXRDUploadService`.
**Parser chain:** `XRDAutoDetectService.upload()` → `AerisXRDUploadService.bulk_upsert_from_excel()`

Aeris Sample ID parsing (`_parse_aeris_sample_id`):
```
20260218_HPHT070-d19_02
→ measurement_date = 2026-02-18
→ experiment_id_raw = HPHT070
→ days_post_reaction = 19
```

**Test:**
- Upload file via UI
- Verify `XRDPhase` rows created for the detected experiment and timepoint
- Fix any Aeris parser issues (regex, experiment lookup, date extraction)
- E2E journey 5: `05-upload-xrd.spec.ts`

---

### Chunk F — Elemental Composition (ActLabs)
**Goal:** Create new `elemental_composition.py` parser per spec; fix known `external_analysis_id` bug; test with `sample_actlabs_rock_composition.xlsx`.

**File:** `docs/sample_data/sample_actlabs_rock_composition.xlsx`

**What exists:**
- `backend/services/bulk_uploads/actlabs_titration_data.py` — the current `ElementalCompositionService` (heuristic multi-header ActLabs format)
- Known bug: creates `ElementalAnalysis` without required `external_analysis_id`

**What is new:**
- `backend/services/bulk_uploads/elemental_composition.py` — new flexible parser per `docs/specs/elemental_composition_upload.md`
  - Wide-format: `Sample ID` + analyte columns with unit in header (`Symbol (unit)`)
  - Auto-creates `Analyte` records; upserts `ElementalAnalysis` linked to an `ExternalAnalysis` record (fixes the missing `external_analysis_id` pattern)
  - This is a distinct parser from `actlabs_titration_data.py`, which stays for structured ActLabs report files
- New `POST /api/bulk-uploads/elemental-composition` endpoint wiring the new parser
- New upload card on the Bulk Uploads page for this parser

**Known bug fix (in existing `actlabs_titration_data.py`):**
- Fix `ElementalCompositionService` to create `ExternalAnalysis` record first (type=`Elemental`), then link `ElementalAnalysis` to it via `external_analysis_id`

**Spec reference:** `docs/specs/elemental_composition_upload.md`

**Test:**
- Upload file via UI using the new elemental composition card
- Verify `ElementalAnalysis` rows created for the sample with correct analyte values
- E2E test: `09-elemental-composition.spec.ts`

---

### Chunk G — Core E2E Journeys + Documentation
**Goal:** Complete the original 6 M8 E2E journeys; write all documentation.

**Remaining journeys:**
1. `01-create-experiment.spec.ts` — Login → create experiment → conditions → additives → verify derived fields on detail page
2. `04-update-status-dashboard.spec.ts` — Update experiment status via the inline `StatusBadge` on the ReactorGrid → reload the dashboard page → verify the card's status badge reflects the new status
3. `06-recalculate-derived-fields.spec.ts` — Edit `rock_mass_g` → verify `water_to_rock_ratio` recalculated

**Additional tests:**
- Calculation regression test (pytest): all derived fields for a known dataset match expected values

**Documentation:**
- `README.md` — full rewrite; must work on a clean machine
- `docs/user_guide/USER_MANUAL.md` — complete user manual
- `CONTRIBUTING.md`
- `docs/deployment/PRODUCTION_DEPLOYMENT.md`
- Audit `docs/CALCULATIONS.md` and `docs/FIELD_MAPPING.md` for accuracy
- FastAPI docstring audit (`backend/api/routers/`)
- React JSDoc audit (`frontend/src/`)

---

## 4. Real Sample Files Reference

| File | Upload type | Chunk |
|------|-------------|-------|
| `docs/sample_data/new_experiments_template.xlsx` | New Experiments | B |
| `docs/sample_data/icp_raw_data.csv` | ICP Results | C |
| `docs/sample_data/solution chemistry upload.xlsx` | Solution Chemistry (Scalar) | C |
| `docs/sample_data/Master Reactor Sampling Tracker.xlsx` | Master Results Sync | D |
| `docs/sample_data/XRD_result_070d19.xlsx` | XRD Mineralogy (Aeris) | E |
| `docs/sample_data/sample_actlabs_rock_composition.xlsx` | Elemental Composition (ActLabs) | F |

---

## 5. Acceptance Criteria

- [ ] Smoke test (`00-smoke.spec.ts`) passes — Playwright reaches app, auth works, dashboard loads
- [ ] All 9 journey specs (`01`–`09`) pass (`npx playwright test`)
- [ ] Calculation regression test passes
- [ ] All 6 upload types process real sample files with 0 unexpected errors
- [ ] Master Results Sync: mutable config store + `GET`/`PATCH /config` endpoints + redesigned UI card working
- [ ] `elemental_composition.py` new parser created; `external_analysis_id` bug fixed in `actlabs_titration_data.py`
- [ ] `GET /api/experiments/next-ids` returns all 4 types (HPHT, Serum, CF, Autoclave), no auth required
- [ ] `README.md` works end-to-end on a clean machine
- [ ] All documentation accurate and up to date

---

## 6. Out of Scope

- Load test (5 concurrent users)
- Firefox/WebKit Playwright projects — Chromium only
- Docker or CI pipeline integration
- Firebase emulator — real Firebase credentials used throughout
