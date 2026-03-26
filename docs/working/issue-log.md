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
  - `frontend/src/pages/NewExperiment/index.tsx` — added `handleCopyFrom`, `handleClearCopy`, copy banner, `CopyFromExisting` integration
  - `frontend/src/pages/NewExperiment/CopyFromExisting.tsx` — new component (referenced; created on that branch)
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
