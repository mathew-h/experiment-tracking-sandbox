# Project Working Memory

## Current Status
**Active Milestone:** M5 — Experiment Pages
**Branch:** `feature/m4-react-shell`
**Last Updated:** 2026-03-17

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

## Issue #8 — Fix experiment_fk result write paths: COMPLETE

### Branch
`fix/issue-8-experiment-fk-result-writes` — cut from `feature/m4-react-shell`

### Problem
`experiment_id` (string label e.g. "HPHT_001") and `experiments.id` (integer PK) were being conflated on result write paths. A string could be passed as `experiment_fk`, bypassing the FK constraint silently in some cases.

### What Was Done
- Added `ConfigDict(strict=True)` to `ResultCreate` — Pydantic v2 no longer coerces `"42"` → `42`
- Added `Field(description=...)` to `experiment_fk` clarifying it is the integer PK
- Added FK existence guard in `create_result` router: `db.get(Experiment, payload.experiment_fk)` → 404 if not found
- Rewrote `frontend/src/api/results.ts` with typed `ResultCreate`/`ScalarCreate` interfaces (`experiment_fk: number`)
- Built `AddResultModal` component with `experimentPk: number` prop — structural TypeScript guard
- Wired `ExperimentDetail` to pass `experiment.id` (integer from query) not URL string `id`
- Vitest + jsdom + React Testing Library setup for frontend unit tests
- 5 schema tests, 4 router tests, 5 API contract tests, 8 AddResultModal component tests

### Decisions Made
- `strict=True` applied only to `ResultCreate` (not all schemas) to avoid breaking existing callers
- FK existence check returns 404 with a message that explicitly names the correct field
- jsdom `type="number"` sanitization workaround via `Object.defineProperty` documented in test comments
- ESM spy via `vi.spyOn(resultsModule, 'resultsApi')` documented as assumption in test comments

### Tests
- Backend: 50 passing (`pytest tests/api/ -v`)
- Frontend: 13 passing (`npx vitest run`)

### Commits
- `1379675` — initial implementation (schema, router, frontend API, AddResultModal, ExperimentDetail)
- `203e950` — plan document
- `c9f117c` — strict=True on ResultCreate
- `b86fef4` — schema tests (5 new in test_schemas.py)
- `12ad10e` — router tests (4 new in test_results.py)
- `56afcf1` — vitest setup
- `0d2cea1` — API contract tests
- `fef1c1c` — AddResultModal component tests
- `545c23e` — test comments (ESM spy + jsdom fragility)

### Sign-off
- [ ] Pending user sign-off — merge or PR decision deferred

---

## M5 — Experiment Pages: NOT STARTED

### Objective
Build the three fully-functional experiment management pages, wired to the live FastAPI backend.

### Branch
`feature/m5-experiment-pages` — cut from `feature/m4-react-shell` (after M4 merge)

### Pages
- **Experiment List (`/experiments`):** Filterable table (status, type, sample ID, date range, reactor number). Server-side pagination. Row click → detail.
- **New Experiment (`/experiments/new`):** Multi-step form (basic info → conditions → chemical additives → review/submit). Live `water_to_rock_ratio` preview. Real-time experiment ID uniqueness check.
- **Experiment Detail (`/experiments/:id`):** Tabs — Conditions (read-only + edit modal), Results (timepoints with scalar + ICP expandable rows), Notes (chronological feed + add), Analysis (linked XRD/pXRF/elemental), Files.

### Acceptance Criteria
- Creation round-trips with derived fields populated
- All filters work
- Derived fields display from stored DB values
- Lineage visible
- Chrome DevTools loop: no console errors

### Pending
- [ ] Brainstorm + plan before implementation
- [ ] Experiment List page
- [ ] New Experiment multi-step form
- [ ] Experiment Detail tabs
- [ ] Form validation, API integration, filter logic tests (Test Writer Agent)
- [ ] User-facing guide: creating and managing experiments (Documentation Agent)
- [ ] M5 acceptance criteria sign-off from user

---

## Context Restructure (completed 2026-03-16)
The original CLAUDE.md was refactored into a hierarchical context system (27 files). All content preserved. See previous plan entries for details.
