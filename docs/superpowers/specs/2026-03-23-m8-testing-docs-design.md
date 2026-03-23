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
3. **New feature implementation** — specs in `docs/specs/` that are designed but not yet built (Master Results Sync server-side UI, `next-ids` endpoint, elemental composition parser)

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
**Goal:** Test `new_experiments_template.xlsx` end-to-end; implement `next-ids` endpoint and NextIdChips UI.

**New backend work:**
- `GET /api/experiments/next-ids` — returns `{ HPHT: N, Serum: N, CF: N, Autoclave: N }` (per spec `docs/specs/new_experiments_upload.md`)

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

This chunk is the largest — it implements a new UI pattern and new endpoints not yet built.

**New backend work:**
- `AppConfig` key-value table (or settings mechanism) for storing the file path
- `GET /api/bulk-uploads/master-results/config` — read configured path
- `PATCH /api/bulk-uploads/master-results/config` — validate and save path
- Update `POST /api/bulk-uploads/master-results` — reads from configured path (no file upload body)
- `PermissionError` handling (file open in Excel → clear user message)

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
**Parser:** `XRDAutoDetectService` → `AerisXRDUploadService`

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
**Goal:** Test `sample_actlabs_rock_composition.xlsx`; fix known `external_analysis_id` bug in `elemental_composition.py`.

**File:** `docs/sample_data/sample_actlabs_rock_composition.xlsx`
**Parser:** `backend/services/bulk_uploads/elemental_composition.py`

**Known bug (from M6):**
- `ElementalCompositionService` creates `ElementalAnalysis` without required `external_analysis_id`
- Fix: create `ExternalAnalysis` record first (type=`Elemental`), then link `ElementalAnalysis` to it

**Spec reference:** `docs/specs/elemental_composition_upload.md`

**Test:**
- Upload file via UI
- Verify `ElementalAnalysis` rows created for the sample
- E2E test: `09-elemental-composition.spec.ts`

---

### Chunk G — Core E2E Journeys + Documentation
**Goal:** Complete the original 6 M8 E2E journeys; write all documentation.

**Remaining journeys:**
1. `01-create-experiment.spec.ts` — Login → create experiment → conditions → additives → verify derived fields on detail page
2. `04-update-status-dashboard.spec.ts` — Update experiment status → verify dashboard reflects change
3. `06-recalculate-derived-fields.spec.ts` — Edit `rock_mass_g` → verify `water_to_rock_ratio` recalculated

**Additional tests:**
- Calculation regression test (pytest): all derived fields for a known dataset match expected values
- Load test: 5 concurrent users hitting the API simultaneously (using pytest-asyncio or locust)

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

- [ ] All 9 E2E journey specs pass (`npx playwright test`)
- [ ] Calculation regression test passes
- [ ] All 6 upload types process real sample files with 0 unexpected errors
- [ ] Master Results Sync server-side config implemented and tested
- [ ] `external_analysis_id` bug in `elemental_composition.py` fixed
- [ ] `GET /api/experiments/next-ids` implemented
- [ ] `README.md` works end-to-end on a clean machine
- [ ] All documentation accurate and up to date

---

## 6. Out of Scope

- Load test deferred unless time permits in Chunk G
- Firefox/WebKit Playwright projects — Chromium only
- Docker or CI pipeline integration
- Firebase emulator — real Firebase credentials used throughout
