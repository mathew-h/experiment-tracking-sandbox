# Project Working Memory

## Current Status
**Active Milestone:** M8 — Testing and Docs
**Branch:** `feature/m8-testing-docs`
**Last Updated:** 2026-03-23

---

## M8 — Testing and Docs: IN PROGRESS

### Objective
Playwright E2E infrastructure, test all upload types with real lab files, fix parser bugs found, complete documentation pass.

### Branch
`feature/m8-testing-docs` — cut from `infra/lab-pc-server-setup`

### Implementation Plan
`docs/superpowers/plans/2026-03-23-m8-testing-docs.md` — Read before starting any M8 work.
Spec: `docs/superpowers/specs/2026-03-23-m8-testing-docs-design.md`

### Key Decisions / Patterns (M8)
- **Firebase auth in Playwright:** Firebase Web SDK v9 stores auth in IndexedDB; Playwright's `storageState` only captures localStorage. Solution: worker-scoped `BrowserContext` fixture that logs in once via UI and shares the authenticated context (with IndexedDB intact) across all tests. One login per worker = one login per run with `workers: 1`. All spec files import `test, expect` from `../fixtures/auth` (not `@playwright/test`).
- **E2E file input selector:** The `UploadRow` component renders `id` prop but doesn't apply it to the DOM. To scope file inputs, use: `page.locator('.rounded-lg').filter({ has: page.getByRole('button', { name: /CardTitle/ }) }).locator('input[type="file"]')`.
- **ICP update/skip error reporting:** `icp_service.py` was putting standards-skip messages and update confirmations into `errors`. Fixed: standards silently skipped, updates counted in `updated` field (not errors). Return signature of `bulk_create_icp_results` changed to `(results, updated_count, errors)`.
- **scalar_results variable_config stub:** `bulk_uploads/scalar_results.py` imports `frontend.config.variable_config` at module load time; the endpoint was missing the sys.modules stub that ICP had. Fixed: added stub with `SCALAR_RESULTS_TEMPLATE_HEADERS` in `upload_scalar_results` endpoint.

### Completed
- [x] Chunk A: Playwright infrastructure
  - `feature/m8-testing-docs` branch cut from `infra/lab-pc-server-setup`
  - `frontend/playwright.config.ts` — baseURL, workers:1, no globalSetup/storageState
  - `frontend/e2e/fixtures/auth.ts` — worker-scoped BrowserContext fixture with Firebase UI login
  - `frontend/e2e/journeys/00-smoke.spec.ts` — 2 tests passing
  - `.gitignore` updated with `frontend/e2e/.auth/` and `frontend/e2e/.env.e2e`
  - `dotenv` devDependency added
- [x] Chunk B: Next-IDs fix + New Experiments upload
  - `GET /api/experiments/next-ids`: removed Firebase auth requirement, added `Autoclave` type
  - `frontend/src/api/bulkUploads.ts`: `Autoclave` added to `NextIds` interface
  - `frontend/src/pages/BulkUploads.tsx`: `NextIdChips` now renders Autoclave chip
  - `tests/api/test_experiments.py`: 2 new tests (no-auth, Autoclave) — all 21 pass
  - `frontend/e2e/journeys/02-bulk-upload-experiments.spec.ts` — 1 test passing
- [x] Chunk C: ICP + Solution Chemistry uploads
  - Bug fix: `icp_service.py` — standards silently skipped, updates counted separately (not in errors)
  - Bug fix: `bulk_uploads.py` `/scalar-results` endpoint — added missing `variable_config` sys.modules stub
  - `frontend/e2e/journeys/03-upload-icp.spec.ts` — 1 test passing
  - `frontend/e2e/journeys/08-solution-chemistry.spec.ts` — 1 test passing

### Pending
- [ ] Chunk D: Master Results Sync config store
  - New `AppConfig` DB table (key-value store for runtime-mutable settings)
  - `GET /api/bulk-uploads/master-results/config` + `PATCH /api/bulk-uploads/master-results/config`
  - Update `master_bulk_upload.py` `sync_from_path()` to read from `AppConfig` (not hardcoded settings)
  - No frontend changes needed (spec confirmed `UploadRow.syncFn` pattern already works)
  - One-time setup: configure path via Swagger UI before running E2E test
  - `frontend/e2e/journeys/07-master-results-sync.spec.ts`
