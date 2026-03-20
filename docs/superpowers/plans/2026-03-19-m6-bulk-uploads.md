# M6 Implementation Plan — Bulk Uploads
**Date:** 2026-03-19
**Branch:** `feature/m6-bulk-uploads`
**Milestone file:** `docs/milestones/M6_bulk_uploads.md`

---

## Decisions Recorded

| Question | Answer |
|---|---|
| Master Results mode | Dual: "Sync from SharePoint" button (reads fixed path) + manual file upload |
| Master Results path | `C:\Users\MathewHearl\Addis Energy\All Company - Addis Energy\01_R&D\02_Results\Master Reactor Sampling Tracker.xlsx` |
| XRD Mineralogy card | Auto-detect format from file headers (one card, one endpoint, routes internally) |
| pXRF card | Keep it |
| actlabs_titration_data.py | Add as card 11 — "ActLabs Rock Analysis" (naming conflict with card 9 noted; user said "Sample Chemical Composition" but that name is taken) |
| UploadResponse.message field | Keep for backwards compat |
| UI layout | Expandable accordion rows, not card grid |
| Card order | Master Data → ICP → XRD → then rest |

---

## Current State Assessment

### API endpoints already live
| Endpoint | Parser | Status |
|---|---|---|
| POST `/api/bulk-uploads/scalar-results` | `scalar_results.py` | ✓ Working |
| POST `/api/bulk-uploads/new-experiments` | `new_experiments.py` | ✓ Working |
| POST `/api/bulk-uploads/pxrf` | `pxrf_data.py` | ✓ Working |
| POST `/api/bulk-uploads/aeris-xrd` | `aeris_xrd.py` | ✓ Working |

### Parsers that exist but lack API endpoints
| Parser | Service class | Notes |
|---|---|---|
| `rock_inventory.py` | TBD — audit return signature | Ready to wrap |
| `chemical_inventory.py` | TBD — audit return signature | Ready to wrap |
| `experiment_status.py` | TBD — audit return signature | Ready to wrap |
| `actlabs_xrd_report.py` | `ActlabsXRDReportService` | Routed from unified XRD endpoint |
| `actlabs_titration_data.py` | `ElementalCompositionService` + `ActlabsRockTitrationService` | Two separate cards |
| `backend/services/icp_service.py` | ICP service | In services/, not bulk_uploads/; needs lazy wrapper |

### Parsers that must be written
| Parser | Description | Complexity |
|---|---|---|
| `master_bulk_upload.py` | Reads from fixed SharePoint path OR uploaded file; delegates to scalar_results_service | Medium |
| `timepoint_modifications.py` | Bulk-set `brine_modification_description` on ExperimentalResults rows | Medium |
| `xrd_upload.py` | Unified XRD: auto-detects Actlabs vs Aeris format; routes to existing parser | Low (routing only) |

### NOT needed (previously planned)
- `elemental_composition.py` — `ElementalCompositionService` in `actlabs_titration_data.py` already covers this use case

### Frontend current state
- `BulkUploads.tsx`: 4-card grid stub
- `BulkUploadResult` interface: uses `rows_processed / rows_inserted / rows_skipped` — **mismatches** backend `UploadResponse` (`created / updated / skipped`)
- Missing: accordion layout, template downloads, next-ID chips, collapsible errors, 8 more upload types

### Schema mismatch to fix
Backend: `UploadResponse(created, updated, skipped, errors, message)` — missing `warnings`, `feedbacks`
Frontend: `BulkUploadResult(rows_processed, rows_inserted, rows_skipped, errors)` — wrong field names
M6 target: add `warnings: list[str]` and `feedbacks: list[dict]` to `UploadResponse`; keep `message`

---

## Final Card List (12 items)

