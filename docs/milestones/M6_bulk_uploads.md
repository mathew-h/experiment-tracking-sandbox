# Milestone 6: Bulk Upload Feature

**Owner:** api-developer (primary), frontend-builder (UI), test-writer
**Branch:** `feature/m6-bulk-uploads`

---

## Objective

Expose all bulk data ingestion workflows through a clean, card-based React UI.
Each upload type wraps an existing backend parser — do not modify parser logic without
explicit user instruction. New parsers (Master Results sync, flexible XRD, flexible
elemental composition) are net-new additions in `backend/services/bulk_uploads/`.

---

## Upload Cards (one per type)

| # | Card Title | Backend Parser | Template Available | Notes |
|---|---|---|---|---|
| 1 | Master Results Sync | `master_bulk_upload.py` | No — fixed living file | Sync mode, not one-off upload |
| 2 | New Experiments | `new_experiments.py` | Yes — downloadable Excel | Show next-ID hints before download |
| 3 | Solution Chemistry | `scalar_results.py` | Yes — existing | No changes |
| 4 | ICP-OES Data | `icp_service.py` | No — raw instrument CSV | See spec: `docs/specs/icp_oes_upload.md` |
| 5 | XRD Mineralogy | `xrd_upload.py` (new) | Yes — downloadable Excel | Unified card; see spec |
| 6 | Timepoint Modifications | `timepoint_modifications.py` | Yes — downloadable Excel | No changes to parser |
| 7 | Rock Inventory | `rock_inventory.py` | Yes — existing | No changes |
| 8 | Chemical Inventory | `chemical_inventory.py` | Yes — existing | No changes |
| 9 | Sample Chemical Composition | `elemental_composition.py` (new) | Yes — downloadable Excel | Flexible wide-format; see spec |
| 10 | Experiment Status Update | `experiment_status.py` | Yes — existing | No changes to parser |

---

## Per-Card UI Requirements

Every card must include:
- **Header:** Upload type name + short description
- **File zone:** Drag-and-drop area (or "Sync Now" button for Master Results)
- **Pre-upload validation:** File type check before the file reaches the backend
- **Progress indicator:** Spinner during processing
- **Result summary:** Created / updated / skipped counts + collapsible error table
- **Template download button:** Where a template is defined (grayed out where N/A)
- **Help text / format hint:** What the file should look like; link to full spec

Cards with special UI behaviour are called out in individual specs below.

---

## Atomic Transactions

Every upload must write zero rows if validation fails mid-file.
The backend endpoint must wrap the parser call in a single DB transaction and
roll back on any unhandled exception.

---

## Calculation Engine

After every successful upload, the calculation engine must run for all affected records.
Call `registry.recalculate(instance, session)` for each modified model instance before
committing the transaction.

Affected models by upload type:
- Master Results Sync → `ScalarResults`
- Solution Chemistry → `ScalarResults`
- New Experiments → `ExperimentalConditions`, `ChemicalAdditive`
- ICP-OES → `ICPResults` (no calc engine fields; audit log only)
- XRD Mineralogy → `XRDPhase` (no calc engine fields)
- Sample Chemical Composition → `ElementalAnalysis` (no calc engine fields)

---

## Next-ID Helper (New Experiments card only)

Before the user downloads the template, the UI queries:

```
GET /api/experiments/next-ids
```

Response shape:
```json
{
  "HPHT": 72,
  "Serum": 43,
  "CF": 8
}
```

These are displayed as info chips on the card:
> Next HPHT: **072** · Next Serum: **043** · Next CF: **008**

The template download button is enabled immediately. The chips update on each
page load via a short-lived React Query with `staleTime: 60_000`.

The endpoint logic: for each `experiment_type`, query `MAX(experiment_number)` from
`Experiment` and return `max + 1`. Return `1` if no experiments of that type exist.

---

## Template Files

Template files live in `docs/upload_templates/`. Each template must exactly match
the column expectations of its parser. Any change to a parser's expected columns
requires a corresponding update to the template file and this milestone file.