- [ ] Chunk E: XRD Mineralogy (Aeris format)
  - Upload `docs/sample_data/XRD_result_070d19.xlsx` via UI, fix parser if needed
  - `frontend/e2e/journeys/05-upload-xrd.spec.ts`
- [ ] Chunk F: Elemental Composition (ActLabs)
  - Bug fix: `actlabs_titration_data.py` `ActlabsRockTitrationService.import_excel()` — creates `ElementalAnalysis` without `external_analysis_id` (see plan Task F1 for exact fix)
  - New `backend/services/bulk_uploads/elemental_composition.py` parser (flexible wide-format)
  - New `POST /api/bulk-uploads/elemental-composition` endpoint
  - `frontend/e2e/journeys/09-elemental-composition.spec.ts`
- [ ] Chunk G: Core E2E journeys + documentation
  - `01-create-experiment.spec.ts` — Login → create experiment → conditions → additives → verify derived fields
  - `04-update-status-dashboard.spec.ts` — Status change via StatusBadge → reload → verify dashboard badge
  - `06-recalculate-derived-fields.spec.ts` — Edit rock_mass_g → verify water_to_rock_ratio recalculated
  - Calculation regression test: `tests/regression/test_calc_regression.py`
  - Documentation: README.md rewrite, USER_MANUAL.md, CONTRIBUTING.md, PRODUCTION_DEPLOYMENT.md
  - FastAPI docstring audit, React JSDoc audit

### Parser Bugs Fixed in M8 (do not reintroduce)
- `icp_service.py` `process_icp_dataframe()`: standards with unrecognized label format now silently skipped (no error message)
- `icp_service.py` `bulk_create_icp_results()`: return signature changed to `(List, int, List)` — updated_count is tracked separately; update messages removed from errors
- `bulk_uploads.py` `upload_scalar_results()`: added `variable_config` sys.modules stub (same pattern as ICP endpoint)

### Next Action
Start **Chunk D**: Create `AppConfig` table, write migration, add `GET/PATCH /bulk-uploads/master-results/config` endpoints, update `sync_from_path()` to read from `AppConfig`. See plan `docs/superpowers/plans/2026-03-23-m8-testing-docs.md` Tasks D1–D3.

---

## M0 — Infrastructure Setup: COMPLETE

### What Was Done
- Configured GitHub remote: `https://github.com/mathew-h/experiment-tracking-sandbox.git`
- PAT authentication via `GITHUB_PAT` Windows env var; `GITHUB_PERSONAL_ACCESS_TOKEN` needed separately for GitHub MCP plugin
- PostgreSQL 18 installed on dev PC at `C:\Program Files\PostgreSQL\18`
- Created `experiments` database and `experiments_user` with password `password`
- Updated `.env` `DATABASE_URL` from SQLite to `postgresql://experiments_user:password@localhost:5432/experiments`
- Created `.venv` and installed all requirements from `requirements.txt`
- Created all tables via `Base.metadata.create_all()` (initial Alembic migration was empty — written against existing SQLite DB)
- Stamped Alembic at `head` (`4efd20d110e8`)
- FastAPI skeleton confirmed running: `GET /health → {"status":"ok","service":"experiment_tracking_api"}`

### Decisions Made
- **SQLite→PostgreSQL bootstrap pattern:** Initial migration chain was written against an existing SQLite DB (the `b1fc58c4119d` initial migration is empty). On a fresh PostgreSQL DB, use `Base.metadata.create_all()` + `alembic stamp head` rather than running the migration chain. This is the standard approach for bootstrapping.
- **Deployment deferred to lab PC phase:** `scripts/install_services.bat`, `scripts/deploy.bat`, `scripts/backup.bat`, and `docs/deployment/LAB_PC_SETUP.md` are not yet written. These will be addressed when setting up the lab PC. NSSM not yet installed.
- **Running on dev PC for now:** User will use their personal PC as the application host until lab PC setup is revisited.

### Deferred M0 Items (lab PC phase)
- [ ] `scripts/install_services.bat` — idempotent setup (PostgreSQL service, NSSM, firewall)
- [ ] `scripts/deploy.bat` — replaces `auto_update.bat`
- [ ] `scripts/backup.bat` — pg_dump with 30-day retention + Power BI dump
- [ ] `docs/deployment/LAB_PC_SETUP.md`
- [ ] NSSM install + uvicorn Windows service registration