| # | Card Title | Parser | Endpoint | Template | Mode |
|---|---|---|---|---|---|
| 1 | Master Results Sync | `master_bulk_upload.py` (new) | POST `/api/bulk-uploads/master-results` | — | Sync button + file upload |
| 2 | ICP-OES Data | `icp_service.py` | POST `/api/bulk-uploads/icp-oes` | — | File upload |
| 3 | XRD Mineralogy | `xrd_upload.py` (new, routes to actlabs or aeris) | POST `/api/bulk-uploads/xrd-mineralogy` | ✓ | File upload |
| 4 | Solution Chemistry | `scalar_results.py` | POST `/api/bulk-uploads/scalar-results` | ✓ | File upload |
| 5 | New Experiments | `new_experiments.py` | POST `/api/bulk-uploads/new-experiments` | ✓ | File upload + next-ID chips |
| 6 | Timepoint Modifications | `timepoint_modifications.py` (new) | POST `/api/bulk-uploads/timepoint-modifications` | ✓ | File upload |
| 7 | Rock Inventory | `rock_inventory.py` | POST `/api/bulk-uploads/rock-inventory` | ✓ | File upload |
| 8 | Chemical Inventory | `chemical_inventory.py` | POST `/api/bulk-uploads/chemical-inventory` | ✓ | File upload |
| 9 | Sample Chemical Composition | `ElementalCompositionService` (actlabs_titration_data.py) | POST `/api/bulk-uploads/elemental-composition` | ✓ | File upload |
| 10 | ActLabs Rock Analysis | `ActlabsRockTitrationService` (actlabs_titration_data.py) | POST `/api/bulk-uploads/actlabs-rock` | — | File upload |
| 11 | Experiment Status Update | `experiment_status.py` | POST `/api/bulk-uploads/experiment-status` | ✓ | File upload |
| 12 | pXRF Readings | `pxrf_data.py` | POST `/api/bulk-uploads/pxrf` | — | File upload |

---

## Implementation Plan

### Chunk A — Schema alignment (backend + frontend client)

**A1 — Extend `UploadResponse` Pydantic schema**
- File: `backend/api/schemas/bulk_upload.py`
- Add: `warnings: list[str] = []` and `feedbacks: list[dict] = []`
- Keep: `message: str` (backwards compat)
- Update the 4 existing endpoints to pass through warnings/feedbacks where parsers return them

**A2 — Fix frontend API client**
- File: `frontend/src/api/bulkUploads.ts`
- Rename `BulkUploadResult` fields to match backend: `created`, `updated`, `skipped`, `errors`, `warnings`, `feedbacks`
- Add functions for all 8 new upload types + `getNextIds()` + `downloadTemplate(type)`

**A3 — Parser return signature audit**
Read each parser before writing the endpoint wrapper. Record the exact tuple shape.
This is done as part of Chunk C (inline, before writing each endpoint).

---

### Chunk B — New parsers

**B1 — `timepoint_modifications.py`**
- File: `backend/services/bulk_uploads/timepoint_modifications.py`
- Inputs: Excel/CSV with `experiment_id`, `time_point`, `experiment_modification`
- Optional: `timepoint_type` (`actual_day` | `bucket_day`), `overwrite_existing`
- Column aliases: `experiment id`, `time (days)`, `description`, `modification`, `overwrite`
- Logic:
  - Parse float time_point
  - Use `find_timepoint_candidates` (±0.0001 day tolerance) to find `ExperimentalResults` row
  - Reject batch if duplicate `(experiment_id, time_point)` pairs without `overwrite_existing=true`
  - Set `brine_modification_description` on matched row (model `@validates` auto-sets `has_brine_modification`)
  - Write `ModificationsLog` entry for each changed row
- Template: `generate_template_bytes()` via openpyxl; required headers highlighted; INSTRUCTIONS sheet
- Returns: `(updated, skipped, errors, feedbacks)`

**B2 — `master_bulk_upload.py`**
- File: `backend/services/bulk_uploads/master_bulk_upload.py`
- Config: reads `MASTER_RESULTS_PATH` from `backend/config/settings.py`
  - Default: `C:\Users\MathewHearl\Addis Energy\All Company - Addis Energy\01_R&D\02_Results\Master Reactor Sampling Tracker.xlsx`
  - Override via env var `MASTER_RESULTS_PATH`
- Dual mode (single service, different entry points):
  - `sync_from_path(db)` — reads file from configured path, no user bytes
  - `from_bytes(db, file_bytes)` — reads from uploaded file bytes
- Both entry points: load "Dashboard" sheet; validate required cols (`Experiment ID`, `Duration (Days)`); delegate to `ScalarResultsService.bulk_create_scalar_results_ex`
- Column spec: `Experiment ID`, `Duration (Days)`, `Description`, `Sample Date`, `NMR Run Date`, `ICP Run Date`, `GC Run Date`, `NH4 (mM)`, `H2 (ppm)`, `Gas Volume (mL)`, `Gas Pressure (psi)` (→ MPa), `Sample pH`, `Sample Conductivity (mS/cm)`, `Modification`, `Overwrite`
- Returns: `(created, updated, skipped, errors, feedbacks)`

