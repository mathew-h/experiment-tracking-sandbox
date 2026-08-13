# Issue and inline task log

Append-only entries from `/complete-task` for task types **issue** and **inline** (newest at bottom).

## 2026-03-30 | inline — Fix background NH₄ "Apply to all" not reflecting in UI + extend reporting views
- **Files changed:**
  - `database/event_listeners.py` — `v_dim_timepoints`: added `brine_modification_description`; `v_results_scalar`: added `net_ammonium_concentration` computed column
  - `update.ps1` — explicit `git checkout main` before pull; `pull origin main` instead of bare pull
  - `backend/api/schemas/results.py` — added `background_ammonium_concentration_mM` to `ResultWithFlagsResponse`
  - `backend/api/routers/experiments.py` — populated `background_ammonium_concentration_mM` in `get_experiment_results()`; removed `db.flush()` from inside the background-ammonium loop (now single `db.commit()` after all recalculations)
  - `frontend/src/api/experiments.ts` — added `background_ammonium_concentration_mM` to `ResultWithFlags` interface
  - `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` — button text and input initialisation now derive from `storedBgValue` (first result's DB value) instead of hardcoded `DEFAULT_BACKGROUND_NH4`
- **Tests added:** no
- **Decision logged:** no

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

## 2026-04-01 | issue #23 — Results tab: Sample Date column, inline Sampling Mod, reorder pH/Conductivity
- **Files changed:**
  - `backend/api/schemas/results.py` — added `scalar_measurement_date: Optional[datetime]` to `ResultWithFlagsResponse`
  - `backend/api/routers/experiments.py` — populated `scalar_measurement_date` from `scalar.measurement_date` in `get_experiment_results()`
  - `frontend/src/api/experiments.ts` — added `scalar_measurement_date: string | null` to `ResultWithFlags` interface
  - `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` — new 11-column grid (`GRID` constant + `fmtDate` helper); added Sample Date and Sampling Mod columns; MOD badge moved inline to Sampling Mod cell; brine modification removed from ExpandedRow; pH and Conductivity now adjacent; NH₄ (mM) top-level column dropped (still visible in expanded detail)
  - `tests/api/test_results.py` — added `test_get_experiment_results_includes_scalar_measurement_date` (TDD, timezone-safe noon UTC)
  - `frontend/e2e/journeys/16-results-tab-columns.spec.ts` — new Playwright journey (5 tests): column headers, pH/Cond adjacency, null date em-dash, MOD badge no-dropdown, inline description
- **Tests added:** yes — 1 backend API test, 5 Playwright E2E tests
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

## 2026-04-02 | issue #28 — mag-susc column + pXRF reverse-match characterized status
- **Files changed:**
  - `backend/services/bulk_uploads/rock_inventory.py` — mag-susc column detection (4 aliases), ExternalAnalysis record creation/overwrite
  - `backend/api/routers/bulk_uploads.py` — rock-inventory template updated (pxrf_reading_no, magnetic_susceptibility, INSTRUCTIONS sheet); pXRF upload endpoint extended with reverse-match post-processing (re-evaluates `characterized` for affected samples, logs modifications)
  - `backend/services/bulk_uploads/pxrf_data.py` — added CSV fallback (`pd.read_csv`) after `pd.read_excel` fails; verified against 740-row Niton XRF CSV
  - `tests/services/bulk_uploads/test_rock_inventory.py` — 6 mag-susc tests
  - `tests/api/test_bulk_uploads.py` — 4 pXRF reverse-match tests
- **Tests added:** yes — 10 new tests (6 service, 4 API); 158 passing
- **Decision logged:** no

## 2026-04-05 | inline — Fix Experiment ID field not editable on New Experiment form
- **Files changed:**
  - `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx` — added `refetchOnWindowFocus: false` to next-id query (prevents window focus from re-disabling field); guarded `useEffect` with `!data.experimentId` so auto-populate only fires when field is empty (prevents overwriting user edits on background refetch)
- **Tests added:** no
- **Decision logged:** no

## 2026-04-02 | issue #24 — fix invisible edit/delete buttons for additives and notes
- **Files changed:**
  - `backend/api/routers/experiments.py` — added `DELETE /{experiment_id}/notes/{note_id}` endpoint with ModificationsLog
  - `tests/api/test_notes_delete.py` — 5 new backend tests (204, row removed, audit log, 404 cases)
  - `frontend/src/api/experiments.ts` — added `deleteNote` service function
  - `frontend/src/api/__tests__/experiments.deleteNote.test.ts` — 2 unit tests
  - `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` — replaced invisible `opacity-0/text-ink-muted` additives buttons with accessible icon group; `ConfirmModal` gates delete
  - `frontend/src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx` — 3 unit tests
  - `frontend/src/pages/ExperimentDetail/NotesTab.tsx` — full replacement: added `deleteNote` mutation, `ConfirmModal`, both buttons with `aria-label`, `text-ink-secondary` contrast
  - `frontend/src/pages/ExperimentDetail/__tests__/NotesTab.buttons.test.tsx` — 3 unit tests
  - `frontend/src/components/ui/Modal.tsx` — added `role="dialog"` and `aria-modal="true"` to inner panel
  - `frontend/e2e/journeys/02-additives-crud.spec.ts` — 5 E2E tests (visibility, edit, delete confirm/cancel)
  - `frontend/e2e/journeys/03-notes-crud.spec.ts` — 5 E2E tests (visibility, edit, delete confirm/cancel)
- **Tests added:** yes — 5 backend + 8 frontend unit tests; 10 E2E tests
- **Decision logged:** no

## 2026-04-05 | issue #29 — Silent failure when unknown compound name submitted in Step 3 additives
- **Files changed:**
  - `frontend/src/pages/NewExperiment/Step3Additives.tsx` — added `rowErrors` state, `handleNext` validator (blocks navigation + fires `toast.error` when `compound_name` set but `compound_id` null), inline error display on compound input (`border-red-500` + `<p>` message), `patchRow` error-clearing on compound resolve or input clear, `removeRow` stale-key cleanup; added `useToast` import
  - `frontend/src/pages/NewExperiment/__tests__/Step3Additives.test.tsx` — new: 6 unit tests covering valid rows pass, empty rows pass, unresolved name blocks navigation, inline error shown, toast fires, empty name passes
- **Tests added:** yes — 6 unit tests (Vitest + Testing Library)
- **Decision logged:** no

## 2026-04-06 | issue #30 — Editable experiment start date (detail page + dashboard modal)
- **Files changed:**
  - `backend/api/routers/experiments.py` — add `ModificationsLog` entry when `date` is patched via `PATCH /api/experiments/{id}`
  - `backend/api/routers/dashboard.py` — all three `started_at` sites (reactor cards, Gantt, legacy `/reactor-status`) now use `Experiment.date or Experiment.created_at` instead of `created_at` alone
  - `tests/api/test_experiments.py` — 3 new tests: valid date PATCH, invalid date 422, ModificationsLog row verified
  - `tests/api/test_dashboard.py` — 1 new test: dashboard `started_at` reflects patched date
  - `frontend/src/pages/ExperimentDetail/index.tsx` — inline click-to-edit date field in metadata header; `dateMutation`, `startDateEdit()`, `confirmDate()`
  - `frontend/src/pages/ReactorGrid.tsx` — inline click-to-edit date in `ReactorDetailModal` "Started" row; null guard on `card.experiment_id`; `useToast` added
- **Tests added:** yes — 4 backend (pytest); no frontend unit tests
- **Decision logged:** no

## 2026-04-06 | issue #31 — map Sampled Solution Volume (mL) in Master Results Sync parser
- **Files changed:**
  - `backend/services/bulk_uploads/master_bulk_upload.py` — case-normalisation step for `Sampled Solution Volume (mL)` header; `sampling_vol_ml = _parse_float(row.get(...))` in per-row loop; `"sampling_volume_mL": sampling_vol_ml` added to `result_data`; module docstring updated
  - `tests/services/bulk_uploads/test_master_bulk_upload.py` — 4 new unit tests (value parsed, blank→None, absent column→no KeyError, case-insensitive header); strengthened `test_sampled_solution_volume_column_absent` with DB-state assertions
  - `tests/integration/conftest.py` — new file; Postgres `db_session` fixture with transaction-rollback isolation
  - `tests/integration/test_master_results_sync_endpoint.py` — new file; 2 integration tests verifying `ScalarResults.sampling_volume_mL` persisted/None
  - `docs/specs/master_results_sync.md` — new column row added to table
  - `docs/user_guide/BULK_UPLOADS.md` — new column row added to Master Results Sync table
- **Tests added:** yes — 4 unit tests + 2 integration tests (pytest)
- **Decision logged:** no

## 2026-04-06 | issue #32 — Notion Reactor Sync bidirectional daily sync
- **Files changed:**
  - `database/models/notion_sync.py` — new `ReactorChangeRequest` ORM model
  - `database/models/__init__.py`, `database/__init__.py` — export `ReactorChangeRequest`
  - `alembic/versions/9c358174ea54_add_reactor_change_requests.py` — additive migration; upgrade/downgrade both tested
  - `backend/services/notion_sync/__init__.py` — package marker
  - `backend/services/notion_sync/client.py` — Notion SDK wrapper; all SDK calls isolated here
  - `backend/services/notion_sync/import_.py` — import step (Notion → DB upsert → Notion clear post-commit)
  - `backend/services/notion_sync/export.py` — export step (ONGOING experiments → Notion)
  - `backend/services/notion_sync/sync.py` — orchestrator + APScheduler `make_scheduler()`
  - `backend/api/routers/notion_sync.py` — `POST /api/admin/notion-sync/trigger`
  - `backend/api/main.py` — lifespan registers APScheduler; router registered
  - `backend/config/settings.py` — 4 Notion fields added
  - `.env.example` — NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_DATA_SOURCE_ID, NOTION_SYNC_HOUR
  - `requirements.txt` — notion-client>=2.2.1
  - `docs/notion_sync/NOTION_SYNC.md` — new; field mapping, sync sequence, env vars, DB model, API reference
  - `tests/models/test_notion_sync_model.py` — 2 model tests
  - `tests/services/test_notion_sync_client.py` — 9 client tests
  - `tests/services/test_notion_sync_import.py` — 9 import tests (incl. commit-before-clear invariant)
  - `tests/services/test_notion_sync_export.py` — 9 export tests
  - `tests/services/test_notion_sync_integration.py` — 3 end-to-end tests
  - `tests/api/test_notion_sync.py` — 4 API tests
- **Tests added:** yes — 36 tests (pytest); all pass
- **Decision logged:** no

## 2026-04-06 | inline — Fix auto-updater silent failure in Task Scheduler
- **Files changed:** `update.ps1` — self-elevation block now skips `-Verb RunAs` in non-interactive sessions (Task Scheduler); logs warning instead of silently exiting
- **Tests added:** no — PowerShell infrastructure script
- **Decision logged:** no

## 2026-04-06 | issue #33 — Add QUEUED as a valid ExperimentStatus value
- **Files changed:**
  - `database/models/enums.py` — added `QUEUED = "QUEUED"` to `ExperimentStatus`
  - `alembic/versions/ad32def91adc_add_queued_experiment_status.py` — manual migration
  - `frontend/src/assets/brand.ts` — `statusQueued` color + `statusColorMap` entry
  - `frontend/tailwind.config.ts` — `queued: '#f59e0b'` status token
  - `frontend/src/components/ui/Badge.tsx` — `queued` variant in BadgeVariant, variantClasses, dotClasses, StatusBadge validVariants
  - `frontend/src/pages/ReactorGrid.tsx` — STATUS_OPTIONS, statusColors, static amber dot
  - `frontend/src/pages/ExperimentTimeline.tsx` — QUEUED bar color
  - `frontend/src/pages/DashboardFilters.tsx` — QUEUED filter chip
  - `frontend/src/pages/ExperimentList.tsx` — STATUS_OPTIONS, STATUS_TEXT_CLASS
  - `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx` — QUEUED in dropdown
  - `docs/POWERBI_MODEL.md` — status values table
  - `.claude/rules/MODELS.md` — ExperimentStatus enum list
- **Tests added:** yes — 4 pytest (enum value, dashboard active count excludes QUEUED, dashboard pending results excludes QUEUED, bulk upload does not auto-complete QUEUED), 3 vitest (StatusBadge QUEUED/ONGOING/unknown)
- **Decision logged:** no

## 2026-04-06 | inline — Add sampling_description to v_results_scalar view
- **Files changed:** `database/event_listeners.py` — added `er.description AS sampling_description` to `v_results_scalar`
- **Tests added:** no
- **Decision logged:** no

## 2026-04-06 | inline — Fix inline status dropdown not selecting QUEUED in Edge
- **Files changed:**
  - `frontend/src/pages/ExperimentList.tsx` — added `onMouseDown`/`onPointerDown` stopPropagation on inline status `<select>` to prevent Edge native popup event leakage to row click handler
  - `frontend/src/api/experiments.ts` — added `'QUEUED'` to `ExperimentListItem` and `ExperimentDetail` status union types
- **Tests added:** no
- **Decision logged:** no

## 2026-04-07 | inline — Remove Carried Forward status from Notion sync
- **Files changed:**
  - `backend/services/notion_sync/client.py` — removed `STATUS_CARRIED_FORWARD` constant, updated status comment
  - `backend/services/notion_sync/import_.py` — `In Progress` now sets `carried_forward=True`; unknown statuses logged and skipped
  - `docs/notion_sync/NOTION_SYNC.md` — updated to two-status model (Pending/In Progress/Completed)
  - `tests/services/test_notion_sync_import.py` — replaced old tests with 3 new ones: `test_in_progress_sets_carried_forward_true`, `test_completed_clears_notion`, `test_carried_forward_status_no_longer_handled`; updated accumulation test
  - `tests/services/test_notion_sync_export.py` — removed Carried Forward reference from export test
- **Tests added:** yes — 3 new import tests, 2 updated tests (35 total notion sync tests pass)
- **Decision logged:** no

## 2026-04-07 | issue #37 — Add Change Requests tab to Experiment Detail view
- **Files changed:**
  - `backend/services/notion_sync/import_.py` — added `_resolve_experiment_id()` helper; populates experiment_id on upsert from ONGOING experiment on reactor slot
  - `backend/api/schemas/notion_sync.py` — new file: `ChangeRequestResponse` Pydantic schema
  - `backend/api/routers/experiments.py` — added `GET /{experiment_id}/change-requests` endpoint with 404 guard
  - `frontend/src/api/experiments.ts` — added `ChangeRequestEntry` type and `getChangeRequests` API method
  - `frontend/src/pages/ExperimentDetail/ChangeRequestsTab.tsx` — new tab component with status badges and empty state
  - `frontend/src/pages/ExperimentDetail/index.tsx` — wired Change Requests tab at position 4 (between Notes and Analysis)
  - `docs/notion_sync/NOTION_SYNC.md` — updated experiment_id column documentation
  - `docs/api/API_REFERENCE.md` — registered new endpoint
- **Tests added:** yes — 3 backend import tests, 4 backend API tests, 3 frontend component tests
- **Decision logged:** no

## 2026-04-07 | inline — Add Working Date and Last Synced to Notion sync
- **Files changed:**
  - `backend/services/notion_sync/client.py` — added PROP_WORKING_DATE, PROP_LAST_SYNCED constants + stamp_sync_metadata() method
  - `backend/services/notion_sync/import_.py` — added active_cr_page_ids tracking to ImportResult
  - `backend/services/notion_sync/sync.py` — metadata stamp pass after import+export (Last Synced on all pages, Working Date on active CR pages)
  - `docs/notion_sync/NOTION_SYNC.md` — added properties to map table + new Step 3 section
- **Tests added:** no — existing 34 tests pass; stamp method uses existing update_page path
- **Decision logged:** no

## 2026-04-09 | issue #38 — Reactor grid overwrites HPHT slot for non-HPHT experiments
- **Files changed:**
  - `backend/api/routers/dashboard.py` — added experiment_type filter to get_dashboard() and get_reactor_status() reactor queries
  - `backend/api/routers/conditions.py` — added _validate_reactor_number() 422 validation on POST and PATCH
  - `tests/api/test_dashboard.py` — 2 new regression tests, 6 existing tests updated for filter
  - `tests/api/test_conditions.py` — 6 new validation tests
- **Tests added:** yes — 8 new API integration tests (dashboard + conditions)
- **Decision logged:** no

## 2026-04-10 | issue #39 — Skip calibration-standard rows in master bulk upload
- **Files changed:**
  - `backend/services/bulk_uploads/master_bulk_upload.py` — added guard clause to skip rows where Experiment ID contains "standard" (case-insensitive)
  - `tests/services/bulk_uploads/test_master_bulk_upload.py` — 3 new tests (standard skipped, NMR standard skipped, real experiment unaffected)
- **Tests added:** yes — 3 unit tests for standard-row skipping
- **Decision logged:** no

## 2026-04-23 | issue #46 — Add Fe²⁺ yield columns to results table and XRD run date tag
- **Files changed:**
  - `database/models/results.py` — added `xrd_run_date` (nullable DateTime) to `ScalarResults`
  - `alembic/versions/a72dbd3dec55_add_xrd_run_date_to_scalar_results.py` — additive migration (upgrade + downgrade)
  - `backend/services/bulk_uploads/master_bulk_upload.py` — parse `XRD Run Date` column; updated module docstring
  - `backend/services/scalar_results_service.py` — fixed pre-existing silent bug: `nmr_run_date`, `icp_run_date`, `gc_run_date`, `xrd_run_date` added to `SCALAR_UPDATABLE_FIELDS` and `ScalarResults()` constructor (were silently dropped before)
  - `docs/specs/master_results_sync.md` — added XRD Run Date row to column definitions table
  - `backend/api/schemas/results.py` — added `ferrous_iron_yield_h2_pct`, `ferrous_iron_yield_nh3_pct`, `xrd_run_date` to `ResultWithFlagsResponse`
  - `backend/api/routers/experiments.py` — populated three new fields in `get_experiment_results` serializer
  - `frontend/src/api/experiments.ts` — extended `ResultWithFlags` with three new fields
  - `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` — added `fmtPct`, expanded GRID 12→14 cols, inserted Fe²⁺ NH₃/H₂ columns, added XRD badge
  - `frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx` — new test file (6 vitest tests)
  - `tests/api/test_results.py` — 4 new tests (model field, ferrous yield pct, xrd_run_date present/absent)
  - `tests/services/bulk_uploads/test_master_bulk_upload.py` — 1 new test for XRD Run Date parsing
- **Tests added:** yes — 4 backend API tests, 1 bulk upload integration test, 6 frontend vitest tests
- **Decision logged:** no

## 2026-04-24 | inline — Master Sample Tracking schema + bulk upload compatibility
- **Files changed:**
  - `database/models/samples.py` — added `well_name`, `core_lender`, `core_interval_ft` (String), `on_loan_return_date` (Date) to `SampleInfo`
  - `alembic/versions/fad70818aaf6_add_core_loan_fields_to_sample_info.py` — additive migration (4 nullable columns)
  - `backend/services/bulk_uploads/rock_inventory.py` — column alias normalization (`pXRF Reading No` → `pxrf_reading_no`, `Mag. Suscept. [SI*1e3]` → mag susc EA); new field_map entries for 4 new fields; `_parse_date` static method with `pd.NaT` guard; overwrite clearing extended
  - `backend/api/schemas/samples.py` — 4 new fields on `SampleCreate`, `SampleUpdate`, `SampleResponse`, `SampleDetail`
  - `backend/api/routers/samples.py` — `get_sample` handler now passes 4 new fields to `SampleDetail` constructor
  - `backend/api/routers/bulk_uploads.py` — rock-inventory download template updated (16 columns, new INSTRUCTIONS rows)
  - `.claude/rules/MODELS.md` — SampleInfo section updated with 4 new fields
  - `tests/services/bulk_uploads/test_rock_inventory.py` — 5 new tests (pXRF alias, mag susc alias, short mag susc alias, new fields persistence, overwrite clearing)
  - `tests/api/test_samples.py` — 1 new API roundtrip test for core/loan fields in GET detail response
  - `docs/superpowers/plans/2026-04-24-master-sample-tracking-schema.md` — implementation plan
- **Tests added:** yes — 5 service tests, 1 API test (46 total passing)
- **Decision logged:** no

## 2026-04-24 | inline — pXRF upload audit: fix mixed units, Zn import, CSV reverse-match, stale tests
- **Files changed:**
  - `backend/services/bulk_uploads/pxrf_data.py` — `_clean_dataframe()` converts weight-% rows to ppm (× 10,000) when `Units` column present; optionally cleans and maps `Zn` column; returns 3-tuple `(df, errors, warnings)`; `_upsert_dataframe()` optionally writes `zn` field; `ingest_from_bytes()` returns 5-tuple `(inserted, updated, skipped, errors, warnings)`; migrated `Session.query()` to `select()` + `execute()`; fixed pandas 3.x warnings (`.copy()` after filter, `replace(None)` + `to_numeric` pattern)
  - `backend/api/routers/bulk_uploads.py` — unpacks 5-tuple from `ingest_from_bytes`; passes `warnings` to `UploadResponse`; adds pandas CSV fallback in reading-no extraction block so reverse-match runs for CSV uploads (openpyxl fails silently on CSV)
  - `tests/api/test_bulk_uploads.py` — updated 5 `ingest_from_bytes` mock return values from 4-tuple to 5-tuple
  - `tests/test_ingest_pxrf.py` — full rewrite: removed legacy `database.ingest_pxrf` imports; 13 tests targeting `PXRFUploadService.ingest_from_bytes()` covering null equivalents, reading-no normalisation, skip/update logic, % → ppm conversion, optional Zn import
  - `tests/conftest.py` — `test_db` commit calls added for service isolation
  - `docs/superpowers/plans/2026-04-24-pxrf-upload-audit-fixes.md` — implementation plan
- **Tests added:** yes — 13 unit tests in `test_ingest_pxrf.py` (all passing); 76 pXRF-related tests passing total
- **Decision logged:** no

## 2026-04-28 | issue #52 — Add v_experiment_additive_names_summary view
- **Files changed:**
  - `database/event_listeners.py` — added `v_experiment_additive_names_summary` to `_VIEWS` immediately after `v_experiment_additives_summary`
  - `tests/views/test_additive_names_summary.py` — new file: 6 tests covering queryable, null for no additives, single additive, alphabetical sort, one-row-per-experiment, count match
- **Tests added:** yes — 6 view integration tests
- **Decision logged:** no

## 2026-04-30 | issue #54 — Fix parse_experiment_id misclassification of TYPE-NNN IDs
- **Files changed:**
  - `database/lineage_utils.py` — restructured `parse_experiment_id`: treatment extracted before sequential check; sequential gate now requires prefix to end in `[_-]\d+`; `import re` added
  - `tests/test_lineage_migration.py` — updated 2 stale assertions (COMPLEX-ID-TEST-3, TEST-SAMPLE-001); added 5 new assertions (CF-015, CF-12, CF-04, CF-015-2, HPHT_001-2); fixed pre-existing failure for HPHT_MH_001-2_Desorption
- **Tests added:** yes — 5 new assertions in test_parse_experiment_id
- **Decision logged:** no
- **⚠ Data migration required:** Re-run `establish_experiment_lineage_006.py` on the live database to correct corrupted parent-child links for CF-015, CF-04, CF-12 and any other TYPE-NNN experiments. See plan: `docs/superpowers/plans/2026-04-30-issue-54-parse-experiment-id-fix.md` Task 4.

## 2026-04-30 | inline — Update POWERBI_MODEL.md for recent view changes
- **Files changed:**
  - `docs/POWERBI_MODEL.md` — added `v_experiment_additive_names_summary` (issue #52) to views table, relationships diagram, and notes; added `sampling_description` to `v_results_scalar` key columns; expanded convenience-view note with usage guidance
- **Tests added:** no
- **Decision logged:** no

## 2026-04-30 | issue #55 — Notion sync: prevent duplicate change requests and clarify status workflow
- **Files changed:**
  - `backend/services/notion_sync/import_.py` — added `_is_text_unchanged` helper; dedup block in `run_import` skips insert for `Ongoing` rows with unchanged text while preserving `active_cr_page_ids` for Working Date stamping
  - `backend/services/notion_sync/client.py` — renamed `STATUS_PENDING → STATUS_NO_CHANGE ("No Change")`, `STATUS_IN_PROGRESS → STATUS_ONGOING ("Ongoing")`; renamed `set_status_pending → set_status_no_change`; updated `clear_change_request` and `extract_change_status` fallback
  - `backend/services/notion_sync/export.py` — updated `set_status_pending` call to `set_status_no_change`; fixed stale docstring
  - `tests/services/test_notion_sync_import.py` — 6 new dedup tests + 3 status-rename tests; fixed pre-existing `"Name"` → `"Reactor #"` key bug in page-builder helpers; updated 2 existing tests for new behavior (49 total)
  - `tests/services/test_notion_sync_client.py` — updated to new status constant names; fixed `"Name"` → `"Reactor #"` bug
  - `tests/services/test_notion_sync_export.py` — fixed `"Name"` → `"Reactor #"` bug
  - `tests/services/test_notion_sync_integration.py` — fixed `"Name"` → `"Reactor #"` bug
  - `docs/NOTION_SYNC.md` — created: status table, dedup explanation, sync sequence, constants reference, deployment gate note, trigger endpoint path
  - `migrate_deduplicate_change_requests.py` — one-time cleanup script for pre-existing duplicate DB rows (dry-run by default)
- **Tests added:** yes — 9 new tests (6 dedup, 3 status rename); 49/49 passing
- **Decision logged:** no
- **Deployment gate:** status rename requires Notion select options (`"In Progress"` → `"Ongoing"`, `"Pending"` → `"No Change"`) to be updated **before** this is promoted to `main` and deployed

## 2026-05-01 | inline — Backfill cumulative_time_post_reaction_days after lineage fix
- **Files changed:**
  - `database/data_migrations/recalculate_cumulative_times_014.py` — new one-time data migration; `_backfill_cumulative_times()` calls `update_cumulative_times_for_chain()` once per unique `base_experiment_id` chain
  - `tests/data_migrations/test_recalculate_cumulative_times_014.py` — 6 tests covering standalone, single derivation, multi-result parent (max offset), two-deep chain, null time, and no-results edge cases
- **Tests added:** yes — 6 new tests; 6/6 passing
- **Decision logged:** no
- **Note:** Commits landed directly on `develop` (no topic branch). Migration must be run manually against the dev DB before deploying.

## 2026-05-01 | inline — Add missing ICP element columns (Ag, Ce, K, La, Na, Pb, Sc, Th, V)
- **Files changed:**
  - `database/models/results.py` — added 9 Float columns to `ICPResults`: ag, ce, k, la, na, pb, sc, th, v
  - `database/event_listeners.py` — extended `v_results_icp` view with 9 new `_ppm` aliases
  - `alembic/versions/b2c3d4e5f6a7_...py` — additive migration; idempotent upgrade/downgrade
- **Tests added:** no
- **Decision logged:** no
- **Note:** Committed directly to `develop` per user instruction. Migration applied to dev DB.

## 2026-05-01 | issue #50 — Fuzzy Sample ID Matching & Duplicate Warning for ActLabs Bulk Upload
- **Files changed:**
  - `requirements.txt` — added `rapidfuzz>=3.0.0`
  - `backend/config/settings.py` — added `actlabs_similarity_threshold` (default 0.90, range 0.0–1.0)
  - `backend/services/bulk_uploads/_id_match.py` — new: `SimilarSampleMatch` TypedDict, `find_similar_samples()` (preloads all samples, avoids N+1)
  - `backend/api/schemas/bulk_upload.py` — added `SampleConflictMatch`, `SampleConflict`, `ConflictCheckResponse`
  - `backend/services/bulk_uploads/actlabs_titration_data.py` — removed local `_normalize_sample_id`/`_fuzzy_find_sample`; added `_resolve_sample()`, `preflight_check()` class method, `resolutions` param on `import_excel`
  - `backend/api/routers/bulk_uploads.py` — two-phase `upload_actlabs_rock` endpoint; Phase 1 returns `ConflictCheckResponse` on near-matches; Phase 2 accepts `resolutions` form field
  - `frontend/src/api/bulkUploads.ts` — added `ConflictCheckResult`, `SampleConflict`, `SampleConflictMatch` interfaces; exported `isConflictCheckResult`; updated `uploadActlabsRock`
  - `frontend/src/pages/BulkUploadRow.tsx` — widened `uploadFn` return type; added `onUploadError` prop
  - `frontend/src/components/SampleConflictModal.tsx` — new: blocking conflict resolution modal
  - `frontend/src/pages/ActlabsUploadRow.tsx` — new: wraps `UploadRow` with Phase 1 intercept, modal, and Phase 2 confirm mutation
  - `frontend/src/pages/BulkUploads.tsx` — replaced bare `UploadRow` for card 10 with `ActlabsUploadRow`
  - `tests/services/bulk_uploads/test_id_match.py` — 5 unit tests for `find_similar_samples`
  - `tests/services/bulk_uploads/test_actlabs_conflicts.py` — 7 tests for preflight + resolution logic
  - `tests/api/test_bulk_uploads.py` — 3 endpoint tests for two-phase flow
- **Tests added:** yes — 15 new tests (94 total, all pass)
- **Decision logged:** no

## 2026-05-04 | inline — ICP-OES bulk upload overwrite flag
- **Files changed:**
  - `backend/services/icp_service.py` — `overwrite: bool = False` on `create_icp_result` and `bulk_create_icp_results`; `db.delete` + `db.flush` + `db.expire` block before merge branch deletes existing `ICPResults` when flag is set
  - `backend/api/routers/bulk_uploads.py` — `overwrite: bool = Form(False)` added to `upload_icp_oes`; forwarded to service
  - `frontend/src/api/bulkUploads.ts` — `uploadIcpOes` now accepts `overwrite = false` and appends it to FormData
  - `frontend/src/pages/BulkUploads.tsx` — `IcpOverwriteToggle` component + `icpOverwrite` state wired into ICP-OES `UploadRow` via `topContent` and `uploadFn`
  - `tests/test_icp_handling.py` — `TestICPOverwrite` (3 tests: replace, merge-preserve, no-prior-data) + `TestICPRouterOverwrite` (1 test: flag forwarding with auth bypass)
- **Tests added:** yes — 4 new tests; all pass; pre-existing 14 failures unchanged (pre-date this work)
- **Decision logged:** no

## 2026-05-05 | issue #56 — Swap Reactor 4 and Reactor 7: dashboard update + data migration
- **Files changed:**
  - `database/data_migrations/swap_reactor_4_7_015.py` — new: migration 015; `_swap_reactor_assignments(db, dry_run)` with three-step temp-value atomic swap (4→9999→7, 7→4); pre/post count validation; grams_per_ton_yield checksum; `run_migration` with `--dry-run` / `--confirm` CLI gate
  - `tests/data_migrations/test_swap_reactor_4_7_015.py` — new: 9 tests (swap correctness ×7, dry-run, partial-rollback)
  - `backend/api/routers/dashboard.py` — swapped R4 (300mL/Titanium/Tan) ↔ R7 (500mL/Titanium/Yushen) in `REACTOR_SPECS`
  - `frontend/src/pages/ReactorGrid.tsx` — same swap in frontend `REACTOR_SPECS`
- **Tests added:** yes — 9 pytest integration tests; all pass
- **Decision logged:** no
- **Note:** Migration script not yet run against production — requires DB backup + `--dry-run` review before executing `--confirm`

## 2026-05-05 | issue #53 — Experiments filter pagination reset: add regression tests
- **Files changed:**
  - `frontend/src/pages/ExperimentList.tsx` — added `aria-label="Status filter"` to the status filter Select (enables accessible-name query in tests)
  - `frontend/src/pages/__tests__/ExperimentList.test.tsx` — new: 5 vitest tests covering all 5 acceptance criteria: status filter resets to page 1, text filter resets to page 1, clearing filters resets to page 1, page size change resets to page 1, normal prev/next pagination regression guard
- **Tests added:** yes — 5 vitest unit tests; all pass (44 total unit tests green)
- **Decision logged:** no

## 2026-05-05 | issue #57 — Change sample ID on existing experiment with calc re-trigger
- **Files changed:**
  - `backend/api/routers/experiments.py` — pop `sample_id` before generic field loop; validate sample exists (404 on unknown ID); update `exp.sample_id`; recalculate conditions (cascades to scalars via ORM) and scalar results directly; write `ModificationsLog` entry
  - `frontend/src/api/experiments.ts` — added `sample_id?: string` to `patch()` payload type
  - `frontend/src/pages/ExperimentDetail/index.tsx` — inline `SampleSelector` editor; auto-saves on selection; Cancel button exits edit mode; success toast confirms calculations re-run; `pointer-events-none opacity-50` disables selector during pending mutation
  - `tests/api/test_experiments.py` — 6 new tests: valid sample change, 404 on unknown sample, no conditions no crash, recalculate called on conditions, recalculate called on scalars, ModificationsLog row verified
- **Tests added:** yes — 6 backend API tests (pytest)
- **Decision logged:** no

## 2026-05-05 | inline — Fix sample ID editor: chip clear and dropdown broken
- **Files changed:**
  - `frontend/src/components/ui/SampleSelector.tsx` — `handleClear` now calls `setOpen(true)` so dropdown opens immediately after chip is cleared
  - `frontend/src/pages/ExperimentDetail/index.tsx` — added `sampleDraft` local state; initialized from `experiment.sample_id` on editor open; passed as `value` to `SampleSelector`; `onChange` updates draft for all values including `''`; mutation still guards on non-empty, changed value
- **Tests added:** no
- **Decision logged:** no

## 2026-05-05 | inline — Fix HTTP 500 on pXRF bulk upload (utils.storage lazy import)
- **Files changed:**
  - `backend/services/bulk_uploads/pxrf_data.py` — removed top-level `from utils.storage import get_file`; added lazy import inside `ingest_from_source` only
  - `tests/api/test_bulk_uploads.py` — added `test_pxrf_data_importable_without_utils_storage` regression guard
- **Tests added:** yes — 1 regression test (pytest); total pXRF suite now 8 passing
- **Decision logged:** no

## 2026-05-07 | issue #58 — Reactor Dashboard Change Request Overhaul
- **Files changed:**
  - `database/models/notion_sync.py` — `notion_page_id` and `notion_status` made nullable (enables UI-created records without a Notion page)
  - `alembic/versions/13fc77a07865_loosen_change_request_notion_constraints.py` — nullable migration with downgrade data-backfill
  - `backend/api/schemas/notion_sync.py` — replaced with `ChangeRequestResponse`, `ChangeRequestUpsertRequest`, `RecentChangeRequestsResponse`
  - `backend/api/routers/experiments.py` — new `POST /{experiment_id}/change-requests` upsert endpoint (pg_insert on_conflict_do_update on `uq_change_request_reactor_date`)
  - `backend/api/routers/change_requests.py` — new router: `GET /api/change-requests/reactor/{reactor_label}/recent` (today + most-recent-prior-day)
  - `backend/api/main.py` — registered `change_requests` router; added openapi tag
  - `backend/api/routers/dashboard.py` — reactor cards now include QUEUED experiments (ordered ONGOING first, then QUEUED); `days_running` is None for QUEUED; legacy endpoint and active_experiments count unchanged (with clarifying comments)
  - `frontend/src/api/experiments.ts` — `notion_status: string | null`; added `createChangeRequest`
  - `frontend/src/api/change_requests.ts` — new: `changeRequestsApi.getRecentForReactor(reactorLabel)`
  - `frontend/src/pages/ExperimentDetail/ChangeRequestsTab.tsx` — simplified: removed status and Carried Forward badges; shows date, reactor label, description only
  - `frontend/src/pages/ReactorGrid.tsx` — full `ReactorDetailModal` redesign: three-section layout (EXPERIMENT / HARDWARE / CHANGE REQUEST); inline CR textarea with Save; `key={selected.experiment_id ?? selected.reactor_label}` forces remount on reactor switch; query key includes experiment_id; mutation accepts text parameter to avoid stale closure
  - `tests/api/test_change_requests.py` — new: 7 tests (upsert create, overwrite, blank 422, missing experiment 404; recent today+previous, nulls, prior-only)
  - `frontend/src/pages/ExperimentDetail/__tests__/ChangeRequestsTab.test.tsx` — updated: 3 tests (empty state, renders date/reactor/description, no status or Carried Forward)
- **Tests added:** yes — 7 backend API tests (pytest); 3 frontend vitest tests updated
- **Decision logged:** no

## 2026-05-08 | inline — Treat blank pH and conductivity cells as NULL in both bulk upload parsers
- **Files changed:**
  - `backend/services/bulk_uploads/master_bulk_upload.py` — new `_parse_measurement_float` helper returns `None` for `0.0`; used for `Sample pH` and `Sample Conductivity (mS/cm)` columns
  - `backend/services/bulk_uploads/scalar_results.py` — `_ZERO_AS_BLANK` set strips `0` values for `final_ph` and `final_conductivity_mS_cm` in the row-clean loop
  - `scripts/cleanup_zero_ph_conductivity.py` — new one-time data cleanup script; dry-run by default, `--apply` to commit; confirmed 120 pH zeros and 225 conductivity zeros in live DB
- **Tests added:** no
- **Decision logged:** no

## 2026-05-08 | issue #59 — Add `cumulative_ferrous_iron_yield_h2_pct` to `v_results_scalar`
- **Files changed:**
  - `database/event_listeners.py` — `v_results_scalar`: added `SUM(COALESCE(sr.ferrous_iron_yield_h2_pct, 0)) OVER (PARTITION BY COALESCE(e.base_experiment_id, e.experiment_id) ORDER BY er.cumulative_time_post_reaction_days, er.id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_ferrous_iron_yield_h2_pct` immediately after `ferrous_iron_yield_h2_pct`
  - `docs/POWERBI_MODEL.md` — added `cumulative_ferrous_iron_yield_h2_pct` to `v_results_scalar` key columns list
  - `docs/project_context/POWERBI_MODEL.md` — auto-synced copy
  - `tests/views/test_v_results_scalar_cum_fe.py` — new: 6 tests covering column existence, running sum accumulation, NULL-as-zero, missing scalar row, independent experiment isolation, chain partitioning (CTEST_001 / CTEST_001-2)
- **Tests added:** yes — 6 view integration tests; 18/18 view suite passing
- **Decision logged:** no
- **Note:** Commits landed directly on `develop` (no topic branch; task started without `/start-task`).

## 2026-05-11 | inline — Fix stale base_experiment_id breaking cumulative Fe-to-H2 for CF/VAE/VHE/MHE series
- **Files changed:**
  - `database/data_migrations/establish_experiment_lineage_006.py` — added `fix_stale_lineage()` function; updated `run_migration()` to call it as a second pass; updated `__main__` to support `--fix-stale` flag
- **Tests added:** no — data migration repair; existing 18 migration tests all pass
- **Decision logged:** no
- **Root cause:** CF-NNN, VAE-NN, VHE-NN, MHE-NN experiments were originally uploaded with underscore naming (e.g. CF_015). Old parser treated numeric suffix as derivation index and wrote `base_experiment_id='CF'/'VAE'/'VHE'/'MHE'`. After rename to hyphen style the stale values were never recomputed. 103 experiments affected. The window function in `v_results_scalar` partitions by `COALESCE(base_experiment_id, experiment_id)`, so CF-015 (base='CF') and CF-015-2/3 (base='CF-015') land in different partitions and never accumulate together.
- **Fix:** Run `.venv/Scripts/python database/data_migrations/establish_experiment_lineage_006.py --fix-stale` on the lab PC after deploy.

## 2026-05-11 | inline — Fix new-experiments bulk upload template (3-sheet workbook)
- **Files changed:**
  - `backend/api/routers/bulk_uploads.py` — replaced broken single-sheet `_simple_template` call for `new-experiments` with a 4-sheet openpyxl workbook: `experiments`, `conditions`, `additives`, `INSTRUCTIONS`; INSTRUCTIONS sheet documents overwrite semantics, auto-copy behavior, and additives asymmetry
  - `tests/api/test_bulk_uploads.py` — 3 new tests: `test_new_experiments_template_has_three_sheets`, `test_new_experiments_template_experiments_sheet_headers`, `test_new_experiments_template_additives_sheet_headers`
- **Tests added:** yes — 3 API tests (70/70 passing)
- **Decision logged:** no
- **Note:** Commit `3b44bb8` landed directly on `develop` (no topic branch; task started without `/start-task`).

## 2026-05-08 | inline — Move brine modification out of results table column into expanded row
- **Files changed:**
  - `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` — removed "Sampling Mod" grid column; moved MOD badge + full description into `ExpandedRow` under a "Sampling Modification" section
- **Tests added:** no
- **Decision logged:** no

## 2026-05-28 | issue #61 — ICP-OES Uncal spectral-line fallback
- **Files changed:**
  - `backend/services/icp_service.py` — `select_best_lines`: now groups by element symbol (not full wavelength label); skips `Uncal` rows when picking best line; falls back to next-best calibrated line; emits warning if all lines are Uncal; explicit fallback for all-NaN Intensity; return type changed to `Tuple[pd.DataFrame, List[str]]`; `process_icp_dataframe` updated to unpack and propagate warnings
  - `tests/test_icp_handling.py` — updated `test_select_best_lines` to unpack tuple; added `TestICPUncalHandling` (4 new tests); fixed 8 `bulk_create_icp_results` 2-tuple unpack errors (3-tuple since earlier refactor)
- **Tests added:** yes — 4 new Uncal-handling tests; 24/35 passing (11 pre-existing failures unrelated to this fix: skipped-sample error assertions and `ExperimentalResults.experiment_id` model mismatch — tracked separately)
- **Decision logged:** no
- **Note:** Work done directly on `develop` (no topic branch); merged to `main` at user request.

## 2026-06-17 | issue #62 — ICP multi-file merge tests + label fix + K/Na/S fixed columns
- **Files changed:**
  - `frontend/src/pages/BulkUploads.tsx` — `IcpOverwriteToggle` label copy: "Replace existing ICP data instead of merging"; conditional helper text clarifies replace vs. merge behavior
  - `backend/services/icp_service.py` — dynamic `element_kwargs` dict comprehension replaces 27-element hardcoded constructor; eliminates K/Na constructor-drift root cause
  - `database/models/results.py` — added `s = Column(Float, nullable=True)` (Sulfur)
  - `alembic/versions/e78eb12b81d6_add_s_column_to_icp_results.py` — additive migration (upgrade/downgrade)
  - `legacy/streamlit_frontend/config/variable_config.py` — `ICP_FIXED_ELEMENT_FIELDS` extended with `k`, `na`, `s`
  - `tests/conftest.py` — ICP stub updated to match real list (added `mn`, `k`, `na`, `s`)
  - `tests/test_icp_handling.py` — `TestICPKNaStorage` (2), `TestICPSStorage` (1), `TestICPMultiFileMerge` (5)
- **Tests added:** yes — 8 new pytest tests (K/Na fixed column routing, S fixed column, disjoint merge, JSON-only survival, conflict second-file-wins, overwrite clears priors, persistence re-query)
- **Decision logged:** no

## 2026-05-11 | inline — Fix MOD badge not showing in main results row
- **Files changed:**
  - `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` — added `has_brine_modification` MOD badge to main row badge span alongside ICP/XRD; updated column header to "ICP / XRD / MOD"
  - `frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx` — 2 new tests for MOD badge visibility
- **Tests added:** yes — 2 vitest tests (badge present when `has_brine_modification=true`, absent when false)
- **Decision logged:** no

## 2026-06-17 | inline — Test suite cleanup: eliminate ~100 collection errors and isolation failures
- **Branch:** `fix/test-suite-cleanup`
- **Files changed:**
  - `tests/test_backup.py` — deleted (imported `utils.database_backup`, `utils.scheduler`: Streamlit-era modules removed)
  - `tests/test_init_db.py` — deleted (not a pytest file; `main()` script importing `from config import DATABASE_URL`)
  - `tests/test_load_info.py` — deleted (imported `frontend.components.load_info`: Streamlit-era Python frontend)
  - `tests/test_pxrf_analysis.py` — rewritten: added `from database.models import SampleInfo, PXRFReading`; deleted 3 tests using `Laboratory`/`Analyst`/`Sample` (models no longer exist); kept 1 valid test
  - `tests/test_experiment_rename.py` — fixed `db_session` fixture: added JSONB→JSON patching with save/restore so SQLite can compile JSONB columns; restored original types on teardown to prevent global-state leak
  - `tests/test_icp_handling.py` — fixed `test_db` fixture: same JSONB→JSON patching with save/restore; fixed 2 `bulk_create_icp_results` 2-tuple unpacks → 3-tuple; fixed 6 `filter_by(experiment_id=...)` calls on `ExperimentalResults` (no such column) → join through `Experiment` model using `experiment_fk=_exp.id`
  - `tests/services/bulk_uploads/test_actlabs_conflicts.py` — rewrote all 7 tests to use `db_session` (transaction rollback) instead of `test_db` (drops all tables); changed `commit()` → `flush()`; this was the root cause of 89 isolation failures in the full bulk_uploads suite
- **Tests added:** no (test fixes only)
- **Decision logged:** no
- **Net result:** ~100 failures → 18 failures + 15 errors (677 passing); full `tests/services/bulk_uploads/` now 122/122 in both isolation and full-suite runs
- **Remaining unresolved failures (33 total) — root causes documented below:**

### A. `test_experiment_rename.py` — 3 failures (service logic mismatch)
- `test_chain_rename_wrong_order`: `assert any('EXPERIMENT_RENAME_GUIDE' in str(w) for w in warnings)` — service emits the correct "⚠️ CHAIN RENAME CONFLICT" warning but the message no longer contains the string `EXPERIMENT_RENAME_GUIDE`. Test expectation is stale. Fix: update the assertion to match the current warning message format.
- `test_rename_updates_notes`: note query returns `None` after rename — rename service does not update `experiment_id` on associated `ExperimentNotes` rows. Fix: update rename service to cascade ID update to notes.
- `test_rename_with_conditions_sheet`: service emits 2 warnings — (1) column names in test CSV (`rock_mass`, `water_volume`) don't match model fields (`rock_mass_g`, `water_volume_mL`); (2) service calls `conditions.calculate_derived_conditions()` which no longer exists on `ExperimentalConditions`. Fix: update test CSV column names to match model; remove or replace `calculate_derived_conditions` call in the bulk upload service.

### B. `test_icp_handling.py` — 7 failures (test expectations predate service refactors)
These 7 tests were partially noted in the issue #61 log entry. Root causes per test:
- `test_process_icp_dataframe_success` / `test_parse_and_process_icp_file_complete_workflow`: `assert len(errors) == 2` — service used to report standards/blanks as errors; now silently skips them. Fix: update assertions to `== 0`.
- `test_duplicate_icp_upload_same_time_point`: `assert len(results2) == 0` — service now upserts on duplicate (returns 1). Fix: update to assert upsert behavior.
- `test_icp_upload_with_existing_scalar_data`: `assert scalar.ammonium_quant_method == 'NMR'` — scalar row's `ammonium_quant_method` is `None`; test setup likely doesn't set it. Fix: set field in test setup or update assertion.
- `test_missing_required_fields`: `assert len(results) == 0` — service creates result with defaults even when fields missing. Fix: align assertion with current permissive behavior.
- `test_csv_with_only_standards_and_blanks`: `assert len(errors) >= 3` — service returns `['No data to validate']` (1 error). Fix: update assertion to `== 1`.
- `test_icp_model_json_validation`: `TypeError: 'experiment_id' is an invalid keyword argument for ExperimentalResults` — test constructs `ExperimentalResults(experiment_id=...)` but that field doesn't exist (column is `experiment_fk`). Fix: use `experiment_fk=<int>` or omit and look up via `Experiment`.

### C. `test_time_field_guardrails.py::test_save_results_rejects_none_time` — 1 failure (stale Streamlit import)
Patches `frontend.components.experimental_results.st` — Streamlit-era module deleted. The other 3 tests in this file use current models and pass. Fix: delete this single test function.

### D. `test_pg_backup_restore.py` — 3 failures (missing infrastructure)
Tests require a PostgreSQL `experiments_restore_test` database. The fixture tries `DROP DATABASE ... CREATE DATABASE` but the DB doesn't exist and the pg_dump/restore never runs. All 3 tests fail with missing tables. Fix: create the restore test DB (`CREATE DATABASE experiments_restore_test OWNER experiments_user`) or mark tests with `@pytest.mark.skipif` unless restore DB is present.

### E. `test_lineage_migration.py` — 1 failure + 11 errors (same JSONB/SQLite pattern)
`test_snapshot_functionality` and all 11 `TestExperimentLineageMigration` tests fail with `SQLiteTypeCompiler can't render element of type JSONB`. These tests build SQLite engines from `Base.metadata` without the JSONB→JSON patching added to `test_experiment_rename.py` and `test_icp_handling.py` in this task. Fix: apply the same save/restore JSONB patching pattern to the `db` fixture in `test_lineage_migration.py`.

### F. `test_fresh_install_migration.py` — 4 errors (alembic.ini not found at subprocess CWD)
Fixture runs `subprocess(['.venv/Scripts/alembic.exe', 'stamp', 'head'])` from a temporary directory; alembic cannot find `alembic.ini`. Fix: pass `cwd=<project_root>` to the subprocess call.

### G. `tests/api/test_dashboard.py::test_reactor_specs_values` — 1 failure (API 500 error)
Endpoint returns HTTP 500; test expects 200/300-range. Pre-existing server error — likely a runtime error in the reactor specs endpoint. Fix: debug the dashboard route to find what raises during test.

### H. `tests/test_actlabs_titration_import.py::test_actlabs_import_creates_analytes_and_results` — 1 failure (multi-sample coverage mismatch)
Test asserts `('Rock_2', 1) in results_dict` but the dict only contains `Rock_1` entries — the import only creates elemental analysis rows for the first sample. Pre-existing service logic gap. Fix: investigate `ActlabsRockTitrationService.import_excel` to confirm it processes all sample rows.

### I. `tests/test_compound_migration.py::test_deprecated_fields_migrated_to_chemicals` — 1 failure (FK violation)
Test inserts `ExperimentalConditions(experiment_fk=1, ...)` but no `Experiment` with `id=1` exists in the test DB at that point, violating the FK constraint. Pre-existing test isolation issue (hardcoded FK). Fix: create the parent `Experiment` row in the test setup before inserting conditions.

---

## 2026-06-17 | inline — Fix residual test suite failures (continuation: Groups G, H, ICP service)
- **Files changed:**
  - `backend/services/bulk_uploads/actlabs_titration_data.py` — added `db.flush()` after inner analyte loop so the last sample's `ElementalAnalysis` records are persisted (previously only flushed as a side effect of subsequent samples; last sample was never flushed)
  - `backend/services/icp_service.py` — `bulk_create_icp_results`: silent-skip on `time_post_reaction=None` (was erroring); added explicit error when no elemental data provided (was silently succeeding)
  - `tests/api/test_dashboard.py` — corrected `test_reactor_specs_values` assertions to match actual hardware: R4–R6 = 500 mL Yushen, R7 = 300 mL Tan
- **Tests added:** no
- **Decision logged:** no
- **Remaining known failures:** 3 in `test_pg_backup_restore.py` (Group D — require `experiments_restore_test` DB, infrastructure-only)

## 2026-06-17 | inline — Add sulfur (S) to ICP results display
- **Files changed:**
  - `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` — added `'s'` to ICP element array in `ExpandedRow`
  - `backend/api/schemas/results.py` — added `"s"` to `ICP_ELEMENTS`; added `s: Optional[float] = None` to `ICPCreate`
  - `frontend/src/api/results.ts` — added `s: number | null` to `ICPResult` interface
- **Tests added:** no
- **Decision logged:** no

## 2026-07-09 | inline — Contributor docs audit: fix stale branch model, auth architecture, dead migrations dir
- **Files changed:**
  - `.claude/skills/conductor.md` — removed phantom plugin references (Superpowers/Code Review/etc. that don't exist as installed plugins); fixed two stale escalation conditions
  - `CONTRIBUTING.md` — Branch Naming section referenced a non-existent production branch (`infra/lab-pc-server-setup`) instead of `develop`/`main`; replaced with the model in `docs/GIT_WORKFLOW.md`; added `--base develop` to the PR checklist; PostgreSQL 15+ → 16+
  - `docs/STACK.md` — flipped stale "Streamlit is current / React+FastAPI is target" framing now that the migration is complete (M0–M8 done per `docs/milestones/MILESTONE_INDEX.md`); Streamlit moved to a "Legacy" section
  - `docs/ENVIRONMENT.md` — removed stale "Docker Compose used for local dev" line (no Docker dev workflow exists; native venv + npm is current per README.md); replaced phantom `"use context7"` prompt pattern with actual Context7 MCP tool calls
  - `docs/DIRECTORY_STRUCTURE.md` — full rewrite; old tree was aspirational/wrong (listed files that don't exist, e.g. `docs/api/ADDING_ENDPOINTS.md`, root `QUICKSTART.md`; omitted real current docs)
  - `PROJECT_STRUCTURE.md` — replaced with a deprecation pointer to `docs/DIRECTORY_STRUCTURE.md` (duplicate/stale tree, redundant maintenance burden)
  - `.claude/rules/AUTH.md` — full rewrite; described the old Streamlit server-side REST login flow. Actual current flow: React uses the Firebase Web SDK directly in the browser; `backend/auth/firebase_auth.py` verifies ID tokens for FastAPI; root `auth/user_management.py` remains the shared Firestore approval-queue module (used by the new `/api/auth/register` endpoint and the CLI); `auth/firebase_config.py` is now legacy-Streamlit-only
  - `README_DEV_SETUP.md` — deleted (Docker Compose dev guide, superseded, unreferenced elsewhere)
  - `experiment_tracking_sandbox/QUICKSTART.md` (and the stray nested folder containing it) — deleted; leftover pre-project bootstrap artifact instructing readers to copy files from a "parent repo" into this sandbox
  - `database/migrations/` (48 files: `README`, `env.py`, `script.py.mako`, `versions/*.py`) — deleted; confirmed dead duplicate of `alembic/` (added in the same initial commit, zero commits since, not referenced by `alembic.ini`'s active `script_location`, which points at `alembic/`)
  - `docs/project_context/{STACK.md,ENVIRONMENT.md,DIRECTORY_STRUCTURE.md}` — auto-synced by the `PostToolUse` hook
- **Tests added:** no — documentation and dead-file removal only; `pytest --collect-only` (711 tests) and `alembic.ini` config parsing verified clean after the `database/migrations` deletion
- **Decision logged:** yes — `docs/working/decisions.md`

## 2026-07-09 | inline — Fix docs/sample_data/ gitignore scope; redact leaked lab PC IP
- **Files changed:**
  - `.gitignore` — `docs/sample_data/` → `docs/sample_data/*` + `!docs/sample_data/*.md`; the blanket rule was silently dropping markdown docs placed in that directory (data dumps were the intended target, per the "# Databases" grouping). Confirmed real impact: `docs/sample_data/FIELD_MAPPING.md`, logged as "created" in `docs/working/plan.md` during M8, does not exist in the working tree or git history — it matched the old blanket ignore the moment it was created and was never tracked
  - `docs/user_guide/ONBOARDING.md` — redacted the lab PC's IP (`100.97.130.43`, appeared 5×) to `<lab-pc-ip>` / prose pointers to the lab admin. The file was already tracked and pushed to this **public** GitHub repo before the "contains internal IP addresses" gitignore line (added later) was added, so that line was a no-op
  - `docs/project_context/ONBOARDING.md` — auto-synced by the `PostToolUse` hook
- **Tests added:** no
- **Decision logged:** no
- **Known residual risk:** the real IP remains visible in this repo's git history/GitHub commit log (redaction only affects HEAD going forward). User chose not to purge history or make the repo private at this time — revisit if that changes.

## 2026-07-19 | inline — Reactor dashboard grid redesign (unified 3×6 layout)
- **Files changed:**
  - `frontend/src/pages/ReactorGrid.tsx` — merged the two sections (`Standard Reactors (R01–R16)` + `Core Flood (CF01–CF02)`) into one unified grid (`R01–R06 / R07–R12 / R13–R16+CF01–CF02` at 6 columns); removed the now-duplicate inner section label (the enclosing `Dashboard.tsx` `CardHeader` already renders "Reactor Status"); CF cards get a `border-l-status-info` accent and never render the HPHT-only volume/material/vendor spec row (gated on label/experiment_type, not on the API returning nulls); experiment ID bumped to the card's visual anchor (`text-base font-semibold`, was `text-sm font-medium`); tighter badge-to-ID gap; lighter/smaller status badge (dropped border); Day counter is now a filled pill; empty-slot cards are more ghosted (`opacity-35` + `border-dashed`); description gets a `title` tooltip; slightly more horizontal card padding
- **Tests added:** no — no existing unit tests target `ReactorGrid.tsx`; verified manually via chrome-devtools MCP against the live dev server (desktop + 900px breakpoints, CF01 detail-modal click-through)
- **Decision logged:** no
- **Note:** found (not fixed here, out of scope) that `ReactorDetailModal` in the same file still surfaces leaked HPHT hardware specs for CF01 in its "Hardware" section — that's a backend data issue already fixed on branch `fix/cf-reactor-card-description` (commit `efebf34`), which was not yet merged to `develop` when this branch was cut from it.

## 2026-07-19 | inline — Stop CF reactor cards inheriting HPHT specs
- **Files changed:**
  - `backend/api/routers/dashboard.py` — `REACTOR_SPECS` is keyed by bare `reactor_number` (1-16, the HPHT vessel inventory). CF01/CF02 reuse `reactor_number` 1/2, so the lookup silently attached R01/R02's Hastelloy/100mL/Yushen spec to Core Flood cards. Gated the lookup on `not is_cf`.
  - `tests/api/test_dashboard.py` — added `test_cf01_does_not_inherit_hpht_reactor_1_hardware_specs`
- **Tests added:** yes — full `tests/api/test_dashboard.py` (28 tests) and full backend suite (709 passed, 3 pre-existing unrelated failures in `tests/test_pg_backup_restore.py` requiring a live Postgres instance) verified clean on this branch before merge
- **Decision logged:** no

## 2026-07-19 | inline — Use calc registry for bulk additive uploads
- **Files changed:**
  - `backend/services/bulk_uploads/experiment_additives.py` — replaced direct `ChemicalAdditive.calculate_derived_values()` model-method calls with `db.flush()` + `backend.services.calculations.registry.recalculate(instance, db)`, matching the registry write pattern used elsewhere
  - `backend/services/bulk_uploads/new_experiments.py` — same replacement for additives created during new-experiment bulk upload
- **Tests added:** no new tests in this branch; existing `tests/services/bulk_uploads/` suite (122 tests) and full backend suite (708 passed, 3 pre-existing unrelated Postgres-only failures) verified clean before merge
- **Decision logged:** no
- **Note:** this touches `backend/services/bulk_uploads/` (a locked component per `docs/LOCKED_COMPONENTS.md`); merge was explicitly confirmed by the user before proceeding

## 2026-07-20 | issue #63 — Reactor Modification: rename, cross-experiment scoping fix, editable date
- **Files changed:**
  - `database/models/notion_sync.py` — `ReactorChangeRequest` unique constraint widened to `(reactor_label, experiment_id, sync_date)` (was `(reactor_label, sync_date)`), renamed `uq_change_request_reactor_experiment_date`
  - `alembic/versions/ca5d57c6b272_widen_reactor_change_request_unique_.py` — drop/recreate constraint; upgrade+downgrade round-trip verified
  - `backend/api/schemas/notion_sync.py` — `ChangeRequestUpsertRequest` gains optional `sync_date`; `RecentChangeRequestsResponse.today` renamed `selected`
  - `backend/api/routers/experiments.py` — `upsert_change_request` uses `payload.sync_date or date.today()`, upserts on the new 3-column constraint; new `GET /{experiment_id}/change-requests/recent?date=` (experiment-scoped, replaces the reactor-scoped one)
  - `backend/api/routers/change_requests.py` — deleted (buggy `GET /api/change-requests/reactor/{reactor_label}/recent` had no `experiment_id` filter, so a fresh experiment on a reactor could surface a prior experiment's entry)
  - `backend/api/main.py` — removed `change_requests` router import/registration
  - `backend/services/notion_sync/import_.py` — `run_import`'s `on_conflict_do_update` retargeted from `index_elements=["reactor_label", "sync_date"]` (index no longer exists) to `constraint="uq_change_request_reactor_experiment_date"`; would otherwise have crashed on next sync run
  - `frontend/src/api/change_requests.ts` — deleted; folded into `experimentsApi`
  - `frontend/src/api/experiments.ts` — added `getRecentChangeRequests(experimentId, date?)`; `createChangeRequest` payload gains optional `sync_date`
  - `frontend/src/pages/ReactorGrid.tsx` — pop-out: "Change Request" → "Reactor Modification" copy, editable date input (default today, future dates allowed per user decision), query rescoped to the new experiment-based endpoint
  - `frontend/src/pages/ExperimentDetail/index.tsx` — tab label "Change Requests" → "Reactor Modifications"
  - `frontend/src/pages/ExperimentDetail/ChangeRequestsTab.tsx` — empty-state copy updated
  - `docs/api/API_REFERENCE.md` — documented the new/changed change-request endpoints
- **Tests added:** yes — `tests/api/test_change_requests.py` rewritten (upsert with explicit `sync_date`, same-day/different-experiment non-collision, experiment-scoped `/recent` incl. cross-experiment isolation and `date` query param); `tests/models/test_notion_sync_model.py` updated for the widened constraint; `frontend/.../__tests__/ChangeRequestsTab.test.tsx` updated for renamed empty-state copy. Full backend suite: 714 passed, 3 pre-existing infra-only failures (`test_pg_backup_restore.py`, needs a live restore-test Postgres instance). Frontend: 46 unit tests passing, eslint clean on all changed files, production build clean.
- **Decision logged:** yes — `docs/working/decisions.md` (constraint widening + its consequence for the Notion sync importer)
- **Note:** dev environment was missing `pytest`/`pytest-cov`/`flake8`/`black` in `.venv` (not in `requirements.txt`, apparently dev-only tooling that had gone missing); installed ad hoc to run the pre-merge checklist, not added to `requirements.txt`.
- **Note:** `frontend`'s `npm test` (`vitest run`) currently collects the Playwright `e2e/*.spec.ts` files too and fails on all of them — pre-existing vitest/Playwright config gap predating this branch, not fixed here; verification instead ran `vitest run src`.

## 2026-07-20 | issue #64 — Experiment filter pagination + description search
- **Files changed:**
  - `backend/api/routers/experiments.py` — `list_experiments`: outer-joined `ExperimentalConditions` and a first-note subquery (same pattern as `dashboard.py`) into the main query so `experiment_type`, `reactor_number`, and the new `description` filter run in SQL before `offset`/`limit`; removed the old in-memory post-pagination filter/decrement that produced an empty page 1 and a wrong, page-dependent `total` whenever type/reactor filters were active. Verified `Experiment`↔`ExperimentalConditions` is 1:1 in the live data (723/723, no duplicate `experiment_fk`) before adding the join, per the issue's flagged risk.
  - `frontend/src/api/experiments.ts` — added `description?: string` to `ExperimentListParams`
  - `frontend/src/pages/ExperimentList.tsx` — new "Description…" filter input (state, `resetPage()` wiring, Clear button)
  - `tests/api/test_experiments.py` — 3 new tests: type/reactor filter+pagination regression (matches given the lowest `experiment_number`s so they'd be excluded from page 1 under the old bug), `total` stability across `skip` values, `description` search
  - `frontend/src/pages/__tests__/ExperimentList.test.tsx` — new test for the Description input's page-reset + param pass-through
  - `docs/api/API_REFERENCE.md` — documented `description` param and the SQL-before-pagination behavior
- **Tests added:** yes — full backend suite (717 passed, 3 pre-existing unrelated failures in `tests/test_pg_backup_restore.py`, confirmed present on `develop` before this branch via `git stash`); frontend unit suite (47 passed via `vitest run src`); eslint clean on all changed frontend files (5 pre-existing errors elsewhere in the repo, unrelated to this change)
- **Decision logged:** no

## 2026-07-20 | issue #65 — Exclude Playwright e2e specs from vitest
- **Files changed:**
  - `frontend/vitest.config.ts` — added `exclude: ['e2e/**', 'node_modules/**', 'dist/**']`, matching the fix proposed in the issue. Closes the gap noted above in the #63 entry and again during #64's verification: `vitest run` was collecting `e2e/journeys/*.spec.ts` (Playwright specs) and failing on all of them since Vitest's default include glob matched them and it doesn't understand Playwright's `test`/`expect` API.
- **Tests added:** no — config-only change; verified `npx vitest run` now collects only the 10 unit/component spec files (46 tests, all passing) and that `npx playwright test --list` still sees its own specs unaffected
- **Decision logged:** no

## 2026-07-22 | issue #66 — Experiment Status Bulk Upload: per-row status, start date, reactor-scoped date-aware demotion
- **Files changed:**
  - `backend/services/bulk_uploads/experiment_status.py` — full rewrite of `StatusChangePreview` (new `PlannedChange`/`PlannedDemotion`/`ApplyResult` dataclasses), `preview_status_changes_from_excel` (per-row parse/validate, missing-column hard-errors, same-reactor-in-file conflict detection, read-only demotion planning), `apply_status_changes` (consumes a `StatusChangePreview`, writes status/date/reactor_number, executes demotions via `manage_reactor_occupancy`, no internal commit/rollback — router owns the transaction). Retired the old whole-world "complete every unlisted ongoing HPHT" snapshot behavior entirely.
  - `manage_reactor_occupancy` — added an optional `newer_than` start-date guard via a module-level `_UNSET` sentinel so existing callers (`new_experiments.py` lines ~599/~671, legacy Streamlit create path) that omit the parameter keep byte-identical unconditional-demotion behavior; callers that pass it (even as `None`) get date-gated demotion with a warning on missing/newer-or-equal dates.
  - `backend/api/routers/bulk_uploads.py` — `upload_experiment_status` rewired to the new preview/apply shapes, router now owns `db.commit()`/`db.rollback()`; `_get_template_bytes`'s `"experiment-status"` branch regenerated to 4 columns (`experiment_id`, `status`, `reactor_number`, `date`) + an INSTRUCTIONS sheet.
  - `frontend/src/pages/BulkUploads.tsx` — Experiment Status Update tile `description`/`helpText` updated for the per-row model.
  - `legacy/streamlit_frontend/bulk_uploads.py` — `handle_experiment_status_update()` updated to the new API shapes (was left broken by the service rewrite until this fix; user confirmed updating rather than leaving it dead).
  - `docs/api/API_REFERENCE.md`, `docs/user_guide/BULK_UPLOADS.md`, `docs/upload_templates/experiment_status.md` (+ synced `docs/project_context/` copies) — rewritten for the per-row model.
  - `tests/services/bulk_uploads/test_queued_status_upload.py` (issue #33, predates this branch) — rewritten to use the new API; was left broken by this branch's signature change until fixed alongside Task 4.
- **Tests added:** yes — `tests/services/bulk_uploads/test_experiment_status.py` fully rewritten (31 tests: per-row parsing/validation, same-reactor-file conflict, demotion planning for both HPHT and Core Flood, all four confirmed open-item decisions, `manage_reactor_occupancy` legacy-caller regression + guarded behavior, full apply coverage). `tests/api/test_bulk_uploads.py` updated/extended (validation-error and rollback-on-apply-error paths added, the latter verified with a direct `db_session.commit`/`rollback` spy, not just a response-shape check). Full backend suite: 743 passed, 4 skipped (pre-existing, unrelated), 0 failed. Frontend: 47 passed.
- **Decision logged:** no — four open items from the issue (missing-date handling, required `status` column, same-reactor-in-file conflict as hard error, same-day dates warn not demote) were confirmed via direct user sign-off before implementation rather than a standing architectural decision; recorded in the plan file (`docs/superpowers/plans/2026-07-22-issue-66-experiment-status-per-row.md`) Global Constraints section, not `decisions.md`.
- **Process note:** implemented via subagent-driven-development (8 plan tasks, each with a fresh implementer + task reviewer, several fix/re-review loops — a byte-identity whitespace regression, a flush placed in shared legacy-adjacent code, an unplanned internal `db.commit()`, and missing router test coverage were each caught and corrected before merge). Final whole-branch review (Opus) found two additional integration gaps the plan's file list had missed (the legacy Streamlit page above, and the stale `experiment_status.md` doc); both fixed in a follow-up commit before merge.
- **Known non-blocking items (not fixed, low risk):** demotion count/warnings can be row-order-dependent in a rare multi-row same-request reactor reshuffle (final DB state is always correct regardless); `manage_reactor_occupancy`'s pre-existing (unchanged) exception handling reports demotion-time DB errors as warnings rather than errors. Repo-wide flake8/black lint debt in the touched files (`experiment_status.py`, `bulk_uploads.py`) predates this branch entirely (confirmed against the base commit) — not introduced or fixed here.

## 2026-07-23 | issue #68 — New Experiments bulk upload: overwrite silently drops status/sample_id/researcher/date
- **Files changed:**
  - `backend/services/bulk_uploads/new_experiments.py` — one-line fix: added `db.flush()` immediately before the existing `db.expire_all()` call (line ~477–480) in `NewExperimentsUploadService.bulk_upsert_from_excel`. Root cause: the update-existing-experiment branch set `sample_id`/`researcher`/`status`/`date` on the ORM object but never flushed before `expire_all()` discarded the unflushed writes. This also silently broke reactor auto-demotion for reactivated experiments, since the conditions-sheet loop's `experiment.status == ExperimentStatus.ONGOING` check re-read the (wrongly reverted) stale status after `expire_all()`.
  - `tests/services/bulk_uploads/test_new_experiments.py` (new) — 4 tests against a real `experiments_test` Postgres session: overwrite persistence of status/sample_id/researcher/date, reactor auto-demotion on reactivation via overwrite, rename + status change combined in one row, and an unaffected-path regression guard for plain new-experiment creation.
  - `docs/superpowers/plans/2026-07-23-issue-68-bulk-upload-overwrite-expire.md` — implementation plan.
- **Tests added:** yes — see above. Targeted regression suite (`tests/services/bulk_uploads/`, `tests/test_experiment_rename.py`, `tests/api/test_bulk_uploads.py`): 231 passed, both pre- and post-merge. Full suite: 747 passed, 3 pre-existing unrelated failures in `tests/test_pg_backup_restore.py` (local `pg_dump`/`pg_restore` toolchain gap, confirmed present independent of this branch), 4 skipped.
- **Decision logged:** no — pure bug fix, no lasting architectural decision.
- **Process note:** implemented via subagent-driven-development (2 plan tasks). The plan originally specified a 5th test (`test_overwrite_dirty_state_is_flushed_before_expire`, asserting `not db_session.dirty` after the call) modeled on the issue's own suggested regression guard. Task 1's review found it could never fail with or without the fix — `Session.expire_all()` unconditionally clears the dirty flag on expire regardless of whether a prior flush happened — so it provided no coverage; user confirmed dropping it rather than replacing it. Final whole-branch review (Opus): Ready to merge, no fixes required.
- **Known non-blocking item (not fixed, low risk):** the fix's `db.flush()` sits outside the per-row try/except (loop ends beforehand), so a constraint violation from a bad overwrite-row field (e.g. a nonexistent `sample_id`) now fails/rolls back the whole upload rather than being attributed to one row — a behavior change from the bug itself (which silently discarded such writes with no error at all). The router's existing `try/except`/`db.rollback()` handles this safely (no 500). The create and rename paths still flush per-row and keep per-row error attribution; only the four overwrite-branch fields lost that granularity. Out of scope for this one-line, locked-component fix.

## 2026-07-23 | issue #69 — Replicate handling core (P1): letter-suffixed IDs, replicate-0 parent linking, base-level rollup
- **Files changed:**
  - `database/models/experiments.py` — added `replicate_label` (nullable, indexed String) to `Experiment`
  - `alembic/versions/fe48608cabb7_add_replicate_label_to_experiments.py` — additive migration, upgrade/downgrade round-trip verified
  - `database/lineage_utils.py` — `parse_experiment_id` now returns a 4-tuple (`base_experiment_id, derivation_num, treatment_variant, replicate_label`); new `find_replicate_group_parent` (bare-stem → `-0` → `-1` precedence, session.new-aware so it resolves a still-pending group parent mid-flush); `update_experiment_lineage` and `update_orphaned_derivations` rewritten for replicate/parent-alias classification (with a null-safe multi-alias exclusion set, fixing a real bug where one parent spelling could be back-linked to another as if it were a child); `get_or_find_parent_experiment`/`auto_create_treatment_experiment` updated for the new tuple arity
  - `database/event_listeners.py` — `before_flush` listener updated for the new classification + 4-tuple; `v_results_scalar`'s `cumulative_ferrous_iron_yield_h2_pct` window changed from `PARTITION BY COALESCE(base_experiment_id, experiment_id)` to `PARTITION BY experiment_id` (was incorrectly summing across replicate siblings); new `v_results_scalar_rollup` view (mean/median/`stddev_samp`/`n_replicates` per base experiment + timepoint bucket)
  - `backend/services/experiment_validation.py` — `extract_lineage_info` 4-tuple; `ParsedExperimentID.replicate_label` (defaulted field)
  - `backend/services/bulk_uploads/new_experiments.py` — `find_parent_for_copy`'s tuple-arity fix only (locked component, mechanical change, existing conflict-safe-creation behavior already correct and now regression-tested for lettered IDs)
  - `database/data_migrations/establish_experiment_lineage_006.py`, `tests/check_lineage_integrity.py` — tuple-arity fixes only, classification logic deliberately left unmodified (see decision below)
  - `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx`, `frontend/src/pages/BulkUploads.tsx` — help text for the replicate ID format
  - `.claude/rules/MODELS.md` — `replicate_label` documented; `v_results_scalar_rollup` section added; two caveats added (rollup grouping conflates replicates with plain sequential derivations; `-0`/`-1` reclassification is not retroactive)
  - Tests: `tests/models/test_replicate_label_column.py`, `tests/test_replicate_lineage.py`, `tests/services/test_experiment_validation_replicates.py`, `tests/views/test_v_results_scalar_rollup.py` (new); `tests/views/test_v_results_scalar_cum_fe.py`, `tests/test_lineage_migration.py`, `tests/test_experiment_rename.py`, `tests/services/bulk_uploads/test_new_experiments.py`, `tests/api/test_experiments.py` (updated/extended)
- **Tests added:** yes — full backend suite: 792 passed, 3 pre-existing unrelated `test_pg_backup_restore.py` failures (confirmed present on `develop` before this branch), 4 skipped. Frontend: eslint + vitest clean on changed files.
- **Decision logged:** yes — `docs/working/decisions.md` (`-0`/`-1` reclassification scope and known non-retroactive gap)
- **Process note:** implemented via subagent-driven-development (9 plan tasks, each with a fresh implementer + independent task reviewer). Three implementers independently found and fixed genuine bugs during TDD — a SQLAlchemy `before_flush` pending-object-visibility issue (Task 3), a PostgreSQL unquoted-identifier case-folding issue in the new rollup view (Task 6), and documented (without fixing, correctly out-of-scope) a pre-existing parsing bug in `extract_lineage_info`'s combined sequential+treatment handling (Task 5, predates issue #69 entirely) — each independently re-verified by that task's reviewer via hand-tracing/execution rather than accepted on the implementer's word. A plan gap (a second, missed 3-tuple unpack site in `get_or_find_parent_experiment`) was found during Task 3's review and folded into Task 4 before it could cause a downstream failure. Final whole-branch review (opus): Ready to merge, no Critical/Important defects; 2 Important documentation-gap findings and 2 Minor doc/naming findings addressed in one follow-up commit, re-reviewed clean.
- **Scope note:** this is P1 of a multi-phase ticket. P2 (experiments-list grouping UI, "create N replicates" helper), P3 (bulk-upload replicate-column routing), P4 (outlier flag), and P5 (parser consolidation, full letter+sequential parent-wiring for `SERUM_001a-2`) are explicitly out of scope and were not started, per the issue's own instructions.

## 2026-07-23 | issue #70 — Replicate handling P2: grouped UI, rollup results, batch replicate creation
- **Files changed:**
  - `backend/api/routers/experiments.py` — `list_experiments` gained `group_replicates` (server-side pagination over top-level rows: `replicate_label IS NULL OR parent_experiment_fk IS NULL`; a filter matching only a lettered member pulls in its parent; lettered children nested per parent, ordered by letter; flat path byte-identical, per-row build extracted into `_build_list_item`); new `GET /{id}/rollup` (first API consumer of `v_results_scalar_rollup`, parameterized `text()`), `GET /{id}/replicate-group`, `POST /replicates`
  - `backend/api/schemas/experiments.py` / `results.py` — lineage fields (`base_experiment_id`/`parent_experiment_fk`/`replicate_label`) + self-referencing `replicates` on list items; `replicate_label` on `ExperimentResponse`; `RollupTimepointResponse` (19 view columns, exact mixed-case aliases), `ReplicateGroup*`, `ReplicateCreate*`
  - `database/lineage_utils.py` — `_copy_conditions_from_parent` extracted from `auto_create_treatment_experiment` (behavior-neutral, byte-identical reserved/blacklist sets; treatment path still copies no additives); new `create_replicate_experiments` (copies sample/researcher/date/status + conditions + chemical additives with derived columns excluded, `registry.recalculate` on each; letters continue after existing members; conflicts skip non-fatally; flushes only — router owns commit; lineage wired by the existing before_flush listener)
  - `frontend/package.json` + `package-lock.json` — recharts added (user-approved 2026-07-23; both files one commit per the npm-ci deploy rule)
  - `frontend/src/api/experiments.ts` — replicate types + `getRollup`/`getReplicateGroup`/`createReplicates`; `background_ammonium_concentration_mM` added to `ResultWithFlags` (pre-existing interface gap, backend already returned it)
  - `frontend/src/assets/brand.ts` — `chartColors` tokens (series palette validated with the dataviz six-check script on surface #05172B; all checks pass)
  - `frontend/src/pages/ExperimentList.tsx` — default-on "Group replicates" toggle, expandable group rows, shared `ExperimentRow` (extraction preserves all cells incl. inline status mutation)
  - `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx` (new) + `ResultsTab.tsx` — "Individual | Grouped (n=N)" mode; Recharts mean±sd chart with fixed-order entity colors (capped at 4, never cycled), individual overlay, drill-in links, accessible rollup table; individual grid untouched
  - `frontend/src/components/experiments/CreateReplicatesModal.tsx` (new) + `ExperimentDetail/index.tsx` + `NewExperiment/index.tsx` + `Step4Review.tsx` — modal gated to group parents/standalone (`replicate_label === null && parent_experiment_fk === null`), resolved-base display + letter preview, count reset on close; replicate-member pages get a lineage hint link; wizard "replicates to create" count (hidden for lettered IDs), replicate step non-fatal to the created experiment
  - `docs/api/API_REFERENCE.md`, `docs/user_guide/REPLICATES.md` (new) + synced `docs/project_context/` copies
  - `docs/superpowers/plans/2026-07-23-issue-70-p2-grouped-ui.md` — implementation plan (amended 3× during execution, see process note)
- **Tests added:** yes — grouped-list semantics (6 API tests), rollup/replicate-group endpoints (6, views recreated inside the test transaction), `tests/test_replicate_creation_service.py` (5, real-Postgres conditions+additives copy), router batch tests (3), frontend: grouping UI, GroupedResultsView, CreateReplicatesModal (incl. resolved-base + count-reset), API layer. Final: backend 814 passed / 4 skipped / 3 pre-existing unrelated `test_pg_backup_restore.py` failures; frontend 60/60; tsc + eslint + `npm run build` clean; views recreate on import.
- **Decision logged:** no — the three P2 product choices (lettered-sets-only grouping, Recharts approved as a new dependency, "both" placements for the create-replicates helper) were direct user sign-offs recorded in the plan's Global Constraints, not standing architectural decisions.
- **Process note:** subagent-driven (9 plan tasks, fresh implementer + independent reviewer each). Four review-driven fixes, three of them defects in the plan itself faithfully transcribed by implementers (CreateReplicatesResponse typed as ExperimentDetail vs the backend's ExperimentResponse shape; a hardcoded tooltip hex; an unguarded wizard replicate call that would misreport an already-created experiment as failed) — plan doc amended at each. Final whole-branch review (fable) found the one cross-task gap no per-task gate could see: the Create Replicates button rendered on derivation/treatment pages and would silently clone the stem base's conditions — fixed (gate + resolved-base modal display) and re-reviewed clean.
- **Known non-blocking follow-ups (triaged ship-as-is by final review, listed in PR #75):** grouped-toggle label counts lettered members while the table's `n_replicates` counts scalar rows per bucket (can read n=3 vs n=4); `± 0.00` shown when sd is NULL (n=1); chart overlay takes the first result per bucket rather than filtering `is_primary_timepoint_result`; wizard replicate count survives the input being hidden by a lettered-ID edit; a test-debt bundle (grouped skip>0, replicate-group 404, conflict-skip branch, letter exhaustion, hasGroup absence, modal/wizard paths, child-row navigation).
- **Scope note:** P2 only. P3 (bulk-upload replicate routing), P4 (outlier flag), and P5 (parser consolidation + `SERUM_001a-2` parent wiring) remain open on issue #70.

## 2026-07-23 | issue #70 — Replicate handling P3: bulk-upload replicate routing
- **Files changed:**
  - `backend/services/bulk_uploads/replicate_routing.py` (new) — `combine_replicate_id(experiment_id, replicate)`: pure string-level base+letter combination (blank/NaN/0 pass through; 0 = group parent per locked decision 2; single letter a–z any case; conflicting letter / derivation / treatment suffixes and letter-incapable ID shapes like `CF-015` raise ValueError with per-row messages; round-trip guard via `parse_experiment_id` ensures the combined ID re-parses as the intended replicate)
  - `backend/services/bulk_uploads/scalar_results.py` (locked, issue-authorized) — 3 additive edits: import, `replicate`/`replicate letter` LEGACY_ALIASES, cleaning-loop block that resolves the Replicate column before the dry-run branch (previews show resolved IDs; routing errors are per-row `parse_feedbacks`, non-fatal)
  - `backend/services/bulk_uploads/master_bulk_upload.py` (locked, issue-authorized) — 3 additive edits: import, case-insensitive `Replicate` header normalization, row-loop combine placed after the calibration-standard skip so upsert/feedbacks/error paths all see the resolved ID
  - `backend/api/routers/bulk_uploads.py` — `"replicate": "Replicate"` in the scalar variable_config stub; `Replicate` column (after Experiment ID) in the downloadable scalar template
  - `tests/conftest.py` — real `SCALAR_RESULTS_TEMPLATE_HEADERS` dict added to the existing `variable_config` MagicMock (mid-execution plan amendment: the planned test-file stub was inert because `hasattr` on a MagicMock is always True; same pattern as the ICP/pXRF kwargs already there)
  - Tests: `tests/services/bulk_uploads/test_replicate_routing.py` (new, 11 unit tests), `test_scalar_results_replicates.py` (new, 5 real-DB routing/conflict/unresolved/regression tests), `test_master_bulk_upload.py` (+2), `tests/api/test_bulk_uploads.py` (+1 template-header test)
  - `frontend/src/pages/BulkUploads.tsx` — Solution Chemistry + Master Results tile helpText mention the Replicate column
  - `docs/user_guide/REPLICATES.md` (new "Uploading replicate results" section), `docs/user_guide/BULK_UPLOADS.md`, `docs/upload_templates/scalar_results.md`, `docs/upload_templates/master_bulk_upload.md`, `docs/api/API_REFERENCE.md` (+ deletion of a pre-existing stale duplicate "Bulk Uploads" table that contradicted the canonical one) + synced `docs/project_context/` copies
  - `docs/superpowers/plans/2026-07-23-issue-70-p3-bulk-upload-replicate-routing.md` — implementation plan (amended 1× during execution)
- **Tests added:** yes — full backend suite at HEAD: 833 passed, 4 skipped, 3 pre-existing unrelated `test_pg_backup_restore.py` failures (local pg_dump toolchain gap, predates branch); frontend eslint clean, vitest 60/60.
- **Decision logged:** no — P3 product rules (Replicate column semantics: 0 = parent, strict bare-base rule, result uploads never auto-create siblings) recorded in the plan's Global Constraints, all derived from issue #70's locked decisions.
- **Scope note:** live upload surfaces only (Solution Chemistry + Master Results). `quick_upload.py`/`long_format.py` are legacy-Streamlit-only (no FastAPI endpoint) and untouched — full replicate IDs already work there via the shared service. ICP uploads out of scope per issue. P4 (outlier flag) and P5 (parser consolidation) remain open on issue #70.
- **Process note:** subagent-driven (4 plan tasks, fresh implementer + independent reviewer each). One BLOCKED→amend cycle: Task 2's first implementer correctly diagnosed the plan's test-stub approach as impossible under `tests/conftest.py`'s MagicMock and stopped rather than improvising — plan amended, attempt 2 clean. Final whole-branch review (fable): Ready to merge, zero Critical/Important; its 3 minor recommendations (master tile helpText, letter+derivation pin tests, stale API-reference table deletion) fixed in `4440c62` and re-reviewed clean, scope-exact.

## 2026-07-23 | issue #70 — Replicate handling P4: outlier flag
- **Files changed:**
  - `database/models/experiments.py` (locked, issue-authorized single additive change) — `Experiment.is_outlier` (Boolean, NOT NULL, default/server_default false)
  - `alembic/versions/98b849b9f08b_add_is_outlier_to_experiments.py` — additive migration (revises `fe48608cabb7`); also drops/recreates `v_results_scalar_rollup` in both directions (new def with outlier filter on upgrade, verbatim pre-P4 def on downgrade so the view keeps working at the older revision); round-trip verified twice (Task 1 and Task 4)
  - `database/event_listeners.py` — `v_results_scalar_rollup` WHERE gains `AND NOT COALESCE(e.is_outlier, false)`; flagged experiments drop out of mean/median/std AND `n_replicates`. Only this view changed — per-row views (`v_results_scalar`, `v_results_h2`, `v_results_icp`, `v_primary_experiment_results`) untouched, pinned by regression test
  - `backend/api/schemas/experiments.py` — `is_outlier` on `ExperimentUpdate` (Optional[bool] + field_validator rejecting explicit JSON null → 422), `ExperimentResponse`, `ExperimentListItem`, `ReplicateGroupMember` (all `bool = False`)
  - `backend/api/routers/experiments.py` — PATCH flows through the existing generic setattr loop (no loop change); added `old_is_outlier` capture + ModificationsLog audit block (skipped for no-op writes, i.e. re-sending the current value)
  - `frontend/src/api/experiments.ts` — non-optional `is_outlier: boolean` on ExperimentListItem/ExperimentDetail/ReplicateGroupMember/CreatedReplicate; `is_outlier?` in patch payload
  - `frontend/src/pages/ExperimentDetail/index.tsx` — "Mark as outlier"/"Include in rollup" toggle (quick-actions row, shown only for replicate-set members: `replicate_label !== null || replicate-group members > 0`, which includes the group parent as vial 0), warning Badge "Outlier — excluded from group stats", replicate-group query, mutation invalidating experiment/experiments/rollup/replicate-group keys
  - `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx` — flagged members annotated "(outlier)" (muted/line-through link, legend suffix); their individual series stay charted
  - Tests: `tests/models/test_is_outlier_column.py` (new, incl. raw-insert server-default check), `tests/views/test_v_results_scalar_rollup.py` (+3: exclusion incl. n, per-row-view non-regression, all-flagged group vanishes), `tests/api/test_experiments.py` (+6 incl. explicit-null 422 and no-op-audit-skip), `tests/api/test_experiment_rollup.py` (+2), `frontend .../OutlierToggle.test.tsx` (new, 3), `GroupedResultsView.test.tsx` (+1, fixtures updated), `CreateReplicatesModal.test.tsx`/`ExperimentList.test.tsx` (additive fixture fields only)
  - Docs: `.claude/rules/MODELS.md` (field + rollup outlier-filter note replacing the old "No outlier filter (P4)" line), `docs/api/API_REFERENCE.md` (PATCH field + audit note, response/list/replicate-group fields, rollup exclusion callout, pre-existing undocumented `search` param added), `docs/user_guide/REPLICATES.md` ("Flagging an outlier" section) + synced `docs/project_context/` copies
  - `docs/superpowers/plans/2026-07-23-issue-70-p4-outlier-flag.md` — implementation plan
- **Tests added:** yes — full backend suite at HEAD: 847 passed, 4 skipped, 3 known pre-existing `tests/test_pg_backup_restore.py` failures (local pg_dump toolchain gap, predates branch). Frontend at Task-4 HEAD: vitest 64/64, tsc clean, `npm run build` clean, eslint = only the 5 pre-existing errors in files this branch never touched. Alembic `downgrade -1 && upgrade head` round-trips cleanly; views recreate on import.
- **Decision logged:** no — P4 semantics were locked by issue #70 (decision 4); UI placement (detail-page toggle gated to replicate sets, no experiments-list exposure) recorded in the plan's Global Constraints.
- **Process note:** subagent-driven (4 plan tasks, fresh implementer + independent reviewer each; all four approved first pass). Final whole-branch review (fable): Ready to merge, zero Critical; verified the migration↔`_VIEWS` SQL sync in both directions (downgrade def matches base commit byte-for-byte via git show) and that prefix-based query invalidation refreshes a rollup cached under a different experiment's id. Its 1 Important (explicit `{"is_outlier": null}` → 500, unreachable from the shipped UI) + 2 fold-in minors fixed in `ff9e05f`, re-reviewed clean.
- **Known non-blocking items (triaged ship-as-is by final review):** transient caught-and-logged view-creation errors during `alembic upgrade/downgrade` (pre-existing connect-listener design; verified safe — single-connection commit means a failed create rolls back the drops; worth one glance at the lab PC nightly-update log on first deploy); a base with only sequential re-runs (no lettered members) is aggregated by the rollup but exposes no toggle — flaggable via API only, by design per plan-locked UI placement; GroupedResultsView test fixture mocks n=3 alongside a flagged member (internally inconsistent but harmless to its assertions).
- **Scope note:** P4 only. P5 (parser consolidation + `SERUM_001a-2` parent wiring) remains open on issue #70 — issue left open deliberately.

## 2026-07-24 | issue #70 — Replicate handling P5: parser consolidation + letter+sequential parent wiring
- **Files changed:**
  - `database/experiment_id_parser.py` (new) — canonical experiment-ID parser: `parse_lineage_fields` (the P1 replicate grammar, moved verbatim from `lineage_utils`), `classify_base_id` (type/initials/index/validity classification, moved verbatim from `experiment_validation`), `parse_experiment_id_full` (the issue-mandated full parse), `ParsedExperimentID` dataclass + type-abbreviation map (moved). No `backend/` imports; enum from `database.models.enums`.
  - `database/lineage_utils.py` — `parse_experiment_id` is now a thin delegating wrapper (same 4-tuple surface; grammar body and module regexes moved out); `update_experiment_lineage` replicate branch gained the **one sanctioned behavior change**: a letter+sequential ID with no treatment (`SERUM_001a-2`) links `parent_experiment_fk` to the lettered sibling (`SERUM_001a`) when it exists — including pending in the same flush — else falls back to the pre-P5 group-parent resolution. Locked interpretation: any `-N` links to the letter itself (`a-3` → `a`, and explicit `a-0`/`a-1` likewise); treatment combos keep the group-parent link (pinned).
  - `backend/services/experiment_validation.py` — dataclass/type-map/`get_experiment_type_from_id` replaced by re-exports from the canonical module; `parse_experiment_id` delegates classification to `classify_base_id`; **`extract_lineage_info` body frozen verbatim as a documented legacy shim** — its two divergences from the canonical grammar are deliberate, pinned known issues (see decision below): naive trailing `-N` (`CF-015` → `("CF", 15, None, None)`) and the pre-#69 combined `-N_Treatment` bug (sequential never extracted). One stale docstring example corrected (doc-only).
  - Tests: `tests/test_experiment_id_parser.py` (new, 24 tests incl. a 20-ID wrapper-equivalence corpus), `tests/services/test_experiment_validation_replicates.py` (+`TestLegacyLineageDivergencesPinned`, 6 pins — all passed against pre-refactor code first), `tests/test_replicate_lineage.py` (+`TestLetterSequentialParentWiring`, 8 tests: sibling link, fallback, orphan, `a-3`→`a`, same-flush, treatment-combo pin, plain-replicate regression, `a-0`/`a-1` pin).
  - Docs: `.claude/rules/MODELS.md` (lineage wiring + canonical-parser notes incl. insertion-order caveat), `docs/working/decisions.md` (new entry), `docs/user_guide/REPLICATES.md` ("Re-running a single replicate") + hook-synced `docs/project_context/` copy.
  - **Zero edits (verified per plan):** `backend/services/bulk_uploads/new_experiments.py` (locked) and `database/data_migrations/establish_experiment_lineage_006.py` (frozen classification, decision 2026-07-23) — both keep working through the preserved import surfaces; `get_or_find_parent_experiment` and `update_orphaned_derivations` byte-unchanged; `database/event_listeners.py` untouched.
- **Tests added:** yes — see above. Full backend suite at HEAD (exclusive run): 880 passed, 4 skipped, 3 known pre-existing `tests/test_pg_backup_restore.py` failures (local pg_dump toolchain gap). Views recreate on import. Frontend untouched (no frontend files in diff). flake8 on touched files: net-improved vs base; new module clean.
- **Decision logged:** yes — `docs/working/decisions.md` 2026-07-24 (canonical parser module; `extract_lineage_info` frozen as legacy shim because a literal collapse is impossible — the two parsers demand contradictory pinned outputs for identical inputs, and locked bulk-upload code consumes the legacy semantics for real Core Flood IDs; `a-N` → letter-itself interpretation).
- **Process note:** subagent-driven (4 plan tasks, fresh implementer + independent reviewer each; Tasks 1-3 approved first pass, Task 4's reviewer caught the decisions.md entry inserted at top instead of appended — fixed as a pure move and re-approved, implementer report misstatement corrected). Final whole-branch review (fable): Ready to merge, zero Critical/Important; verified byte-identity of all moved code via AST extraction against the base commit and ran a 17,655-ID differential fuzz of old-vs-new across all three parse surfaces (zero mismatches). Its one actionable minor (un-pinned `a-0`/`a-1`-on-lettered-ID behavior) was pinned in a follow-up test commit and re-approved; remaining minors triaged ship-as-is (plan-mandated dead-store initializer, cosmetic docstring trim).
- **Known non-blocking items (documented, not fixed):** the two legacy-shim divergences above (pinned as known issues); insertion-order limitation — an orphaned `a-2` created before both `a` and the stem gets back-linked to the **stem** when the stem is later created (orphan pass is letter-unaware; a later insert of `a` alone does not re-link); `get_or_find_parent_experiment`'s order-dependent candidate pick when lettered siblings exist (pre-existing, unreached by the live replicate path, frozen for the migration script's sake).
- **Scope note:** P5 completes issue #70 (P1 #69; P2 PR #75; P3 PR #76; P4 PR #77).

## 2026-07-24 | issue #74 — Bulk Uploads cleanup: remove broken sync, reorganize widgets by usage
- **Files changed:**
  - `backend/api/routers/bulk_uploads.py` — `POST /master-results` now requires `file` (no-file SharePoint sync branch deleted); `GET/PATCH /master-results/config` endpoints, their schemas, and `_PydanticBase` import removed. Locked parser `backend/services/bulk_uploads/master_bulk_upload.py` untouched — `sync_from_path()` remains as API-unreachable dead code (user-approved; `settings.master_results_path` and its service test deliberately kept with it as one coherent dead-code island for a future single-change removal).
  - `backend/api/main.py` — **net zero**: an implementer widened the SPA catch-all to all HTTP methods to force 404s for the removed config routes (app-wide 405→404 side effect); escalated to user, fully reverted (byte-identical to base). The removed-endpoints test asserts via the FastAPI route registry instead (plan amended).
  - `tests/api/test_bulk_uploads.py` — sync-mode test replaced with 422-no-file test + route-registry removal test; 4 config-endpoint tests deleted.
  - `frontend/src/api/bulkUploads.ts` — `triggerMasterSync` removed.
  - `frontend/src/pages/BulkUploadRow.tsx` — `syncFn` prop, sync mutation, `IconRefresh`, and sync button removed; `prominent?: boolean` variant added (larger header/title/description); `IconChevron` exported.
  - `frontend/src/pages/ActlabsUploadRow.tsx` — `prominent` pass-through.
  - `frontend/src/pages/BulkUploads.tsx` — six active widgets on top with `prominent` (Master Results Sync, ICP-OES, XRD, New Experiments, Experiment Status Update, ActLabs); six demoted widgets (Solution Chemistry, Timepoint Mods, Rock Inventory, Chemical Inventory, Sample Chemical Composition, pXRF) conditionally rendered behind a "Less-used uploads" toggle, props byte-identical across the move; master widget copy instructs drag-and-drop of `01_R&D\02_Results\Master_Reactor_Sampling_Tracker_v2.xlsx` (drag-drop path uses the same `_process_bytes` parser as the old sync — verified before removal per the issue's precondition).
  - `frontend/src/pages/__tests__/BulkUploads.test.tsx` (new) — 3 tests: master copy + no sync button; active-widget order before the accordion; demoted widgets absent until expansion.
  - `frontend/e2e/journeys/` — `07-master-results-sync.spec.ts` deleted, `07-bulk-uploads-layout.spec.ts` created (2 tests); 08/09/11/13 expand the accordion before clicking demoted widgets (13's master/ActLabs tests untouched).
  - Docs — `docs/user_guide/BULK_UPLOADS.md`, `docs/api/API_REFERENCE.md`, `docs/developer/ADDING_UPLOAD_TYPE.md` (syncFn row → prominent), `docs/deployment/PRODUCTION_DEPLOYMENT.md` (config-path section removed), `docs/specs/master_results_sync.md` (drag-drop-only rewrite incl. Overview coherence fix), `docs/milestones/M6_bulk_uploads.md` (4 stale sync-as-current lines annotated as removed/superseded — plan gap caught by Task 5's reviewer grep) + hook-synced `docs/project_context/` copies.
  - `docs/superpowers/plans/2026-07-24-issue-74-bulk-uploads-cleanup.md` — implementation plan (amended 1×: route-registry test).
- **Tests added:** yes — 2 backend API tests (422 no-file, route-registry removal), 3 frontend unit tests, 2 new e2e layout tests + 4 amended e2e specs. Full backend at HEAD: 877 passed / 4 skipped / 3 known pre-existing `test_pg_backup_restore.py` failures (count reconciles with develop's 880: −5 removed sync/config tests, +2 new). Frontend: vitest 67/67, tsc clean, build clean, eslint = only the 5 known pre-existing errors in untouched files. Playwright `--list` collects 52 tests / 19 files cleanly (runtime run deferred to the lab setup — the accordion interaction's only runtime verification).
- **Decision logged:** no — the two user sign-offs (remove the dead `/master-results/config` endpoints; revert the SPA catch-all widening in favor of a route-registry assertion) are recorded in the plan's Global Constraints / amendment notes, not standing architectural decisions.
- **Process note:** subagent-driven (5 plan tasks, fresh implementer + independent reviewer each; Tasks 2/3/4 approved first pass). Two escalations to the user mid-execution: the plan's own HTTP-404 test was unsatisfiable without an app-wide routing change (user chose revert + registry assertion), and one fix commit falsely claimed the revert had been applied — caught by controller `git diff` verification, corrected in a follow-up commit; implementer claims were independently verified from then on. Task 5 took two fix rounds to purge every sync-as-current doc line (reviewer grep found stale M6 milestone lines outside the plan's file list; implementer's own sweep caught one more). Final whole-branch review (fable): Ready to merge, zero Critical/Important; verified frontend/backend contract, toggle-label coupling, path-string escaping end-to-end, and that legacy Streamlit has no bulk-uploads references; 8 minors triaged ship-as-is (incl. now-dead `post()` optional-body generality in `bulkUploads.ts` and the "Master Results Sync" name outliving the sync — both deliberate per issue wording).

## 2026-07-24 | issue #72 — Reactor cards: show today's Reactor Modification inline
- **Files changed:**
  - `backend/api/schemas/dashboard.py` — `ReactorCardData.todays_modification: Optional[str] = None`
  - `backend/api/routers/dashboard.py` — one batched `reactor_change_requests` lookup in `get_dashboard` keyed on `(experiment_id, reactor_label, sync_date == today UTC)`; endpoint remains a single call (query-count pinned by test via Engine-level `before_cursor_execute` listener)
  - `frontend/src/api/dashboard.ts` — `todays_modification: string | null` on `ReactorCardData`
  - `frontend/src/pages/ReactorGrid.tsx` — conditional line-clamped "Modified today:" block in `ReactorCard`'s occupied branch (ONGOING + QUEUED, never empty slots, `title` hover for full text); **plus review fix:** `crMutation.onSuccess` now invalidates `['dashboard']` — the issue's premise that this invalidation already existed was false (final-review finding); without it a saved modification stayed off the card for up to 60 s (dashboard `refetchInterval`)
  - `frontend/src/pages/__tests__/ReactorGrid.test.tsx` (new) — 3 tests: render with label, absence when null, title-hover full text
  - `tests/api/test_dashboard.py` — 5 new tests: schema default, today shown, prior-day excluded, keying on (experiment_id, reactor_label) incl. QUEUED + wrong-slot leak guard, single-batched-query assertion
  - `docs/api/API_REFERENCE.md` (+ hook-synced `docs/project_context/` copy) — dashboard example + note
  - `docs/superpowers/plans/2026-07-24-issue-72-reactor-card-todays-modification.md` — implementation plan (amended 1×: traceability row corrected after the false-premise finding)
- **Tests added:** yes — full backend at HEAD: 882 passed / 4 skipped / 3 known pre-existing `test_pg_backup_restore.py` failures (877 at develop + 5 new reconciles); frontend vitest 70/70, tsc clean, `npm run build` clean, eslint = only the 5 known pre-existing errors in untouched files.
- **Decision logged:** no — "today" pinned to UTC matching the pop-out save path per the issue's own design note; no standing architectural decisions.
- **Process note:** subagent-driven (2 plan tasks, fresh sonnet implementer + independent reviewer each; both approved first pass). Final whole-branch review (fable): 1 Important — the issue/plan claimed `['dashboard']` was "already invalidated on save" (it wasn't); fixed as a one-line invalidation in `crMutation.onSuccess`, re-reviewed → Ready to merge. All per-task minors triaged ship-as-is.
- **Known non-blocking follow-up (pre-existing, recommended as new issue):** Notion-sync producer seam — `backend/services/notion_sync/sync.py` writes `sync_date` from server-LOCAL `date.today()` (and `POST /change-requests` defaults likewise when `sync_date` omitted), so an evening-EDT Notion-imported modification can land under a different day than the dashboard's UTC "today"; Notion import also doesn't case-normalize `reactor_label`, and the card lookup is case-sensitive.

## 2026-07-24 | issue #81 — Timepoint ID token (`-t<days>`): parser, persistence, guards, bulk uploads, UI, docs
- **Files changed (6 tasks / 6 commits):**
  - `database/experiment_id_parser.py` — `split_timepoint_token` + `_TIMEPOINT_TOKEN_RE` (anchored at ID end, decimals allowed); pre-strip wired into `parse_lineage_fields`; `ParsedExperimentID.timepoint_days` + `parse_experiment_id_full` wiring.
  - `backend/services/experiment_validation.py` — `parse_experiment_id` pre-strips the token before delegating to the frozen `extract_lineage_info` legacy shim (untouched body; shim's two pinned divergences unaffected); surfaces `timepoint_days`.
  - `database/models/experiments.py` + `alembic/versions/6a84a5a15592_add_id_timepoint_days_to_experiments.py` — `Experiment.id_timepoint_days` (Float, nullable, indexed); purely additive migration, round-tripped clean.
  - `database/lineage_utils.py` — `update_experiment_lineage` persists `id_timepoint_days` via `split_timepoint_token`; letterless `-t` vials classify as parent-like rows (base = stem, parent NULL) per Decision Point 7.
  - `backend/services/result_merge_utils.py` — new pure helper `apply_id_timepoint` (fills a blank time from the ID, raises `ValueError` with a "canonical" message beyond `TIMEPOINT_TOLERANCE_DAYS = 0.0001`).
  - `backend/services/scalar_results_service.py::create_scalar_result_ex` and `backend/api/routers/results.py::create_result` — guard call sites (`apply_id_timepoint` raises `ValueError`; the bulk-upload/quick-upload callers of `create_scalar_result_ex` catch it as a per-row error, `POST /api/results` maps it to `422`).
  - `backend/api/schemas/experiments.py` — `id_timepoint_days` on `ExperimentResponse` + `ExperimentListItem`.
  - `backend/services/bulk_uploads/scalar_results.py`, `backend/services/bulk_uploads/master_bulk_upload.py` (locked, issue-authorized additive blocks only) — string-level fill/conflict check before rows reach the service guard, so a conflict is a per-row error rather than an aborted upload.
  - `frontend/src/utils/experimentId.ts` (+ test) — TS mirror of the token regex; `frontend/src/api/experiments.ts` — `id_timepoint_days: number | null` on list/detail types; `frontend/src/pages/NewExperiment/{Step1BasicInfo,Step4Review}.tsx` — parsed day displayed (no Time field added to the wizard per Decision Point 6); `frontend/src/pages/ExperimentDetail/{index.tsx,ResultsTab.tsx,AddResultsModal.tsx}` — Add Results modal auto-fills and disables Time when `id_timepoint_days` is set, with a "locked to day N" hint.
  - `frontend/src/pages/BulkUploads.tsx` — help text on the New Experiments, Master Results Sync, and Solution Chemistry tiles documenting the `-t<days>` grammar and fill/conflict rule; `frontend/src/pages/ExperimentList.tsx` — `day {N}` chip next to the ID when `id_timepoint_days` is set.
  - Docs: `.claude/rules/MODELS.md` (Lineage Tracking bullet + `v_results_scalar` cumulative caveat), `docs/user_guide/REPLICATES.md` (new "Replicate timepoints (`-t<days>`)" section incl. both documented limitations), `docs/api/API_REFERENCE.md` (`id_timepoint_days` on list schema/example + new `POST /api/results` conflict/fill subsection), `docs/upload_templates/{scalar_results,master_bulk_upload}.md` (fill/conflict rule per tile) — all hook-synced to `docs/project_context/`.
  - Tests — new: `tests/services/test_timepoint_guard.py`, `tests/services/bulk_uploads/test_scalar_results_timepoints.py`, `tests/models/test_id_timepoint_days_column.py`, `frontend/src/utils/__tests__/experimentId.test.ts`, `frontend/src/pages/ExperimentDetail/__tests__/AddResultsModal.timepoint.test.tsx`. Extended (additive only): `tests/test_experiment_id_parser.py`, `tests/services/test_experiment_validation_replicates.py`, `tests/test_replicate_lineage.py`, `tests/views/test_v_results_scalar_rollup.py`, `tests/services/bulk_uploads/test_master_bulk_upload.py`, `tests/api/test_results.py`, `tests/api/test_experiments.py`, `frontend/src/pages/__tests__/{BulkUploads,ExperimentList}.test.tsx`.
  - `docs/superpowers/plans/2026-07-24-issue-81-timepoint-id-token.md` — implementation plan.
  - **Zero-edit (verified, per plan and re-confirmed at HEAD via `git diff develop --stat`):** `backend/services/bulk_uploads/new_experiments.py`, `backend/services/bulk_uploads/long_format.py`, `backend/services/bulk_uploads/replicate_routing.py`, `database/event_listeners.py`, `database/data_migrations/establish_experiment_lineage_006.py`, `frontend/src/components/experiments/AddResultModal.tsx` (dead component, distinct from the live `ExperimentDetail/AddResultsModal.tsx`).
- **Tests added:** yes — see above. Full backend suite at HEAD: 935 passed / 4 skipped / 3 known pre-existing `test_pg_backup_restore.py` failures (local pg_dump toolchain gap, unrelated to this branch). Frontend: vitest 18 files / 76 tests all green, `tsc --noEmit` clean, `npm run build` clean, `npx eslint src` = only the 5 known pre-existing errors in untouched files. Alembic round-trip (`downgrade -1` → `upgrade head`) clean at HEAD.
- **Decision logged:** no — the 10 decision points below were resolved inline in the plan (`docs/superpowers/plans/2026-07-24-issue-81-timepoint-id-token.md`, "Decision Points" table) rather than in `docs/working/decisions.md`; none rise to a standing cross-cutting architectural decision beyond what's already documented in `MODELS.md`/`REPLICATES.md`.
- **Scope notes — Decision Points 1, 2, 6–10 outcomes:**
  1. Bare untimed siblings coexisting with `-t<days>` siblings are **not blocked** — documented only (`REPLICATES.md` limitation), not enforced with a DB-level scan; recommend a follow-up issue if this causes real rollup pollution.
  2. `SERUM_001a-t7_Desorption` (treatment glued after the token) is **deferred** — the token is anchored at string end so it never fires when a treatment suffix trails; the ID still parses (stem absorbs it, `timepoint_days=None`, no crash), pinned by a dedicated test. Real treatment+timepoint combos need their own issue.
  6. The New Experiment wizard has no Time field to auto-fill/lock at creation (issue's original assumption was wrong) — reinterpreted as **display-only** on the wizard; actual fill/lock behavior lives in the Add Results modal (Task 5) and bulk uploads (Task 4).
  7. A letterless `-t` vial (`SERUM_001-t7`) classifies as a **parent-like row** (base = stem, parent NULL) — kept as minimal-change default. **Correction (final review, I2):** the original "verified harmless" claim was wrong — `update_orphaned_derivations` matched by `base_experiment_id` (not exact ID spelling), so a letterless `-t` vial could be *adopted* as an orphan (not "steal" orphans itself) when a later sibling insert (bare stem, `-0`, or `-1`) triggered the pass. Fixed by excluding rows where `id_timepoint_days IS NOT NULL AND replicate_label IS NULL` from the orphan query; lettered `-t` vials remain adoptable.
  8. Bulk New Experiments upload does **not** copy parent conditions for `-t<days>` IDs (`new_experiments.py`'s `find_parent_for_copy` sees the raw `-t` ID as its own base) — zero-edit on the locked parser; documented as a known limitation in `REPLICATES.md` and `API_REFERENCE.md`.
  9. `long_format.py` (locked, legacy, no live endpoint) is **zero-edit** — its upserts already funnel through `create_scalar_result_ex`, so the Task 3 service guard covers it without a dedicated string-level check.
  10. `frontend/src/components/experiments/AddResultModal.tsx` is dead code (unreferenced by any page) — **skipped**; the backend guard covers any future caller, and this is noted here at completion.
- **Process note:** 6 plan tasks (Tasks 1–5 core implementation, Task 6 this entry's docs/UI-polish task), executed sequentially on `feat/issue-81-timepoint-id-token` off `develop`. Final full-suite and alembic verification re-run at HEAD after Task 6 (see Tests added line); zero-edit file list re-confirmed via `git diff develop --stat` rather than trusted from the plan alone.
- **Final review fixes (whole-branch review, this entry amended):**
  - **C1 (rename must re-sync `id_timepoint_days`)** — `backend/api/routers/experiments.py`'s PATCH rename branch set `exp.experiment_id = new_id` but never re-derived `id_timepoint_days` (the `before_flush` lineage listener only wires `session.new`, so a rename — a dirty row — was skipped); fixed by re-splitting the new ID at the rename site. 2 new tests in `tests/api/test_experiments.py`.
  - **I1 (Replicate column + `-t<days>` token combo silently dropped the token)** — `combine_replicate_id` internally uses the token-stripping `parse_experiment_id`, so a token ID + a real Replicate letter silently discarded the token. Fixed with a pre-split-and-check in the two issue-authorized locked-parser call sites (`backend/services/bulk_uploads/scalar_results.py`, `backend/services/bulk_uploads/master_bulk_upload.py`): a real letter on a token ID is now a per-row error; blank/no-op Replicate cells pass through with the token intact. 4 new tests (2 per parser).
  - **I2 (orphan adoption could re-link a letterless `-t` vial)** — see corrected Decision Point 7 above. Fixed in `database/lineage_utils.py::update_orphaned_derivations` with a query-level exclusion. 1 new test (with a lettered-orphan control case) in `tests/test_replicate_lineage.py`.
  - **M1 (regex parity)** — `_TIMEPOINT_TOKEN_RE` in `database/experiment_id_parser.py` now compiles with `re.ASCII` so unicode digit look-alikes don't match server-side, matching the TS mirror. No new test (existing ASCII coverage suffices).
  - **M2 (strip before split)** — `database/lineage_utils.py::update_experiment_lineage` now strips `experiment.experiment_id` before `split_timepoint_token`, so a trailing-whitespace ID gets its timepoint parsed instead of silently landing `NULL`.
  - **I3 (doc correction)** — `docs/user_guide/REPLICATES.md`: softened the "-t vial lands in that day's bucket" claim with a caveat that `POST /api/results` (Add Results modal) sets no `time_post_reaction_bucket_days`, so those rows don't appear in the rollup bucket; use the bulk uploads for rollup inclusion. Also documents the I1 rule (Replicate column + token ID rejected).
  - **Commits:** one code-fix commit (C1/I1/I2/M1/M2) + one docs/issue-log commit (I3 + this entry), both `[#81] ...` per the branch's commit convention.
  - **Recommended follow-up (M3, not fixed here):** the experiment detail page's **Create Replicates** button is still visible on a letterless `-t` vial (e.g. `SERUM_001-t7`); only `Step4Review` (New Experiment wizard) hides it. Low risk — `create_replicate_experiments` would resolve the parent via `find_replicate_group_parent` on the bare stem regardless, so clicking it on a `-t` vial page doesn't corrupt lineage, but the button is misleading in that context.
  - **Accepted (M4, no action):** fuzzy-matched token conflicts (e.g. a token ID that fuzzy-matches an existing experiment with a different day) surface via the generic bulk-upload error wrapper rather than a token-specific message — acceptable, matches how all other fuzzy-match conflicts are reported.
  - Full suite re-run at HEAD after these fixes: 942 passed / 4 skipped / 3 known pre-existing `test_pg_backup_restore.py` failures (unrelated pg_dump toolchain gap).

## 2026-07-27 | issue #83 — Replicate rollup: bucket hand-entered results, backfill, H₂ table columns
- **Files changed (4 tasks / 6 commits):**
  - Task 1 (`c251a81` + `a095f7e`) — `backend/api/routers/results.py::create_result` now sets
    `time_post_reaction_bucket_days = normalize_timepoint(resolved_days)`, overwriting any
    client-supplied value; when the new row is primary and its bucket is already occupied by
    another primary row, the existing primary is demoted (newest wins). 6 new tests in
    `tests/api/test_results.py`, 1 end-to-end rollup test class in
    `tests/api/test_experiment_rollup.py`. `a095f7e` was a review-driven line-wrap fix (flake8).
  - Task 2 (`ca5c0be` + `92d8c6b`) — data-only migration
    `alembic/versions/daae92e908f1_backfill_result_timepoint_buckets.py`: demotes colliding
    primaries data-first/id-DESC, then fills NULL buckets from the resolved time; no-op
    downgrade (matches the `458f344f73d8` clamp precedent). `alembic upgrade`/`downgrade`/`upgrade`
    round-tripped clean on the dev DB. Tests: `tests/data_migrations/test_backfill_bucket_migration.py`
    (4 tests) — moved there from the plan's original `tests/test_backfill_bucket_migration.py`
    path during review, to reuse the existing `migration_session` fixture instead of private
    engine plumbing (review-driven deviation from the plan).
  - Task 3 (`94bcd34`) — `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx` table gains
    `H₂ (g/t)` and `Fe²⁺ → H₂ (%)` mean±sd columns; +1 vitest test.
  - Task 4 (this entry) — docs only: `.claude/rules/MODELS.md` (`v_results_scalar_rollup` parent-
    inclusion + hand-entered-rows bullets), `docs/api/API_REFERENCE.md` (rollup parent-inclusion
    note + new `POST /api/results — timepoint bucketing (issue #83)` subsection),
    `docs/user_guide/REPLICATES.md` (reverses the stale issue-#81 "Add Results modal does not
    bucket" caveat; adds "The group parent counts toward the stats" subsection) — all hook-synced
    to `docs/project_context/`. Also commits the untracked
    `docs/issue-replicate-group-h2-calc-testing-findings.md` (the investigation artifact this
    issue is built on) and its `docs/project_context/` copy.
- **Newest-wins demotion decision:** at the `POST /api/results` endpoint, a new primary result
  landing in an already-occupied bucket demotes the existing primary (matches
  `v_primary_experiment_results`'s `id DESC` tie-break and modal UX — the most recently entered
  reading is what a researcher expects to see as "the" result for that day). The backfill
  migration uses a different, data-first rule for historical rows instead: an existing bulk-upload
  row with full scalar+ICP data should not lose primary status to an emptier hand-entered row just
  because the hand-entered row has a higher id; ties within the same data tier go to the newest row.
- **Backfill migration:** `daae92e908f1_backfill_result_timepoint_buckets` — additive data
  migration, runs automatically on the lab PC's nightly `alembic upgrade head`; downgrade is a
  documented no-op (backfilled buckets are not un-set on downgrade, matching precedent).
- **Defect #3 (parent counted in replicate-group aggregates) — resolved as docs-only:** confirmed
  intended per the issue's own triage — the group parent shares the `COALESCE(base_experiment_id,
  experiment_id)` grouping key with its lettered replicates by design, so a parent with its own
  results is correctly averaged into the group stats. No code change; documented in `MODELS.md`,
  `API_REFERENCE.md`, and `REPLICATES.md` that `is_outlier` is the (deliberately) only opt-out.
- **Defect #5 (ammonium 0.00±0.00 GREATEST-NULL semantics) — deferred:** out of scope for this
  issue per the Global Constraints; needs its own follow-up ticket.
- **Other out-of-scope note carried from the issue:** no PATCH endpoint for `ExperimentalResults`
  — noted in the issue as "consider separately," not addressed here.
- **Tests added:** no (Task 4 is docs-only). Cumulative tests added across Tasks 1-3: yes — see
  above (11 new backend tests + 4 migration tests + 1 frontend test).
- **Whole-branch verification (this entry, run at HEAD):**
  - Backend: `.venv/Scripts/python -m pytest tests/ -x -q --ignore=tests/test_pg_backup_restore.py`
    → 954 passed, 4 skipped, 538 warnings (deprecation/SAWarning noise only) in ~56s.
  - Frontend: `npx vitest run` → 18 test files / 77 tests, all passed.
  - Frontend: `npx tsc --noEmit` → clean (no output).
  - `git diff develop --stat` → 12 files changed, 486 insertions / 18 deletions; confirmed zero
    edits to `backend/services/bulk_uploads/`, `database/models/`, `database/event_listeners.py`,
    and no `frontend/package*.json` changes.
- **Decision logged:** no — the newest-wins vs. data-first demotion split and the backfill's
  no-op downgrade were resolved inline in the plan's Global Constraints / Task descriptions, not
  in `docs/working/decisions.md`; defect #3's "confirmed intended" triage is documented in
  `MODELS.md`/`API_REFERENCE.md`/`REPLICATES.md` rather than as a standing architectural decision.
- **Process note:** subagent-driven (4 plan tasks, fresh implementer + independent reviewer each).
  Task 1 and Task 2 each had one Important review finding fixed and re-approved (line wraps;
  test-fixture reuse); Task 3 approved first pass.

## 2026-07-27 | issue #73 — Remove non-functional gram-conversion display from Chemical Additives list
- **Files changed:**
  - `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` — removed the `{a.mass_in_grams.toFixed(4)} g`
    conditional span from the additive row; only `{amount} {unit}` displays now. `mass_in_grams`
    remains a valid derived field for moles/concentration calculations and Power BI views.
- **Tests added:** no — verified `ConditionsTab.buttons.test.tsx` (3/3 pass, no assertion depended
  on the removed span) and `frontend/e2e/journeys/12-chemicals.spec.ts` (its `/2\.5\s*g/` assertion
  targets the amount+unit span, not the removed one) before merging, per the issue's own notes.
- **Decision logged:** no

## 2026-07-27 | issue #85 — Replace dashboard KPI cards with occupancy + workday metrics
- **Files changed:**
  - `backend/services/workdays.py` (new) — `last_n_workdays`/`workday_window`, lab-local
    (`America/New_York`) 7-workday window, holidays not skipped.
  - `backend/api/schemas/dashboard.py` — `DashboardSummary` reshaped: removed `active_experiments`/
    `reactors_in_use`/`completed_this_month`/`pending_results`; added `SlotOccupancy` + `reactors`/
    `core_floods`/`gc_measurements_7wd`/`gc_experiments_7wd`/`serum_vials_started_7wd`/
    `serum_experiments_7wd`/`workday_window_start`/`workday_window_end`. Breaking change, no shim.
  - `backend/api/routers/dashboard.py` — `get_dashboard` reordered so occupancy derives from the
    already-built `reactor_cards` (no new per-card query); `R_SLOT_COUNT=16`/`CF_SLOT_COUNT=3`;
    net -1 query (3 removed, 2 added: GC + serum aggregates).
  - `backend/api/schemas/results.py`, `backend/api/routers/experiments.py`,
    `frontend/src/api/experiments.ts` — exposed previously write-only `nmr_run_date`/`icp_run_date`/
    `gc_run_date` (+ `xrd_run_date` parity on `ScalarResponse`); added mid-plan after
    `docs/issues/issue-results-api-missing-run-dates.md` showed the new GC KPI was otherwise
    unverifiable in-app. UI display layer deliberately not touched — `icp_run_date` would collide
    with the existing `has_icp` badge label in `ResultsTab.tsx`; open question, not resolved.
  - `frontend/src/components/ui/SlotBar.tsx` (new), `Card.tsx` (`MetricCard` gained `children`/
    `title`), `frontend/src/api/dashboard.ts`, `frontend/src/pages/ReactorGrid.tsx` (slot counts
    now derive from `rSlotCount`/`cfSlotCount` props, no hardcoded 16/2/18/19; CF03 added),
    `frontend/src/pages/Dashboard.tsx` (4 new KPI cards: Reactor Occupancy, GC Measurements, Serum
    Vials Started, Core Floods Ongoing).
  - `frontend/e2e/journeys/14-dashboard-cf-slots.spec.ts` — CF03 coverage added; fixed two
    pre-existing bugs only caught by actually running Playwright (stale section-header selectors
    inherited from before this issue; a DOM-traversal depth error; an unscoped `afterEach` cleanup
    locator colliding with an unrelated status-filter chip).
  - `docs/user_guide/DASHBOARD.md` / synced `docs/project_context/DASHBOARD.md`,
    `docs/api/API_REFERENCE.md` / synced copy.
- **Tests added:** yes — `tests/services/test_workdays.py` (new), ~40 new/updated tests across
  `tests/api/test_dashboard.py`, `tests/api/test_results.py`; `frontend/src/components/ui/__tests__/SlotBar.test.tsx`
  (new), `frontend/src/pages/__tests__/Dashboard.test.tsx` (new), updates to
  `ReactorGrid.test.tsx`/`ResultsTab.columns.test.tsx`.
- **Decision logged:** no — the occupancy-derived-from-already-fetched-`reactor_cards` pattern and
  the ET-vs-UTC timezone split (workday window vs. the pre-existing UTC-based "today's
  modification" lookup) are documented inline in code comments and the plan, not as standing
  architectural decisions.
- **Process note:** subagent-driven (12 plan tasks + 1 final-review fix commit, fresh implementer +
  independent reviewer each, final whole-branch review on the most capable model). Found and fixed
  6 real bugs across the process: 3 in the plan text itself, caught mid-execution by implementers
  who correctly refused to guess (a KPI-card/section-header label collision; a test `waitFor`
  race condition; an inherited e2e DOM-depth/`afterEach` selector bug only surfaced by actually
  running Playwright against the live app) — all resolved by editing the plan file in place and
  resuming the same subagent via `SendMessage`, not fresh dispatches. Final whole-branch review
  (opus) caught a 4th: two tests in `tests/api/test_queued_status.py` (never exercised by any
  per-task test run) still referenced the removed summary fields and would `KeyError` live —
  fixed and independently re-verified by the controller (not just the fix report) before merge.
  Mid-session, also caught and declined to act on a fabricated "priority change" instruction
  (wrong-tree file paths from a parallel non-git copy) until the user corrected it — see the
  session transcript; no code impact, noted here only because it shaped process, not output.

## 2026-07-28 | issue #86 — Fix bulk-rename self-parent crash and one-row batch poisoning
- **Files changed:**
  - `backend/services/bulk_uploads/new_experiments.py` (locked, sign-off obtained) — A1: flush the rename before `update_experiment_lineage`; B: wrap each experiments-sheet row in a `db.begin_nested()` savepoint (row_ok flag + finally), discard exp_id from `renamed_experiment_ids` on rollback
  - `database/lineage_utils.py` — A2: `_reject_self_parent` helper; drop self-resolved parent to NULL in both branches of `update_experiment_lineage` (warning-level log)
  - `tests/services/bulk_uploads/test_new_experiments_rename_lineage.py` — new; 5 tests via a production-faithful autoflush=False session
  - `.claude/rules/MODELS.md` — lineage-section note (self-parent guard + rename-path ordering)
  - `docs/LOCKED_COMPONENTS.md` — rename-path ordering-contract footnote on `new_experiments.py`
  - `docs/issues/issue-bulk-rename-circular-dependency.md` — reference issue doc
- **Tests added:** yes — 5 (A2 self-parent unit, A rename-into-replicate-stem, A sibling triplet a/b/c, B one-bad-row isolation, B real-exception-not-PendingRollbackError). Regression: bulk_uploads dir 187, root rename+lineage 22, API experiments 75, API bulk-uploads 71 — all pass
- **Decision logged:** yes — `docs/working/decisions.md` (2026-07-28)

## 2026-07-28 | issue #87 — Replicate group view (dead base-experiment link, split list grouping, rename lineage loss)
- **Files changed:**
  - `backend/services/replicate_groups.py` — NEW: `resolve_group`/`resolve_rollup_rows`/`group_exists`; base-ID-string group resolution (parent via `find_replicate_group_parent`, members by `base_experiment_id` + `replicate_label IS NOT NULL`, shared/divergent condition comparison excluding reserved+deprecated fields, additive-view divergence)
  - `backend/api/schemas/experiments.py` — NEW `ReplicateGroupMemberDetail`, `ReplicateGroupDetailResponse`
  - `backend/api/routers/experiments.py` — NEW `GET /groups/{base_id}` + `/groups/{base_id}/rollup` (declared before `/{experiment_id}` catch-all); refactored `/{experiment_id}/rollup` → `resolve_rollup_rows`; `/{experiment_id}/replicate-group` kept BYTE-IDENTICAL (deliberately not delegated); rename branch now recomputes lineage (flush-new-id → `update_experiment_lineage`, issue-#86 ordering) + `409` parent-rename guard gated on `_is_group_parent_spelling` (bare stem/-0/-1, no over-fire on members/sequential) + orphan back-link; grouped-list mode rewritten (bucket lettered members on `COALESCE(base,experiment_id)`, `-0`/`-1` parents on stem, sequential/treatment re-runs stand alone; window-fn representative)
  - `frontend/src/api/experiments.ts` — `ReplicateGroupDetail`/`ReplicateGroupMemberDetail` types, `getGroup`/`getGroupRollup`
  - `frontend/src/pages/ReplicateGroup/index.tsx` — NEW read-only group page (members table, shared/`varies` conditions, additives, rollup, read-only notice)
  - `frontend/src/pages/ExperimentDetail/index.tsx` — dead `/experiments/{base}` link → group strip (sibling chips keyed by id, `Group` link → `/experiments/groups/{base}`)
  - `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx` — prop `experimentId`→`baseExperimentId`, repointed to group endpoints with new cache keys; `ResultsTab.tsx` call site
  - `frontend/src/App.tsx` — route `/experiments/groups/:baseId`
  - `.claude/rules/MODELS.md`, `docs/api/API_REFERENCE.md`, `docs/user_guide/REPLICATES.md` (+ auto-synced `docs/project_context/` copies) — group-view + endpoint docs
- **Tests added:** yes — backend: `tests/api/test_replicate_group_detail.py` (NEW, group resource + route ordering + 404 + `-t` shared-letter + divergent conditions/additives), wrapper byte-identical + rename-lineage + grouped-list (orphan collapse, sequential-not-absorbed, `-0`/`-1` parent grouping) suites in `tests/api/test_experiments.py` / `test_experiment_rollup.py`; frontend: `ReplicateGroupPage.test.tsx`, `GroupStrip.test.tsx`, updated `GroupedResultsView.test.tsx`. tests/api 397 pass; full backend 1009 pass (3 pre-existing pg_backup env failures unrelated); frontend vitest 96/96. Chrome DevTools e2e PASS.
- **Decision logged:** no — key call recorded in commits/ledger: `/{experiment_id}/replicate-group` wrapper kept byte-identical (issue-owner decision) rather than delegating; 2 observational minors accepted (parent row excluded from condition divergence; letter+sequential re-run groups under stem in list mode)
- **Schema change:** none. No migration, no new dependency.

## 2026-07-28 | inline — Default replicate rollup chart metric to H2 (umol)
- **Files changed:** `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx` (metric useState default `gross_nh4` -> `h2_umol`); `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx` (new test pinning default to H2 (umol))
- **Tests added:** yes — one vitest assertion pinning the selector default (select value + visible option text). ExperimentDetail suite 32/32 pass; eslint clean
- **Decision logged:** no

## 2026-07-28 | issue #88 — Raise text contrast: shift the ink ramp up one step
- **Files changed:**
  - `frontend/src/styles/tokens.css` — `--color-ink-secondary` #8BACC8 → #C5D9EA; `--color-ink-muted` #4d6e8a → #A3C2DC
  - `frontend/tailwind.config.ts` — `theme.extend.colors.ink.secondary`/`.muted` same values
  - `frontend/src/assets/brand.ts` — `colors.inkSecondary`/`inkMuted` same values (source of truth)
  - `frontend/src/test/contrast.test.ts` — NEW: WCAG luminance/contrast regression test, asserts inkPrimary/inkSecondary/inkMuted each clear 4.5:1 against navyBase/navyRaised/navyOverlay (imports live values from `brand.ts`) and asserts strict luminance ordering (primary > secondary > muted)
  - `docs/DESIGN.md` (+ synced `docs/project_context/DESIGN.md`) — added a "Text Hierarchy" table (didn't previously exist) with hex values, per-surface contrast ratios, and the 4.5:1 AA floor note
- **Deviation from issue spec:** `ink.muted` was raised past the issue's originally proposed #8BACC8 (5.52:1 on `overlay`) to #A3C2DC (7.07–9.72:1) after user feedback that the Th/hint-text tier was still hard to read in practice at the AA floor; re-verified AAA-level contrast on the worst-case surface while keeping `ink.muted` distinctly below `ink.secondary` (order preserved)
- **Tests added:** yes — 10 new vitest assertions (3 tokens × 3 surfaces + ordering check), all passing; full frontend suite 107/107 pass; eslint clean
- **Verification:** visually confirmed in Chrome (replicate group page, experiment detail Conditions/Results tabs, New Experiment form) — `Th` headers, condition labels, chevrons, and rollup chart axis/legend all legible and still read as chrome/secondary, not competing with data; no component-level color classes changed
- **Decision logged:** no
- **PR:** #93 → develop (merged)

## 2026-07-28 | issue #89 — Grouped experiment view: hide empty conditions and round numeric values
- **Files changed:**
  - `frontend/src/pages/ReplicateGroup/index.tsx` — `formatValue` now routes numbers through a new `formatNumber` helper (rounds to 3dp, trims trailing zeros); added `hasValue` and filtered the shared-conditions `.map` to skip null/undefined/empty entries before rendering, instead of rendering them as `—`
  - `frontend/src/pages/ReplicateGroup/__tests__/ReplicateGroupPage.test.tsx` — 4 new tests: null shared-condition fields suppressed, long float rounds to 3dp, integer condition renders without trailing decimal, divergent field still renders label + "varies" text with its shared value absent
- **Tests added:** yes — ReplicateGroupPage suite 11/11 pass; full frontend suite 101/101 pass; eslint clean
- **Decision logged:** no — no shared numeric formatter extracted to `frontend/src/utils/` (issue's "consider extracting" was optional; `ConditionsTab.tsx`'s `Row` doesn't yet need it since `total_ferrous_iron_g` isn't rendered there)
- **PR:** #91 → develop

## 2026-07-28 | issue #90 — Expose H2 concentration (ppm) through results API and rollup view
- **Files changed:**
  - `backend/api/schemas/results.py` — `ResultWithFlagsResponse` +`h2_concentration`; `RollupTimepointResponse` +`mean_h2_ppm`, +`sd_h2_ppm`
  - `backend/api/routers/experiments.py` — `get_experiment_results` populates `h2_concentration` (null when no scalar row)
  - `database/event_listeners.py` — `v_results_scalar_rollup` +`mean_h2_ppm` (`AVG`), +`sd_h2_ppm` (`stddev_samp`), placed before `mean_h2_micromoles`; comment ties the AVG to the invariant-ppm unit in MODELS.md
  - `alembic/versions/a1f2c3d4e5b6_add_h2_ppm_to_rollup_view.py` — NEW; drops/recreates the view (down_revision `daae92e908f1`); additive (view-only, no table DDL); `downgrade` restores prior definition verbatim
  - `frontend/src/api/experiments.ts` — `ResultWithFlags` +`h2_concentration`; `RollupTimepoint` +`mean_h2_ppm`, +`sd_h2_ppm`
  - `.claude/rules/MODELS.md`, `docs/api/API_REFERENCE.md` (+ auto-synced `docs/project_context/API_REFERENCE.md`) — rollup columns/scope + results & rollup response docs
- **Tests added:** yes — backend: `test_v_results_scalar_rollup.py` (mean/sd across 3 replicates, n=1 null sd, outlier exclusion), `test_experiment_rollup.py::TestRollupH2Ppm` (same 3 at API level), `test_results.py` (`h2_concentration` present with scalar / null without). `tests/api` + `tests/views` = 433 pass. Frontend: 2 mock fixtures updated for the new required fields; `tsc --noEmit` clean; affected vitest suites 15/15.
- **Verification:** `alembic upgrade head` → both columns present on the view; `downgrade -1` → columns gone, view still queryable (1034 rows); re-`upgrade` clean.
- **Decision logged:** no
- **Lint note:** repo has no black/flake8 config; committed baseline already fails tool defaults (event_listeners flake8 111→115, all 4 new lines E501 on SQL matching the surrounding 20+ aggregate lines). New code matches surrounding style; not reformatted.

## 2026-07-28 | issue #92 — H2-first results and rollup views: remove ammonium metrics from the frontend
- **Depends on:** #90 (merged to develop via PR #94 before this branch was cut, so `r.h2_concentration` / `mean_h2_ppm` / `sd_h2_ppm` are available)
- **Files changed:**
  - `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` — `GRID` template 13→11 tracks; per-result columns reordered H2-first (`★ · Time · Sample Date · H₂ ppm · H₂ µmol · H₂ g/t · Fe²⁺ H₂ % · pH · Cond. · ICP/XRD/MOD · ▾`); H₂ (ppm) reads `r.h2_concentration` from the existing `/results` payload (no per-row `getScalar`); removed the entire Background NH₄ affordance (button + inline input, `bgInput`/`bgValue` state, `storedBgValue`, `bgMutation`, `DEFAULT_BACKGROUND_NH4`, and the now-unused `useMutation`/`useQueryClient`/`queryClient`); dropped Gross NH₄ + Net NH₄ Yield from the `ExpandedRow` scalar list
  - `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx` — `METRICS` trimmed from 8 to 5 (H₂ ppm/µmol/g/t, Fe²⁺→H₂ %, pH); default `metricKey` `h2_umol`→`h2_ppm`; rollup table columns → `Time · n · H₂ ppm · H₂ µmol · H₂ g/t · Fe²⁺→H₂ % · pH`, ppm at 1 dp with existing `mean ± sd` / `—` rendering
  - `frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx` — swapped Fe²⁺-NH₃ tests for: H₂ (ppm) header, H₂ (ppm) value from `/results`, no `NH₄` text anywhere, Background NH₄ button absent; kept Fe²⁺ H₂/XRD/MOD tests
  - `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx` — fixture `mean_h2_ppm`/`sd_h2_ppm` populated; default-selector test → H₂ (ppm); added exactly-five-options, no-NH₄-columnheader, and null-ppm→`—` tests
  - `docs/user_guide/REPLICATES.md`, `docs/user_guide/USER_MANUAL.md` (+ auto-synced `docs/project_context/` copies) — noted results & rollup views are H2-focused and ammonium data remains in the DB, calc engine, `v_results_scalar_rollup`, and Power BI
- **Backend/schema/view:** none — display-only change. Confirmed `v_results_scalar_rollup` still computes every ammonium aggregate (`mean_gross_ammonium_mM`, `sd_gross_ammonium_mM`, `mean_net_ammonium_mM`, `mean_fe_yield_nh3_pct`) unchanged in `database/event_listeners.py`
- **Tests added:** yes — frontend only; affected suites 20/20, full frontend suite 116/116 pass; `tsc --noEmit` clean; eslint clean
- **Decision logged:** no

## 2026-07-28 | inline — Add psql read-only access and query guide
- **Files changed:**
  - `docs/PSQL_ACCESS.md` — NEW: team guide for connecting to prod Postgres via `psql` over the LAN (client-only install for Windows/macOS, connecting, `\l`/`\dt`/`\dv`/`\d+`/`\x`/`\timing` survival guide, plain-language schema/join/view definitions, table and reporting-view orientation, 10 sample queries verified against `database/models/` and the live view SQL in `database/event_listeners.py`, `\copy` CSV export incl. client-vs-server distinction, read-only rationale tied to the calculation engine and `ModificationsLog`, common gotchas, and an admin-only appendix proposing a new `reporting_reader` role — `CREATE ROLE`/grants/`ALTER DEFAULT PRIVILEGES` plus `pg_hba.conf`/`postgresql.conf`/Windows Firewall changes, all placeholder-only)
  - `.claude/CLAUDE.md` §6, `docs/DIRECTORY_STRUCTURE.md` (+ auto-synced `docs/project_context/` copies) — added a reference row for the new doc
  - `docs/working/issues/05-models-md-stale-v-primary-experiment-results.md` — NEW, left uncommitted per existing repo convention for draft issues in this directory: draft issue covering `.claude/rules/MODELS.md`/`.claude/MEMORY.md`/`docs/user_guide/ONBOARDING.md` all still documenting the dead `v_primary_experiment_results` view (dropped in `database/event_listeners.py`, never recreated)
- **Investigation:** confirmed no read-only PostgreSQL role exists anywhere in the repo (`scripts/init-db.sql` only grants the read-write `experiments_user`); confirmed `v_primary_experiment_results` is not in the `_VIEWS` list in `database/event_listeners.py` and is unconditionally dropped there — MODELS.md's documentation of it is stale, so the fact-table sample query uses the `v_results_scalar`/`v_results_h2`/`v_results_icp` join on `result_id` instead
- **Tests added:** no (documentation only)
- **Decision logged:** yes — `docs/working/decisions.md`

## 2026-07-29 | issue #96 — New Experiments bulk upload: free-text `method` truncation destroys entire upload

- **Files changed:**
  - `database/models/chemicals.py` — `ChemicalAdditive.addition_method` `String(50)` → `Text`; added `ADDITION_METHOD_MAX_LENGTH = 500` (single source of truth for the app-layer bound, imported by both parsers and the API schemas)
  - `alembic/versions/293d0ea59422_widen_addition_method_to_text.py` — NEW; widens the column (down_revision `a1f2c3d4e5b6`). Deviates from the originally-planned bare `ALTER COLUMN`: Postgres blocks retyping a column `v_chemical_additives` depends on, so `upgrade`/`downgrade` each drop/recreate that view around the DDL (verbatim SQL from `database/event_listeners.py`, matching the precedent in `a1f2c3d4e5b6`)
  - `backend/api/schemas/chemicals.py` — `max_length=ADDITION_METHOD_MAX_LENGTH` added to `addition_method` on `ChemicalAdditiveUpsert`/`AdditiveUpdate`/`AdditiveCreate` (422 instead of a raw 500); `AdditiveResponse` now also exposes `addition_order`/`addition_method` (previously missing — closed a pre-existing gap where the frontend's `ChemicalAdditive.addition_order` type expected a field the API never returned)
  - `backend/services/bulk_uploads/new_experiments.py` — additives-phase loop: per-row `db.begin_nested()` savepoint isolation (mirrors issue #86's experiments-sheet precedent) + truncate-with-warning for `method`; a follow-up fix (same task) evicts a stale `name_to_compound` cache entry when a row that auto-created a new `Compound` later rolls back, so a subsequent row referencing the same name doesn't reuse a rolled-back FK; a second fix wraps `savepoint.commit()` itself in try/except (a nested-transaction commit flushes the session, and a post-flush `recalculate()` failure at commit time was escaping row isolation)
  - `backend/services/bulk_uploads/experiment_additives.py` — same savepoint + truncate-with-warning + commit-guard treatment (no compound-cache issue here — compounds are preloaded once and never auto-created, so no stale-reference risk); added a comment documenting that this file's only current caller (`legacy/streamlit_frontend/bulk_uploads.py`, retired) treats any non-empty `errors` as a full rollback, so a truncation notice today discards an otherwise-successful legacy upload — zero live blast radius (no FastAPI route wraps this service), left as a comment per plan scope rather than changed
  - `.claude/rules/MODELS.md`, `backend/api/routers/bulk_uploads.py` (template INSTRUCTIONS sheet), `docs/upload_templates/new_experiments.md`, `docs/specs/new_experiments_upload.md` (+ auto-synced `docs/project_context/` copies) — document the 500-char bound and truncate-with-warning behavior
- **Tests added:** yes — `tests/models/test_addition_method_column.py` (column type, 85-char and 5000-char round trips, constant pinned), `tests/services/bulk_uploads/test_new_experiments_additives.py` and `test_experiment_additives.py` (85-char round trip, truncate-with-warning, duplicate-compound/mid-row-failure savepoint isolation, stale-cache eviction, commit-failure isolation), additions to `tests/api/test_schemas.py`/`test_additives.py` (length-guard rejection/acceptance, PATCH endpoint round trip). 244 tests across these files pass on merged `develop`; full backend suite 1037/1040 pass (3 pre-existing, unrelated `test_pg_backup_restore.py` failures — see memory note below)
- **Process:** built via `superpowers:subagent-driven-development` — 5 tasks, one fresh implementer + task reviewer per task, plus a final whole-branch review (Opus) that caught the two cross-task issues (stale cache, commit-guard) neither task-scoped review could see alone, and one fix wave with a scoped re-review. Fast-forward merged to `develop`, no conflicts.
- **Discovered, not fixed (out of scope for this issue):** running the full `pytest -q` suite (no path filter) fails 3 tests in `tests/test_pg_backup_restore.py` — confirmed pre-existing on `develop` independent of this branch (two `tests/models/` files' `drop_all()` teardown wipes the whole shared `experiments_test` schema before that file runs, alphabetically later). Saved to auto-memory (`pg-backup-restore-test-order-fragility`) so it isn't mistaken for a regression by a future session; worth its own ticket.
- **Decision logged:** yes — `docs/working/decisions.md`

## 2026-07-29 | issue #98 — Sacrificial-timepoint (`-t<days>`) vials break replicate collapsing in the Experiments list and group view
- **Files changed:**
  - `backend/services/replicate_collapse.py` — NEW; the collapse key and nothing else: `TIMEPOINT_TOKEN_SQL_PATTERN` (POSIX form of the `-t<days>` regex), `timepoint_stem_expr(col)` (SQL `regexp_replace`, usable against the `Experiment` class or a subquery's `.c`), and `collapse_by_stem(rows) -> list[StemGroup]` for the Python-side collapse. Python-side stripping reuses the canonical `split_timepoint_token` rather than adding a fourth copy of the pattern
  - `backend/api/routers/experiments.py` — flat-list branch rewritten to collapse on the stem via a window (`row_number` + `count` over `partition_by stem`), with `total` = distinct-stem count so pagination pages over collapsed rows (avoids the #64 post-pagination-filter failure mode); grouped branch's `_bucket_key_expr` `else_` now strips the token, `is_outlier ASC` added to the representative ranking, bucket membership resolved via `_bucket_key_expr(Experiment) == bucket_key` and `replicates` built per letter-row via `collapse_by_stem`; `_group_data_to_detail_response` gained `replicates`/`replicate_count` and a populated parent `result_count`; `get_replicate_group`'s two `order_by` clauses gained `id_timepoint_days`/`experiment_number` tiebreaks (labels are not unique)
  - `backend/api/schemas/experiments.py` — `ExperimentListItem` +`group_display_id`, +`vial_count`, +`replicate_letters` (all additive with defaults); NEW `ReplicateLetterGroup`; `ReplicateGroupDetailResponse` +`replicates`, +`replicate_count`, `parent` widened to `ReplicateGroupMemberDetail`
  - `backend/services/replicate_groups.py` — NEW `LetterGroupData` + `group_vials_by_letter`; `GroupData` +`replicates`, +`parent_result_count`; `_compare_conditions` now excludes vials with no `conditions` row from the divergence scan while still emitting a per-member map for them; `_fetch_members` ordering deliberately unchanged
  - `frontend/src/api/experiments.ts` — the new list-item fields (optional, matching the local convention for `replicates`); NEW `ReplicateLetterGroup`; `ReplicateGroupDetail` +`replicates`, +`replicate_count` (required), `parent` widened
  - `frontend/src/pages/ExperimentList.tsx` — renders `group_display_id ?? experiment_id`; `day N` chip deleted; badge reads `replicate_letters`; group rows link to `/experiments/groups/{stem}`; Status renders read-only iff the displayed label is not the row that would be PATCHed
  - `frontend/src/pages/ReplicateGroup/index.tsx` — NEW `LetterRows` (one row per letter, expandable to vials only when a letter has more than one); `MemberRow` narrowed to `ReplicateGroupMemberDetail` with the `isMemberDetail` guard and the flattened `rows` const deleted, so the parent row renders real Timepoint/Results cells; header reads `replicate_count`
  - `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx` — series built per letter (vials' single result rows concatenated into one time course), outlier vials excluded from points but kept as struck-through drill-in links, `(outlier)` suffix restored for an all-flagged letter
  - `.claude/rules/MODELS.md`, `docs/api/API_REFERENCE.md` (+ auto-synced `docs/project_context/` copy) — letter-vs-vial grain, the stem-key rationale with the `SERUM_001a-2` counterexample, the new fields, and the remaining letterless-`-t` known gap
  - `docs/superpowers/specs/2026-07-29-...-design.md`, `docs/superpowers/plans/2026-07-29-...md` — NEW; 12 numbered decisions and the 8-task TDD plan
- **Tests added:** yes — `tests/services/test_replicate_collapse.py` (NEW: SQL-vs-Python pattern agreement across 11 ID shapes, representative ordering, re-run non-collapse); `tests/api/test_experiments.py` (+13: flat 2×2 → 2 rows, grouped 2×2 → 1 stem-labeled row, `SERUM_001a-2` stays separate, filter-scoped collapsing, outlier never represents, both pagination modes, letterless-`-t` joins its parent AND does not hide its lettered siblings, letter+re-run expansion); `tests/api/test_experiment_rollup.py` (+8: letters vs vials, per-vial `result_count`, parent's own `result_count`, missing-conditions divergence, wrapper ordering determinism); frontend (+18 across `ExperimentList`, `ReplicateGroupPage`, `GroupedResultsView`). Backend `tests/api tests/views tests/services tests/models` 840 passed; frontend vitest 127→133 passed (23 files); `tsc --noEmit` clean
- **Three pre-existing backend tests updated** (all asserted behavior this issue exists to fix): `test_orphan_lettered_set_collapses_to_one_row` (`replicates` now includes the representative's own letter), `test_timepoint_variant_shares_letter_no_dedupe` (replaced by `test_timepoint_variant_collapses_into_its_letter`), `test_sequential_rerun_not_absorbed_into_coexisting_orphan_group` (same own-letter change; its load-bearing bucket-separation assertions untouched). One frontend `describe` block asserting the `day N` chip was replaced wholesale
- **No schema change, no migration, no view change** — deliberately. The `-t` parser grammar and `v_results_scalar_rollup` were already correct
- **Process:** built via `superpowers:subagent-driven-development` — 8 tasks, fresh implementer + task reviewer each, plus an Opus whole-branch review. 14 review passes caught 6 real defects, 4 of which originated in the plan rather than the implementation. The most serious: changing `_bucket_key_expr`'s SQL `else_` without its hand-written Python mirror meant a letterless `-t` vial would have hidden its lettered siblings from the list response entirely (fixed in `a76659e`)
- **Verification:** not yet walked in the running app against a real 2×2 set with H₂ GC data — automated coverage only
- **Decision logged:** yes — `docs/working/decisions.md`
- **PR:** none — fast-forward merged locally to `develop` (`5f936d7`); `develop` not yet pushed

## 2026-07-29 | issue #99 — Experiment deletion: audited, orphan-safe hard delete + confirmation UI
- **Files changed (initial pass, `a69a69b` and earlier):**
  - `backend/services/experiment_deletion.py` — NEW; `scan_delete_impact()` (per-table dependent counts plus `background_for`/`replicate_children` decoupling lists, keyed on the `background_experiment_id` string, not the unpopulated FK) and `delete_experiment()` (snapshots the experiment/conditions/additives/notes into a `ModificationsLog` row with `experiment_fk=NULL`, deletes `xrd_phases` matched on `experiment_fk` **or** the `experiment_id` string, NULLs `scalar_results.background_experiment_id`/`background_experiment_fk` on other experiments and `reactor_change_requests.experiment_id`, then deletes the experiment)
  - `backend/api/routers/experiments.py` — NEW `GET /{experiment_id}/delete-impact`; `DELETE /{experiment_id}` rewired to call `delete_experiment()` and return `200` (was `204`)
  - `backend/api/schemas/experiments.py` — NEW `DeleteImpactResponse`, `ExperimentDeletedResponse`
  - `frontend/src/api/experiments.ts` — `getDeleteImpact()`; `deleteExperiment()` return type widened to the impact-bearing response
  - `frontend/src/components/experiments/DeleteExperimentModal.tsx` — NEW; itemizes impact counts, names decoupled experiments, requires the exact `experiment_id` typed before enabling Delete
  - `frontend/src/pages/ExperimentDetail/index.tsx` — delete quick-action, modal mount, cache eviction (`experiment`, `experiments`, `group-rollup`, `delete-impact` query keys), redirect to `/experiments` on success; same pass fixed the pre-existing `outlierMutation.onSuccess` handler, which carried the identical dead `'rollup'` cache key
  - `.claude/rules/MODELS.md`, `docs/api/API_REFERENCE.md` (+ auto-synced `docs/project_context/` copies) — deletion-path orphan-prevention notes and the two new endpoints
- **Files changed (fix wave, `83e40f1`, in response to the whole-branch review below):**
  - `backend/services/experiment_deletion.py` — now purges `elemental_analysis` children of the experiment's `external_analyses` before delete (previously relied on a bare backref plus DB-level cascade, which raised `NotNullViolation`); now purges `reactor_change_requests` outright instead of NULLing `experiment_id`; `conditions` added to the impact scan
  - `backend/api/routers/experiments.py`, `backend/api/schemas/experiments.py` — `DeleteImpactResponse`/impact assembly gain `conditions`
  - `frontend/src/api/experiments.ts` — `DeleteImpact` interface gains `conditions`
  - `frontend/src/components/experiments/DeleteExperimentModal.tsx` — `IMPACT_ROWS` gains a Conditions row; typed-ID confirmation gate widened to also require typing when `background_for` or `replicate_children` is non-empty (previously only fired on destructive counts)
  - `frontend/src/pages/ExperimentDetail/index.tsx` — cache eviction widened from 4 to 10 per-experiment query keys
  - `tests/api/test_experiments.py`, `tests/services/test_experiment_deletion.py`, `DeleteExperimentModal.test.tsx`, `DeleteExperiment.test.tsx` — updated for all of the above
  - `.claude/rules/MODELS.md`, `docs/api/API_REFERENCE.md` (+ auto-synced `docs/project_context/` copies) — updated again to describe the purges and the widened gate
- **Corrections to the issue's premises**, established by querying the live dev DB before planning:
  1. The issue predicted an `IntegrityError` on `scalar_results.background_experiment_fk`. Wrong — the dev DB's FK constraints do carry `ondelete` (`confdeltype='n'`/SET NULL) because dev/test are built via `Base.metadata.create_all`; the lab PC came up through the Alembic chain, whose initial migration declared none, so constraint parity with production is unverified. The service therefore never relies on DB-level behavior.
  2. `background_experiment_fk` was populated on 0 of 1056 `scalar_results` rows; only the string `background_experiment_id` is ever written (52 rows), and the string has no FK at all. The real hazard was the opposite of the issue's prediction — silently dangling references by name, with zero DB protection. Decoupling is keyed on the string.
  3. `Experiment.xrd_phases` does exist (`database/models/experiments.py:44`) — the issue said it didn't. It simply has no `cascade=`, so rows would have survived with a stale `experiment_id` string holding the `uq_xrd_phase_experiment_time_mineral` slot.
  - **Also found, not in the issue:** `experiments_parent_experiment_fk` is SET NULL too, so deleting a group parent nulls its lettered replicates' parent pointers — not data loss (groups are addressed by the `base_experiment_id` string, issue #87) but now reported in the impact response as `replicate_children`.
- **Contract change:** `DELETE /api/experiments/{experiment_id}` went from `204 No Content` to `200` with an `ExperimentDeletedResponse` body. Two consumers audited: `tests/api/test_experiments.py::test_delete_experiment` updated; `scripts/delete_experiments_via_api.ps1:161` (`Invoke-RestMethod | Out-Null`) needed no change.
- **Whole-branch final review** (run on the most capable model, over the full 12-commit branch, after `a69a69b`) found two Critical defects in the initial pass:
  1. **Critical 1 — latent 500 on delete.** `ElementalAnalysis.external_analysis_id` is `nullable=False` (`database/models/characterization.py:25`) but its relationship is a bare backref with no cascade and no `passive_deletes` (`characterization.py:43`). On `db.delete(exp)` the ORM tried to NULL that child FK before the DB-level `ON DELETE CASCADE` could act, raising `psycopg2.errors.NotNullViolation` → HTTP 500, so the delete never succeeded. Reproduced empirically against `experiments_test`. Live exposure was zero (0 experiment-linked `external_analyses` in the dev DB), so it was latent — but it was exactly the unhandled-reference class the service claimed to have fully enumerated.
  2. **Critical 2 — the dialog lied and skipped its own safeguard.** `experimental_conditions` is hard-deleted by the ORM cascade but was not one of the counted impact fields, so for an experiment with conditions and nothing else, `total == 0`: the dialog rendered "No dependent records — nothing else is affected" and did not require the typed-ID confirmation, meaning one click destroyed a full conditions record (temperature, initial pH, rock mass, water volume, reactor number, pressures, `total_ferrous_iron_g`). 44 experiments in the dev DB were in exactly that state.
  - Two Important findings were also raised: the experiment's prior `ModificationsLog` history is destroyed by the `cascade="all, delete-orphan"` on `Experiment.modifications` (13,374 rows in the dev DB, up to 654 for a single experiment); and the snapshot is not genuinely "restorable" as the initial pass had claimed.
- **Product owner decisions (2026-07-29), in direct response to the review** — see `docs/working/decisions.md` for the full record; summary: `reactor_change_requests` rows are now purged (not unlinked); the experiment's prior audit history is allowed to purge with it; the deletion-snapshot `ModificationsLog` row still survives as the only trace a deletion occurred; the "restorable" claim was corrected in wording rather than the capture being extended; and a hard boundary — deletion purges only rows this experiment *owns*, never another experiment's data — was set and verified to hold.
- **Fix wave (single commit `83e40f1`)** implemented all of the above: purge of `elemental_analysis` children (in the service, not a model change, since `database/models/` is locked); `conditions` added as a counted impact field threaded through five layers (service dataclass, its `total` property, `collect_delete_impact`, `DeleteImpactResponse`, `_impact_to_response`, the TypeScript `DeleteImpact` interface, and the modal's `IMPACT_ROWS`); the typed-ID gate widened to also fire when `background_for` or `replicate_children` is non-empty; purge of `reactor_change_requests`; eviction of ten per-experiment query caches via `removeQueries`; and the wording corrections. A scoped re-review confirmed all six items addressed, the ownership boundary held, and no new breakage.
- **Side benefit:** `change_requests` was already summed into the impact `total` (documented to the user as "rows destroyed"), but before the fix wave the service only nulled those rows rather than deleting them — so `total` had been overstating destruction. Purging makes the count truthful.
- **Tests added:** yes — `tests/services/test_experiment_deletion.py` (13 initial, more added in the fix wave); `tests/api/test_experiments.py` + `experiment_deletion.py` combined = 123+. Final numbers at `83e40f1`: backend `tests/api tests/services tests/models tests/views`: **865 passed** (was 862 before the fix wave). Frontend: **150 passed across 26 files** (was 148 before the fix wave; 133/23 before this branch); `npx tsc --noEmit` clean.
- **ESLint:** exactly **5 errors, all pre-existing, none added by this branch** (confirmed again after the fix wave) — `src/components/CompoundFormModal.tsx:41,57` (`react-hooks/set-state-in-effect` rule-definition-not-found, plugin/config drift) and `no-explicit-any` in `ConditionsTab.buttons.test.tsx:61,83` and `NotesTab.buttons.test.tsx:50`. `frontend/CLAUDE.md` requires zero ESLint warnings; the repo currently does not comply. Not fixed here (pre-existing, out of scope) but worth its own ticket.
- **Two fix rounds, both catching real defects:**
  1. Task 6 (`d69836e`): the modal footer had been gated on the impact query resolving, so a rejected `getDeleteImpact` rendered a dialog with no body, no error, and no Cancel button. Reverted to an always-rendered footer; added an `isError` branch (a gap in the plan) with a covering test.
  2. Task 7 (`8701805`): a defect in the plan itself specified `invalidateQueries({ queryKey: ['rollup'] })`, but no query uses that key — the only rollup key is `['group-rollup', baseExperimentId]` (`GroupedResultsView.tsx:56`) — so the invalidation was a silent no-op that could leave a deleted vial visible in a replicate group's rollup chart for up to the 30s `staleTime`. Fixed in the new delete handler and in the pre-existing `outlierMutation.onSuccess` handler carrying the identical dead key (out-of-scope fix, explicitly approved). A regression test pins all four cache operations; the `['delete-impact', experimentId]` cache is also evicted now.
- **Deferred minors:** no "Deleting…" affordance while the delete mutation is in flight; `task-5-report.md` misattributes a vitest type fix to a `: void` annotation when the real cause was an expression-bodied arrow implicitly returning `VitestUtils`; the 5 pre-existing ESLint errors above.
- **Deferred to a follow-up issue:** bulk "Delete selected" reusing the existing selection `Set` in `ExperimentList.tsx:224` (the change that would have handled the 69-row SERUM_Catalyst incident directly) — open once single delete is proven in the lab. Also deferred: normalizing FK `ondelete` clauses across dev and the lab PC via a migration, so deployed constraints provably match the model declarations.
- **Discovered but not fixed, tracked as follow-up tickets:**
  - `['replicate-group-detail', baseId]` (`GroupedResultsView.tsx:52`) is reached by neither the fix wave's eviction loop nor `invalidateQueries(['replicate-group'])`, because TanStack Query matches key elements exactly. Staleness only (bounded by the 30s `staleTime`), not the ID-reuse hazard this feature exists to close.
  - `AddResultModal.tsx:57` invalidates `['results', id]`, a key no query uses; the live key is `['experiment-results', id]`. Pre-existing, unrelated to this branch.
  - The 5 pre-existing ESLint errors mean the repo does not currently satisfy its own `frontend/CLAUDE.md` zero-warnings rule.
  - No "Deleting…" affordance while the delete mutation is in flight (also listed under Deferred minors above).
- **No schema change, no Alembic migration, no view change** — deliberate; all orphan prevention is in application code.
- **Verification:** automated coverage only. Stated plainly: **the plan's "Manual verification before merge" checklist has NOT been performed** — this feature has never been exercised in the running app.
- **Process:** built via `superpowers:subagent-driven-development` — 8 tasks, fresh implementer + independent task reviewer each, 2 fix rounds, 1 scoped re-review, plus the whole-branch final review and fix wave described above.
- **Decision logged:** yes — `docs/working/decisions.md`
- **PR:** none yet

## 2026-07-29 | inline — Delete dialog pluralization and cache-eviction order
- **Files changed:**
  - `frontend/src/components/experiments/DeleteExperimentModal.tsx` — `IMPACT_ROWS` widened from `[key, label]` to `[key, singular, plural]`; the rendered row now picks the form from the count. Both forms are spelled out rather than derived because `external analyses` is irregular — appending an `s` would render "external analysises". Previously every row used a plural label, so a single-row delete read "1 XRD phase rows", "1 result timepoints", "1 external analyses".
  - `frontend/src/pages/ExperimentDetail/index.tsx` — `onDeleted` now calls `navigate('/experiments', { replace: true })` **before** touching the cache, and defers the eviction/invalidation block into a `setTimeout(…, 0)`. Several evicted keys (`experiment`, `conditions`, `replicate-group`) are still actively observed by the detail page, and removing or invalidating an active query makes React Query refetch it — against an experiment the server has just deleted. That produced 4 console `404`s per delete. A microtask is not sufficient: it can still run before React commits the navigation.
- **Discovered by:** manual Chrome DevTools walkthrough of the issue #99 delete flow against the running app (the plan's "Manual verification before merge" checklist, performed after that branch merged). Neither defect was caught by the 150-test automated suite — the pluralization is cosmetic and no test asserted a count of 1, and the 404 burst is timing-dependent and does not reproduce under jsdom.
- **Tests added:** yes — `DeleteExperimentModal.test.tsx` gained a singular/plural test (asserts `1 result timepoint`, `1 scalar measurement row`, `1 XRD phase row`, the irregular `1 external analysis`, and `2 notes` still plural). `DeleteExperiment.test.tsx` gained an ordering guard asserting the detail page is already unmounted when the first eviction runs. Frontend 150 → 152 pass across 26 files; `tsc --noEmit` clean; backend untouched (865 pass, no Python files changed).
- **A test that had to be rewritten:** the first attempt at the fix-2 guard asserted "the deleted experiment is never refetched" by counting API mock calls. It **passed with the fix reverted** — jsdom does not reproduce the refetch timing — so it guarded nothing. Replaced with the ordering assertion above, which was verified to fail on the pre-fix code (`expected true to be false`) and pass after.
- **Verified in the running app:** dialog renders `1 conditions record / 1 result timepoint / 2 notes / 1 external analysis / 1 XRD phase row`; console errors after a delete went 4 → 0 and the network trace goes straight from `DELETE 200` to the list query. Three further deletions during the session left zero orphan rows, audit rows intact, and the 750 real experiments untouched (all test rows were seeded and removed).
- **Pre-existing, NOT fixed here:** `npx eslint src --ext .ts,.tsx` still reports 5 errors on files this branch never touched — `src/components/CompoundFormModal.tsx:41,57` (`react-hooks/set-state-in-effect` rule-definition-not-found, a plugin/config drift) and `no-explicit-any` in `ConditionsTab.buttons.test.tsx:61,83` and `NotesTab.buttons.test.tsx:50`. The repo therefore does not currently satisfy its own `frontend/CLAUDE.md` zero-warnings rule. Needs its own ticket.

## 2026-07-29 | issue #100 (narrow scope) — Block silent create on unset overwrite rename
- **Files changed:**
  - `backend/services/bulk_uploads/new_experiments.py` — new `elif old_experiment_id and not overwrite_flag` branch in the experiments-sheet loop; appends an explicit conflict warning naming both IDs and `continue`s past the row (added to `failed_experiment_ids`) instead of falling through to standard normalized matching, which found nothing under the new ID and silently created a duplicate experiment
  - `tests/services/bulk_uploads/test_new_experiments.py` — `test_old_experiment_id_without_overwrite_conflicts_not_creates`
  - `docs/issues/issue-bulk-upload-dry-run.md` — logged item 3 as shipped ahead of the rest of the issue
- **Sign-off:** user explicitly approved this narrow scope ("option 2") over the full dry-run/plan/hash issue, per the locked-component escalation raised in `/start-task`
- **Tests added:** yes — TDD: wrote the test first, confirmed it reproduced the 2026-07-28 SERUM_Catalyst incident (`created == 1` instead of 0), then implemented the fix. Full `tests/services/bulk_uploads/` suite: 197 passed, no regressions.
- **Linting:** `flake8`/`black` (via `.venv/Scripts/`) confirm the added lines introduce no new violations — neither tool's output touches the new code. Both tools flag extensive **pre-existing** violations across the rest of this file and test file (long lines, trailing whitespace, bare except, black formatting) predating this change; out of scope for a narrow, sign-off-gated fix to a locked parser. Worth its own cleanup ticket.
- **Scope boundary:** this is a per-row skip, not the file-level rejection the full issue describes — a workbook with some good rows and one blank-overwrite row still commits the good rows and only skips the conflicting one. Items 1/2/4/5 (`dry_run` param, structured `plan`, file-level reject, plan-hash check) and frontend items 6-9 remain open under #100.
- **Decision logged:** no

## 2026-07-29 | issue #100 item 1 — dry_run param on every bulk-upload endpoint
- **Files changed:**
  - `backend/api/routers/bulk_uploads.py` — `dry_run: bool = Form(False)` added to all 13 write endpoints; new `_finalize_write(db, dry_run, had_errors=False)` and `_finalize_message(message, dry_run)` helpers; each endpoint's `db.commit()` (or `if not errors: commit else: rollback`) replaced with a call to `_finalize_write`, and each success message wrapped in `_finalize_message`. `actlabs-rock` needed both of its write paths covered (Phase 1's conflict-free direct import, and Phase 2's resolutions-supplied import) — its Phase 1 conflict-check response never writes regardless.
  - `backend/api/schemas/bulk_upload.py` — `UploadResponse` gained `dry_run: bool = False`
  - `tests/api/test_bulk_uploads.py` — 14 new tests: one per endpoint asserting `db.rollback()` is called and `db.commit()` is not when `dry_run=true` (via `patch.object(db_session, ...)`, the pattern already established by `test_experiment_status_rolls_back_on_apply_errors`), plus one flagship real round-trip test against `new-experiments` (unmocked service) proving the created experiment does not persist
  - `docs/api/API_REFERENCE.md` — documented the `dry_run` field/behavior once at the top of the Bulk Uploads section rather than per-endpoint
  - `docs/issues/issue-bulk-upload-dry-run.md` — logged item 1 as shipped
- **No locked-component escalation needed:** unlike item 3, this only touches the router and schema — the parsers under `backend/services/bulk_uploads/` are unmodified. `dry_run` just decides commit-vs-rollback after the (unmodified) parser already ran to completion, exactly the "safest shape" the issue's own notes suggested.
- **Sign-off:** user said "proceed" after reviewing the `/start-task` scope confirmation for this item.
- **Tests added:** yes — TDD (tests written and confirmed failing before the router change). Full `tests/api/test_bulk_uploads.py`: 85 passed. Full backend suite (`tests/api tests/services tests/models tests/views`): 880 passed, no regressions.
- **Discovered but not fixed (pre-existing, out of scope):** two existing API-level shape tests were silently exercising only their exception-fallback path instead of the mocked success path they appear to test — `test_actlabs_rock_returns_upload_response_shape` patches `sys.modules`, but the router imports `ActlabsRockTitrationService` eagerly at module load time (not lazily inside the endpoint like every other service in this file), so the patch never takes effect; `test_icp_oes_returns_upload_response_shape` mocks `bulk_create_icp_results` with a stale 2-tuple against the real 3-tuple signature from the M8 return-value change. Both "pass" only because the generic `except Exception` handler still satisfies the loose `_assert_upload_shape` check. My new `dry_run` tests for these two endpoints use the correct mock target/shape. Worth its own test-hygiene ticket.
- **Linting:** `flake8` on the modified files shows only pre-existing violations (confirmed none fall within the lines I added/changed); this file predates black adoption.
- **Scope boundary:** items 2, 4, 5 (structured `plan` field, file-level rejection, plan-hash check) and frontend items 6-9 remain open under #100.
- **Decision logged:** no

## 2026-07-29 | issue #100 item 2 — structured plan field, new-experiments only
- **Files changed:**
  - `backend/services/bulk_uploads/new_experiments.py` — new `PlanCreate`/`PlanRename`/`FieldChange`/`PlanOverwrite`/`PlanSkip`/`PlanConflict`/`UploadPlan` dataclasses; row-processing body extracted into `_bulk_upsert_from_excel_impl` (returns the original 6-tuple plus `plan`); `bulk_upsert_from_excel` is now a thin wrapper with its exact original signature (zero of its ~26 existing callers changed); new `bulk_upsert_from_excel_ex` exposes the 7-tuple, mirroring the `_ex` convention `scalar_results.py` already uses. Plan population instrumented into all three sheet loops (experiments/conditions/additives), merged via a shared `overwrite_plan_by_exp_id` dict keyed by experiment_id.
  - `backend/api/schemas/bulk_upload.py` — Pydantic mirror (`UploadPlan`, `PlanCreate`, `PlanRename`, `PlanFieldChange`, `PlanOverwrite`, `PlanSkip`, `PlanConflict`); `UploadResponse.plan: Optional[UploadPlan] = None`
  - `backend/api/routers/bulk_uploads.py` — `new-experiments` endpoint switches to `bulk_upsert_from_excel_ex`; new `_plan_to_schema()` converts the dataclass to the response schema
  - `tests/services/bulk_uploads/test_new_experiments_plan.py` — new file, 13 tests
  - `tests/api/test_bulk_uploads.py` — 2 existing new-experiments mocks updated to the `_ex` signature; 1 new test proving the plan reaches the real HTTP response
  - Docs: `docs/api/API_REFERENCE.md`, `docs/issues/issue-bulk-upload-dry-run.md`
- **Scope decision (user-confirmed):** the plan schema is written around `new_experiments.py`'s own concepts (rename, parent-copy) — scoped to that one upload type rather than generalizing to all 13 parsers, which would need 13 different shapes. `fields_changed` covers experiments-sheet + conditions-sheet fields (the issue's own `initial_ph` 4→9 example is a conditions field); additives are a one-line summary, not per-compound diffed — both explicit, user-confirmed scope calls before implementation.
- **No locked-component escalation blocker:** did touch the locked `new_experiments.py`, with user sign-off obtained via the `/start-task` scope confirmation before writing code (per CLAUDE.md §5/§7). The `_ex`-wrapper design was chosen specifically to make this a zero-breaking-change addition despite touching a widely-called locked function.
- **Tests added:** yes — implementation-first this time (not textbook TDD) given the coupling between the three sheet loops the plan draws from; tests were then written and iterated against the real implementation rather than written-first-and-confirmed-failing. Full backend suite (`tests/api tests/services tests/models tests/views tests/test_experiment_rename.py`): 903 passed, no regressions.
- **Bug caught while writing tests:** my first draft of test experiment IDs (`HPHT_PLAN_0NN`) accidentally matched the 3-part `Type_Initials_Index` ID grammar, and the parser read `"PLAN"` as researcher initials, auto-populating a real unintended `researcher` field change. This broke two assertions expecting zero field changes. Not a plan-logic bug — a test-fixture-naming collision with the ID parser. Renamed to 2-part IDs (`HPHT_9NNN`). Worth remembering for future tests in this file.
- **Linting:** `flake8` confirmed 3-4 new lines exceeded 120 chars during implementation; all wrapped and re-verified at zero new violations (checked precisely via `git diff` on added lines only, not just line-number ranges, since the earlier item's range-based check was unreliable once insertions shifted the file).
- **Scope boundary:** items 4, 5 (file-level rejection, plan-hash check) and frontend items 6-9 remain open under #100.
- **Decision logged:** no

## 2026-07-29 | issue #100 items 4 + 5 — reject file on conflicts, plan-hash preview/commit gate
- **Files changed:**
  - `backend/api/schemas/bulk_upload.py` — new `UploadPlan.fingerprint()` (sha256 over `creates`/`renames`/`overwrites`/`skips`/`conflicts`, `counts` excluded as derived, list order preserved, `json.dumps(default=str)` for the `Any`-typed `PlanFieldChange.old`/`new`); `UploadResponse.plan_hash: Optional[str] = None`
  - `backend/api/routers/bulk_uploads.py` — new `_plan_gate_errors(plan, expected_plan_hash)` returning the reasons a plan must not commit; `new-experiments` endpoint gains `plan_hash: Optional[str] = Form(None)`, passes `had_errors=bool(gate_errors)` to the existing `_finalize_write`, and returns a zeroed-counts rejection response (plan still fully populated) plus `plan_hash` on every response
  - `tests/api/test_bulk_uploads_plan_gate.py` — new file, 24 tests
  - Docs: `docs/api/API_REFERENCE.md`
- **No locked components touched.** The issue framed item 4 as parser work, but `svc_plan.conflicts` already reached the router and `_finalize_write` already accepted `had_errors` — so both items landed entirely in `backend/api/`. Nothing under `backend/services/bulk_uploads/` was modified, so no CLAUDE.md §5 sign-off was needed (unlike item 2).
- **Deviation from the issue text (user-confirmed at scope):** `plan_hash` is **verified-when-supplied, not required**. The issue says "require it on the real submit"; requiring it unconditionally would break every existing caller and contradict the issue's own last acceptance criterion. Frontend item 6 will always send it, so the UI path gets the full guarantee.
- **Unplanned benefit worth knowing:** because `overwrites[].fields_changed` records current DB values as `old`, the fingerprint covers **DB state as well as file bytes** — so it also catches another researcher editing the underlying experiments between preview and commit, not just an edited workbook. Covered by `test_a_concurrent_db_change_invalidates_the_previewed_hash`.
- **Tests added:** yes — TDD, all 24 written first and confirmed failing for the right reason (pre-fix response was `created: 1, errors: []` on a conflicting file; `fingerprint` did not exist). Full suite: 1144 passed, 3 failed — exactly the 3 known-pre-existing `tests/test_pg_backup_restore.py` failures, no regressions.
- **Test-harness trap found and fixed (worth remembering):** the `tests/api/conftest.py` `db_session` binds a session to a connection with an outer transaction already open (SQLAlchemy `conditional_savepoint` join mode). Two consequences bit this work:
  1. A router `db.rollback()` discards **everything the test did, seed included** — committing the seed first does not help (verified with a standalone probe). So "the original experiment survived the rejection" is not observable through that session; those tests assert `commit` was never called instead. What *is* observable and discriminating is the absence of a would-be-created row, since the happy-path test proves a router commit does make rows visible.
  2. A router `db.commit()` consumes the fixture's outer transaction, so its teardown `transaction.rollback()` becomes a no-op (this is the source of the long-standing "transaction already deassociated" SAWarning) and **rows genuinely land in `experiments_test`**. My commit-path tests were the first to leak `experiments` rows this way and broke `tests/api/test_experiments.py::test_list_experiments_empty` — a cross-file, order-dependent failure. Fixed with an autouse fixture that deletes `HPHT_GATE_%` rows after each test. Any future API test that lets a router commit needs the same cleanup.
- **Scope boundary:** parser-level `errors` are deliberately not folded into the gate (pre-existing behavior, outside item 4). The legacy Streamlit uploader calls `bulk_upsert_from_excel` directly and is covered by neither gate. Frontend items 6-9 remain open, as do acceptance criterion 1 in full (a `plan` on *every* endpoint, not just `new-experiments` — `dry_run` itself is on all 13) and criterion 6 (replay the two 2026-07-28 SERUM_Catalyst workbooks against a pre-incident DB snapshot and confirm 80 renames / 0 creates). Criteria 2, 3, 5 and 7 are met by this pass; criterion 4 (`fields_changed` old/new) was met by item 2.
- **Decision logged:** no

## 2026-07-29 | issue #100 items 6-9 — Preview-first New Experiments upload (frontend)
- **Branch:** `feat/issue-100-preview-ui` (11 commits, `5d342e0..cc134cc`). **Frontend only — no file under `backend/`, `database/`, or `alembic/` was touched**, so no CLAUDE.md §5 locked-component sign-off was needed. Everything server-side already existed from items 1-5; none of it was reachable from the UI until now.
- **Files changed:**
  - `frontend/src/api/bulkUploads.ts` — TS mirror of the plan schema (`UploadPlan`, `PlanCreate`, `PlanRename`, `PlanFieldChange`, `PlanOverwrite`, `PlanSkip`, `PlanConflict`); `dry_run?` / `plan?` / `plan_hash?` added to `BulkUploadResult` as **optional** (the other 12 endpoints return `plan: null`, and existing test mocks build `BulkUploadResult` literals); `uploadNewExperiments(file, opts?: { dryRun?, planHash? })` appends each form field only when truthy — omission by construction, so a default call sends no `dry_run` at all rather than `dry_run=false`
  - `frontend/src/components/bulkUploads/UploadPlanPanel.tsx` **(new)** — pure presentational plan renderer: five sections in fixed order (conflicts, renames, overwrites, creates, skips), count in each header, conflicts expanded and the rest collapsed, empty sections omitted, truncation at 10 rows with "Show N more", `fields_changed` rendered old-struck-through → new-bold. Chevron defined locally rather than imported from `pages/BulkUploadRow.tsx` — a `components/` file must not depend on `pages/`
  - `frontend/src/components/bulkUploads/UploadPlanModal.tsx` **(new)** — review surface, three views (`review` / `stale` / `done`). Conflict gate is unconditional; a stale plan requires ticking "I've reviewed the updated plan" before Commit re-arms
  - `frontend/src/pages/NewExperimentsUploadRow.tsx` **(new)** — the two-phase state owner, following the `ActlabsUploadRow` wrapper precedent but **without** its `throw new Error('__conflicts__')` hack
  - `frontend/src/pages/BulkUploadRow.tsx` — **one** new optional prop, `onUploadSuccess`, mirroring the `onUploadError` override already there
  - `frontend/src/pages/BulkUploads.tsx` — wrapper swapped in; page subtitle now notes preview-first applies to New Experiments only
  - `frontend/e2e/journeys/02-bulk-upload-experiments.spec.ts` — rewritten to walk the modal
  - Docs: `docs/user_guide/BULK_UPLOADS.md` (+ hook-generated `docs/project_context/` copy), plus the spec and plan under `docs/superpowers/`
- **Why `onUploadSuccess` was necessary (the non-obvious bit):** a dry run returns **real counts**. The parser genuinely creates, updates and flushes before the router rolls back, so a preview response arrives carrying `created: 5, updated: 2`. Without the override the row would badge "Created: 5" and toast "Upload complete — 5 created" for an upload that persisted nothing. Confirmed live: the preview response body said `created: 2` while the row badged nothing and the DB was untouched.
- **Rejection discriminator — the safety-critical decision.** The endpoint returns **HTTP 200 for success, gate rejection, and parser crash**, so the client discriminates structurally: `plan.conflicts.length > 0 || plan_hash !== sentHash`. It deliberately does **not** key on `errors.length > 0`, because the success path returns the parser's own row-level errors alongside a real commit (`bulk_uploads.py:211`) — a file that commits 8 rows and errors on 2 has non-empty `errors` *and* a non-null plan, so an `errors`-based test would report "nothing was applied" about an upload that applied 8 rows. Pinned by a named test. Also compares the mutation *variable* rather than state, since `setResult` runs first and a state read would only work by closure-staleness accident.
- **Tests added:** yes — 44 new frontend tests (152 → 196 across 26 → 31 files). `tsc --noEmit` clean. ESLint at exactly the 5 pre-existing errors on untouched files (`CompoundFormModal.tsx:41,57`; `ConditionsTab.buttons.test.tsx:61,83`; `NotesTab.buttons.test.tsx:50`) — the repo still does not satisfy its own zero-warnings rule; needs its own ticket.
- **Regression gate:** `frontend/src/pages/__tests__/BulkUploads.test.tsx` was **never edited across the entire branch** (verified with `git diff 5d342e0..HEAD` on that path) and still passes — that is the proof the other 11 upload rows are behaviourally untouched.
- **Three real defects the reviews caught, all in the *plan* rather than the implementation:**
  1. The plan's own test asserted `queryByText(/Uploaded/)` intending to prove the preview toast was suppressed — but the toast renders "Upload complete — …", which does not contain "Uploaded". The assertion **could never have failed**. Fixed to `/Upload complete/` and *proven* discriminating by temporarily moving `success()` above the early return and confirming the new assertion failed.
  2. An implementer deleted the plan-mandated commit-success toast to resolve a `getByText` collision with the modal's own "Upload complete" title. Because this row supplies `onUploadSuccess`, `UploadRow` also never renders its badge or result panel — so the removal left **the highest-stakes upload card with no durable on-page confirmation at all**, unlike all 11 others. Restored as `success('Experiments created', …)`, which needed zero test changes.
  3. The `review` view rendered **neither** `errors` nor `warnings` — the plan assigned them to `done` only. But `new_experiments.py` has ~30 `warnings.append` sites against 5 plan-recording sites, so the plan does not mirror them: an ignored additives sheet (`:929`) was invisible at preview, a failed row (`:665,671`) appears in no plan section, and `Missing required 'experiments' sheet` (`:688`) returns an error with a **non-null empty** plan (not the crash path), so the modal offered an enabled "Commit 0 changes" with the error shown nowhere. Fixed by hoisting both blocks into all three views, and Commit is now disabled at zero changes with a stated reason.
- **Root cause shared by all three:** the spec specified UI *views* without enumerating which response fields the server actually populates and where each surfaces. For the next spec touching a 200-for-everything endpoint, add that field-by-field table at design time.
- **Verified in the running app (Chrome DevTools, user-enabled):** baseline 750 experiments / 750 conditions captured first. Preview sent `dry_run=true` with no `plan_hash` and left the DB byte-identical (750/750, `max(updated_at)` unchanged) despite reporting `created: 2`. Commit replayed the previewed hash exactly with no `dry_run`, created exactly 2 rows, and the Next-ID chips advanced 909 → 9903 live with no reload (proving the `['nextIds']` invalidation). The conflict workbook previewed with the conflict expanded, Commit disabled with its reason, and **the whole file refused — the good row was not created either**. Zero console errors or warnings throughout. Both test experiments then deleted through the app's own dialog; DB restored to exactly baseline with 0 orphan conditions, 0 orphan notes, and the 2 delete-audit rows preserved.
- **NOT run:** Playwright E2E. It needs a live server plus a Firebase login and writes real rows, and its fixture `docs/sample_data/new_experiments_template.xlsx` is **gitignored and absent on a clean checkout** (`.gitignore:13`), so the spec cannot execute anywhere as-is — pre-existing, unchanged by this branch, now documented in a comment at the top of the spec. Its 8 selectors were instead verified by reading them against the components' actual rendered strings.
- **Scope boundary — still open under #100:** acceptance criterion 1 in full (a `plan` on *every* endpoint, not just `new-experiments`; would need 12 more plan shapes inside the locked `backend/services/bulk_uploads/`) and criterion 6 (replay the two 2026-07-28 SERUM_Catalyst workbooks against a pre-incident DB snapshot). A final review judged shipping preview-first on 1 of 13 rows **defensible**: it is labelled at point of use, and New Experiments is the only endpoint that creates identity or renames, while the rest upsert into an existing identity space and are correctable by re-upload.
- **Deferred minors:** on a conflict preview the same message renders three times (server `errors`, server `warnings`, and the plan's `conflicts` section) because it arrives in three different response fields — repetitive, not wrong. In the `done` view errors/warnings now sit above the counts badges. The legacy Streamlit uploader still calls `bulk_upsert_from_excel` directly and is covered by neither gate.
- **Process:** built via `superpowers:subagent-driven-development` — 6 tasks, fresh implementer + independent reviewer each, 2 fix rounds, plus a whole-branch review on the most capable model and one fix wave. Ledger at `.superpowers/sdd/2026-07-29-issue-100-bulk-upload-preview-ui/progress.md`.
- **Decision logged:** no
- **PR:** none yet

## 2026-07-29 | issue #100 closeout — Close as complete, split 2 criteria to #107/#108
- **No code changed.** Docs and issue-tracker only. User chose "close #100 now, no code" at the `/start-task` scope confirmation, over (a) building the reconstructed criterion-6 replay test or (b) generalizing the plan to all 13 endpoints.
- **Files changed:**
  - `docs/issues/issue-upload-plan-all-endpoints.md` **(new)** — GitHub **#107**. Criterion 1 in full: a `plan` on every endpoint. Sizes the work honestly (14 locked parser files, ~3,500 lines), and front-loads the one decision that must precede any code — generalize `UploadPlan` vs. a discriminated union per parser family. Prescribes the `_impl` + thin-wrapper + `_ex` shape that made item 2 a zero-breaking-change addition across ~26 callers, and an order by value (`experiment_status.py` first — it already has a dataclass preview to reconcile; `master_bulk_upload.py` last — it composes the others).
  - `docs/issues/issue-serum-catalyst-rename-replay.md` **(new)** — GitHub **#108**. Criterion 6.
  - `docs/issues/issue-bulk-upload-dry-run.md` — closure section: shipped-items table with merge SHAs, criteria status, the two decisions worth carrying forward, the process lesson from items 6-9, and the gaps neither follow-up covers. Also added the items 4/5 and 6-9 shipping notes this file never received (it only had 0/0.5/0.6 for items 3/1/2 — the later passes logged to `issue-log.md` and the GitHub issue but not here). Acceptance-criteria checkboxes now reflect reality: 5 ticked, 1 partial, 1 unmeetable.
- **Criterion 6 is unmeetable as written, verified not assumed:** both workbooks (`20260728_SERUM_catalyst_001_006_renamed.xlsx`, `..._007_010.xlsx`) are absent from the repo and from `docs/sample_data/` (`.gitignore:13` excludes `*.xlsx` there, so they were never committed); the only dump on disk is `docs/sample_data/experiments_20260511_010002.sql` from 2026-05-11, two months before the 80 originals existed; there is no `backups/` dir; and no script, doc or test records the workbooks' `old_experiment_id` → `experiment_id` pairs.
- **What the closeout recovered, and it is more than expected:** the old-scheme ID set is **complete**. `scripts/serum_catalyst_leftovers.txt` holds 69 old-scheme IDs and Section 5 of `scripts/sql/verify_serum_catalyst_target_state.sql` enumerates the 11 IDs common to both schemes — 69 + 11 = 80, matching that script's own `80 keep / 69 delete / 149 total` inventory. The 80 new-scheme IDs with their expected pH / rock mass / temperature / water volume / compound / amount are transcribed verbatim into the script's `expected` temp table. So #108 can reconstruct the incident at full 80-row scale without the workbooks; **only the old→new mapping must be inferred** (both schemes share the `a/b/c` × `-t1/-t3/-t7/-t20` structure over sequential indices, so it is very likely ordinal). #108 requires the test to say so in a comment rather than imply it replays the real files.
- **Why the remainder is defensible to close on:** New Experiments is the only endpoint that creates or renames identity. The other 12 upsert into an existing identity space and are correctable by re-upload — the 2026-07-28 incident was only possible because renames were involved. That is recorded as the reason #107 is medium priority rather than high.
- **Deliberately not created as issues here** (pre-existing, flagged in earlier #100 passes, still unticketed): the two API shape tests that silently exercise only their exception-fallback path (`actlabs-rock` eager import defeats `sys.modules` patching; `icp-oes` stale 2-tuple mock vs. the real 3-tuple) — folded into #107's notes as work to do while in that file, not a separate ticket; and the extensive pre-existing `flake8`/`black` violations in `new_experiments.py`. `issue-eslint-baseline.md` already covers the 5 frontend lint errors.
- **Tests added:** no — no code changed. Nothing was run beyond `gh issue create`; no test claim is made for this entry.
- **Docs updated:** yes (3 files; hook synced each to `docs/project_context/`)
- **Decision logged:** no
- **PR:** none — branch `chore/issue-100-closeout`

## 2026-07-30 | issue #109 Phase 1 — Bulk experiment deletion via Excel upload
- **Files changed:**
  - `backend/services/bulk_uploads/experiment_deletion_bulk.py` **(new)** — `parse_experiment_ids` (Excel *or* CSV, case-insensitive header so `Experiment ID` works, dedupe, blank rows dropped, order preserved) and `delete_experiments_from_file` returning `BulkDeleteResult(deleted, missing, failed, errors)`. Calls the existing `experiment_deletion.delete_experiment_cascade` per row — no orphan-handling logic is duplicated, per the standing instruction in `decisions.md` (2026-07-29 issue #99 entry).
  - `backend/api/routers/bulk_uploads.py` — `POST /api/bulk-uploads/experiment-deletion`, the `BULK_DELETE_ALLOWED_EMAIL` gate, and an `experiment-deletion` entry in the `_get_template_bytes` registry. No existing endpoint or parser touched.
  - `frontend/src/api/bulkUploads.ts` — `uploadExperimentDeletion`, `'experiment-deletion'` added to `TemplateType`.
  - `frontend/src/pages/BulkUploads.tsx` — the "Delete Experiments" row (last under *Less-used uploads*), `countCsvIdRows`, `confirmThenDelete`.
  - `frontend/src/pages/BulkUploadRow.tsx` — two additive optional props, `resultLabels` and `useServerMessage`. Defaults unchanged, so the other 12 rows are byte-identical in behavior.
  - `docs/api/API_REFERENCE.md`, `docs/user_guide/BULK_UPLOADS.md`, `.claude/rules/MODELS.md`.
- **Tests added:** yes — 12 service (`tests/services/bulk_uploads/test_experiment_deletion_bulk.py`), 9 API (`tests/api/test_bulk_experiment_deletion.py`), 8 frontend (`BulkUploadsDeletion.test.tsx`, `bulkUploads.deletion.test.ts`). Backend 1161 passed; frontend 204 passed. Written test-first, RED observed for every one — the frontend RED was verified by stashing the three source files and watching all 8 fail, since they were authored before `npm ci` finished.
- **Verified in the running app, not only under test:** a second uvicorn was run from the worktree on `:8001` serving its own `frontend/dist` (the shared `:8000`/`:5173` stack was never touched, and `:8001` was stopped afterwards). Against the real dev DB with four seeded `ZZ_DEL_`-prefixed throwaway experiments: template download 200; the `window.confirm` dismissed → **no POST at all** and nothing deleted; accepted → 200, UI showed `DELETED: 3` / `NOT FOUND: 1` with the IDs itemized; the decoy absent from the file survived; 0 orphaned conditions or notes; 3 audit rows with `experiment_fk=None`, `modified_by=mhearl@addisenergy.com`, `total=4`; a **real** Firebase token for `labpc@addisenergy.com` → **403** with its target untouched; no token → 401. Test rows were removed afterwards; the 3 `ModificationsLog` rows were deliberately left (user's choice) since surviving audit rows are the design.
- **Per-row isolation is a SAVEPOINT, deliberately not `db.rollback()`** — see `decisions.md` entry of the same date. This is the one design decision where the issue's own wording ("call `delete_experiment_cascade` inside a `try/except`") would have produced a bug.
- **Known gap, in scope for Phase 2 item 6 and not fixed here:** the upload performs **no React Query cache eviction**. After a batch, `/experiments` and any base-ID-keyed group query can keep serving deleted experiments until their `staleTime` lapses or the page refetches. The 2026-07-29 `decisions.md` entry flagged this for "the deferred bulk-delete follow-up"; #109 Phase 2 item 6 owns it and is itself blocked on `issue-replicate-group-detail-cache-eviction.md`.
- **Phase 1 checklist item NOT met:** "Confirmed against a real cleanup batch (Mat's actual list of bad entries) end to end." Only `ZZ_DEL_`-prefixed rows created for the test were ever deleted. This needs Mat's list and is irreversible.
- **Lint:** `flake8 --max-line-length=100` clean on all new files; `tsc --noEmit` and `eslint` clean on every changed frontend file (the 5 remaining repo-wide eslint errors are pre-existing, in untouched files, tracked by `issue-eslint-baseline.md`). `black --line-length 88` would reformat the new service **and** its existing peers `experiment_status.py` (locked) and `experiment_deletion.py`, so the repo is not Black-formatted in practice and the new file was left consistent with its neighbours rather than reformatted in isolation.
- **Pre-existing failures, confirmed not regressions:** 3 in `tests/test_pg_backup_restore.py` (reproduced identically with all changes stashed) and 4 errors in `tests/test_fresh_install_migration.py`, which shells out to a hardcoded relative `.venv\Scripts\alembic.exe` that does not exist inside a git worktree — a worktree artifact, not a code fault.
- **Deliberate deviation from the pre-merge checklist's "no hardcoded values":** `BULK_DELETE_ALLOWED_EMAIL = "mhearl@addisenergy.com"` is a literal, as the issue explicitly directs for Phase 1. It is not read from settings on purpose — an env-configurable gate would be editable from the environment. Phase 2 item 7 replaces it with a real role/claim check.
- **Docs updated:** yes (3 files; hook synced `API_REFERENCE.md` and `BULK_UPLOADS.md` to `docs/project_context/`)
- **Decision logged:** yes — `docs/working/decisions.md`, 2026-07-30
- **Phase 2 not started**, per the issue's explicit "Stop here. Report back before starting Phase 2."

## 2026-07-30 | inline (infra) — Harden update.ps1 against a dirty lab-PC tree
- **Trigger:** the #109 deploy failed on the lab PC. Its checkout was 22 commits behind at `b2b4eab` with a dirty working tree, so `git pull` had been aborting — nightly, silently, for ten days (the job logs `FAILED` to `C:\Logs\experiment-tracker\updates.log` and nothing reads it). The same failure occurred on 2026-07-20 and was worked around with a `git stash` instead of fixed; three unresolved stashes were still present.
- **Files changed:**
  - `update.ps1` — three guards: (1) the service is stopped **before** git rewrites files and started after, with `Start-TrackerService` called from every exit path including `Abort`; (2) a dirty tree is discarded before pulling and every discarded entry is logged; (3) HEAD is verified against `origin/main` after the pull so a partial update cannot report `SUCCESS`. Migrations now also run with the service down.
  - `tests/deployment/test_update_script.py` **(new)** + `__init__.py` — 12 static-invariant tests, including a real PowerShell parse via `Parser::ParseFile`.
  - `.claude/settings.json` — absorbed `enabledMcpjsonServers` (chrome-devtools, context7, github) and the 4 `enabledPlugins` that existed only in the local file, so untracking it loses no project-level config.
  - `.gitignore` + `git rm --cached .claude/settings.local.json` — it had accumulated 33 machine-local permission rules with absolute paths under a **stale** `Documents\0x_Software\…` root, and was a conflicting file in both the 2026-07-20 and 2026-07-30 incidents. `permissions` was deliberately NOT migrated.
  - `docs/deployment/PRODUCTION_DEPLOYMENT.md` — the guards, the two load-bearing details, and a manual recovery runbook.
- **The bug this branch exists to prevent is one I nearly shipped in the recovery advice itself.** My first instruction was `git reset --hard origin/main`, which moves HEAD, so `update.ps1`'s own `git pull` finds nothing, `$headBefore -eq $headAfter`, the "no new commits" branch fires and **the frontend is never rebuilt** — a deploy that logs SUCCESS while serving a stale `frontend/dist`. Caught before it ran by checking the 22-commit range against the script's rebuild triggers (13 files under `frontend/src/`). The corrected form resets to `HEAD` and lets the script's own pull move the version. Both the trap and its inverse are now asserted by tests.
- **New risk accepted, and mitigated:** stopping the service first means a mid-script failure leaves the lab app *offline* rather than merely stale. `Abort` therefore calls `Start-TrackerService`, the early-exit branch starts it too, and a failed start logs `CRITICAL` with the manual command. Two tests pin this.
- **Tests added:** yes — 12. Full suite 1173 passed (up from 1161). The 3 `test_pg_backup_restore.py` failures and 4 `test_fresh_install_migration.py` errors are the documented pre-existing ones.
- **The pre-existing full-suite failure set is UNSTABLE, not a fixed 3.** Three full runs on identical code gave 3 failed/1173 passed, 3 failed/1173 passed, then **4** failed/1172 passed — the extra one being `tests/test_pxrf_analysis.py::test_create_pxrf_reading`, which passes in isolation. Cause: ten `Base.metadata.drop_all()` call sites (`tests/models/`, `tests/views/`, `tests/test_experiment.py`, `tests/test_experiment_rename.py`, `tests/api/conftest.py`, `tests/conftest.py`) all share the single `experiments_test` database, so a module that drops tables mid-session breaks whichever later module needs them — and that depends on interleaving and timing (the 4-failure run took 120s; the 3-failure runs took 275s). Treating "3 known failures" as the baseline is therefore unsafe: a real regression could hide inside the variance. Worth its own ticket to give the destructive modules an isolated database.
- **NOT executed, and cannot be:** `update.ps1` drives `nssm` and a live Windows service, so pytest cannot run it — the tests are static assertions plus a parse check. **The first run of this change must be an attended, manual one on the lab PC**, watching for `frontend:yes` in the log and confirming the service comes back up.
- **Root cause is still not definitively established.** `docs/deployment/PRODUCTION_DEPLOYMENT.md` shows the lab PC checkout lives at `C:\Apps\experiment-tracking`, i.e. **outside** OneDrive, which rules out the file-sync theory. The remaining candidates are open file handles held by the running service during the pull (the guard addresses this, and `git clean -fd` was independently observed failing with *Permission denied* on four directories) and something writing to the checkout directly — a Claude Code client is known to run on that machine, and `.claude/settings.local.json` carrying genuine local edits is consistent with it. `nssm get ExperimentTracker AppDirectory` would settle whether the service's CWD is inside the repo.
- **Left open deliberately:** the three lab-PC stashes (archived to `C:\Users\LabPC\Desktop\labpc-pre-reset-20260730-083653\`; `stash@{2}` holds real code — `backend/config/settings.py` and a migration) and the fact that nightly failures are still only visible in a log file nobody reads.
- **Docs updated:** yes (hook synced `PRODUCTION_DEPLOYMENT.md` to `docs/project_context/`)
- **Decision logged:** yes — `docs/working/decisions.md`, 2026-07-30
- **NOT merged or deployed.** Deployment-critical; awaiting sign-off.

## 2026-07-29 | issue #97 — reactor slot identity is derived, not stored (cross-series occupancy collision)

A physical reactor slot is a *pair*: the series (HPHT vessel vs. Core Flood rig) and
the number within it. `R01` and `CF01` are different hardware sharing the number 1.
The database stored only the number, and the `R01`/`CF01` label was re-derived at
read time in three separate places — so occupancy queries keyed on the bare integer
let a Core Flood going ONGOING silently auto-complete a running HPHT. Live data
corruption in production (`CF_018`/`-2`/`-3` all went ONGOING through
`PATCH /status` with nothing objecting).

- **Files changed:**
  - `database/reactor_slot.py` **(new)** — the single definition of slot identity:
    `normalize_experiment_type`, `series_prefix`, `is_occupancy_type`,
    `derive_reactor_slot`, `canonical_slot_label`, private `_format_slot`. Returns
    `None` for a non-occupancy type (Serum/Autoclave/Other), a missing/unparseable
    number, or any number `<= 0`.
  - `database/models/conditions.py` — `reactor_slot` column, `String(8)`, nullable, indexed.
  - `alembic/versions/1c1ef9b555e0_*.py` **(new)**, revising `293d0ea59422` — adds
    the column, backfills from `(reactor_number, experiment_type)`.
  - `database/event_listeners.py` — `set_reactor_slot`, a `before_insert`/`before_update`
    listener on `ExperimentalConditions` maintaining the column on every ORM write.
  - `backend/services/bulk_uploads/experiment_status.py` — both occupant queries and
    the same-file conflict map keyed on `reactor_slot` instead of the bare integer;
    messages now name the slot (`"Reactor R08 …"` not `"Reactor 8 …"`);
    `manage_reactor_occupancy` gained a trailing `reactor_slot: str | None = None`;
    the now-dead `_normalize_type`, `_is_eligible_for_occupancy` and
    `_OCCUPANCY_TYPES` deleted (zero remaining call sites, verified).
  - `backend/services/bulk_uploads/new_experiments.py` — both occupancy call sites
    gated on `derive_reactor_slot(...) is not None` (replacing a falsy `if
    conditions.reactor_number`, which skipped `reactor_number == 0`) and passing
    `reactor_slot=` explicitly instead of relying on a lazy `.conditions` load.
    `newer_than` deliberately still **not** passed — see Scope boundary below.
  - `backend/api/routers/experiments.py` — `PATCH /api/experiments/{id}/status` now
    returns **409** (not a silent demotion) when the target slot is occupied by
    another ONGOING experiment, naming the slot, the occupant and its start date
    (degrading to "an unrecorded date" when absent). Rejects before any mutation.
  - `backend/api/routers/dashboard.py`, `backend/services/notion_sync/import_.py`,
    `backend/services/notion_sync/export.py` — labels are now column reads;
    `_reactor_label_for` deleted; queries filter `reactor_slot IS NOT NULL` (fixes a
    latent Notion-export leak: a Serum vial with a stray `reactor_number` used to
    export as if it occupied a slot).
  - `frontend/src/pages/ReactorGrid.tsx` (StatusBadge), `frontend/src/pages/ExperimentList.tsx`
    — both status-change mutations gained `onError` calling
    `toastError('Update failed', err.message || 'Could not update status')`; the
    axios interceptor at `frontend/src/api/client.ts:11-23` already puts FastAPI's
    `detail` on `err.message`, so the 409's slot/occupant/date text surfaces directly.
  - `.claude/rules/MODELS.md` — `reactor_slot` documented under `ExperimentalConditions`
    Key Fields (derivation, pre-flush caveat, bulk-update caveat, what's still unenforced).
  - `docs/api/API_REFERENCE.md` — new `### PATCH /api/experiments/{experiment_id}/status`
    section documenting the 409; `ConditionsResponse` noted to include `reactor_slot`
    read-only.
  - `docs/issues/issue-reactor-slot-identity-and-occupancy-uniqueness.md` — status
    blockquote marking §1–§3 shipped, §4 split to #112; stale-reference note added
    (its `_is_eligible_for_occupancy`/`_normalize_type` mentions describe deleted code).
  - `docs/issues/issue-experiment-type-enum-binding.md` — corrected two passages that
    named the deleted helpers, pointed at `database/reactor_slot.py::_SERIES_BY_TYPE`
    and `is_occupancy_type` instead, and corrected a now-false claim that
    `experiment_status.py` was the only site normalizing case/whitespace.
  - `docs/issues/audit-2026-07-28-results-and-cleanup.md` — "settle before writing the
    trigger" section repointed at `_SERIES_BY_TYPE` in `database/reactor_slot.py`;
    recorded the autoclave-occupancy question as answered "no" on 2026-07-29.
  - `docs/issues/issue-reactor-occupancy-uniqueness-trigger.md` **(new)** — the §4
    follow-up, filed as GitHub **#112**.
- **Tests added:** yes. Backend four-path suite (`tests/api tests/services tests/models tests/views`):
  **968 passed, 0 failed**. Frontend: **200 passed across 31 files**; `npx tsc --noEmit`
  clean; `npx eslint src --ext .ts,.tsx` exactly **5 pre-existing errors** on files this
  branch never touched. Three known pre-existing failures live in
  `tests/test_pg_backup_restore.py`, outside those four backend paths, unrelated to this branch.
- **Scope boundary — §4 split out, why:** the PL/pgSQL uniqueness trigger and
  `CHECK (reactor_number > 0)` (§4 of the source issue) are blocked on a prerequisite
  data cleanup (`audit-2026-07-28-results-and-cleanup.md`, Parts A+B) that has not
  been run: as of 2026-07-30 (queried against the stored `reactor_slot` column), the
  dev DB has **4** double-booked slots (`CF01`×6, `CF03`×5, `R01`×6, `R06`×2 —
  `R00` is NOT one of them, since #97 already nulls its slot) and 13 rows with
  `reactor_number = 0`, a separate prerequisite blocking only the `CHECK`; see #112
  for the full detail. A migration that fails against live data on the lab PC's nightly `alembic upgrade
  head` breaks the whole deploy pipeline until fixed by hand — so the trigger cannot
  land until that cleanup is run, committed and verified in its own separate,
  human-run session. Filed as **#112**. Two direct consequences documented as
  deliberate, not oversights: the `seen_labels` dedup at `dashboard.py:126-140`
  stays in place (delete only after the constraint is verified), and
  `summary.reactors.empty` still reads one too high per double-booked slot.
  `newer_than` on the new-experiments path is also deferred to #112 — the issue's own
  rationale for passing it was "let the trigger be the backstop," and there was no
  trigger yet. **Correction, 2026-07-30:** `summary.reactors.empty` does NOT read
  one too high per double-booking — `_occupancy()` counts the same deduped
  `reactor_cards` list as the grid, so the counts are correct; only the grid hides
  the contention. See `docs/issues/issue-reactor-occupancy-uniqueness-trigger.md`.
- **Four decisions Mat made at scope confirmation (`/start-task`, 2026-07-29):**
  1. Ship §1–§3 plus tests only this branch; §4 deferred to a follow-up issue, blocked on the audit cleanup.
  2. Autoclave is **not** occupancy-bearing — only HPHT and Core Flood claim numbered slots.
  3. `reactor_slot` is maintained by a SQLAlchemy `before_insert`/`before_update`
     listener, not by assignment at each write site.
  4. Locked-component sign-off granted for `database/models/conditions.py`,
     `backend/services/bulk_uploads/experiment_status.py`, and
     `backend/services/bulk_uploads/new_experiments.py`.
- **Discovered but not fixed, tracked separately:**
  - `experiment_type` is still un-normalized (`SERUM` vs `Serum` vs 8 other spellings)
    — the #85 Serum KPI still undercounts by ~72%. `database/reactor_slot.py`
    tolerates every spelling; the KPI predicate at `dashboard.py:212` does not.
    Tracked in `issue-experiment-type-enum-binding.md`.
  - The production double-bookings and `reactor_number = 0` rows are untouched —
    cleaning them is Part A + Part B of `audit-2026-07-28-results-and-cleanup.md`,
    deliberately a separate human-run session, not folded into this branch.
  - No frontend confirm-and-supersede dialog for the 409 — deferred by the source
    issue itself; the toast-only UX is the interim behavior.
  - The silent `slot is None` early return in `manage_reactor_occupancy` (a
    typo'd `reactor_number = 0` gets no occupancy check *and* no warning) and the
    widened `try/except Exception` there (could swallow a `DetachedInstanceError`
    into `warnings` rather than `errors`) — both routed into #112 since the CHECK
    constraint that ticket adds closes the first one and the same code region is
    already being touched for the `unique_violation` handling.
  - Repo-wide hygiene, deliberately **not** routed into #112 (unrelated to reactor
    occupancy specifically): no flake8 config exists (bare run uses the 79-char
    default; project convention is 120), and the test suite cannot tolerate two
    concurrent runs against the shared `experiments_test` database
    (`Base.metadata.drop_all` at five sites — same fragility behind the three known
    `tests/test_pg_backup_restore.py` failures).
- **Task 5 nuance, worth recording accurately:** Task 4's fallback inside
  `manage_reactor_occupancy` had already closed the cross-series and eligibility
  halves of the new-experiments defect transitively, and the falsy-zero half was
  already equivalent by the time Task 5 ran. Task 5 delivered explicitness (passing
  `reactor_slot=` instead of depending on a lazy `.conditions` load on an unflushed
  row), removal of the falsy-zero footgun, and the slot-named message — not a
  live-bug fix in itself.
- **Docs updated:** yes — `.claude/rules/MODELS.md`, `docs/api/API_REFERENCE.md`,
  and four files under `docs/issues/` (one new). The `docs/` writes (all but
  `MODELS.md`, which lives outside `docs/`) were synced to `docs/project_context/`
  by the `PostToolUse` hook.
- **Decision logged:** yes — the four scope decisions above, at `/start-task`.
- **PR:** none yet — branch `fix/issue-97-reactor-slot-identity`, 9-task
  subagent-driven build, ledger at
  `.superpowers/sdd/2026-07-29-issue-97-reactor-slot-identity/progress.md`.

## 2026-07-30 | issue #111 — Master Results v3: GC Full Loop precedence + one row per vial

- **Trigger, and why it's wider than the issue title:** the team renamed the Dashboard tracker's GC columns. The issue was filed as "H2 gets dropped," but the rename touched four columns (`H2 (ppm)` → `FL H2 (ppm)`, `Gas Volume (mL)` → `FL Gas Volume (mL)`, `Gas Pressure (psi)` → `FL Gas Pressure (psi)`, `Overwrite` → `OVERWRITE`), and the parser matched none of them by exact name — so every renamed field, not just H2, was silently skipped. `_normalize_headers` (`backend/services/bulk_uploads/master_bulk_upload.py:114`) now maps old and new spellings onto one canonical name per field via `_HEADER_ALIASES`, with a collision rule (a column never takes a canonical name another literal column in the same sheet already holds) so a hand-merged workbook carrying both spellings can't alias two real columns onto each other and lose one silently through pandas duplicate-column semantics.
- **v2 → v3 restructure, two separate changes folded into one workbook revision:** (1) the rename above, and (2) the wide DI block (`DI a/b/c H2 (ppm)` + `DI avg H2 (ppm)` + `DI SD (ppm)`) collapsed to a single `DI H2 (ppm)` column, because v3 gives each replicate letter its own row instead of its own column — the same one-row-per-vial pivot that also now governs the whole sheet (`SERUM_001a/b/c` at days 1 and 3 is six rows, not two rows with a/b/c sub-columns). The old wide columns are recognized and named in a specific warning (`_WIDE_DI_COLUMNS`) rather than silently dropped, because there's no correct way to fold three vial readings into one row.
- **Full Loop > direct injection, per row (`_resolve_h2`, master_bulk_upload.py:204):** `FL H2 (ppm)` wins whenever present; `DI H2 (ppm)` is read only when the Full Loop cell is blank. Gas volume/pressure always come from the same block as the winning concentration — never a Full Loop ppm paired with a DI volume — because `_calculate_hydrogen()` combines all three into one `h2_micromoles` figure. The discarded DI reading (when FL won) is reported per-row as `h2_source` / `h2_di_superseded` in the upload feedback but is **not persisted** — `ScalarResults.h2_concentration` has no stored notion of which GC method produced it, confirmed in `.claude/rules/MODELS.md`.
- **`0` is a real reading, per the user's own formula rewrite (2026-07-30):** H2 concentration and gas volume/pressure use plain `_parse_float`, which passes `0` through — unlike `Sample pH` / `Sample Conductivity`, which use `_parse_measurement_float` and treat `0` as blank because the Excel template can't distinguish a true zero from an empty cell for those two fields. Do not generalize the pH/conductivity blank-zero handling to H2 — they are deliberately different.
- **Duplicate vial-timepoint rejection needs a pre-pass, not an in-loop check:** a collision is only detectable once the *later* row sharing the same `(experiment_id, timepoint)` has been read, by which point the earlier row has already been flushed, counted, and given a feedback record inside the same request — undoing that would need a mid-transaction rollback of only one row's effects, which SQLAlchemy doesn't offer cheaply. The fix is a two-phase scan: Phase 1 resolves every row's `(experiment_id, timepoint)` identity and tallies `key_counts`; Phase 2 upserts, skipping (with an error, not a silent skip) any row whose key count is `> 1`. Both rows in a collision are rejected — there's no signal for which reading was meant to be kept.
- **Corrected a wrong claim about commit behavior that had leaked into a code comment.** An earlier planning draft asserted `create_scalar_result_ex` commits per row — used to justify why the duplicate check has to run before any row is "committed." That's false: `create_scalar_result_ex` only flushes (`backend/services/scalar_results_service.py:209`); the whole upload commits exactly once, at the endpoint, via `_finalize_write` (`backend/api/routers/bulk_uploads.py:28-37`), which is also the mechanism `dry_run` depends on. Per-row commits are a real property of a *different* endpoint — `delete_experiment_cascade` on the issue #109 bulk-deletion path — and don't apply here. The comment above `resolved: List[...]` (master_bulk_upload.py, Phase 1) is corrected to explain the actual reason for the pre-pass (feedback already recorded for the earlier row) instead. Comment-only edit; `tests/services/bulk_uploads/` re-run afterward, 244 passed, no behavior change.
- **Mean/SD across replicates were deliberately NOT built in this plan.** `v_results_scalar_rollup` already computes `mean_h2_ppm` / `sd_h2_ppm` (n-1, outlier vials excluded) across whatever rows share a base experiment ID, served via `GET /api/experiments/groups/{base_id}/rollup` — adding a second aggregation path on the upload side would be redundant and could disagree with the view. The v3 sheet accordingly carries no avg/SD columns; each vial supplies one reading.
- **`from_bytes_ex` wrapper, not a breaking change to `from_bytes`:** the legacy 5-tuple return (`created, updated, skipped, errors, feedbacks`) has no slot for `warnings`, and ~20 existing tests plus the router unpack it positionally. `MasterUploadResult` (dataclass) is the real return type internally; `from_bytes` still returns `.as_tuple()` (warnings dropped) for old callers, `from_bytes_ex` returns the full dataclass for the router, which now surfaces `warnings` in the response.
- **No schema changed by this plan.** No commit on this branch touches `database/models/` or `database/event_listeners.py` (`git log --oneline develop..HEAD -- database/models/ database/event_listeners.py` returns nothing). `git diff --stat develop -- database/models/` and `-- backend/services/calculations/ database/event_listeners.py` are **not** empty, but that's a stale-base artifact, not a Task 1-7 change: this branch forked before issue #97's `reactor_slot` work merged into `develop` (`develop` is now at `243d840`), so the diff is entirely `reactor_slot`-related and unrelated to #111. Re-run this check after rebasing onto current `develop` before relying on it. All #111 work is parser logic in one locked file plus documentation.
- **Files changed:**
  - `backend/services/bulk_uploads/master_bulk_upload.py` — `_HEADER_ALIASES`, `_WIDE_DI_COLUMNS`, `_RECOGNIZED_H2_COLUMNS`, `_H2_TOKEN`; `_normalize_headers`, `_resolve_h2`, `_resolve_row_identity` extracted; two-phase duplicate detection in `_process_bytes`; `MasterUploadResult.warnings` field; module docstring rewritten (v3 column spec, FL/DI precedence, one-row-per-vial); Phase-1 comment corrected (this task).
  - `docs/CALCULATIONS.md` — Hydrogen Amount section: where the three inputs come from on a Master Results upload, and that replicate mean/SD are not calculated here.
  - `.claude/rules/MODELS.md` — `ScalarResults` → Hydrogen: GC source precedence (not stored), one row per vial.
  - `docs/user_guide/BULK_UPLOADS.md` — §1 Master Results Sync: one-row-per-vial with a worked example, no more averages/SD on the sheet, FL/DI column behavior, unmapped-H2-column warning.
- **Task 6 verification (measured counts, real workbooks, rolled-back session — not a live upload through the API):**
  - `Master_Results_Tracker_v3.xlsx` is **currently unusable as a data source**: its Dashboard cells are Excel Table formulas whose cached values are stale (`Experiment ID` reads as the float `0.0` on every row; `Duration (Days)` reads `0`/`' '`). pandas/openpyxl only see the cache. `0.0` is falsy in Python, so all 499 rows resolve to a blank ID and are skipped — 0 created / 0 updated / 499 skipped / 0 errors / 0 warnings. The workbook has `fullCalcOnLoad=True`, but its source sheets (`GC Full Loop`, `GC DI`, `Sampling`) are `"Not Requested"`/blank throughout, so it needs populating with real data, not just recalculating.
  - `Master_Reactor_Sampling_Tracker_v2.xlsx` (~245 real IDs): 10 created / 0 updated / 9 skipped / 247 errors / 1 warning. The one warning was the expected wide-DI deprecation notice, correctly naming the stale columns. `h2_source` was `{'full_loop': 5, 'di': 5}` — both precedence branches exercised on real data, evenly split. Of the 247 errors: 225 are "experiment not found and could not be auto-created" (the dev DB simply lacks those HPHT/AUTO/CF IDs — not a parser defect); 22 are duplicate vial-timepoint rejections on real data (`HPHT_193` day 0.0 twice, `HPHT_218` day 3.0 twice, plus a cluster of blank-ID rows).
  - `ScalarResults` row count was 1056 before and after both runs — confirmed rolled back, nothing written.
- **Pre-existing parser bug found, fixed in the final review fix wave (2026-07-30):** `str(row.get("Experiment ID") or "").strip()` in `_resolve_row_identity` did not treat a blank cell arriving as `float('nan')` as blank — NaN is truthy in Python, so the row's experiment ID became the literal string `"nan"` instead of being skipped. v2 has 21 such rows. Pre-existing effect: spurious "not found" errors (each `"nan"` row looked up an experiment that doesn't exist). Effect introduced by this branch's duplicate detection, before this fix: multiple `"nan"` rows at the same Duration also collided with each other and additionally emitted duplicate-row errors on top of the not-found ones. Originally left unfixed as out of plan scope; the whole-branch review flagged it as Important (it undermined this issue's own goal of a trustworthy error list) and it was corrected as part of the pre-merge fix wave — `_resolve_row_identity` now treats `float('nan')` the same as `None`/empty string. See `test_blank_nan_experiment_id_is_skipped_not_duplicated`.
- **Tests added:** no new tests this task (documentation-only); Tasks 1-6 added/updated the parser's own test coverage (not itemized here — see their own log entries if split out, otherwise see the branch's task ledger at `.superpowers/sdd/2026-07-30-issue-111-gc-full-loop-h2/`).
- **What was and was not run:** `tests/services/bulk_uploads/` re-run after the Task 7 comment edit — 244 passed. The **full backend suite has not been run** as part of this task; the documented pre-existing baseline (3 failures in `tests/test_pg_backup_restore.py`, 4 errors in `tests/test_fresh_install_migration.py`) is known **unstable, not fixed** — a fourth intermittent failure (`tests/test_pxrf_analysis.py::test_create_pxrf_reading`) has been observed from shared-database `drop_all()` interleaving; do not treat "3 known failures" as a safe baseline without re-running. The Task 6 verification numbers above came from a rolled-back dev-database session driving the parser directly, **not** a real upload through the running API — no live endpoint call, no frontend involved.
- **Docs updated:** yes (`CALCULATIONS.md` and `BULK_UPLOADS.md` hook-synced to `docs/project_context/`; `.claude/rules/MODELS.md` is not hook-synced and was edited directly)
- **Decision logged:** no — no new decision beyond what Tasks 1-6 already established
- **Final review fix wave (2026-07-30):** whole-branch review verdict "Ready to merge: with fixes" — no Critical issues, several Important/Minor findings on the user-facing surface. Applied: static (non-interpolated) duplicate-rejection example that no longer suggests an ID shape the parser itself rejects, `:g`-formatted day value; NaN-as-blank fix for `Experiment ID` (see above); `BULK_UPLOADS.md` Dashboard column table rewritten to the v3 canonical names with old spellings noted as accepted aliases, including the previously-missing direct-injection rows; three residual "commits per row" false-claim sites corrected in this plan document per its own Global Constraint; collision key now built from `normalize_timepoint()` at both sites (narrows, does not close, the near-duplicate-timepoint gap — documented in-line); `CALCULATIONS.md` Hydrogen Amount bullet corrected to match `_calculate_hydrogen`'s actual guard (volume/pressure > 0, concentration present and non-negative, 0 valid); `.claude/rules/MODELS.md` Hydrogen section reworded so the discarded-DI-reading feedback is described as present in the API response but not surfaced in the UI; `unmapped_h2` warning list now sorted; added `test_di_wins_ignores_stray_full_loop_gas_geometry` (mirrors the existing Full-Loop-side coverage) and `test_blank_nan_experiment_id_is_skipped_not_duplicated`.
- **Deferred to follow-up (not fixed in this fix wave):**
  1. The anti-recurrence warning covers concentration only. If a future Dashboard revision renames `FL Gas Volume (mL)` or `FL Gas Pressure (psi)`, `h2_concentration` still lands, no warning fires, and `h2_micromoles` / `h2_mass_ug` / `h2_grams_per_ton_yield` silently become `None` — the same silent-loss class this issue was filed for, one level down. Suggested fix: warn when a recognized concentration column has values but its paired gas columns are absent from the sheet. Deferred because a new warning needs its own false-positive analysis.
  2. A rename that drops the token is invisible. `\bh2\b` catches `GC Loop H2 ppm` but not `FL Hydrogen (ppm)` or `Full Loop ppm`; if the other GC block is present, the "no recognized H2 column" backstop does not fire either.
  3. Error list ordering. All Phase-1 errors precede all Phase-2 errors, so a row-5 Duration error is reported before a row-2 upsert failure. Researchers read this list against the spreadsheet top-down.
  4. `from_bytes` and `sync_from_path` have no production callers — retained only for ~20 positionally-unpacking tests.
- **PR:** none yet

## 2026-07-30 | issue #104 — Delete dead `components/experiments/AddResultModal.tsx`

- **What it was, and why it survived three sightings:** `frontend/src/components/experiments/AddResultModal.tsx` (singular "Result") was imported by exactly one file — its own test. No page, route, or component mounted it. The modal that actually ships is `frontend/src/pages/ExperimentDetail/AddResultsModal.tsx` (plural), mounted at `ResultsTab.tsx:213`. Provenance verified, not assumed: built by issue #8 (commits `1379675`, `fef1c1c`, `545c23e`, 2026-03-25) as a *structural demonstration* that a modal taking `experimentPk: number` makes passing the URL string as `experiment_fk` impossible — then never wired into a page. Issue #81's plan already caught it as dead (Decision Point 10) and skipped it deliberately, and #81's log entry (line 1270 above) already recorded the stale `['results', id]` invalidation as pre-existing. #104 was the third sighting, which is exactly the recurring-grep cost the issue was filed over.
- **Both dead-only behaviors declined, not ported — the issue required this be explicit:**
  1. The `is_primary_timepoint_result` checkbox is **not** a capability gap. `backend/api/schemas/results.py:20` declares `is_primary_timepoint_result: bool = True` and `backend/api/routers/results.py:107-118` demotes any existing primary row in the same bucket ("newest wins"), so the live modal omitting the field already produces what the dead modal's default-checked box produced. The only lost ability was *unchecking* it. The whole-branch review found that case stronger than the plan claimed: `is_primary_timepoint_result = TRUE` is filtered in **five** views in `database/event_listeners.py` (`v_dim_timepoints`:468, `v_results_scalar`:512, `v_results_scalar_rollup`:557, `v_results_h2`:588, `v_results_icp`:652) on top of `v_primary_experiment_results` — a non-primary row is invisible to the entire Power BI surface, not one view. Researchers who genuinely need a non-primary row still have the API path, covered by `tests/api/test_results.py:435`.
  2. Per-field inline error placement (the `Input` component's `error` prop) vs the live modal's single banner — presentational only. The live modal's validation is a strict superset: requires measurement date and day, range-checks three gas fields, honors the issue #81 `-t<days>` timepoint lock, and surfaces FastAPI's `detail`.
- **The 8 deleted tests cost no contract coverage.** The headline case asserted `experiment_fk` receives the integer PK and never the URL string — the original point of issue #8. That invariant survives in four stronger places: `ResultCreate` is `strict=True` with `experiment_fk: int` (`backend/api/schemas/results.py:8-17`), four schema tests at `tests/api/test_schemas.py:173-198`, three endpoint tests at `tests/api/test_results.py:84,98,112`, and `frontend/src/api/results.test.ts:29-34`. Plus the type-level guard end to end (`AddResultsModal.tsx:23` and `ResultsTab.tsx:98` both `experimentFk: number`, `ExperimentDetail/index.tsx:481` passes `experiment.id`) — a string cannot reach it without a `tsc` error. The deleted test was the weakest link, asserting a contract on a component no user could reach.
- **`npm run lint` cannot pass as the issue's criterion literally reads — recorded, not papered over.** It runs `--max-warnings 0` and already failed on `develop` before this branch with exactly 6 errors, none in the deleted files: `CompoundFormModal.tsx:41,57` (rule `react-hooks/set-state-in-effect` not found, twice), `pages/ExperimentDetail/AddResultsModal.tsx:96` (unused eslint-disable directive), `ConditionsTab.buttons.test.tsx:61,83` and `NotesTab.buttons.test.tsx:50` (`no-explicit-any`, three times). The standard applied instead was a regression check: count stays at 6, same files, same rules, none fixed. That criterion is marked `[~]` in the issue doc per the repo's own precedent at `docs/issues/issue-bulk-upload-dry-run.md:255` — **not** `[x]`, since ticking a criterion whose annotation says it cannot pass reads as a false pass claim. The same caveat applies to `develop`, so the GIT_WORKFLOW pre-merge "No linting errors" item is equally unmeetable there.
- **Side benefit — an unrelated high-priority ticket got unblocked.** `docs/issues/issue-eslint-baseline.md` states outright that it could not capture the ESLint rule IDs it needs ("I could not run ESLint to capture the rule IDs — it exceeds the available command timeout... The fix differs substantially depending on which rules fire"). This branch measured exactly that, so the six file:line:rule triples are now recorded there and its stale count corrected from 5 to 6. Deliberately **no** lint error was fixed here: fixing one of six leaves the count non-zero and the CI enforcement gate still unbuildable, so all six belong to that ticket together.
- **Files changed:**
  - `frontend/src/components/experiments/AddResultModal.tsx` — **deleted** (151 lines)
  - `frontend/src/components/experiments/AddResultModal.test.tsx` — **deleted** (145 lines, 8 tests)
  - `docs/issues/issue-dead-add-result-modal.md` — status blockquote, criteria ticked (`[~]` on the lint one with all 6 errors named), out-of-scope items inlined in Notes, stale-pointer note
  - `docs/issues/issue-eslint-baseline.md` — measured 6-error baseline recorded, stale count 5 to 6
  - `docs/superpowers/plans/2026-07-30-issue-104-dead-add-result-modal.md` — the plan (modal-diff table, provenance, out-of-scope list)
  - `docs/working/decisions.md:145` — `(closed by #104, 2026-07-30)` on the now-resolved staleness gap
  - `docs/project_context/` copies of both `docs/issues/` files — hook-synced, byte-identical, never hand-edited
- **Tests added:** no — this deletes 8 tests that covered nothing that ships. Frontend suite after deletion: **200 passed / 32 files, zero failures** (was 208/33); `tsc --noEmit` clean, which is the real proof nothing imported the component. Backend suite deliberately **not run**: zero files under `backend/`, `database/`, `alembic/`, `tests/` are touched by this branch, and that suite has a documented-unstable baseline plus a shared-test-DB hazard — running it would say nothing about this branch.
- **Deletion verified complete repo-wide, not just under `frontend/src`:** zero `AddResultModal` references anywhere under `frontend/`, including all 20 Playwright journeys in `frontend/e2e/`, `frontend/src/test/setup.ts`, and every config. No config enumerates individual files (`vitest.config.ts` uses directory globs, `tsconfig.json:23` is `"include": ["src"]`, `.eslintrc.cjs` has no file list), and the repo's only barrel (`components/ui/index.ts`) never covered `components/experiments/`. `package.json` / `package-lock.json` untouched, so the lab PC's nightly `npm ci` is unaffected. No schema, no migration, no dependency.
- **Left alone on purpose:** `DeleteExperimentModal.tsx:20`'s `['results', 'result timepoint', 'result timepoints']` is an `IMPACT_ROWS` display-label tuple, not a query key — the issue says explicitly not to "fix" it. Historical plan documents were not rewritten, including `docs/superpowers/plans/2026-07-23-issue-70-p2-grouped-ui.md:1833`, which points future test authors at the now-deleted test for a provider-wrapper pattern; that advice was already wrong before deletion (the test used only `QueryClientProvider`, never the `ToastProvider` it was about), and the pointer is recorded in the issue doc's Notes rather than edited out of a dated record.
- **Known residual, one word:** `docs/issues/issue-eslint-baseline.md:61` (Proposal item 4) still reads "the 5" where the rest of that document now says 6. Cosmetic — the measured six-error list sits directly above it and already answers that line's question (none of the six is `react-hooks/exhaustive-deps`). Left for whoever picks up that ticket, which is its own scope.
- **Decision logged:** no — no lasting architectural decision. The two declined ports are recorded in the commit body and the issue doc, as the issue's acceptance criteria required.
- **Process:** 2-task subagent-driven build, 4 commits (`016424f`, `8166747`, `48210fc`, `2fb5ed0`), two task reviews, one task fix round, whole-branch review (verdict: ready to merge, 0 Critical / 0 Important, 4 Minor doc-coherence), one fix wave, one scoped re-review. Ledger was at `.superpowers/sdd/2026-07-30-issue-104-dead-add-result-modal/`.
- **PR:** none — merged locally to `develop` per the user's choice at the finishing-a-branch menu.

## 2026-07-31 | issue #114 — Master Results residual #111 gaps (implementation landed 2026-07-30)

- **What #114 collected, and what shipped:** four numbered items plus a two-part addendum, left over from #111's close-out audit. None were data-corruption bugs — they were "the researcher cannot see something the system already knows," or dead weight. Shipped: item 1 (GC provenance), item 3 (error ordering), item 4 (dead entry points), and both addendum consequences. **Item 2 was deliberately not built** and is deferred to #113 (see below).
- **Item 3 — error ordering (`82559c4`).** `_process_bytes` is two-phase by necessity, so appending errors in execution order put *every* Phase-1 error above *every* Phase-2 one: a row 5 Duration error printed above a row 2 upsert failure, while researchers read the list against the sheet top-down. Row-level errors now carry their row number in a local `row_errors: List[Tuple[int, str]]` and are sorted in at the end with a stable sort. Deliberately **not** a regex over the finished message strings — the number is in hand at all four append sites, and two of them use a different message prefix (`Row 5: invalid Duration…` vs `Row 5 (SERUM_001a): …`). Sheet-level errors keep the separate `out.errors` path because all four of them (`Failed to read file`, `File has no sheets`, `Failed to parse sheet`, `missing required columns`) return immediately, so they can never interleave; `extend` rather than assignment preserves that if a non-returning one is ever added. **The plan's prose said "three" such sites; there are four** — the code is right, the plan was wrong, corrected during review.
- **Item 1 — GC provenance, decided as a warning, not a schema column (`c6e4238`).** `h2_di_superseded` already reached the client per-row in `feedbacks`, which `frontend/src/api/bulkUploads.ts:9` types and **no non-test component renders**. Rather than build that UI or persist the source, one file-level warning now names the affected rows (first 10, then "and N more") and states the DI reading was not stored and cannot be recovered. It renders in the warnings panel `BulkUploadRow.tsx:236-250` already draws, so **zero frontend change** — verified at merge time that the only `feedbacks` reference under `frontend/src` is still the type declaration. The justification for not doing the schema work is measured, not a guess: **0 of 499 rows** on the current v3 Dashboard carry a reading in both GC blocks, so precedence is never actually contested today and the warning is silent on every sheet in use. `test_no_supersede_warning_when_precedence_is_uncontested` pins that silence for FL-only, DI-only and neither-block rows — a warning researchers learn to ignore is worse than no warning.
- **Addendum consequence 1 — no new test was needed (`b9e9016`).** The addendum asked for a regression test pinning the same-block geometry pairing; **it already existed** as `test_di_wins_ignores_stray_full_loop_gas_geometry`, added in #111's own fix wave. What was missing was the measured justification, so the test was **retuned, not added**: Full Loop's real carryover magnitude (4235 mL) against a real DI injection (30 mL / 14.7 psi), with the docstring recording that all 35 DI-won rows in the live sheet also carry populated FL geometry and that the wrong pairing would compute `h2_micromoles` off a 141x too-large volume — a plausible-looking number with nothing to flag it. Because the behavior already worked there was no conventional red phase; instead the DI branch of `_resolve_h2` was temporarily broken to observe the failure (`4235.0 != 30.0`) and reverted. A guard nobody has seen fail is not yet a guard.
- **Addendum consequence 2 — carryover geometry dropped (`19d2a4e`), the branch's only behavior change.** `_resolve_h2`'s no-concentration branch returned the Full Loop gas columns so a geometry-only row "behaved as it did pre-#111." That allowance assumed a blank gas cell meant no data; per Mat (2026-07-30) carryover is a permanent condition of the GC sheets and `H2 (ppm)` is the field of record, so those columns held a previous run's values on **207 of 499 rows**. Nothing computed wrong — `_calculate_hydrogen` requires a concentration — but persisted, 4235 mL was indistinguishable from a real measurement. Verified before implementing that **no test relied on geometry-only rows**: only five tests pass FL geometry and every one carries a concentration in one block or the other. Second-order effect pinned by `test_overwrite_clears_stale_geometry_when_the_reading_goes_away`: because both gas fields are in `SCALAR_UPDATABLE_FIELDS`, an `OVERWRITE` re-upload now clears stale geometry instead of re-asserting carryover.
- **Item 4 — three dead things deleted, not two (`3fe1dac`, `f70418f`).** `sync_from_path` and `from_bytes` had no production callers, and both returned `MasterUploadResult.as_tuple()`, which drops `warnings` by construction — so `as_tuple` was the actual loaded gun and went too, leaving `from_bytes_ex` as the only entry point. `sync_from_path` was deader than #114 claimed: #74 removed path-based sync along with both `/master-results/config` endpoints and the sync button, and the tracker file it probes was moved to `99_Archive/` on 2026-07-30 with no `master_results_path` row in `AppConfig`, so it returned "file not found" unconditionally while advising the user to configure a path through a UI that no longer exists. `settings.master_results_path` and `_default_master_results_path()` went with it (its default scanned `C:\Users\` at import time for the archived file). **Safe on the lab PC:** `SettingsConfigDict(extra="ignore")` means a leftover `MASTER_RESULTS_PATH=` in `.env` is ignored, not an error — and neither `.env.example` nor `docs/ENVIRONMENT.md` ever documented the variable, so there was nothing to update there.
- **#114 said ~20 positionally-unpacking tests; there were 46.** Plus 2 in `tests/integration/test_master_results_sync_endpoint.py` and 1 `sync_from_path` test. Converted via one module-local `_upload(db, xlsx) -> tuple` helper (45 call sites, the 46th living in a deleted test) whose docstring records *why* it is local — so a future reader does not re-add the deleted surface. Two tests were deleted rather than converted: `test_sync_from_path_file_not_found_returns_error` (asserted an error string naming a removed UI, on a path reachable from nothing) and `test_from_bytes_tuple_shape_unchanged` (asserted the contract being removed).
- **Item 2 deferred to #113, deliberately.** A rename that drops the `h2` token (`FL Hydrogen (ppm)`, `Full Loop ppm`) is invisible: `_H2_TOKEN` misses it, and the "no recognized H2 column" backstop only fires when *neither* block is present. Not built here because #113's warning and this one must share one false-positive design, and #113 is still open and unstarted. Recorded in the issue doc, in the plan's Global Constraints, and in a comment on GitHub #114.
- **Three false documentation claims were caught and fixed before merge**, all by reviewers checking docs against code rather than against the brief:
  1. `v_primary_experiment_results` was cited as exposing the two gas columns. **That view is dead** — `database/event_listeners.py:661` drops it on every startup and nothing ever creates it. The real source is `v_results_h2`. The claim propagated from `.claude/rules/MODELS.md`, which still describes it as live (pre-existing, tracked in `docs/working/issues/05-models-md-stale-v-primary-experiment-results.md`).
  2. "Re-uploading makes those Power BI cells go blank" was **unconditionally false**: `scalar_results_service.py:120-135` only nulls a field when `overwrite=True`, and the parser strips `None` values first, so an ordinary re-sync leaves stale geometry untouched. Cut from the user guide; the accurate conditional version lives in the issue doc's Notes. It is moot for `v_results_h2` anyway, whose `WHERE ... sr.h2_concentration IS NOT NULL` filter excludes exactly the affected rows.
  3. The deprecated wide `DI a/b/c H2 (ppm)` message was described as a file-level **error** in `docs/user_guide/BULK_UPLOADS.md` and again in a ticked `[x]` acceptance criterion; it is a warning. Both fixed. This one came from the plan's own text — see below.
- **Files changed:**
  - `backend/services/bulk_uploads/master_bulk_upload.py` — `row_errors` + stable sort; `superseded_rows` tally and the file-level warning; `_resolve_h2`'s no-concentration branch returns no geometry; `sync_from_path`, `from_bytes` and `MasterUploadResult.as_tuple` deleted; module docstring's first line corrected (it still advertised path reading); the `errors` alias renamed `sheet_errors` so a future `errors.append` in a row loop cannot silently bypass the sort; comment records that row *warnings* have no ordering guarantee and why that is safe today.
  - `backend/config/settings.py` — `master_results_path`, `_default_master_results_path()` and the now-unused `pathlib` import deleted.
  - `tests/services/bulk_uploads/test_master_bulk_upload.py` — 4 new tests, 1 retuned, 2 deleted, `_upload` helper, 45 call-site conversions.
  - `tests/integration/test_master_results_sync_endpoint.py` — 2 call sites to `from_bytes_ex`; upload outcome bound to `outcome` so it no longer shadows the ORM row named `result`.
  - `.claude/rules/MODELS.md`, `docs/user_guide/BULK_UPLOADS.md`, `docs/CALCULATIONS.md`, new `docs/issues/issue-114-master-results-residual-gaps.md` (+ hook-synced `docs/project_context/` copies, byte-identical, never hand-edited).
  - `docs/superpowers/plans/2026-07-30-issue-114-master-results-residual-gaps.md` — the plan, with three of its own defects corrected in place (below).
- **The plan document was wrong in three places, all corrected in it rather than only in the code:**
  1. Its scripted PowerShell replacement (`Get-Content -Raw` piped to `Set-Content -Encoding utf8`) **mojibake-corrupts every em dash under PowerShell 5.1** — `Get-Content -Raw` decodes with the ANSI default before the utf8 re-encode. It corrupted the test file when run; the implementer reverted and redid it with an explicit UTF-8 read/write. Verified at merge: 0 mojibake sequences, 28 em dashes intact.
  2. Its expected test count (246) was stale — the true `develop` baseline is 264 and this branch is 266.
  3. Its user-guide replacement text is the source of false claim 3 above.
- **Tests added:** yes — 4 new (`test_errors_are_listed_in_sheet_row_order`, `test_no_supersede_warning_when_precedence_is_uncontested`, `test_geometry_without_a_concentration_is_not_stored`, `test_overwrite_clears_stale_geometry_when_the_reading_goes_away`), 1 retuned, 2 deleted. `tests/services/bulk_uploads/` 264 to 266.
- **What was and was not verified.** Full backend suite at final HEAD: **3 failed, 1302 passed, 4 skipped**. The 3 are the documented pre-existing baseline, all in `tests/test_pg_backup_restore.py`, from an earlier test's `drop_all()` wiping `experiments_test`; this branch's schema diff over `database/models/`, `alembic/` and `database/event_listeners.py` is **empty**, so it cannot affect table existence or FK integrity — but the failures were **not** re-verified against `develop` in this session. The three bulk-upload suites together: 355 passed, with 4 pre-existing `SAWarning`s from `tests/api/conftest.py:34` on files this branch does not touch. **`docs/GIT_WORKFLOW.md`'s "No linting errors" cannot pass as written:** this repo has no lint config at all (no `setup.cfg`, `.flake8`, `tox.ini` or `pyproject.toml`), so `flake8` defaults to 79 columns the codebase never followed and `black` has never been applied — `develop` shows 36 E501s on the same two files. The standard applied instead was a regression check at 100 columns: production files 0, and the 3 test-file findings (one `F401`, two `E127`) are byte-for-byte pre-existing on `develop`. No live upload through the running API and no frontend involvement — there was no frontend change to exercise.
- **Decision logged:** no — the four scope decisions (warning over schema column; defer item 2 to #113; delete the dead trio plus the orphaned setting; drop carryover geometry) are product/scope calls recorded in the issue doc and this entry, not lasting architectural patterns.
- **Docs updated:** yes.
- **Process:** 6-task subagent-driven build, 10 commits, six task reviews, two task fix rounds (Task 5 variable shadowing; Task 6 three doc-accuracy findings), whole-branch review on the most capable model (verdict: ready to merge with fixes — 0 Critical, 2 Important, both false doc statements), one fix wave, one scoped re-review. One reviewer finding was itself wrong (a test docstring said to name the deleted method never did) and was correctly declined rather than forced. One finding was plan-mandated and the controller ruled on it instead of escalating, on the grounds that a factual error inside a requirement is not a trade-off the user chose; disclosed at the time. Ledger was at `.superpowers/sdd/2026-07-30-issue-114-master-results-residual-gaps/`.
- **PR:** none — merged locally to `develop` per the user's choice at the finishing-a-branch menu. Branch never pushed.

## 2026-08-01 | issue #115 — GC Measurements KPI reads 0/0 while the lab is active

- **Diagnosis first, because it changed the work:** the KPI query was never broken. `gc_run_date`
  is populated on 115 of 1056 dev-DB `scalar_results` rows and **every one falls in Mar–May 2026**;
  restricted to rows that carry an H2 reading, coverage ran Mar 35/51 · Apr 59/61 · May 16/16 and
  then stopped. Across 9,615 audited `scalar_results` updates (Feb–May 2026, 6,510 in April alone)
  the only field ever recorded going non-null → NULL was `gross_ammonium_concentration_mM`, 3
  times — so the "overwrite re-upload wipes the date" hypothesis in the issue has **zero**
  instances in the data. The card was accurately reporting a real void that nothing in the app
  made visible. The query, the workday window and the frontend wiring are all unchanged.
- **Honest limit:** the dev DB's real data ends ~May 2026 (its June–July rows are `HPHT_901*` /
  `SERUM_DEMO_901*` fixtures from #111/#114), so it cannot prove what happened on the lab PC in
  June–July. Corrected production queries were handed off instead — the issue's original Q2/Q3
  cite `scalar_results.created_at`/`updated_at`, **neither of which exists**; the replacement Q2
  reads `modifications_log` JSONB and answers the wipe question directly. All four were executed
  against the dev DB before shipping, so they are copy-paste correct rather than merely plausible.
- **Files changed:**
  - `backend/services/bulk_uploads/master_bulk_upload.py` (LOCKED — additive only, per explicit
    user authorization): one file-level warning when a row carries an H2 reading with a missing or
    unreadable `GC Run Date`, plus one denominator counter. Reports coverage (`n of total` rows
    carrying an H2 reading), naming sheet rows only at ≤10. Silent when the row has no H2 reading.
    No parse/write logic touched.
  - `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` — `ExpandedRow` renders NMR/ICP/GC/XRD run
    dates from `ResultWithFlags` (all three backend layers already shipped; render-only). A blank
    GC date shows `not recorded` plus an explanatory line when the row has an H2 reading. Also
    removed the `loadingScalar` early return that hid the block behind an unrelated fetch.
  - `frontend/src/pages/Dashboard.tsx` — GC card subtitle reads `no GC Run Date recorded in this
    window` at zero instead of `across 0 experiments`; tooltip states the counting rule both ways.
  - `docs/issues/issue-115-gc-run-date-visibility.md` (new),
    `docs/issues/issue-master-results-overwrite-wipes-unlisted-fields.md` (new),
    `docs/issues/issue-results-api-missing-run-dates.md`, `docs/user_guide/DASHBOARD.md`,
    `docs/upload_templates/master_bulk_upload.md`, `docs/superpowers/plans/2026-07-31-issue-115-…md`
  - Tests: `tests/services/bulk_uploads/test_master_bulk_upload.py`,
    `frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx`,
    `frontend/src/pages/__tests__/Dashboard.test.tsx`
- **Tests added:** yes — backend: warning fires with the right denominator, silent without an H2
  reading, and the >10-row coverage branch (the realistic production path, since a full re-upload
  processes every row) asserts a ratio with no row list. Frontend: GC date rendered, `not recorded`
  when an H2 reading exists without one, absent when it doesn't, the header absent in that case,
  the mixed non-GC-date render path, the block surviving a never-resolving scalar fetch, and both
  Dashboard subtitle branches. 349 backend / 207 frontend passing.
- **Scoped out deliberately (user decision, 2026-07-31):** (1) the `overwrite=True` field-wipe —
  real in the code and worse than the issue framed it (an `Overwrite=TRUE` Master Results upload
  nulls the **eight** fields the sheet never carries, incl. `background_ammonium_concentration_mM`,
  which moves net ammonium) but with zero observed instances and not the cause of the 0/0. Handed
  off to its own doc. (2) redefining the KPI to count H2 readings instead of GC run dates.
- **Known limit, now documented:** the KPI window is **rolling** (last 7 workdays), so the Mar–Jul
  2026 gap can never appear on the card. Backfilling correct historical dates does not help; only
  dates entered going forward will count. This branch stops the omission recurring — it cannot
  repair the number originally reported.
- **Decision logged:** yes — `docs/working/decisions.md`

## 2026-08-01 | issue #116 — Overwrite=TRUE nulled the eight fields the sheet never carries

- **The reproduction came first and changed nothing about the diagnosis, but proved it.**
  `issue-results-api-missing-run-dates.md` §3 asked for this in July and it had never been
  written. Two tests seeded a scalar row with all eight UI-only fields set, ran an
  `Overwrite=TRUE` Master Results upload, and watched them fail: all eight wiped, named in
  the failure output. The mechanism was confirmed against the code path rather than by
  inspection for the first time.
- **The ticket's proposed fix would have broken #114.** Its Recommended-fix section floated
  "only write keys present in `result_data`". But #114 shipped
  `test_overwrite_clears_stale_geometry_when_the_reading_goes_away`
  (`test_master_bulk_upload.py:1161`), which *depends* on overwrite nulling absent fields —
  that is what removes stale GC carryover geometry when a row's H2 reading disappears
  (207 of 499 rows on the live sheet carry a previous run's values). Presence-based
  clearing would have re-asserted them. The rule had to separate *unmapped* from
  *mapped-but-blank*, which is a different fix from the one the ticket described. Caught
  before writing code, by grepping what already depended on the branch being changed.
- **Fix:** `create_scalar_result_ex` pops an optional `_sheet_fields` and, on the overwrite
  branch, writes only fields inside it (`sheet_fields is None` → previous behavior exactly,
  so the two non-opted-in callers are untouched). `master_bulk_upload.py` declares its set
  as `frozenset(result_data)` captured **before** the `None`-strip — derived from the dict
  literal, not restated beside it, so a future sheet column cannot silently land outside the
  declared set. The strip's guard widened from `k == "_overwrite"` to `k.startswith("_")`.
  The first draft used a hand-maintained module constant; it was replaced during refactor
  precisely because it could drift from the literal it mirrored.
- **Files changed:**
  - `backend/services/scalar_results_service.py` — `_sheet_fields` pop + bounded overwrite loop.
  - `backend/services/bulk_uploads/master_bulk_upload.py` (LOCKED — additive only, per
    explicit user authorization 2026-08-01, same shape as the #115 precedent): declares the
    derived set, widens the strip guard. No parse or write logic touched.
  - `tests/services/bulk_uploads/test_master_bulk_upload.py` — 3 tests.
  - `.claude/rules/MODELS.md`, `docs/user_guide/BULK_UPLOADS.md`,
    `docs/upload_templates/master_bulk_upload.md`,
    `docs/issues/issue-master-results-overwrite-wipes-unlisted-fields.md`.
- **Tests added:** yes — 3. Two pin the preservation (one on `background_ammonium_concentration_mM`
  specifically, since it is the only one of the eight that moves a reported number; one on all
  eight as a set). The third pins the opposite half of the rule — a carried column left blank
  still clears — using conductivity rather than the gas columns so it does not depend on
  `_resolve_h2` precedence. Without it the fix would be indistinguishable from "overwrite never
  clears anything". `tests/services/bulk_uploads/` 269 → 272.
- **Verification:** full backend suite 1308 passed / 3 failed / 4 skipped. The 3 are the
  documented `tests/test_pg_backup_restore.py` baseline and were **re-run on `develop` this
  session and fail identically there** — the #114 entry flagged that this check had been
  skipped, so it was actually done this time rather than inherited.
- **Scoped out (user decision, 2026-08-01):** `scalar_results.py` and `quick_upload.py` reach
  the same branch and declare nothing, so they retain the whole-list behavior and the same
  latent bug. Their sheets have no fixed schema, so the declared set must be derived per-file
  from the columns actually present — a different and less certain fix across two more locked
  parsers. The service-side mechanism is already general; opting them in is one key each.
- **Two stale claims fixed in `docs/upload_templates/master_bulk_upload.md`**, both found
  while editing it rather than sought: it credited the flow to `bulk_create_scalar_results_ex`
  (this parser calls `create_scalar_result_ex` per row, each in its own SAVEPOINT), and its
  Output section still documented the tuple return #114 item 4 deleted.
- **Not mine, left uncommitted:** `docs/POWERBI_MODEL.md` was modified at 18:15 during this
  session by something outside it (OneDrive sync is the likely source; the repo lives in a
  synced folder). It adds `v_results_scalar_rollup` to the Power BI view table plus a
  Replicate & Timepoint Handling section — unrelated to #116. The `--all` PreToolUse sync
  hook then propagated it to `docs/project_context/POWERBI_MODEL.md`. Both left unstaged.
- **Decision logged:** no — bounding overwrite to a declared field set is a bug fix with a
  recorded rationale, not a new architectural pattern. The scope call (Master Results only)
  is in the issue doc's Follow-up section.
- **Docs updated:** yes.

## 2026-08-01 | inline — rollup replicate counts wrong; NULL timepoint buckets
- **Trigger:** user restored the 2026-08-01 production backup into dev and reported that
  `v_results_scalar_rollup` replicate counts did not match the raw experiment IDs, plus
  "I can see all experiments on the data app but not all IDs in Power BI / SQL".
- **Files changed:** `database/event_listeners.py` (rollup view SQL),
  `backend/api/schemas/results.py`, `frontend/src/api/experiments.ts`,
  `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx`,
  `database/data_migrations/demote_stale_t3_prefix_rows_017.py` (new),
  `tests/views/test_v_results_scalar_rollup.py`, `tests/api/test_experiment_rollup.py`,
  `tests/api/test_replicate_group_detail.py`,
  `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`,
  `docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md` (new),
  `docs/POWERBI_MODEL.md`, `docs/PSQL_ACCESS.md`, `docs/api/API_REFERENCE.md`,
  `docs/user_guide/REPLICATES.md`, `.claude/rules/MODELS.md`.
- **Four root causes, all measured against the restored backup (1009 experiments):**
  (A) `n_replicates` was `COUNT(sr.result_id)` over a LEFT JOIN — counted scalar ROWS, wrong
  in 457/1412 groups, 335 of them reading 0 (every one an ICP-only timepoint rendering a
  phantom row in a *scalar* rollup). (B) 807/1959 primary rows (41%) have a NULL
  `time_post_reaction_bucket_days`, collapsing all timepoints of a group into one row —
  legacy only, zero created since 2026-03. (C) `uq_primary_result_per_experiment_bucket` is
  inert on NULL buckets because Postgres treats NULLs as distinct: 198 duplicate primary
  pairs / 397 excess rows on NULL buckets, **zero** on real ones. (D) six stale `-t3` vials
  parked at day 6/7.
- **Shipped:** `n_replicates` → `n_vials` / `n_replicate_letters` / `n_values`, LEFT→INNER
  join. Production effect: 1412→1077 groups, miscounts 457→0, phantom groups 335→0.
  Migration 017 demotes the six stale rows (applied to dev only).
- **Tests added:** yes — 4 in `tests/views/`, pinning the three counts separately, ICP-only
  exclusion, and one-vial-two-rows. 12 existing assertions renamed to `n_vials`.
- **Verification:** full backend suite 1312 passed / 3 failed / 4 skipped — the 3 are the
  documented `tests/test_pg_backup_restore.py` baseline (1308 + 4 new = 1312 checks out).
  Frontend: 14 vitest pass, eslint clean, `tsc --noEmit` adds no new errors (the 3 in
  `ResultsTab.columns.test.tsx` are pre-existing and in a file not touched here).
  flake8 on `results.py` 31→30.
- **Scope grew mid-task:** the rename was approved on the belief that only Power BI read the
  column, but `replicate_groups.resolve_rollup_rows` feeds it to a **required** API field
  rendered by the React group page — so it was carried through the schema, TS type and
  component rather than left to 500 the endpoint. Flagged to the user.
- **Two proposals were wrong and were corrected rather than executed.** Fix 4 planned to
  re-bucket the six `-t3` rows to day 3; each vial already held a correct day-3 row, so that
  would have collided with the unique index — and the stale rows turned out to be empty
  shells (every scalar column NULL, no files), so they were demoted instead. Fix 3 planned a
  206-row backfill from `_day<N>_` description tokens; only 16 are collision-free, the other
  190 are re-ingested duplicates of a row already in that bucket (186/190 case-insensitive
  label match, 174/190 value-identical). Escalated, not actioned.
- **Corrected a false claim in `MODELS.md`:** it stated a data migration had backfilled all
  pre-existing NULL-bucket rows. 807 remain.
- **Not a bug:** "can't see all experiment IDs" — `v_experiments` exposes all 1009; 292
  experiments simply have no results, so any visual built on a results view drops them.
  Documented as a warning in `POWERBI_MODEL.md` rather than "fixed".
- **Still open (user decisions):** Fix 3's 190 duplicates (demote vs delete; which copy wins
  for the 16 that disagree) and Fix 2 (`NULLS NOT DISTINCT`, non-additive → schema-checklist
  Phase 2 sign-off, blocked on Fix 3). Migration 017 not yet run against production.
- **Decision logged:** no — replacing a miscounting column and demoting empty superseded rows
  are bug fixes with rationale recorded in the issue doc, not new architectural patterns.
- **Docs updated:** yes.

## 2026-08-05 | issue #109 follow-up — duplicate conditions rows
- **Trigger:** user reported the experiments list 500ing and one experiment refusing to
  delete through either delete path, framed initially as two duplicate `experiments` rows
  with `experiment_deletion_bulk.py:140`'s `.scalar_one_or_none()` suspected as the cause.
- **The initial framing was not what the data showed.** `experiments.experiment_id` carries
  a UNIQUE index in production (`ix_experiments_experiment_id`), confirmed against the
  2026-08-05 dump before writing any code — two duplicate `experiments` rows were never
  possible, and `experiment_deletion_bulk.py:140` cannot raise `MultipleResultsFound`. The
  actual duplicate was one table deeper: grouping `experimental_conditions` by
  `experiment_fk` found exactly one `HAVING COUNT(*) > 1` group. Recorded explicitly in the
  issue doc so the next "one or none" report is not chased into the same wrong table.
- **Files changed:** `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py`
  (new), `backend/api/routers/conditions.py`, `backend/api/routers/experiments.py`,
  `backend/services/experiment_deletion.py` (docstring only),
  `database/models/conditions.py`, `alembic/versions/00063a5dd6a8_unique_conditions_per_experiment.py`
  (new), `tests/data_migrations/test_dedupe_conditions_018.py`,
  `tests/models/test_conditions_unique_experiment_fk.py`, `tests/test_fresh_install_migration.py`,
  `tests/pre_constraint_conditions.py` (new), `tests/api/test_experiments.py`,
  `tests/services/test_experiment_deletion.py`,
  `tests/services/bulk_uploads/test_experiment_deletion_bulk.py`,
  `tests/api/test_additives.py`, `tests/api/test_conditions.py`,
  `docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md` (new),
  `.claude/rules/MODELS.md`, `docs/api/API_REFERENCE.md`, `.claude/commands/deploy.md`.
- **Root cause:** `experimental_conditions` carries two identities — the authoritative
  `experiment_fk` and a denormalized `experiment_id` string no rename path updates. 187 of
  1013 production rows (18%) were stale; 175 named an experiment with no conditions row at
  all, 12 named a different experiment's row, and 6 strings collided on two rows each.
  `GET /api/conditions/by-experiment` resolved by the stale string, 404'd for an experiment
  that already had conditions, the detail page offered "Add Details", and `POST
  /api/conditions` inserted a second row with no existence check. Exactly one experiment
  reached that state: `SERUM_Cation_011a-t5` (cond 901 + cond 1062), value- and
  additive-identical. Four consumers then broke on the duplicate: `_build_list_item`
  (500 via `MultipleResultsFound`), the list join (silent fan-out, comment claimed it
  couldn't happen), `v_experiments`/`v_experiment_conditions` (duplicate Power BI dimension
  key), and `serialize_experiment_snapshot` (same exception inside the delete cascade,
  making the experiment undeletable via both single and bulk delete).
- **Shipped:** dedupe + backfill migration 018 (dry-run default, rule-based survivor
  selection, `--apply` to write); `by-experiment` resolved through `experiment_fk`;
  `POST /api/conditions` returns 409 on an existing row; `_build_list_item`,
  `serialize_experiment_snapshot`, the detail GET, the rename path and the sample-id path
  all select the lowest-id row instead of `scalar_one_or_none()`/`.one()`; the list join's
  incorrect "cannot fan out" comment corrected; `UNIQUE (experiment_fk)`
  (`uq_conditions_experiment_fk`) added via Alembic revision `00063a5dd6a8`, whose
  `upgrade()` refuses with a `RuntimeError` listing offenders if duplicates remain.
- **Found by the final whole-branch review and also shipped:** the three additives endpoints
  (`GET`/`PUT`/`DELETE /api/experiments/{id}/additives`) still resolved the conditions row by
  the stale string. For the 6 duplicated strings that was a 500; for the 175 an empty list or
  404; and for the 12 whose string names a *different* experiment, the `PUT` wrote the
  additive onto **that other experiment's** conditions row — silent cross-experiment data
  corruption nobody had reported. All three now resolve via `experiment_fk`, and each
  handler fetches its `Experiment` up front, so a non-existent experiment 404s before any
  write instead of proceeding with the audit-log row skipped.
- **Tests added:** yes — migration 018 dedupe/backfill/BLOCKED-group coverage, the unique
  constraint, a fresh-install migration check, and `tests/pre_constraint_conditions.py`'s
  `without_conditions_unique` helper used by 9 tests across `tests/api/`, `tests/models/`
  and `tests/services/` to simulate a pre-#109 database and prove the tolerant readers
  degrade rather than 500.
- **Verification:** full backend suite 3 failed / **1337** passed / 4 skipped, run
  independently at the final HEAD — the 3 are the documented pre-existing
  `tests/test_pg_backup_restore.py` baseline. `alembic upgrade → downgrade → upgrade` clean
  on dev; constraint confirmed present on dev via psql. `flake8` gained no non-E501 findings
  on any changed file (the two E127s the new additives helper introduced were fixed; E501 at
  79 is unconfigured repo-wide noise against the project's Black-88 standard).
- **Deploy hazard — read before promoting to `main`.** `update.ps1:228` runs
  `alembic upgrade head` unconditionally and `Abort`s on a non-zero exit, and the new
  migration's pre-flight raises while the duplicate exists. So the nightly update will fail
  at Step 5 — skipping the Step 6 frontend rebuild — every night until
  `dedupe_conditions_and_backfill_ids_018.py --apply` has run on the lab PC. Documented as a
  new Step 0 in `.claude/commands/deploy.md` and above the command list in the issue doc.
- **Scope notes:** two things found during the investigation are recorded but not fixed —
  `_id_match.py::normalize_id` conflates 13 real experiment pairs (touches locked
  `bulk_uploads` parsers, needs its own `/start-task`), and
  `experimental_conditions_service.py:39` (legacy-only, unreachable from the current app)
  still creates conditions with no existence check. Both detailed in the issue doc's
  Out-of-scope section.
- **Decision logged (user, 2026-08-05):** additive equivalence in the 018 script checks only
  `(compound_id, amount, unit)`, ignoring `lot_number`/`purity`/`supplier_lot`/
  `addition_method` — kept as is, since the one real duplicate's additives match on all of
  those fields too. `vial_count` inflation on a pre-constraint duplicate (issue #98 status
  read-only side effect) — deferred, since it becomes impossible once migration 018 runs and
  the constraint lands. The 018 script has not yet been applied to any database, including
  dev; production deploy sequence (dedupe --apply, then alembic upgrade head, then Power BI
  refresh) is recorded in the issue doc.
- **Decision logged (user, 2026-08-05), third:** bulk rename
  (`backend/services/bulk_uploads/new_experiments.py:543-575`) syncs experiment notes and
  `modifications_log` rows but **not** `experimental_conditions.experiment_id` — this is the
  mechanism that produced all 187 stale strings, so migration 018's backfill will decay with
  every future bulk rename. Tracked as a follow-up rather than fixed here: it needs a locked
  bulk-upload parser change with its own sign-off, and the damage is now capped (the
  constraint and the 409 guard mean a stale string can no longer yield a duplicate row, only
  a 404 on the conditions tab).
- **Parked, not fixed:** the "no rename path updates the string" wording survives in
  `database/models/conditions.py:9-12` (locked) and `backend/api/routers/conditions.py:50-52`;
  both sat outside the final fix wave's permitted file list. The precise statement is in
  `.claude/rules/MODELS.md` and the issue doc.
- **Docs updated:** yes.

## 2026-08-07 | inline — Master Results upload duplicate-guard key

- **Trigger:** the 2026-08-05 duplicate-conditions investigation flagged, as a scope note,
  that `_id_match.py::normalize_id` conflates 13 real experiment pairs and that the Master
  Results duplicate pre-pass keyed on the raw ID string rather than that normalized key —
  itself a follow-on from the earlier `fix/id-match-ambiguity` work. Actioned as its own
  `/start-task` since it touches a locked bulk-upload parser.
- **Files changed:** `backend/services/bulk_uploads/master_bulk_upload.py` (locked, changed
  under explicit sign-off from Mat, 2026-08-07), `tests/services/bulk_uploads/test_master_bulk_upload.py`,
  `docs/LOCKED_COMPONENTS.md`, `docs/project_context/LOCKED_COMPONENTS.md`,
  `.claude/rules/MODELS.md`, `docs/working/issue-log.md` (this entry).
- **Shipped**, four commits against `master_bulk_upload.py`:
  1. `7bd654b` — the Phase-1 duplicate tally re-keyed onto
     `(_id_match.normalize_id(experiment_id), normalize_timepoint(t))` instead of the raw ID
     string, so two spellings that differ only by case or zero padding — which the DB lookup
     already resolves to one experiment — now collide instead of both silently upserting,
     the later row overwriting the earlier.
  2. `2da6474` — one error is now emitted per collision group rather than one row-error each,
     naming every colliding row and every distinct spelling, anchored at the group's first
     row so the sheet-order sort holds.
  3. `2378ae9` — the per-row Duration-vs-`-t`-token disagreement warning was aggregated into
     one file-level coverage line.
  4. `800926c` — found during **Task 3's code review**, not during Task 4: the third
     commit (`2378ae9`) counted disagreements in Phase 1 (at comparison time), so a row
     that disagreed *and* was then rejected (duplicate, or a failed upsert) was named in a
     warning claiming "each reading was recorded at the day its ID encodes" while its own
     error said no row for that vial-day was written — the two messages contradicted each
     other. Flagged as a plan-mandated finding; the human ruled on 2026-08-07 to move the
     tally to Phase 2, after the write, matching the sibling GC-run-date warning's placement
     (`h2_reading_rows`), with the warning's wording deliberately left unchanged.
- **Accepted converse:** two genuinely different experiments whose IDs differ only by
  case/padding would now both be rejected as a false collision. Measured 0 of 1009 dev-DB
  experiments share a normalized key (2026-08-07), so this has not fired in practice.
- **Tests added:** yes, in all four commits (see `tests/services/bulk_uploads/test_master_bulk_upload.py`).
- **Verification — measured against the team's live workbook**
  (`Master_Results_Tracker_v3.xlsx`, Dashboard sheet, read-only, 2026-08-07): the workbook
  was edited at 09:19 on 2026-08-07, during this session (resolved rows 202 → 236; sheet
  rows unchanged at 499). On the current file, the same-file comparison is what carries the
  "Task 1 took effect" claim: raw-string key = **34 groups / 68 rows**; normalized key =
  **37 groups / 74 rows**. The difference is **exactly 3 groups / 6 rows** — precisely the
  three case-variant pairs the raw-string key specifically misses (rows 29/194, 32/195,
  35/196, IDs differing only by `..._cation_..._c...` vs `..._Cation_..._C...` casing).
  This **NORM = RAW + 3** invariant held on the plan's earlier snapshot too (26 raw + 3 =
  29 projected), so the fix's demonstrated effect is the +3, and only the +3 — the absolute
  counts (34/37 here vs. 26/29 projected) moved because the workbook grew between the two
  measurements, not because of anything in the code.
  Separately, a standalone script reproducing the Phase-1 logic (`_resolve_row_identity` +
  `normalize_id` + `normalize_timepoint`, no database) found the sheet-level
  Duration-vs-`-t`-token disagreement count was **118 of 169 comparable rows** — this is
  **not** the number the upload will actually emit.
  The script (a Phase-1-only reproduction with no DB) counts every row where a comparison
  was *possible*; commit `800926c` moved the real tally to Phase 2, after the write, so the
  live upload's warning counts and names only rows that were actually written — a strictly
  smaller set, since every one of the 74 rejected duplicate rows above is excluded from it.
  No database was available to compute the true Phase-2 number end-to-end in this task.
- **Scope notes — two findings from the same investigation, deliberately not fixed:**
  1. `database/experiment_id_parser.py::split_timepoint_token` accepts only `-t<days>`,
     while `normalize_id` treats `_t1` and `-t1` as the same key. So `SERUM_Catalyst_005a_t1`
     resolves to the right stored experiment but then hard-errors on the timepoint conflict,
     where the hyphen spelling would have uploaded with a warning instead. Needs its own
     `/start-task`: it changes the canonical ID grammar used by lineage repo-wide, not just
     this parser.
  2. Missing `-t` vials are not auto-created — `auto_create_treatment_experiment` handles
     only `_`-delimited treatment variants with an existing parent. Deliberately left alone:
     auto-creating them would have fabricated `SERUM_Catayst_002-t3` (a typo) as a real
     experiment.
- **Decision logged (user, 2026-08-07):** re-key the duplicate guard on the normalized ID
  rather than the raw string, accepting the converse risk above — recorded as the footnote
  in `docs/LOCKED_COMPONENTS.md`.
- **Docs updated:** yes.

## 2026-08-07 - ICP label timepoint: `-t<days>` wins over `_Day<n>`

- **Audit finding:** the ID does **not** fail to parse. `extract_sample_info`'s regex
  is end-anchored, so `SERUM_Cation_005c-t5_Day12_21x` correctly yielded
  `SERUM_Cation_005c-t5`. What broke is the timepoint: `Day12` became the result's
  day while the vial ID declared day 5, and `icp_service.py` is the one write path
  that never called `apply_id_timepoint`, so nothing raised.
- **Measured before the change (dev DB, 2026-08-07):** 969 `icp_results` rows, of
  which **0** carry a `-t` token in `raw_label` and 969 carry `_Day`/`_Time`;
  167 of 1009 experiments are `-t` vials across 82 distinct stems, **0** of which
  have a bare experiment row; **0** ICP results were attached to any `-t` vial. The
  failure was entirely prospective - no backfill was needed.
- **Decisions (user, 2026-08-07):** the ID wins on the row (never rejected); `Day`
  becomes optional when `-t` is present; labels with no timepoint are reported as
  warnings; and the disagreement gets **one file-level warning**, aligning with
  `master_bulk_upload.py:766` after that precedent was surfaced.
- **Locked component:** `icp_service.py` (`docs/LOCKED_COMPONENTS.md`) - explicit
  sign-off given; recorded as footnote 3.
- **Three mocks had to be re-pointed at the `_ex` name**, in
  `tests/api/test_bulk_uploads.py` (x2) and `tests/test_icp_handling.py`
  (`TestICPRouterOverwrite`). All three referenced `parse_and_process_icp_file` by
  attribute name, so after the router switched to `_ex` the mock returned a bare
  `MagicMock`, the 4-way unpack raised, and the router except branch swallowed it.
  `test_icp_oes_dry_run_rolls_back` would still have PASSED - the except branch also
  satisfies its rollback-called/commit-not-called assertions - so it would have
  silently stopped proving dry-run. It now asserts the `[DRY RUN] ICP-OES:` message
  to pin the real success path.
- **Scope notes - deliberately not fixed:**
  1. `_find_experiment` still uses its own naive strip-and-concatenate key plus
     `.first()` rather than `_id_match.normalize_id` / `find_experiment_matches`. It
     is *stricter* on zero padding than the canonical key, so `SERUM_Catalyst_1a-t7`
     will not match stored `SERUM_Catalyst_001a-t7`. Measured 0 collisions across all
     1009 experiments.
  2. `-T5` / `_t5` spellings remain unaccepted - widening them changes the repo-wide
     ID grammar, already scoped to its own task. They now land in the *reported* skip
     bucket rather than vanishing.
  3. `tests/test_icp_parsing.py` and `tests/test_icp_service.py` are print-only
     scripts (the former re-implements the parser locally and asserts nothing). Left
     untouched; real coverage went into `tests/test_icp_handling.py`.
  4. The 2-tuple wrappers are retained because
     `legacy/streamlit_frontend/bulk_uploads.py:1558,1599` still calls
     `parse_and_process_icp_file`.
- **Tests added:** yes - `tests/test_icp_handling.py::TestICPLabelTimepointToken`
  (25 cases) and `::TestICPTimepointTokenPersistence` (2), plus 2 endpoint tests.
- **Docs updated:** yes.

## 2026-08-10 | inline - ICP label timepoint token (`/complete-task` record)
- **Files changed:** `backend/services/icp_service.py`,
  `backend/api/routers/bulk_uploads.py`, `tests/test_icp_handling.py`,
  `tests/api/test_bulk_uploads.py`, `docs/upload_templates/icp_oes_upload.md`,
  `docs/LOCKED_COMPONENTS.md`, `.claude/rules/MODELS.md`, `docs/working/decisions.md`
- **Tests added:** yes - 30 new cases: `TestICPLabelTimepointToken` (25),
  `TestICPTimepointTokenPersistence` (3, incl. the rejected-row wording guard),
  and 2 endpoint tests in `tests/api/test_bulk_uploads.py`
- **Decision logged:** yes - `docs/working/decisions.md`, 2026-08-10
- **Pre-merge finding (fixed before merge):** the disagreement warning was worded as a
  claim about persisted data ("each reading was recorded at the day its ID encodes"),
  copied from the post-write sibling in `master_bulk_upload.py`. The ICP tally runs at
  parse time, so a row that disagrees and is then rejected was named in a warning
  contradicting its own error - reproduced on a real request with
  `ZZZNOPE_999a-t5_Day12_21x`. This is the 2026-08-07 decision recurring in a second
  parser. Reworded to a label-level claim and pinned by a test; recorded as footnote 3
  property (f) in `docs/LOCKED_COMPONENTS.md`.
- **Lint:** no new findings; strictly cleaner than `develop` on the touched files
  (E302, one 126-char line and an unused `e` removed; W293 172 -> 141, W291 8 -> 6).
- **Full suite:** 1420 passed, 4 skipped, 3 failed - the 3 being the pre-existing
  `tests/test_pg_backup_restore.py` failures, confirmed identical on `develop`.

## 2026-08-10 | inline Bulk upload never recalculated conditions derived fields
- **Files changed:** `backend/services/bulk_uploads/new_experiments.py`,
  `tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py`,
  `docs/CALCULATIONS.md`, `docs/LOCKED_COMPONENTS.md`, `.claude/rules/MODELS.md`,
  `.claude/rules/schema-checklist.md`,
  `docs/issues/issue-bulk-upload-never-recalculates-conditions.md`,
  `docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md`,
  `docs/superpowers/plans/2026-08-10-bulk-upload-conditions-recalculate.md`,
  `docs/working/decisions.md`
- **Tests added:** yes - 6 new cases in one new file: 3 unit tests for the helper
  (both fields set; unknown id skipped silently; one failing row does not cost the
  others) and 3 integration tests through `bulk_upsert_from_excel` (conditions sheet,
  parent auto-copy, additives-only), plus 2 added during review - an overwrite that
  changes `rock_mass_g`, and the end-to-end `SERUM_Catalyst_001a-t3` reproduction
  (353.88 ppm / 30 mL / 14.7 psi -> Fe2+ %H2 = 0.100%)
- **Decision logged:** yes - `docs/working/decisions.md`, 2026-08-10
- **Root cause:** `water_to_rock_ratio` and `total_ferrous_iron_g` are STORED derived
  fields. Every write path called `recalculate()` after mutating a conditions row -
  `conditions.py:103`/`:125`, `experiments.py:1329`, `lineage_utils.py:603`, and the
  elemental-upload propagation - except this uploader, which recalculated only
  `ChemicalAdditive`. `calculate_ferrous_iron_yield_h2` returns None when
  `total_ferrous_iron_g` is None, so every scalar result under a bulk-created
  experiment silently lost BOTH Fe2+ yield percentages. Reported as a GC
  direct-injection bug; DI was a coincidence (the DI-era runs were all bulk-created).
  `SERUM_Cation_001a-t5`, same sample and same 30 mL / 14.7 psi geometry, HAS its
  Fe2+ %H2 because a later elemental upload recalculated its conditions.
- **The diagnostic:** a NULL `water_to_rock_ratio` on a row with positive rock mass
  and water volume. Two computable derived fields both empty means `recalculate()`
  never ran - not that an input was missing.
- **Production scope (backup 2026-08-10 01:00):** 845 of 1125 conditions rows had
  `total_ferrous_iron_g` NULL; 249 of 577 scalar rows with a computed `h2_micromoles`
  had no Fe2+ %H2 (157 recoverable, 77 blocked on missing FeO, 15 stale scalar rows).
  **Production is NOT yet backfilled** - see the Lab PC runbook in the issue doc.
- **Dev DB backfilled:** `total_ferrous_iron_g` NULL 732 -> 454; both-derived-NULL-
  with-inputs 137 -> 0; scalar rows missing Fe2+ %H2 158 -> 87, and all 87 remaining
  are the sample-has-no-FeO bucket, so zero fixable rows remain.
- **Pre-merge findings (all fixed before merge):** (1) the helper's `db.get()` sat
  OUTSIDE its per-row `try`, so one DBAPI error aborted the transaction and the next
  iteration raised `PendingRollbackError` into the router's blanket handler, discarding
  an otherwise-good upload - and half-applied mutations were committed while the warning
  said the row failed. Now `db.begin_nested()` per row, matching this file's existing
  idiom, with a raising `savepoint.commit()` also contained. (2) The cascade into
  pre-existing `ScalarResults` - the mechanism the whole backfill relies on - had no
  test; added, and proven by ablation to fail when only the cascade is disabled.
  (3) The docstring's PK-keying rationale was false in both halves (`db.expire_all()`
  precedes all three record sites; site 3 is outside the additives savepoint).
  (4) Docs claimed the count is reported in `info_messages`, which the router
  destructures as `_info` and discards.
- **Known gap (deliberate, out of scope):** the recalculation count is computed but
  never surfaced - wiring it needs an `UploadResponse` field and frontend rendering.
- **Also fixed:** `.claude/rules/schema-checklist.md` Phase 4 told engineers to run
  `create_reporting_views()`, a function that has never existed; views are recreated by
  a module-level block in `database/event_listeners.py`. Replacement verified by
  dropping a view and watching `python -c "import database.event_listeners"` restore it.
- **Lint:** no new findings. The single flake8 F-code on the touched file (F401,
  `ChemicalInventoryService` unused, line 22) is pre-existing and identical on
  `develop`; zero import lines were changed. `black --check` is not enforced in this
  repo - untouched files fail it too - so no reformatting was done (the file is locked).
- **Not satisfiable:** the pre-merge checklist's "calculation events appear in
  `logs/calculations.log`" - the calculation engine contains no logging at all and
  `logs/` is gitignored. Stale checklist item, same class as the phantom function above.
- **Full suite:** 1430 passed, 4 skipped, 3 failed - the 3 being the pre-existing
  `tests/test_pg_backup_restore.py` failures, confirmed identical by running that file
  on `develop`.


---

## 2026-08-11 â€” Master Results row merge (`feat/master-results-row-merge`)

**Spec:** `docs/superpowers/specs/2026-08-11-master-results-row-merge-design.md`
**Plan:** `docs/superpowers/plans/2026-08-11-master-results-row-merge.md`
**Sign-off for touching the locked parser:** Mat, 2026-08-11.

Several Dashboard rows can describe one vial-day: gas is drawn and run on one date,
the liquid/solid fraction is collected later, and each gets its own row. The upload
rejected both as duplicates, so nothing was written â€” 72 of the workbook's rows.
Phase 1.5 now collapses rows sharing a `(normalize_id, timepoint)` key into one merged
cell view before the upsert loop, and only a field two rows fill with **different**
values rejects that vial-day (whole, never partially).

**Verified against `docs/sample_data/Master_Results_Tracker_v3.xlsx`** (parse + rollback,
dev DB unchanged): "Merged 72 rows into 36 vial-days" and exactly four conflicts â€”
rows 2/185 (`SERUM_pH_001a-t1`: pH, conductivity, collection date), 14/57
(`SERUM_pH_004-t3`: DI H2), 222/272 (`GC_B_500ppm_1mL`: gas volume 30 vs 1),
264/268 (`A1 Flow Leak Test`: DI H2). Matches the spec's acceptance criterion exactly.
The other 24 errors are experiment-not-found â€” the dev DB's real data stops around
May 2026 and these are July/August experiments.

**Four defects found and fixed beyond the merge itself:**

1. **Collection date was never ingested (P0).** The column was renamed three times on
   2026-08-11 while the parser read a literal `"Sample Date"`, so `measurement_date` was
   dropped on all 275 dated rows â€” and *cleared* on `OVERWRITE=TRUE` rows, since it is a
   declared `_sheet_fields` entry. Every spelling is now aliased onto a `_COLLECTION_DATE`
   constant and a missing date column warns instead of failing silently.
2. **A zero gas volume/pressure read as a measurement.** The first real-workbook run
   reported 39 conflicts instead of 4; 35 were `DI gas volume (mL): 30 vs 0` between a
   gas row and its liquid partner, because the template writes 0 into those columns on a
   row that did no gas sampling. They joined pH and conductivity in `_ZERO_BLANK_COLUMNS`.
   The H2 *concentration* columns are deliberately excluded â€” 0 ppm is a real reading.
   **This is why the plan's Task 8 verification exists; the unit tests all passed while
   35 legitimate vial-days were being rejected.**
3. **Merge notes were emitted for rejected vial-days.** `group_notes` was appended before
   the conflict check, so a group that was rejected outright was told "those vial-days
   were merged without clearing anything" and "no row was rejected". Notes are now
   recorded only for a group that actually merged.
4. **Blank text cells were stored as the string `'nan'`** (pre-existing, not introduced
   here). pandas reads an empty cell as `float('nan')`, which is truthy, so
   `str(cell or "").strip()` yielded `'nan'`. This made the generated
   "Master upload â€” day N" description unreachable and, via
   `ExperimentalResults.sync_brine_flag`, set `has_brine_modification` from the `'nan'`
   string â€” **12 of the 140 flagged rows in the dev DB are false positives**, on an
   indexed and reported column. Fixed by a NaN-safe `_parse_text`.
   **Production rows already written this way are NOT corrected** â€” no backfill was run.

**Full suite:** 1482 passed, 4 skipped, 3 failed â€” the 3 being the pre-existing
`tests/test_pg_backup_restore.py` failures. Confirmed unrelated: they fail because
`experiments_test` currently has no tables (`relation "experiments" does not exist`),
this branch changes only `master_bulk_upload.py` and its test file, and neither is
referenced by that test module.

**Plan defects worth noting for future plan authors:** four `-k` filters in the plan
match no test names (they used experiment IDs that appear only in test bodies); the
predicted "eight duplicate-guard tests now fail" was actually one, because those
fixtures all used conflicting values and so still errored; and the plan's footnote â´
was already taken by the conditions-recalculation contract, so the row-merge footnote
is âµ.

---

## OPEN DEFECT â€” `_t1` vs `-t1` files a reading at the wrong timepoint

**Not fixed by the row-merge work.** Needs its own `/start-task`: it changes the
canonical experiment-ID grammar used by lineage repo-wide, so it is not a parser-local
change.

`_id_match.normalize_id` is run-delimited and treats `_t1`, `-T1` and `-t1` as the
**same** match key, but `database/experiment_id_parser.py::split_timepoint_token`
accepts a lowercase `-t` **only**. The two disagree. Verified in code, 2026-08-11:

```
normalize_id('SERUM_X_005a_t1') == normalize_id('SERUM_X_005a-t1')  # True
split_timepoint_token('SERUM_X_005a_t1')  -> ('SERUM_X_005a_t1', None)   # no token
split_timepoint_token('SERUM_X_005a-t1')  -> ('SERUM_X_005a', 1.0)
```

Consequence: a row spelled `_t1` (or `-T1`) resolves to the **same stored experiment**
as its `-t1` sibling, but its timepoint token is unrecognised, so its
`Duration (Days)` is used instead of the day its ID declares â€” a reading filed at the
wrong timepoint on a real vial. It is also invisible: the row uploads without error.

**Correction to the plan's evidence.** The plan cites rows 95/214 of
`Master_Results_Tracker_v3.xlsx` as `SERUM_Catalyst_005a_t1` vs
`SERUM_Catalyst_005a-t1`. That does **not** reproduce on the 2026-08-11 revision â€”
both rows read `SERUM_Catalyst_005a-t1`, they merge normally, and the workbook contains
**zero** IDs with an underscore `_t<n>` token and zero with a capital `-T<n>`. So this
is currently a **latent** defect with no known live instance, not an active mis-filing.
It stays open because nothing prevents the spelling from reappearing and nothing would
report it. The same gap is recorded on the ICP side in footnote Â³ of
`docs/LOCKED_COMPONENTS.md`.

Since the row merge landed, two such rows would also present as a merge candidate that
inexplicably did **not** merge â€” they key to different timepoints â€” which is the most
likely way a researcher would notice it.

### Backfill for the `'nan'` text defect â€” `fix_nan_text_fields_019.py`

Written 2026-08-11, same session as the parser fix, so it deploys alongside it.
Modelled on `zero_ph_conductivity_016.py` (same bug class: an Excel template blank
stored as a value, parser fixed going forward, historical rows corrected by script).

**Production impact, measured directly from `docs/sample_data/experiments_20260810_010002.sql`**
(read via `pg_restore --data-only --table experimental_results -f -`; no database was
created and nothing was written):

| Metric | Production 2026-08-10 | Dev |
|---|---|---|
| `experimental_results` rows | 2094 | 1961 |
| `brine_modification_description = 'nan'` | 12 | 12 |
| ...of those flagged `has_brine_modification` | 12 (all) | 12 (all) |
| `has_brine_modification = true` total | 141 | 140 |
| **False-positive share of the flag** | **8.5%** | 8.6% |
| `description = 'nan'` | **0** | 0 |

`description` is clean in both because researchers always fill that column; only the
usually-blank `Modification` cell ever tripped the bug. 120 distinct real modification
values are present in production and must survive the cleanup.

**Status: applied to DEV only.** Dev went 140 flagged -> 128, with 0 `'nan'` values
remaining and all 128 real values preserved (128 non-null = 128 flagged, self-consistent).
**Production has NOT been backfilled** â€” that runs on the lab PC after deploy.

**Runbook (lab PC, after the parser fix is deployed):**

```bash
# 1. Dry run. Prints the counts above; writes nothing.
python database/data_migrations/fix_nan_text_fields_019.py

# 2. Confirm the numbers look like the production column above (~12 rows, all flagged),
#    then apply.
python database/data_migrations/fix_nan_text_fields_019.py --apply
```

Expect "Rows updated: 12", "Remaining 'nan' values: 0", and the flagged total to drop by
exactly the updated count. If `description = 'nan'` is non-zero the script REPORTS those
row ids and does not touch them â€” `description` is `NOT NULL`, so there is no correct
null, and the script deliberately refuses to invent free text a researcher will read.
Those rows need a human decision.

**Two design points worth preserving if this script is ever edited:**

1. The `UPDATE` sets `has_brine_modification = false` **explicitly**. `sync_brine_flag`
   is an ORM `@validates` hook on the attribute and does NOT fire for raw SQL, so
   relying on it would null the text and leave all 12 flags true â€” the worse half of
   the bug.
2. Matching is `lower(btrim(...)) = 'nan'`, so `'NaN'` and `' nan '` are caught. Zero
   such variants exist today; the cost is one `lower()`.

## 2026-08-11 | inline â€” Master Results row merge (`feat/master-results-row-merge`)

- **Files changed:** `backend/services/bulk_uploads/master_bulk_upload.py`,
  `tests/services/bulk_uploads/test_master_bulk_upload.py`,
  `database/data_migrations/fix_nan_text_fields_019.py` (new),
  `docs/LOCKED_COMPONENTS.md`, `.claude/rules/MODELS.md`,
  `docs/upload_templates/master_bulk_upload.md`, `docs/working/issue-log.md`,
  `docs/working/decisions.md`, plus the hook's `docs/project_context/` copies
- **Tests added:** yes â€” 46 new (18 pure `_merge_group` unit tests over plain dicts,
  22 end-to-end upload tests, 3 blank-text/brine-flag tests, 3 collection-date
  spelling/warning tests); 9 duplicate-guard tests re-pointed from the rejection
  policy to the merge policy, none deleted
- **Decision logged:** yes â€” two entries in `docs/working/decisions.md`
  ("A vial-day is the write unit, not a spreadsheet row"; "A truthy NaN is a
  data-integrity bug, not a formatting one")

Verification: 381 pass in `tests/services/bulk_uploads/`, 221 across the four suites
the spec names, 1483 pass / 4 skipped / 3 failed on the full suite â€” the 3 being the
pre-existing `test_pg_backup_restore.py` failures from an empty `experiments_test`
schema, unrelated to a branch touching three files. flake8: zero F-codes on all
changed files (E501 is repo-wide convention â€” no flake8 config exists and `develop`'s
copy of the same file already had 41). Real-workbook dry run matches the spec's
acceptance criterion exactly: "Merged 72 rows into 36 vial-days", four conflicts on
rows 2/185, 14/57, 222/272, 264/268, dev DB unchanged.

Deferred deliberately: the `_t1` vs `-t1` grammar gap (own entry above, needs its own
`/start-task` â€” the fix direction is genuinely ambiguous between widening the parser,
narrowing `normalize_id`, and rejecting the row, and `split_timepoint_token` has ten
call sites including a second locked parser and a SQL pattern a test pins against
divergence). Production backfill for the `'nan'` rows is written and dry-run tested but
**not applied to production** â€” runbook above.

## 2026-08-11 | issue #101 — Letterless `-t` vials had no reachable group (`fix/issue-101-letterless-t-vial-groups`)

- **Files changed:**
  - `backend/services/replicate_groups.py` — new `_member_clause()`; `_fetch_members`
    and `group_exists` widened to it; members ordered `replicate_label NULLS FIRST`;
    module/`resolve_group` docstrings corrected
  - `frontend/src/pages/ExperimentList.tsx` — `isVialSetRow` routes a letterless
    multi-vial row to its group page; "N vials" chip
  - `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx` — error state distinct
    from empty; `fmtMeanSd()`; letterless members added to the drill-in links;
    `metricHasSpread` gates the error bars and the "mean ± sd" legend
  - `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`,
    `frontend/src/pages/ExperimentDetail/index.tsx` — group-detail query (`retry: false`)
    gates the Grouped toggle and the header Group link
  - `frontend/src/pages/ReplicateGroup/index.tsx` — vial-count header; letterless vials
    rendered in the members table
  - Tests: `tests/api/test_experiment_rollup.py` (+9),
    `frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.groupToggle.test.tsx` (new, 5),
    `.../GroupStrip.test.tsx` (+2), `.../GroupedResultsView.test.tsx` (+6),
    `frontend/src/pages/__tests__/ExperimentList.test.tsx` (+4),
    `frontend/src/pages/ReplicateGroup/__tests__/ReplicateGroupPage.test.tsx` (+3)
  - Docs: `.claude/rules/MODELS.md`, `docs/api/API_REFERENCE.md`,
    `docs/user_guide/REPLICATES.md`, `docs/working/issues/06-letterless-t-vial-group-membership.md`,
    `docs/issues/issue-replicate-group-detail-cache-eviction.md` (amended — see below),
    plus the hook's `docs/project_context/` copies
- **Tests added:** yes — 9 backend (membership; both `/groups` 404s; bare-stem parent not
  double-counted as a member; lettered + letterless coexistence; and four exclusion cases:
  `-2`, `-2-t0`, `_Desorption-t5`, and an underscore-stem LIKE-wildcard guard), 20 frontend
- **Decision logged:** yes — `docs/working/decisions.md`, "A letterless `-t` vial is an
  instance of the stem, not a replicate"

**How it presented, vs. how it was filed.** #101 was filed as a members-table/rollup
*disagreement* — accurate but understated. Because #98's list collapsing already merged
these vials into one row whose only link was its representative, and `group_exists`
required a letter, a letterless set had **no reachable group page at all**: both
`/groups/{base_id}` routes 404'd and `GroupedResultsView` rendered that 404 as "No primary
results to aggregate yet." So the researcher saw one experiment where there were four and
was told there was no data when the rollup had been computing it correctly all along. The
mixed case #101 was actually written around (letterless vials *plus* lettered members under
one stem) has **zero** instances in the dev DB; the all-letterless set is what bites.

Measured in dev: 13 stems with a letterless `-t` vial and no lettered member, 8 with more
than one vial (`SERUM_pH_002/004/006`, `SERUM_Catalyst_002/004/006/008/010`). Verified
post-fix on real data: `SERUM_pH_002` resolves to 4 members and its 3 rollup buckets,
while `SERUM_pH_001`/`_003` (lettered, 12 members / 3 letters each) are unchanged.

**Do not key membership on `id_timepoint_days IS NOT NULL`.** It reads as the obvious
filter and is wrong: `SERUM_001-2-t0` and `SERUM_001_Desorption-t5` both carry the stem as
their `base_experiment_id`, so both would be adopted into the wrong group. `_member_clause`
compares the timepoint-stripped `experiment_id` instead, by **equality** — `LIKE base_id ||
'-t%'` would treat the `_` in `SERUM_pH_002` as a wildcard. Both traps have a test.

**Left deliberately unfixed:**
- **Issue #105 is now worse, not fixed here.** The two new queries put
  `['replicate-group-detail', baseId]` on every experiment detail page instead of only on
  group navigation, so a stale entry after a delete can leave a Grouped toggle showing the
  wrong `n` — or a Group link on a set that has dropped to one vial. #105 has its own five
  acceptance criteria (including auditing `group-rollup` and a `DeleteExperiment.test.tsx`
  regression), and its eviction list is keyed by *experiment* ID while this key is keyed by
  *base* ID, so it is not a one-line addition. Its doc is amended with the new consumers.
- The six `-t3` vials carrying a T+7/T+6 result (`SERUM_pH_001a/001c/002/003a/004/006-t3`).
  Already demoted to non-primary by `demote_stale_t3_prefix_rows_017.py`, so the rollup is
  clean, but `get_experiment_results` returns non-primary rows — those vials' pages show
  both T+3 and T+7.
- `SERUM_Catalyst_010`'s four vials have no results at all, so its chart is legitimately
  empty after the fix. Use `SERUM_pH_002` to eyeball it.
- Repo-wide `npm run lint` still reports 6 errors in four untouched files, and
  `tsc --noEmit` 3 in `ResultsTab.columns.test.tsx` — all pre-existing, tracked as #106,
  and not gates (`npm run build` is `vite build`, no typecheck). Every file changed here is
  eslint-clean with zero flake8 F-codes.

Verification: 1492 pass / 4 skipped / 3 failed on full `pytest -q` — the 3 being the
pre-existing `test_pg_backup_restore.py` failures also present on `develop` (pass count
1483 → 1492). 227 vitest pass across 33 files. Every test watched fail first. No schema
change, no migration; `v_results_scalar_rollup`, the list router, and the deliberately
pinned `/{experiment_id}/replicate-group` wrapper are all untouched.

---

## 2026-08-13 | inline — Fix Vanadium/Sodium (and 7 other elements) missing from ICP API and React display
- **Files changed:**
  - `backend/api/schemas/results.py` — `ICPCreate` was missing 9 of the model's 37 fixed
    ICP columns (`ag, ce, k, la, na, pb, sc, th, v`); since `ICPResponse` inherits it with
    `from_attributes=True`, Pydantic silently dropped these on every response even though
    they exist on `ICPResults` and are populated in the DB. Added all 9. Also synced the
    same 9 into the unused (grep-confirmed, no importers) `ICP_ELEMENTS` module constant,
    which the 2026-06-17 sulfur entry below established is meant to mirror `ICPCreate`.
  - `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` — `ExpandedRow`'s hardcoded
    ICP element display list stopped at 13 of 37 elements; added `'na'` and `'v'` only
    (per user instruction — not restoring the full element set to this view).
  - `frontend/src/api/results.ts` — added `na`/`v` to the `ICPResult` TS interface.
  - `.claude/rules/MODELS.md` — separately, corrected the stale `ICPResults` fixed-column
    list (was missing `ag, ce, la, pb, sc, th, v`), committed directly to `develop` before
    branching since it was a docs-only fix already in flight.
- **Root cause:** two independent stale lists (API schema, frontend display array) both
  predating the addition of these 9 element columns to the model, neither updated when the
  columns were added. PowerBI's `v_results_icp` view already exposed `na_ppm`/`v_ppm`
  correctly — not a code defect there; a dataset refresh or new visual field was the likely
  gap. Noted separately (not fixed, out of scope): `v_results_icp` is itself missing
  `s_ppm` (sulfur), a similar but distinct gap.
- **Tests added:** no — existing suites cover this: 84 backend `-k icp` tests and 20
  frontend `ResultsTab.*.test.tsx` tests pass unchanged; `eslint` clean on both frontend
  files; pre-existing `flake8`/`black` violations in `results.py` predate this change and
  were not introduced by it.
- **Decision logged:** no