### Known Pre-existing Test Issues (not M0-related)
- `tests/test_icp_service.py` — calls `sys.exit(1)` on import; legacy broken file
- `tests/test_time_field_guardrails.py` and others — import `frontend.config.variable_config` which doesn't exist until M4
- These will be addressed in M8 (Testing and Docs)

---

## M1 — PostgreSQL Migration: COMPLETE

### Objective
Migrate existing SQLite data (`docs/sample_data/experiments.db`) to PostgreSQL with full integrity verification.

### What Was Done
- Integrated Alembic with PostgreSQL
- Migrated all schema and data to PostgreSQL
- Created M1 milestone documentation

---

## M2 — Calculation Engine: COMPLETE

### Objective
Extract all derived-field calculation logic from SQLAlchemy model methods into `backend/services/calculations/`.

### Branch
`feature/m2-calculation-engine` — cut from `feature/m1-postgres-migration`

### What Was Done
- Registry pattern: `backend/services/calculations/registry.py` — dispatch dict + `recalculate(instance, session)`
- `conditions_calcs.py` — water_to_rock_ratio
- `additive_calcs.py` — unit conversions, moles, concentration, catalyst fields, format_additives()
- `scalar_calcs.py` — H2 PV=nRT at 20°C, ammonium yield, h2_grams_per_ton_yield
- Deleted calculation methods from `chemicals.py`, `conditions.py`, `results.py` (models now pure storage)
- 29 unit tests passing, no DB required
- `docs/CALCULATIONS.md` created

### Decisions Made
- **Clean break:** Model calculation methods deleted (not wrapped). No dead code.
- **Simple registry:** dispatch dict keyed on `type(instance)` — exact type match, no subclass matching.
- **Background default:** 0.3 mM default for background_ammonium_concentration_mM when not set.

### Sign-off
- [x] User sign-off received 2026-03-16 — proceed to M3

---

## M3 — FastAPI Backend: COMPLETE

### Objective
Build the complete API layer. All business logic lives here. The React app never touches the database directly.

### Branch
`feature/m3-fastapi-backend` — cut from `infra/lab-pc-server-setup` (after M2 merge)

### Implementation Plan
`docs/superpowers/plans/2026-03-16-m3-fastapi-backend.md` — 18 tasks, 6 chunks. **Read this before starting any M3 work.**

### Key Decisions Made
- **Firebase auth:** `auth/firebase_config.py` imports `streamlit` at module load — cannot be imported from FastAPI. `backend/auth/firebase_auth.py` initializes Firebase Admin SDK directly via `pydantic-settings`. Never import `auth.firebase_config` from the backend.
- **Calc engine API:** `docs/CODE_STANDARDS.md` example snippet uses `get_affected_fields()`/`calculation_service.run()` — these do **not exist**. Actual API is `registry.recalculate(instance, session)` from `backend/services/calculations/registry.py`.
- **Bulk upload parsers are locked:** `backend/services/bulk_uploads/` must not be modified. M3 wraps them only.
- **Route order matters:** In `results.py`, static routes (`/scalar/`, `/icp/`) must be registered before `/{experiment_id}` to avoid path shadowing.
- **Test DB:** Use `experiments_test` PostgreSQL DB. Create once: `psql -U postgres -c "CREATE DATABASE experiments_test OWNER experiments_user;"`. Tests use rollback fixtures, not mocks.

### Completed
- [x] Chunk 1: Settings, `get_db`, Firebase auth, test conftest (Tasks 1–4) — 2026-03-16
  - `backend/config/settings.py` — pydantic-settings, CORS list, Firebase cred dict
  - `backend/api/dependencies/db.py` — module-level engine + `get_db` generator
  - `backend/auth/firebase_auth.py` — `FirebaseUser`, `_decode_token`, `verify_firebase_token`
  - `tests/api/conftest.py` — test DB session, client fixture, auth override
  - `httpx==0.28.1` added to `requirements.txt` (required by FastAPI TestClient)
  - `experiments_test` DB created (postgres superuser password: "password")
- [x] Chunk 2: All Pydantic schemas (Tasks 5–7) — 2026-03-16
  - experiments.py, conditions.py, results.py, chemicals.py, samples.py, analysis.py, dashboard.py, bulk_upload.py + __init__.py
  - 5 schema tests passing