**B3 — `xrd_upload.py`**
- File: `backend/services/bulk_uploads/xrd_upload.py`
- Auto-detect logic (inspect column headers from first sheet):
  - **Aeris format**: `Sample ID` column matches regex `^\d{8}_.+?-d\d+_\d+$` → route to `AerisXRDUploadService.bulk_upsert_from_excel`
  - **ActLabs format**: first column is `sample_id` with plain sample IDs → route to `ActlabsXRDReportService.bulk_upsert_from_excel`
  - **Unknown**: return error "Unable to detect XRD file format. Expected Aeris or ActLabs format."
- Returns: `(created, updated, skipped, errors)` (normalised from whichever parser ran)
- Template: downloadable Excel template for the ActLabs wide-format (Aeris files come from instrument, no template needed)

---

### Chunk C — Backend endpoints

**File:** `backend/api/routers/bulk_uploads.py` (extend existing)

New endpoints to add:

```
POST /api/bulk-uploads/master-results
  - Body: optional UploadFile (if omitted, sync from configured path)
  - Lazy import master_bulk_upload; call sync_from_path() or from_bytes()
  - Run registry.recalculate(scalar_result, session) for each affected ScalarResults row

POST /api/bulk-uploads/icp-oes
  - Body: UploadFile (.csv)
  - Lazy import icp_service; call bulk_ingest_from_bytes or equivalent
  - No calc engine fields on ICPResults; audit log only

POST /api/bulk-uploads/xrd-mineralogy
  - Body: UploadFile (.xlsx/.xls/.csv)
  - Lazy import xrd_upload; call auto-detect entry point
  - No calc engine fields on XRDPhase

POST /api/bulk-uploads/timepoint-modifications
  - Body: UploadFile (.xlsx/.xls/.csv)
  - Lazy import timepoint_modifications

POST /api/bulk-uploads/rock-inventory
  - Body: UploadFile (.xlsx/.xls/.csv)
  - Lazy import rock_inventory

POST /api/bulk-uploads/chemical-inventory
  - Body: UploadFile (.xlsx/.xls/.csv)
  - Lazy import chemical_inventory

POST /api/bulk-uploads/elemental-composition
  - Body: UploadFile (.xlsx/.xls)
  - Lazy import actlabs_titration_data.ElementalCompositionService

POST /api/bulk-uploads/actlabs-rock
  - Body: UploadFile (.xlsx/.xls/.csv)
  - Lazy import actlabs_titration_data.ActlabsRockTitrationService

POST /api/bulk-uploads/experiment-status
  - Body: UploadFile (.xlsx/.xls/.csv)
  - Lazy import experiment_status

GET /api/bulk-uploads/templates/{upload_type}
  - upload_type: one of new-experiments | scalar-results | xrd-mineralogy |
    timepoint-modifications | rock-inventory | chemical-inventory |
    elemental-composition | experiment-status
  - Calls parser.generate_template_bytes() where available
  - Returns StreamingResponse (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
  - 404 for types with no template (master-results, icp-oes, aeris-xrd, actlabs-rock, pxrf)

GET /api/experiments/next-ids
  - Add to experiments.py router (after /next-id, before /{id}/results)
  - Query MAX(experiment_number) GROUP BY experiment_type for HPHT, Serum, CF
  - Return {HPHT: N, Serum: N, CF: N}; N = max+1 (or 1 if no experiments of that type)
  - Auth-required; staleTime 60s on frontend
```

**All endpoints must:**
- Require Firebase auth
- Use lazy imports
- Wrap parser call in try/except; return `UploadResponse` with errors list on failure
- Call `registry.recalculate(instance, session)` for affected models before commit (ScalarResults only for master-results and scalar-results uploads)

---

### Chunk D — Frontend BulkUploads page rebuild

