# Issue and inline task log

Append-only entries from `/complete-task` for task types **issue** and **inline** (newest at bottom).

## 2026-03-24 | inline — Close GitHub issue #3 (Ferrous Iron Yield)
- **Files changed:** none — administrative closure only
- **Tests added:** no
- **Decision logged:** no

## 2026-03-24 | inline — Reconcile elemental composition upload write logic (overwrite flag)
- **Files changed:**
  - `backend/services/bulk_uploads/actlabs_titration_data.py` — added `_write_elemental_record` helper; `overwrite: bool = False` param on `ElementalCompositionService.bulk_upsert_wide_from_excel` and `ActlabsRockTitrationService.import_excel`
  - `tests/services/bulk_uploads/test_elemental_composition.py` — 7 new tests (15 total); updated `test_updates_existing_elemental_analysis` to pass `overwrite=True`
  - `docs/upload_templates/actlabs_titration_data.md` — documented overwrite flag and behavior table
  - `docs/working/plan.md` — logged reconciliation under Pre-M9 section
- **Tests added:** yes — insert-new, skip-existing (overwrite=False), overwrite-existing (overwrite=True), null-cell-preservation; both services covered (7 new tests)
- **Decision logged:** yes — `docs/working/decisions.md`

## 2026-03-24 | inline — Fix sample detail 500 + M9 Playwright tests + rock inventory upload
- **Files changed:**
  - `backend/api/routers/samples.py` — removed `.value` call on `experiment_type` (String column, not enum)
  - `backend/services/bulk_uploads/rock_inventory.py` — replaced broken `utils.storage`/`utils.pxrf` imports with `Path.write_bytes` and `normalize_pxrf_reading_no` from `backend.services.samples`
  - `frontend/e2e/journeys/11-sample-management.spec.ts` — new Playwright journey (12 tests: list, detail, regression for 500 bug, tabs, editor, new sample modal, rock inventory upload)
  - `frontend/e2e/fixtures/rock_inventory_fixture.xlsx` — test fixture for rock inventory upload
- **Tests added:** yes — 12 Playwright e2e tests; 21 existing backend sample API tests all pass
- **Decision logged:** no

## 2026-03-24 | inline — Remove Analysis tab from sidebar
- **Files changed:** `frontend/src/layouts/AppLayout.tsx` — removed Analysis nav item from navItems array
- **Tests added:** no
- **Decision logged:** no

## 2026-03-25 | inline — Replace broken deployment bat files with PowerShell setup/update scripts
- **Files changed:**
  - `start_app.bat` — deleted (Streamlit launcher, no longer valid)
  - `auto_update.bat` — deleted (called non-existent `utils.auto_updater`)
  - `setup.ps1` — created (262 lines): self-elevating one-time setup; preflight checks, .env + frontend/.env.local copy-and-pause, venv + pip install, alembic migrations, npm build, NSSM service registration, firewall rule (Private + Domain), Task Scheduler nightly job, service start, success message
  - `update.ps1` — created (113 lines): self-elevating; git pull, HEAD before/after diff, selective rebuild (deps/migrations/frontend only if changed), NSSM restart, timestamped log
  - `docs/deployment/STARTUP_GUIDE.md` — created: plain-English walkthrough for lab techs covering prerequisites, first-time setup, .env fields, manual/scheduled updates, troubleshooting
  - `docs/deployment/PRODUCTION_DEPLOYMENT.md` — updated: replaced manual NSSM steps 6-7-8 with setup.ps1 reference; replaced manual update shell block with update.ps1 reference
- **Tests added:** no — PowerShell scripts; no applicable test framework
- **Decision logged:** no

## 2026-03-24 | inline — Experiment detail UI: input text color, chemical additives editor, tab rename
- **Files changed:** `frontend/src/components/ui/Input.tsx`, `frontend/src/components/ui/Select.tsx`, `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`, `frontend/src/pages/ExperimentDetail/index.tsx`, `frontend/src/api/chemicals.ts`, `frontend/src/pages/ExperimentDetail/NotesTab.tsx`, `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx`, `frontend/src/pages/NewExperiment/Step3Additives.tsx`, `frontend/src/pages/SampleDetail/AnalysesTab.tsx`, `frontend/src/pages/SampleDetail/NewSampleModal.tsx`, `frontend/src/pages/SampleDetail/OverviewTab.tsx`, `frontend/src/pages/SampleDetail/PhotosTab.tsx`, `frontend/src/components/ui/SampleSelector.tsx`, `docs/DESIGN.md`
- **Tests added:** no
- **Decision logged:** yes — updated `docs/DESIGN.md` with Form Input Text Color Rule: use `text-navy-900` for all form fields, never `bg-surface-input` (undefined token)

