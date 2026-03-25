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

## 2026-03-24 | inline — Experiment detail UI: input text color, chemical additives editor, tab rename
- **Files changed:** `frontend/src/components/ui/Input.tsx`, `frontend/src/components/ui/Select.tsx`, `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`, `frontend/src/pages/ExperimentDetail/index.tsx`, `frontend/src/api/chemicals.ts`, `frontend/src/pages/ExperimentDetail/NotesTab.tsx`, `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx`, `frontend/src/pages/NewExperiment/Step3Additives.tsx`, `frontend/src/pages/SampleDetail/AnalysesTab.tsx`, `frontend/src/pages/SampleDetail/NewSampleModal.tsx`, `frontend/src/pages/SampleDetail/OverviewTab.tsx`, `frontend/src/pages/SampleDetail/PhotosTab.tsx`, `frontend/src/components/ui/SampleSelector.tsx`, `docs/DESIGN.md`
- **Tests added:** no
- **Decision logged:** yes — updated `docs/DESIGN.md` with Form Input Text Color Rule: use `text-navy-900` for all form fields, never `bg-surface-input` (undefined token)