**D1 — Accordion row component**
- File: `frontend/src/pages/BulkUploads/UploadRow.tsx`
- Props: `id`, `title`, `description`, `accept`, `uploadFn`, `templateType?`, `syncFn?`, `children?`
- Always-visible header: upload type name + one-line description + last-upload status badge
- Expand/collapse toggle on click (chevron icon, smooth transition)
- Expanded content:
  - Help text / format hint (as short paragraph)
  - File drop zone (FileUpload component) — hidden for Master Results sync-only trigger
  - "Sync from SharePoint" button (Master Results only, alongside file upload)
  - Template download button: enabled when `templateType` set; grayed out otherwise
  - Progress spinner during mutation
  - Result summary: Created / Updated / Skipped / Errors badges
  - Collapsible error table (show first 5, "show N more" toggle)
  - Collapsible warnings list (yellow, below errors)

**D2 — New Experiments row enhancements**
- `useQuery(['nextIds'], getNextIds, { staleTime: 60_000 })`
- Display chips inside expanded area: "Next HPHT: 072 · Next Serum: 043 · Next CF: 008"
- Template download independent of next-ID state

**D3 — Master Results row**
- Two actions in expanded area:
  - "Sync from SharePoint" button → calls `triggerMasterSync()` (no file, POST with no body)
  - File drop zone → calls `uploadMasterResults(file)`
- Help text: explains that sync reads from the configured SharePoint path; upload allows manual override

**D4 — BulkUploadsPage layout**
- File: `frontend/src/pages/BulkUploads/index.tsx` (move from `BulkUploads.tsx`)
- Page header: "Bulk Uploads" + subtitle
- Accordion list, one `UploadRow` per card
- Only one row expanded at a time (single-open accordion)
- Default: all collapsed

**D5 — API client**
- File: `frontend/src/api/bulkUploads.ts` (full rewrite)
- Add all 12 upload functions
- Add `getNextIds()` returning `{ HPHT: number; Serum: number; CF: number }`
- Add `downloadTemplate(type: string)` → triggers browser download via blob URL

---

### Chunk E — Tests

**Per upload type (12 types):**
- Round-trip: valid fixture → assert correct DB state (counts, field values)
- Atomic transaction: malformed mid-file row → assert zero rows written
- Auth rejection: 401 without token

**Type-specific:**
- Master Results: `sync_from_path()` with mocked file path; `from_bytes()` with uploaded file; confirm calc engine ran
- ICP-OES: multi-element multi-timepoint CSV; blank row filtering; duplicate spectral line resolution (best Intensity wins)
- XRD auto-detect: Aeris format detected + routed; ActLabs format detected + routed; unknown format → clear error
- Timepoint Modifications: duplicate (experiment_id, time_point) rejected without overwrite; cleared with overwrite; audit log entry written
- Elemental Composition: unknown analyte symbol skipped; unknown sample_id skipped; correct upsert
- ActLabs Rock: heuristic header detection (row 2 analytes, row 3 units); `<0.01` value stripping; `nd` treated as blank
- next-ids: empty DB → all return 1; seeded DB → returns max+1 per type

**Fixtures to create in `tests/fixtures/bulk_uploads/`:**
One valid + one malformed fixture per upload type.

---

### Chunk F — Documentation
- `docs/user_guide/BULK_UPLOADS.md` — one section per upload type with field descriptions
- `docs/developer/ADDING_UPLOAD_TYPE.md` — step-by-step guide for new cards
- Update `docs/api/API_REFERENCE.md` with all new endpoints
- Update `docs/milestones/M6_bulk_uploads.md` as chunks complete
- Update `plan.md`

---

## Execution Order

```
A1 (schema) → A2 (frontend client types)
  ↓
B1 (timepoint_modifications parser)
B2 (master_bulk_upload parser)
B3 (xrd_upload router parser)
  (B1, B2, B3 can run in parallel)
  ↓
C (all 8 new endpoints + template endpoint + next-ids)
  ↓
D1 (UploadRow component)
D2+D3 (New Experiments + Master Results special logic)
D4+D5 (page layout + API client)
  ↓
E (tests — requires C + B complete)
  ↓
F (docs)
```

---

## Settings to Add

```python
# backend/config/settings.py
MASTER_RESULTS_PATH: str = r"C:\Users\MathewHearl\Addis Energy\All Company - Addis Energy\01_R&D\02_Results\Master Reactor Sampling Tracker.xlsx"
```
Override via env var `MASTER_RESULTS_PATH`.
