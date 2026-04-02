# API Reference

Base URL: `http://localhost:8000`
Auth: All endpoints require `Authorization: Bearer <firebase-id-token>` header.

## Experiments

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/experiments` | List experiments. Query: `skip`, `limit`, `status`, `experiment_type`, `sample_id`, `researcher`, `reactor_number`, `date_from`, `date_to` |
| GET | `/api/experiments/next-id` | Next auto-incremented experiment ID. Query: `type` (Serum/HPHT/Autoclave/Core Flood). Returns `{"next_id": "HPHT_004"}` |
| GET | `/api/experiments/{experiment_id}/exists` | Check if experiment ID string is already in use |
| GET | `/api/experiments/{experiment_id}` | Get single experiment with conditions, notes, and modifications |
| GET | `/api/experiments/{experiment_id}/results` | List result timepoints with scalar/ICP existence flags |
| POST | `/api/experiments` | Create experiment (auto-assigns `experiment_number` if omitted) |
| PATCH | `/api/experiments/{experiment_id}` | Update status, researcher, date, sample_id, and experiment_id (rename) |
| PATCH | `/api/experiments/{experiment_id}/status` | Inline status update. Body: `{"status": "COMPLETED"}` |
| DELETE | `/api/experiments/{experiment_id}` | Delete experiment (cascades all related data) |
| POST | `/api/experiments/{experiment_id}/notes` | Add a note |
| PATCH | `/api/experiments/{experiment_id}/notes/{note_id}` | Edit note text. Body: `{"note_text": "..."}`. No-op if text unchanged. Writes ModificationsLog. Returns updated note with `updated_at`. |

### GET /api/experiments/{experiment_id}/exists

Check whether an experiment ID string is already in use.

**Auth:** Required (Firebase token)

**Path params:**
- `experiment_id` — the string to check

**Response `200`:**
```json
{ "exists": true }
```
or
```json
{ "exists": false }
```

**Usage:** Called by the frontend on a 300 ms debounce while the user types a custom ID, to show real-time availability feedback without submitting the form.

### PATCH /api/experiments/{experiment_id}

Update experiment properties.

**Auth:** Required (Firebase token)

**Path params:**
- `experiment_id` — the experiment string ID

**Request body fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `status` | string (enum) | No | `ONGOING`, `COMPLETED`, `CANCELLED` |
| `researcher` | string | No | Researcher name or initials |
| `date` | string (ISO 8601) | No | Experiment start date |
| `sample_id` | string | No | Reference to `SampleInfo.sample_id` |
| `experiment_id` | string | No | Rename: must be unique; max 100 chars; whitespace stripped before validation |

**Response `200`:** Updated experiment object with all fields.

**Errors:**
- `409 Conflict` — `experiment_id` is already in use by another experiment; `sample_id` FK constraint fails
- `422 Unprocessable Entity` — validation error (e.g., invalid status enum)

**Side effects:**
- On rename, `ExperimentalConditions.experiment_id` is updated and a `ModificationsLog` entry is written.

## Conditions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/conditions/{id}` | Get conditions by PK |
| GET | `/api/conditions/by-experiment/{experiment_id}` | Get conditions by experiment string ID |
| POST | `/api/conditions` | Create conditions (triggers `water_to_rock_ratio` calc) |
| PATCH | `/api/conditions/{id}` | Update conditions (recalculates derived fields) |

## Additives

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/experiments/{experiment_id}/additives` | List chemical additives for an experiment |
| PUT | `/api/experiments/{experiment_id}/additives/{compound_id}` | Upsert additive by compound PK. Body: `{"amount": float, "unit": string}`. Triggers recalculation. Writes ModificationsLog. |
| DELETE | `/api/experiments/{experiment_id}/additives/{compound_id}` | Remove additive by compound PK. Writes ModificationsLog. |
| PATCH | `/api/additives/{additive_id}` | Partial update by additive PK. Accepts `compound_id`, `amount`, `unit`, `addition_order`, `addition_method`. Triggers recalculation. Writes ModificationsLog. Returns 409 if new compound is already in the experiment. |
| DELETE | `/api/additives/{additive_id}` | Remove additive by additive PK. Writes ModificationsLog. |

## Results

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/results/{experiment_id}` | List all result timepoints for an experiment |
| POST | `/api/results` | Create result entry |
| GET | `/api/results/scalar/{result_id}` | Get scalar result |
| POST | `/api/results/scalar` | Create scalar (triggers H2 + ammonium yield calc) |
| PATCH | `/api/results/scalar/{scalar_id}` | Update scalar (recalculates) |
| GET | `/api/results/icp/{result_id}` | Get ICP result |
| POST | `/api/results/icp` | Create ICP result |