| Template file | Parser |
|---|---|
| `new_experiments_template.xlsx` | `new_experiments.py` |
| `scalar_results_template.xlsx` | `scalar_results.py` |
| `xrd_mineralogy_template.xlsx` | `xrd_upload.py` |
| `timepoint_modifications_template.xlsx` | `timepoint_modifications.py` |
| `rock_inventory_template.xlsx` | `rock_inventory.py` |
| `chemical_inventory_template.xlsx` | `chemical_inventory.py` |
| `elemental_composition_template.xlsx` | `elemental_composition.py` |
| `experiment_status_template.xlsx` | `experiment_status.py` |

Templates are generated dynamically at download time via `openpyxl`. Do not commit
static `.xlsx` files to the repo — generate them from code so they stay in sync.

---

## Individual Upload Specs

Full parsing and UI details are in `docs/specs/`:

| Spec file | Upload type |
|---|---|
| `docs/specs/master_results_sync.md` | Master Results Sync |
| `docs/specs/new_experiments_upload.md` | New Experiments |
| `docs/specs/icp_oes_upload.md` | ICP-OES Data |
| `docs/specs/xrd_mineralogy_upload.md` | XRD Mineralogy |
| `docs/specs/elemental_composition_upload.md` | Sample Chemical Composition |

Solution Chemistry, Timepoint Modifications, Rock Inventory, Chemical Inventory, and
Experiment Status upload specs are documented in the existing upload template docs in
`docs/upload_templates/`.

---

## New FastAPI Endpoints Required

All endpoints live under `/api/bulk-uploads/`:

```
POST /api/bulk-uploads/master-results          (multipart or path-based sync)
POST /api/bulk-uploads/new-experiments
POST /api/bulk-uploads/scalar-results
POST /api/bulk-uploads/icp-oes
POST /api/bulk-uploads/xrd-mineralogy
POST /api/bulk-uploads/timepoint-modifications
POST /api/bulk-uploads/rock-inventory
POST /api/bulk-uploads/chemical-inventory
POST /api/bulk-uploads/elemental-composition
POST /api/bulk-uploads/experiment-status

GET  /api/experiments/next-ids                 (new, for New Experiments card)
```

All endpoints:
- Require Firebase auth
- Accept `multipart/form-data` (file upload) except master-results (see spec)
- Return a consistent `UploadResult` Pydantic schema (see below)
- Use lazy imports for parsers that import `frontend.config.variable_config`

### `UploadResult` schema

```python
class UploadResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]
    warnings: list[str]
    feedbacks: list[dict]
```

---

## Acceptance Criteria

- [ ] All 10 upload cards render with correct help text and template download buttons
- [ ] Each upload processes a valid test fixture file and returns correct counts
- [ ] Each upload rejects an invalid file (wrong type, missing required columns) with a clear error — zero DB rows written
- [ ] Calculation engine runs after writes for affected models (verified via `calculations.log`)
- [ ] Master Results sync reads from the configured path on the server, not a user-uploaded file
- [ ] New Experiments card shows correct next-ID chips before download
- [ ] All atomic transaction tests pass (malformed row mid-file → zero rows written)
- [ ] ICP-OES upload correctly handles multi-element, multi-timepoint CSVs with blanks and duplicates
- [ ] XRD upload correctly routes to sample-based or experiment+timepoint-based mode
- [ ] Elemental composition upload parses unit-bearing column headers correctly

---

## Test Writer Agent

- Round-trip test per upload type (valid fixture → assert DB state)
- Atomic transaction test per upload type (malformed fixture → assert zero rows written)
- Auth rejection test per endpoint
- Next-ID endpoint test (empty DB → returns 1; seeded DB → returns max + 1)
- ICP-OES: multi-batch CSV, blank filtering, duplicate spectral line resolution
- XRD: sample-ID mode vs experiment+timepoint mode detection
- Elemental composition: unit extraction from header (%, ppm, ppb)

## Documentation Agent

- `docs/user_guide/BULK_UPLOADS.md` — one section per upload type with screenshots
- `docs/developer/ADDING_UPLOAD_TYPE.md` — step-by-step guide for adding a new card
- `docs/specs/` — all individual upload spec files (listed above)