## 2026-03-25 | inline — Production deployment setup and fixes
- **Files changed:**
  - `setup.ps1` — fixed npm `--legacy-peer-deps`, NSSM stderr try/catch, Azure AD `whoami` credential prefill, Python 3.13 venv creation via `py -3.13`, NSSM service uses `python -m uvicorn` instead of `uvicorn.exe` (Windows Store Python inaccessible to SYSTEM)
  - `backup.ps1` — created: daily pg_dump to `C:\Backups\experiments\`, 30-day retention, logs to `C:\Logs\experiment-tracker\backup.log`
  - `backend/api/main.py` — SPA catch-all now serves static files from `dist/` root (fixes logo not rendering)
  - `alembic/versions/88c99be25944_merge_migration_heads.py` — auto-generated merge of two alembic heads
- **Tests added:** no — deployment scripts and static file serving; ESLint passed on changed frontend files
- **Decision logged:** no

## 2026-03-25 | issue #7 — Chemicals page and additive picker wiring
- **Files changed:**
  - `backend/api/schemas/chemicals.py` — added `CompoundUpdate`, `ChemicalAdditiveUpsert`; validators on name, CAS, MW, density, amount
  - `backend/api/routers/chemicals.py` — added `?search=` param, `PATCH /compounds/{id}`, case-insensitive uniqueness checks (409)
  - `backend/api/routers/experiments.py` — added `GET/PUT/DELETE /api/experiments/{id}/additives/{compound_id}`
  - `tests/api/test_schemas.py` — 11 compound/additive schema validation tests
  - `tests/api/test_chemicals.py` — search, PATCH, 409 uniqueness tests
  - `tests/api/test_experiments.py` — 8 additive endpoint tests (list, upsert, delete, 404 cases)
  - `frontend/src/api/chemicals.ts` — added `updateCompound`, `upsertAdditive`, `deleteAdditive`, `listExperimentAdditives`; full `Compound` type
  - `frontend/src/components/CompoundFormModal.tsx` — created reusable create/edit modal (`minimal` prop for picker inline flow)
  - `frontend/src/pages/Chemicals.tsx` — full compound library UI: searchable table, Add/Edit actions
  - `frontend/src/pages/NewExperiment/Step3Additives.tsx` — per-row typeahead; "Create compound" inline option
  - `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` — delete additive; experiment-scoped endpoints; upsert semantics
  - `frontend/src/pages/NewExperiment/index.tsx` — switched submission to `upsertAdditive`
  - `frontend/e2e/journeys/12-chemicals.spec.ts` — e2e journey for chemicals page and additive flow
- **Tests added:** yes — 11 backend schema tests, 19 backend API tests, 1 Playwright e2e journey (12-chemicals.spec.ts)
- **Decision logged:** no

## 2026-03-25 | inline — Backfill all M3 calculated fields (migration 012)
- **Files changed:**
  - `database/data_migrations/recalculate_all_registry_012.py` — new: `_backfill_conditions`, `_backfill_scalars`, `run_migration` with `--dry-run` flag
  - `database/data_migrations/__init__.py` — new: package marker
  - `tests/data_migrations/__init__.py` — new: package marker
  - `tests/data_migrations/test_recalculate_all_registry_012.py` — new: 3 integration tests
- **Tests added:** yes — 3 integration tests (conditions water_to_rock_ratio, additive mass_in_grams, scalar grams_per_ton_yield)
- **Decision logged:** no

## 2026-03-25 | fix — Remove Files tab; collapse entry log rows
- **Files changed:**
  - `frontend/src/pages/ExperimentDetail/index.tsx` — removed Files tab from tab bar
  - `frontend/src/pages/ExperimentDetail/ModificationsTab.tsx` — refactored to collapsible `ModRow` component; rows start collapsed
- **Tests added:** no
- **Decision logged:** no

## 2026-03-25 | issue #5 — Copy From Existing toggle on New Experiment wizard
- **Files changed:**
  - `frontend/src/pages/NewExperiment/CopyFromExisting.tsx` — new: toggle button, inline debounced search input (300ms), scrollable dropdown (experiment_id / experiment_type / status), badge + clear state
  - `frontend/src/pages/NewExperiment/index.tsx` — added `handleCopyFrom` (parallel fetch of experiment detail + conditions + additives, maps all fields), `handleClearCopy` (resets step to 0 + all form state), copy banner with dismiss, `CopyFromExisting` wired into header
- **Tests added:** no
- **Decision logged:** no

## 2026-03-25 | inline — Background ammonium default 0.2 mM and bulk-apply endpoint
- **Files changed:**
  - `database/models/results.py` — `background_ammonium_concentration_mM` column: added `default=0.2, server_default=text("0.2")`
  - `alembic/versions/a1b2c3d4e5f6_background_ammonium_default_0_2.py` — new migration: sets server_default + backfills existing NULL rows to 0.2
  - `backend/services/calculations/scalar_calcs.py` — both hardcoded `0.3` fallbacks → `0.2`; docstring updated
  - `backend/api/schemas/results.py` — `ScalarCreate` field default `None` → `0.2`; added `BackgroundAmmoniumUpdate` / `BackgroundAmmoniumUpdated` schemas
  - `backend/services/bulk_uploads/scalar_results.py` — rows without background column now receive `0.2` default
  - `backend/api/routers/experiments.py` — new `PATCH /{experiment_id}/background-ammonium` endpoint; bulk-applies value to all scalar results and triggers recalculation
  - `frontend/src/api/experiments.ts` — added `setBackgroundAmmonium(experimentId, value)`
  - `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` — "Background NH₄: 0.2 mM" button; inline input; `useMutation` with cache invalidation
  - `tests/api/test_background_ammonium.py` — new: 6 API tests
- **Tests added:** yes — 6 backend API tests (404, no-scalars, bulk update, recalc trigger, negative rejection, schema default)
- **Decision logged:** no

## 2026-03-26 | inline — Register / Request Access form on login screen
- **Files changed:**
  - `backend/api/schemas/auth.py` — new: `RegisterRequest` (email domain, role, display name, password validators), `RegisterResponse`
  - `backend/api/routers/auth.py` — new: `POST /api/auth/register` (public, no token); calls `auth.user_management.create_pending_user_request()`; 409 on duplicate email
  - `backend/api/main.py` — included `auth` router
  - `frontend/src/pages/Login.tsx` — replaced "Contact lab admin" text with tabbed Sign in / Request access UI; RegisterForm posts to `/api/auth/register`; success state shows confirmation; client-side domain validation
- **Tests added:** no — public endpoint with Firestore dependency; no test fixture for Firestore pending_users
- **Decision logged:** no

## 2026-03-26 | inline — Expand Power BI reporting views in event_listeners.py
- **Files changed:** `database/event_listeners.py`
- **Tests added:** no — no dedicated view tests exist; syntax verified via `ast.parse`; pre-existing test collection errors unrelated to this change
- **Decision logged:** no

## 2026-03-26 | inline — Fix bulk upload UniqueViolation (PostgreSQL sequence desync)
- **Root cause:** SQLite→PostgreSQL migration inserted rows with explicit IDs; sequences were never updated, so every new INSERT tried id=1/2/3 and collided with existing data (external_analyses, modifications_log, and potentially others)
- **Files changed:**
  - `database/database.py` — added `reset_postgres_sequences()`: inspects all tables with an `id` column, calls `setval(pg_get_serial_sequence(table, 'id'), MAX(id))` for each; no-op if sequences are already correct; skips tables without a serial sequence
  - `backend/api/main.py` — added FastAPI `lifespan` context manager that calls `reset_postgres_sequences()` on every startup
- **Tests added:** no — requires a live PostgreSQL instance; manual re-run of both uploads is the acceptance test
- **Decision logged:** no

## 2026-03-27 | issue #10 — Sample analysis data on sample detail page
- **Files changed:**
  - `backend/api/schemas/samples.py` — added `PXRFElementalData` and `XRDPhaseData` schemas; extended `ExternalAnalysisResponse` with optional `pxrf_data` and `xrd_data` fields
  - `backend/api/routers/samples.py` — eager-load `xrd_analysis` on `external_analyses`; bulk-fetch pXRF readings and average elemental values per analysis in `get_sample()`; auto-correct `characterized` flag at read time; added `_avg_pxrf()`, `_get_xrd_data()` helpers; `_to_analysis_response()` accepts optional `pxrf_map`
  - `frontend/src/api/samples.ts` — added `PXRFElementalData` and `XRDPhaseData` interfaces; extended `ExternalAnalysis` with `pxrf_data` and `xrd_data`
  - `frontend/src/pages/SampleDetail/OverviewTab.tsx` — added "Elemental Composition" card rendering `elemental_results` as a table (hidden when empty)
  - `frontend/src/pages/SampleDetail/AnalysesTab.tsx` — added `PXRFDataTable` and `XRDPhaseTable` sub-components rendered inline under each analysis entry
- **Tests added:** no
- **Decision logged:** no

## 2026-03-30 | inline — Clamp negative ICP ppm values to zero
- **Files changed:**
  - `backend/services/icp_service.py` — `process_icp_dataframe`: `float(concentration)` → `max(0.0, float(concentration))` to clamp instrument noise below detection limit
  - `tests/test_icp_service.py` — added `test_negative_concentration_clamped_to_zero` (negative clamp + positive boundary assertion)
  - `tests/conftest.py` — added `sys.modules` stub for `frontend.config.variable_config` (enables test collection; pattern per backend/CLAUDE.md)
  - `alembic/versions/4e8b99151ab0_merge_heads_before_icp_clamp.py` — merge migration joining two open heads
  - `alembic/versions/458f344f73d8_clamp_negative_icp_ppm_to_zero.py` — data migration: sets all existing negative ICP element ppm values to 0 (no-op downgrade)
- **Tests added:** yes — `test_negative_concentration_clamped_to_zero` (upload-path clamping, with positive boundary assertion)
- **Decision logged:** no

## 2026-03-31 | issue #22 — Experiment detail: edit/delete chemical additives and notes
- **Files changed:**
  - `backend/api/schemas/chemicals.py` — added `AdditiveUpdate` (partial PATCH payload)
  - `backend/api/schemas/experiments.py` — added `NoteUpdate`; added `updated_at` to `NoteResponse`
  - `backend/api/routers/experiments.py` — added `PATCH /{id}/notes/{note_id}`; wired `ModificationsLog` to upsert and delete additive endpoints
  - `backend/api/routers/additives.py` — new router: `PATCH /api/additives/{id}`, `DELETE /api/additives/{id}` (by PK; audit trail to `ModificationsLog`)
  - `backend/api/main.py` — registered `additives` router; added openapi tag
  - `frontend/src/api/experiments.ts` — added `patchNote`; added `updated_at` to `Note` type
  - `frontend/src/api/chemicals.ts` — added `AdditiveUpdatePayload` interface, `patchAdditive`, `deleteAdditiveById`
  - `frontend/src/pages/ExperimentDetail/NotesTab.tsx` — inline edit per note (pencil button, textarea, Save/Cancel, `(edited)` label)
  - `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` — edit additive modal (compound typeahead, amount/unit); delete now uses `deleteAdditiveById(a.id)`
  - `tests/api/test_notes.py` — new: 7 tests (happy path, 404 cases, empty text 422, ModificationsLog, no-op)
  - `tests/api/test_additives.py` — new: 11 tests (PATCH amount/unit/compound, 422, 404, ModificationsLog, recalc, 409 duplicate; DELETE by PK, 404, ModificationsLog)
  - `docs/api/API_REFERENCE.md` — documented `PATCH /notes/{note_id}` and new Additives section (5 endpoints)
- **Tests added:** yes — 18 new backend API tests (7 notes + 11 additives)
- **Decision logged:** no

## 2026-03-31 | issue #21 — Fix ferrous iron yield calculations returning NULL
- **Files changed:**
  - `backend/services/calculations/scalar_calcs.py` — fixed `getattr(conditions, 'total_ferrous_iron', None)` → `getattr(conditions, 'total_ferrous_iron_g', None)` (attribute name typo; was silently returning None in production)
  - `backend/services/bulk_uploads/actlabs_titration_data.py` — wired `recalculate_conditions_for_samples` in both `ElementalCompositionService.bulk_upsert_wide_from_excel` and `ActlabsRockTitrationService.import_excel` so elemental uploads retroactively populate `total_ferrous_iron_g`
  - `tests/services/calculations/test_scalar_calcs.py` — fixed `make_result_chain` fixture (same attribute name typo); added 2 new NH3 volume-priority tests (`test_ferrous_iron_yield_nh3_uses_sampling_volume_over_water_volume`, `test_ferrous_iron_yield_nh3_falls_back_to_water_volume_when_sampling_volume_absent`)
  - `tests/services/calculations/test_conditions_propagation.py` — fixed `make_propagation_chain` fixture (same typo); added `unittest.mock.patch` for `get_analyte_wt_pct` in propagation tests; removed vestigial `total_ferrous_iron_g` fixture parameter
- **Tests added:** yes — 2 new unit tests (volume priority); 4 pre-existing propagation tests and 2 pre-existing integration tests corrected and now passing
- **Decision logged:** no

## 2026-04-01 | issue #26 — CF01 dashboard slot not shown as active
- **Root cause:** `experiment_type = NULL` in `ExperimentalConditions` for the affected experiment (created before the type dropdown was added on 2026-03-26). The backend label derivation code in `dashboard.py` is correct — no code changes needed.
- **Files changed:**
  - `tests/api/test_dashboard.py` — 4 new backend integration tests: `test_core_flood_experiment_in_reactor_1_gets_cf01_label`, `test_core_flood_experiment_in_reactor_2_gets_cf02_label`, `test_hpht_experiment_in_reactor_1_gets_r01_not_cf01`, `test_null_experiment_type_in_reactor_1_gets_r01_not_cf01`
  - `frontend/e2e/journeys/14-dashboard-cf-slots.spec.ts` — new Playwright journey (2 tests): CF01 active slot (Core Flood + reactor_number=1), HPHT regression (reactor_number=1 → R01 not CF01)
- **Tests added:** yes — 4 backend integration tests, 2 Playwright E2E tests
- **Decision logged:** no

## 2026-04-01 | issue #25 — Add "wt% of fluid" as a selectable additive unit
- **Files changed:**
  - `database/models/enums.py` — added `WT_PCT_FLUID = "wt% of fluid"` to `AmountUnit`
  - `alembic/versions/db40dd1e6422_add_wt_pct_fluid_to_amountunit.py` — new migration: `ALTER TYPE amountunit ADD VALUE IF NOT EXISTS` for PERCENT, WEIGHT_PERCENT, WT_PCT_FLUID (PostgreSQL-guarded)
  - `backend/services/calculations/additive_calcs.py` — new `elif unit == AmountUnit.WT_PCT_FLUID` branch; formula `(amount / 100) × water_volume_mL`
  - `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` — added `wt% of fluid` to `ADDITIVE_UNIT_OPTIONS`
  - `frontend/src/pages/NewExperiment/Step3Additives.tsx` — added `wt% of fluid` to `AMOUNT_UNITS`
  - `docs/CALCULATIONS.md` — documented `wt% of fluid` formula
  - `tests/services/calculations/test_additive_calcs.py` — 2 new unit tests
  - `frontend/e2e/journeys/15-wt-pct-fluid-additive.spec.ts` — 2 new Playwright E2E tests
- **Tests added:** yes — 2 backend unit tests, 2 Playwright E2E tests
- **Decision logged:** `wt% of fluid` uses formula identical to `wt%` (assumes dilute aqueous solution ρ ≈ 1 g/mL); implemented as a distinct branch for semantic clarity

## 2026-04-02 | issue #27 — Editable Experiment ID (new + existing experiments)
- **Files changed:**
  - `backend/api/schemas/experiments.py` — added `experiment_id` to `ExperimentUpdate` with max_length=100
  - `backend/api/routers/experiments.py` — new `GET /{id}/exists` endpoint; `PATCH /{id}` rename logic (uniqueness check, whitespace strip, blank guard, conditions/notes/analysis/xrd sync, ModificationsLog, structlog)
  - `tests/api/test_experiments.py` — 8 new tests (exists true/false, rename conflict, noop, mod log, whitespace strip, analysis sync)
  - `frontend/src/api/experiments.ts` — added `checkExists`; expanded `patch` payload to include `experiment_id`
  - `frontend/src/hooks/useExperimentIdValidation.ts` — new file; debounced 300ms availability hook with currentId fast-path
  - `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx` — ID field made editable; live validation feedback
  - `frontend/src/pages/ExperimentDetail/index.tsx` — inline rename (pencil → input → save/cancel); 409 toast; redirect on success
  - `docs/api/API_REFERENCE.md` — documented `/exists` endpoint and updated PATCH schema
- **Tests added:** yes — 8 backend API tests
- **Decision logged:** no