## Samples

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/samples` | List samples. Query: `search`, `country`, `rock_classification`, `characterized`, `has_pxrf`, `has_xrd`, `has_elemental`, `skip`, `limit` |
| GET | `/api/samples/geo` | Samples with coordinates only (for map view). Returns `[{sample_id, latitude, longitude, rock_classification, characterized}]` |
| GET | `/api/samples/{sample_id}` | Full sample detail with linked experiments, photos, analyses, elemental results |
| POST | `/api/samples` | Create sample. Auto-evaluates `characterized` on creation. |
| PATCH | `/api/samples/{sample_id}` | Update mutable fields. Auto-evaluates `characterized` unless `characterized` is explicitly set in the payload. |
| DELETE | `/api/samples/{sample_id}` | Delete sample. Returns 409 if experiments are linked. Returns 204. |
| POST | `/api/samples/{sample_id}/photos` | Upload photo (JPEG/PNG, max 20 MB). Returns `201 SamplePhotoResponse`. |
| DELETE | `/api/samples/{sample_id}/photos/{photo_id}` | Delete photo from DB and disk. Returns 204. |
| GET | `/api/samples/{sample_id}/analyses` | List external analyses for the sample |
| POST | `/api/samples/{sample_id}/analyses` | Create external analysis. pXRF: normalizes `pxrf_reading_no`, returns warnings for unmatched reading numbers. Auto-evaluates `characterized`. |
| DELETE | `/api/samples/{sample_id}/analyses/{analysis_id}` | Delete analysis. Auto-evaluates `characterized`. Returns 204. |
| GET | `/api/samples/{sample_id}/activity` | Last 100 modification log entries for the sample |

### GET /api/samples

Query parameters:
- `search` (string) — filter by sample_id or locality (case-insensitive substring)
- `country` (string) — exact match
- `rock_classification` (string) — case-insensitive substring
- `characterized` (bool) — filter by characterized status
- `has_pxrf`, `has_xrd`, `has_elemental` (bool) — filter by analysis type presence
- `skip` / `limit` (int, default limit=50)

Response shape:
```json
{
  "items": [
    {
      "sample_id": "SMP-042",
      "rock_classification": "Peridotite",
      "country": "Oman",
      "locality": "Samail Ophiolite",
      "characterized": true,
      "created_at": "2026-03-01T09:00:00Z"
    }
  ],
  "total": 14,
  "skip": 0,
  "limit": 50
}
```

### POST /api/samples/{sample_id}/analyses — pXRF notes

When `analysis_type` is `"pXRF"` and `pxrf_reading_no` is provided, the server:
1. Normalizes the reading number (strip whitespace, convert `"1.0"` → `"1"`)
2. Looks up `PXRFReading` by the normalized key
3. If not found, returns `ExternalAnalysisWithWarnings` (HTTP 201) with a `warnings` array — creation still succeeds

Response (pXRF with missing reading):
```json
{
  "analysis": { ... },
  "warnings": ["pXRF reading '42' not found in database — analysis created but reading is unlinked"]
}
```

## Chemicals

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chemicals/compounds` | List all compounds |
| GET | `/api/chemicals/compounds/{id}` | Get compound |
| POST | `/api/chemicals/compounds` | Create compound |
| GET | `/api/chemicals/additives/{conditions_id}` | List additives for a conditions record |
| POST | `/api/chemicals/additives/{conditions_id}` | Add additive (triggers full additive calc) |

## Analysis

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/analysis/xrd/{experiment_id}` | XRD phases for an experiment |
| GET | `/api/analysis/pxrf` | List pXRF readings. Query: `skip`, `limit` |
| GET | `/api/analysis/external/{experiment_id}` | External analyses for an experiment |

## Dashboard

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard/` | **M7** Full dashboard payload: summary stats, reactor cards, Gantt timeline, recent activity. Single call. |
| GET | `/api/dashboard/reactor-status` | Legacy — reactors with current ONGOING experiment |
| GET | `/api/dashboard/timeline/{experiment_id}` | All timepoints with scalar/ICP presence flags |

### GET /api/dashboard/

Returns all dashboard data in a single call. Response shape:

```json
{
  "summary": {
    "active_experiments": 5,
    "reactors_in_use": 4,
    "completed_this_month": 2,
    "pending_results": 1
  },
  "reactors": [
    {
      "reactor_number": 5,
      "reactor_label": "R05",
      "experiment_id": "HPHT_MH_072",
      "experiment_db_id": 142,
      "status": "ONGOING",
      "experiment_type": "HPHT",
      "sample_id": "SMP-042",
      "description": "Baseline run with magnetite catalyst",
      "researcher": "MH",
      "started_at": "2026-03-01T09:00:00Z",
      "days_running": 18,
      "temperature_c": 200.0
    }
  ],
  "timeline": [
    {
      "experiment_id": "HPHT_MH_072",
      "experiment_db_id": 142,
      "status": "ONGOING",
      "experiment_type": "HPHT",
      "sample_id": "SMP-042",
      "researcher": "MH",
      "started_at": "2026-03-01T09:00:00Z",
      "ended_at": null,
      "days_running": 18
    }
  ],
  "recent_activity": [
    {
      "id": 501,
      "experiment_id": "HPHT_MH_072",
      "modified_by": "MH",
      "modification_type": "update",
      "modified_table": "scalar_results",
      "created_at": "2026-03-19T14:30:00Z"
    }
  ]
}
```

**Notes:**
- Only occupied reactor slots are returned; the frontend renders all 18 fixed slots
- `description` is the text of the oldest note for the experiment
- Timeline limited to 100 most recent experiments
- Activity limited to last 20 modification log entries
- Core Flood experiments use `CF01`/`CF02` labels; all others use `R01`–`R16`

## Admin

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/admin/recalculate/{model_type}/{id}` | Re-run calc engine. model_type: `conditions`, `scalar`, `additive` |

## Bulk Uploads

All endpoints return `UploadResponse`:
```json
{
  "created": 0, "updated": 0, "skipped": 0,
  "errors": [], "warnings": [], "feedbacks": [], "message": ""
}
```

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/bulk-uploads/master-results` | Master Results sync. `file` optional — if omitted, reads from configured SharePoint path. Runs calc engine on affected `ScalarResults`. |
| POST | `/api/bulk-uploads/scalar-results` | Bulk-create/update `ScalarResults` rows from Excel template. Runs calc engine. |
| POST | `/api/bulk-uploads/new-experiments` | Create `Experiment` + `ExperimentalConditions` rows in bulk. |
| POST | `/api/bulk-uploads/icp-oes` | Import raw ICP-OES instrument CSV. |
| POST | `/api/bulk-uploads/xrd-mineralogy` | Unified XRD upload — auto-detects Aeris or ActLabs format. |
| POST | `/api/bulk-uploads/timepoint-modifications` | Bulk-set `brine_modification_description` on result rows. Writes audit log. |
| POST | `/api/bulk-uploads/rock-inventory` | Create/update `SampleInfo` records. Normalises sample IDs to uppercase, no underscores. |
| POST | `/api/bulk-uploads/chemical-inventory` | Create/update `Compound` (reagent) records. |
| POST | `/api/bulk-uploads/elemental-composition` | Import wide-format elemental composition into `ElementalAnalysis`. Query param: `default_unit` (auto-creates unknown analytes). |
| POST | `/api/bulk-uploads/actlabs-rock` | Import ActLabs geochemical analysis reports (Excel or CSV). Heuristic header detection. |
| POST | `/api/bulk-uploads/experiment-status` | Preview + apply bulk ONGOING/COMPLETED transitions. |
| POST | `/api/bulk-uploads/pxrf` | Import pXRF readings from instrument export. |
| GET | `/api/bulk-uploads/templates/{upload_type}` | Download Excel template. `upload_type`: `scalar-results`, `new-experiments`, `xrd-mineralogy`, `timepoint-modifications`, `rock-inventory`, `chemical-inventory`, `elemental-composition`, `experiment-status`. Returns 404 for types with no template. |
| GET | `/api/experiments/next-ids` | Returns `{"HPHT": N, "Serum": N, "CF": N}` — next experiment number per type. Used by New Experiments card. |

## Bulk Uploads

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/bulk-uploads/scalar-results` | Solution Chemistry Excel upload |
| POST | `/api/bulk-uploads/new-experiments` | New Experiments Excel upload |
| POST | `/api/bulk-uploads/pxrf` | pXRF data file upload |
| POST | `/api/bulk-uploads/aeris-xrd` | Aeris XRD file upload |

All bulk upload endpoints return:
```json
{"created": 5, "updated": 2, "skipped": 0, "errors": [], "message": "..."}
```

## Interactive Docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
