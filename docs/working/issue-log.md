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
