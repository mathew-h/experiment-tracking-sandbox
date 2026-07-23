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