- [x] Chunk 3: Read routers — experiments, samples, chemicals, analysis (Tasks 8–11) — 2026-03-16
  - experiments.py: GET /api/experiments (list + filters), GET /api/experiments/{id}
  - samples.py: GET/POST /api/samples, GET/PATCH /api/samples/{id}
  - chemicals.py: GET/POST /api/chemicals/compounds, GET /api/chemicals/compounds/{id}, GET/POST /api/chemicals/additives/{conditions_id}
  - analysis.py: GET /api/analysis/xrd/{experiment_id}, GET /api/analysis/pxrf, GET /api/analysis/external/{experiment_id}
  - 15 tests passing

### Completed (all chunks)
- [x] Chunk 4: Write routers — experiments write, conditions, results (Tasks 12–13) — 2026-03-16
  - experiments.py: POST/PATCH/DELETE /api/experiments, POST /api/experiments/{id}/notes
  - conditions.py: GET /api/conditions/{id}, GET /api/conditions/by-experiment/{id}, POST/PATCH /api/conditions
  - results.py: GET /api/results/{experiment_id}, POST /api/results, GET/POST /api/results/scalar, PATCH /api/results/scalar/{id}, GET/POST /api/results/icp
  - 32 total API tests passing
- [x] Chunk 5: Dashboard, admin, bulk uploads, wire main.py (Tasks 14–17) — 2026-03-16
  - dashboard.py: GET /api/dashboard/reactor-status, GET /api/dashboard/timeline/{id}
  - admin.py: POST /api/admin/recalculate/{model_type}/{id}
  - bulk_uploads.py: POST /api/bulk-uploads/scalar-results, /new-experiments, /pxrf, /aeris-xrd
    - Uses lazy imports to avoid frontend.config import at startup (frontend not yet built)
  - main.py: full rewrite with openapi_tags for all 9 routers + static file serving
  - 41 total API tests passing
- [x] Chunk 6: docs/api/API_REFERENCE.md + final verification (Task 18) — 2026-03-16
  - docs/api/API_REFERENCE.md created

### Sign-off
- [x] User sign-off received 2026-03-16 — proceed to M4

### Known Patterns / Decisions Made in M3
- **Bulk upload lazy imports:** `backend/services/bulk_uploads/scalar_results.py` and `pxrf_data.py` import `frontend.config.variable_config` which doesn't exist until M4. Bulk uploads router uses lazy imports inside endpoint functions to avoid startup failure. Tests use `sys.modules` patching.
- **41 API tests passing** across all routers.

---

## M4 — React Shell: COMPLETE

### Branch
`feature/m4-react-shell`

### Completed (2026-03-17)
- [x] 4a: Tailwind config, PostCSS, ESLint (zero warnings), Prettier; logo.png renamed; vite proxy pre-configured
- [x] 4b: Design system — `brand.ts`, `tokens.css`, `index.css`; 10 UI components (Button, Input, Select, Badge, Card, Table, Spinner, Toast, Modal, FileUpload); inter + JetBrains Mono fonts; navy/red precision-instrument aesthetic
- [x] 4c: `AppLayout.tsx` (sidebar + header), `AuthLayout.tsx` (centered with decorative grid background)
- [x] 4d: `firebaseConfig.ts`, `AuthContext.tsx` (55-min token refresh), `ProtectedRoute.tsx`, `Login.tsx`
- [x] 4e: `api/client.ts` (Axios + auth interceptor + FastAPI error extraction) + domain files: experiments, samples, chemicals, analysis, dashboard, bulkUploads, results
- [x] 4f: All 8 page stubs with real structure: Dashboard (reactor grid + metrics), ExperimentList (table + filters), ExperimentDetail (conditions panel + results), NewExperiment (form + sample select), BulkUploads (drag-drop cards for all 4 upload types), Samples, Chemicals, Analysis (pXRF table)
- TypeScript strict: 0 errors; ESLint: 0 warnings; production build: clean (474kB)

### Completed (continued, 2026-03-17)
- [x] Firebase `.env.local` configured; full auth flow verified via Chrome DevTools
- [x] Chrome DevTools verification: login, all 7 protected routes, sign out, unauthenticated redirect
- [x] CLAUDE.md files updated for accuracy (active milestone, frontend Firebase setup, DB connection strings)

### Completed (continued, 2026-03-17)
- [x] Documentation Agent: `docs/frontend/ARCHITECTURE.md`, `docs/frontend/ADDING_A_PAGE.md`, `docs/frontend/DESIGN_SYSTEM.md`

### Sign-off
- [x] User sign-off received 2026-03-17 — proceed to M5

### Key Decisions / Patterns
- **Font pairing:** Inter (UI) + JetBrains Mono (data values) — instrument panel aesthetic
- **Token file:** `frontend/src/assets/brand.ts` is single source of truth for all color/spacing values
- **Auth token refresh:** Proactive 55-minute interval via `setInterval` in `AuthContext`
- **API errors:** Interceptor extracts FastAPI `detail` array messages into flat `error.message`
- **No `console.log`:** ESLint `no-console: error` enforced
- **Firebase graceful degradation:** `firebaseConfig.ts` exports `firebaseConfigured = Boolean(VITE_FIREBASE_API_KEY)`. When false, `auth` is exported as `null`, `AuthProvider` skips `onAuthStateChanged`, and `ProtectedRoute` returns children directly. App starts without Firebase for UI-only dev work. Template: `frontend/.env.example`.
- **Hooks-before-early-return rule:** ESLint `react-hooks/rules-of-hooks` is enforced — all `useState`/`useNavigate`/`useLocation` calls must appear before any conditional `return` in a component.
- **Form element IDs:** Use `useId()` from React, not `Math.random()` — stable across renders, ESLint-safe.
- **React Router future flags:** `v7_startTransition` and `v7_relativeSplatPath` set on `<BrowserRouter>` to silence upgrade warnings.
- **Navigation from non-link contexts:** Use `useNavigate()` + `onClick`, not `<Link>` wrapped inside `<Button>` — avoids nested interactive element violation.

### Bugs Fixed in M4 (do not reintroduce)
- Firebase crash on startup when `.env.local` missing — fixed via conditional init + `firebaseConfigured` flag
- `Link`-inside-`Button` in ExperimentList → replaced with `useNavigate`
- `useId()` replaces `Math.random()` in Input/Select for stable IDs
- ESLint `react-refresh` plugin removed (ESM conflict with `.eslintrc.cjs` format)

---

## M5 — Experiment Pages: IN PROGRESS

### Objective
Build the three fully-functional experiment management pages, wired to the live FastAPI backend.

### Branch
`feature/m5-experiment-pages`

### Implementation Plan
`docs/superpowers/plans/2026-03-18-m5-experiment-pages.md` — Read before starting any M5 work.

### Completed (2026-03-19)
- [x] Chunk A: Committed run-date fields migration (nmr_run_date, icp_run_date, gc_run_date to ScalarResults)
- [x] Chunk B: Backend schema + endpoint extensions
  - [x] B1: Extended Pydantic schemas — ExperimentListItem (additives_summary, condition_note, experiment_type, reactor_number), ExperimentListResponse, ExperimentDetailResponse, ExperimentStatusUpdate, NextIdResponse, ResultWithFlagsResponse; ConditionsUpdate/Response with all condition fields. 11 schema tests passing.
  - [x] B2: GET /experiments/next-id (prefix mapping, zero-padded); auto-assign experiment_number on create. 5 tests passing.
  - [x] B3: PATCH /experiments/{id}/status; list_experiments rewritten with pagination, server-side filters, conditions join, inline additives string_agg (replaces broken SQLite GROUP_CONCAT view). 4 new tests + 2 fixed. 17 tests passing.
  - [x] B4: GET /experiments/{id}/results with scalar+ICP flags; get_experiment enriched to return conditions+notes+modifications as ExperimentDetailResponse. 2 tests. 19 tests passing. Full suite: 54 passing.

### Key Decisions / Patterns (M5)
- **Additives summary:** `v_experiment_additives_summary` view uses SQLite `GROUP_CONCAT` and silently fails on PostgreSQL. Replaced with inline `string_agg` query in the list endpoint — no view dependency.
- **Route ordering:** GET /next-id → GET /{id}/results → PATCH /{id}/status → GET /{id} → POST → PATCH /{id} → DELETE → POST /{id}/notes. Static segments before dynamic at same depth.
- **Auto-numbering:** experiment_number is now Optional in ExperimentCreate; if omitted, assigned as max(existing) + 1.

### Pending
- [x] Chunk C: ExperimentList page (frontend API client + full rewrite) — 2026-03-19
- [x] Chunk D: New Experiment multi-step form (D1–D3) — 2026-03-19
- [x] Chunk E: Experiment Detail tabs (E1–E3) — 2026-03-19
- [x] Chunk F: Documentation update — 2026-03-19
- [x] M5 acceptance criteria sign-off from user — 2026-03-19

### Sign-off
- [x] User sign-off received 2026-03-19 — merged to infra/lab-pc-server-setup, proceed to M6

---

## M6 — Bulk Uploads: COMPLETE (signed off 2026-03-19, merged to infra/lab-pc-server-setup)

### Objective
Expose all bulk data ingestion workflows through an accordion-style React UI with 12 upload types.

### Branch
`feature/m6-bulk-uploads`

### Implementation Plan
`docs/superpowers/plans/2026-03-19-m6-bulk-uploads.md` — Read before starting any M6 work.

### Completed
- [x] Chunk A: Schema alignment — UploadResponse + warnings/feedbacks; frontend BulkUploadResult field fix (2026-03-19)
- [x] Chunk B: New parsers — timepoint_modifications, master_bulk_upload, xrd_upload; modified ElementalCompositionService auto-create analytes; MASTER_RESULTS_PATH in settings (2026-03-19)
- [x] Chunk C: All 9 new POST endpoints + GET templates/{type} + GET experiments/next-ids (2026-03-19)
- [x] Chunk D: Frontend rebuild — accordion BulkUploads page, UploadRow component, full API client, DefaultUnitField, NextIdChips (2026-03-19)

### Completed (continued, 2026-03-19)
- [x] Chunk E: Tests — 103 tests total (97 passing, 6 xfailed for known service bugs)
  - `tests/services/bulk_uploads/` — 50 service-level tests across 6 parsers
  - `tests/api/test_bulk_uploads.py` — 53 API-level tests (all endpoints, auth, templates)
  - Fixed 3 router bugs: class name mismatches (RockInventoryUploadService, ChemicalInventoryUploadService), missing image_files parameter
  - Fixed pre-M2 relic: scalar_results_service.py called deleted calculate_yields() → replaced with registry.recalculate()
  - xfailed tests document known service bugs: chemical_inventory (molecular_weight attr mismatch), elemental_composition (missing external_analysis_id)
- [x] Chunk F: Documentation — 2026-03-19
  - `docs/user_guide/BULK_UPLOADS.md` — all 12 upload types documented
  - `docs/developer/ADDING_UPLOAD_TYPE.md` — step-by-step guide
  - `docs/api/API_REFERENCE.md` — all new endpoints added
  - `docs/milestones/M6_bulk_uploads.md` — completion status updated

### Known Service Bugs (documented, not fixed — parsers are locked)
- `chemical_inventory.py`: uses `molecular_weight` attribute; model has `molecular_weight_g_mol` → all rows fail
- `actlabs_titration_data.py` (ElementalCompositionService): creates ElementalAnalysis without required external_analysis_id

---

## M7 — Reactor Dashboard: COMPLETE (signed off 2026-03-20, merge to infra/lab-pc-server-setup pending)

### Objective
Build a fully interactive reactor dashboard with live status grid (R01–R16, CF01–CF02), Gantt timeline, activity feed, filter chips, and a single-call backend endpoint returning all dashboard data under 500 ms.

### Branch
`feature/m7-reactor-dashboard`

### Completed
- [x] Chunk A: Backend — DashboardResponse schema, GET /api/dashboard/ endpoint, 15 tests (incl. performance)
- [x] Chunk B: Frontend — ReactorGrid, ExperimentTimeline, ActivityFeed, DashboardFilters, Dashboard rebuild
- [x] Chunk C: Documentation — DASHBOARD.md, API_REFERENCE.md updated
- [x] Post-implementation bugfixes: reactors_in_use distinct fix, vite proxy port, filter logic, modal theme

### Sign-off
- [x] User sign-off received 2026-03-20 — proceed to M8

### Key Decisions / Patterns (M7)
- **Single API call:** `GET /api/dashboard/` returns all four sections; frontend uses React Query `refetchInterval: 60_000`
- **18 fixed slots:** Frontend renders all slots from a static list; backend returns only occupied ones
- **Client-side filtering:** All Gantt filtering applied in-memory; no extra API calls
- **Reactor label:** Derived at backend from `experiment_type + reactor_number`; `CF01`/`CF02` for Core Flood, `R01`–`R16` for all others

---

## Context Restructure (completed 2026-03-16)
The original CLAUDE.md was refactored into a hierarchical context system (27 files). All content preserved. See previous plan entries for details.
