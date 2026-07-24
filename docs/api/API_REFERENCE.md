# API Reference

Base URL: `http://localhost:8000`
Auth: All endpoints require `Authorization: Bearer <firebase-id-token>` header.

## Experiments

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/experiments` | List experiments. Query: `skip`, `limit`, `status`, `experiment_type`, `sample_id`, `researcher`, `search` (case-insensitive partial match on `experiment_id`), `reactor_number`, `date_from`, `date_to`, `description` (matches the experiment's first note / Description column), `group_replicates` (bool, default false). `experiment_type`, `reactor_number`, and `description` are applied in SQL before `skip`/`limit`, so `total` and the returned page always reflect the fully-filtered set (#64). |
| GET | `/api/experiments/next-id` | Next auto-incremented experiment ID. Query: `type` (Serum/HPHT/Autoclave/Core Flood). Returns `{"next_id": "HPHT_004"}` |
| GET | `/api/experiments/{experiment_id}/exists` | Check if experiment ID string is already in use |
| GET | `/api/experiments/{experiment_id}` | Get single experiment with conditions, notes, and modifications |
| GET | `/api/experiments/{experiment_id}/results` | List result timepoints with scalar/ICP existence flags |
| GET | `/api/experiments/{experiment_id}/rollup` | Cross-replicate mean/median/std per timepoint bucket from `v_results_scalar_rollup` |
| GET | `/api/experiments/{experiment_id}/replicate-group` | The lettered replicate set (parent + members) this experiment belongs to |
| POST | `/api/experiments` | Create experiment (auto-assigns `experiment_number` if omitted) |
| POST | `/api/experiments/replicates` | Batch-create lettered replicates copying a base experiment's setup |
| PATCH | `/api/experiments/{experiment_id}` | Update status, researcher, date, sample_id, experiment_id (rename), and is_outlier |
| PATCH | `/api/experiments/{experiment_id}/status` | Inline status update. Body: `{"status": "COMPLETED"}` |
| DELETE | `/api/experiments/{experiment_id}` | Delete experiment (cascades all related data) |
| POST | `/api/experiments/{experiment_id}/notes` | Add a note |
| PATCH | `/api/experiments/{experiment_id}/notes/{note_id}` | Edit note text. Body: `{"note_text": "..."}`. No-op if text unchanged. Writes ModificationsLog. Returns updated note with `updated_at`. |
| GET | `/api/experiments/{experiment_id}/change-requests` | List reactor modification entries linked to this experiment. Returns `[]` if none. |
| GET | `/api/experiments/{experiment_id}/change-requests/recent` | Reactor modification entry for `date` (query param, default today) plus the most recent prior entry — both scoped to this experiment only, never another experiment that previously occupied the same reactor. Returns `{"selected": ..., "previous": ...}`, either nullable. |
| POST | `/api/experiments/{experiment_id}/change-requests` | Create or update a reactor modification for a given reactor + date. Body: `{"reactor_label": "R05", "requested_change": "...", "sync_date": "2026-07-20"}` (`sync_date` optional, defaults to today). Upserts on `(reactor_label, experiment_id, sync_date)`. |

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

### GET /api/experiments — `group_replicates`

When `group_replicates=true`, pagination runs over **top-level rows** instead of raw experiment rows:

- A row is top-level when `replicate_label IS NULL OR parent_experiment_fk IS NULL`.
- A lettered replicate that matches the active filters is represented by its parent row instead of itself — i.e. filtering that matches only `SERUM_001b` still pulls `SERUM_001` (the parent) into the page, with `b` attached as a child.
- Every list item (flat or grouped mode) now includes `base_experiment_id`, `parent_experiment_fk`, `replicate_label`, `is_outlier`, and `id_timepoint_days`.
- In grouped mode, each parent row additionally gets a `replicates` array: its lettered children (`replicate_label IS NOT NULL`, `parent_experiment_fk` pointing at this row), ordered by letter. Children are attached in full regardless of whether they individually matched the filters — that's the point of grouping. Non-parent items have `replicates: null`.
- `total` counts top-level rows, not raw experiment rows.
- Flat mode (`group_replicates=false`, the default) is unchanged — every experiment row is returned individually.

Example grouped item:
```json
{
  "id": 210,
  "experiment_id": "SERUM_001",
  "base_experiment_id": null,
  "parent_experiment_fk": null,
  "replicate_label": null,
  "is_outlier": false,
  "id_timepoint_days": null,
  "replicates": [
    { "id": 211, "experiment_id": "SERUM_001a-t7", "replicate_label": "a", "parent_experiment_fk": 210, "is_outlier": false, "id_timepoint_days": 7.0, "replicates": null },
    { "id": 212, "experiment_id": "SERUM_001b", "replicate_label": "b", "parent_experiment_fk": 210, "is_outlier": true, "id_timepoint_days": null, "replicates": null }
  ]
}
```

### GET /api/experiments/{experiment_id}/rollup

Cross-replicate mean/median/std per timepoint bucket, sourced from the `v_results_scalar_rollup` reporting view (see `MODELS.md`).

**Auth:** Required (Firebase token)

**Path params:**
- `experiment_id` — any member of the group (base, parent, or a lettered replicate) — the endpoint resolves the group key itself.

**Grouping key:** `COALESCE(base_experiment_id, experiment_id)` for the given experiment — i.e. its `base_experiment_id` if set, else its own `experiment_id`.

**Response `200`:** array of rows, one per `time_post_reaction_bucket_days`, ordered ascending. 19 fields per row:
`base_experiment_id`, `time_post_reaction_bucket_days`, `n_replicates`, `mean_gross_ammonium_mM`, `median_gross_ammonium_mM`, `sd_gross_ammonium_mM`, `mean_net_ammonium_mM`, `sd_net_ammonium_mM`, `mean_h2_micromoles`, `sd_h2_micromoles`, `mean_h2_grams_per_ton`, `sd_h2_grams_per_ton`, `mean_fe_yield_h2_pct`, `sd_fe_yield_h2_pct`, `mean_fe_yield_nh3_pct`, `sd_fe_yield_nh3_pct`, `mean_grams_per_ton_yield`, `sd_grams_per_ton_yield`, `mean_final_ph`.

**Errors:**
- `404 Not Found` — no experiment matches `experiment_id`

**Outlier exclusion (P4):** experiments with `is_outlier = true` are excluded from every statistic in this response, including `n_replicates` — a flagged replicate never contributes to the mean/median/std or the count, though its own data remains queryable via the per-row endpoints/views.

**Caveat (MODELS.md):** the grouping key does not distinguish a lettered replicate set from an ordinary sequential re-run sharing the same `base_experiment_id` (e.g. `HPHT_001` + `HPHT_001-2`). `n_replicates >= 2` on this endpoint does not by itself confirm the group is a lettered replicate set — check case-by-case.

### GET /api/experiments/{experiment_id}/replicate-group

The lettered replicate set (if any) that `experiment_id` belongs to.

**Auth:** Required (Firebase token)

**Response `200`:**
```json
{
  "base_experiment_id": "SERUM_001",
  "parent": { "id": 210, "experiment_id": "SERUM_001", "replicate_label": null, "status": "ONGOING", "is_outlier": false },
  "members": [
    { "id": 211, "experiment_id": "SERUM_001a", "replicate_label": "a", "status": "ONGOING", "is_outlier": false },
    { "id": 212, "experiment_id": "SERUM_001b", "replicate_label": "b", "status": "ONGOING", "is_outlier": true }
  ]
}
```

**Semantics:**
- `members` is `[]` for a non-replicate solo experiment (no lettered children, no parent).
- **Orphan members:** if a lettered member's parent row doesn't exist (or was deleted), `parent` is `null` and `members` still lists the siblings, resolved by matching `base_experiment_id` directly rather than via the parent FK.

**Errors:**
- `404 Not Found` — no experiment matches `experiment_id`

### POST /api/experiments/replicates

Batch-create lettered replicates copying a base experiment's setup.

**Auth:** Required (Firebase token)

**Request body:**
```json
{ "base_experiment_id": "SERUM_001", "count": 3 }
```
- `base_experiment_id` (string, required) — the stem; either the bare base or an explicit `S-0`/`S-1` group-parent spelling resolves to the same parent.
- `count` (int, 1–25, default 3)

**Response `201`:**
```json
{
  "created": [ /* ExperimentResponse-shaped objects, one per new replicate */ ],
  "skipped": [ "'SERUM_001a' already exists — skipped, not overwritten." ]
}
```

**Copy semantics:** each new replicate copies the base (parent) experiment's `sample_id`, `researcher`, `status`, `date`, its `ExperimentalConditions` row, and all `ChemicalAdditive` rows; the calc engine re-runs on the copied conditions and additives. Per-vial actuals (e.g. measured mass, actual reactor) are left as copies and are expected to be edited per replicate afterwards.

**Letter assignment:** continues after any existing lettered members for the base (e.g. `a`, `b` already present → new replicates get `c`, `d`, ...).

**Conflict handling:** a per-letter ID collision (an experiment already exists at that exact ID) is skipped with a message in `skipped` — it is never fatal; other requested replicates in the same call still get created. If fewer free letters remain than `count`, a message is added to `skipped` and only the available letters are created.

**Errors:**
- `404 Not Found` — no base/parent experiment exists for `base_experiment_id` (create the base experiment first)
- `409 Conflict` — unexpected IntegrityError on creation (distinct from the normal skip path above)

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
| `is_outlier` | boolean | No | Flags/unflags a bad vial (see `MODELS.md`). Writing it appends a `ModificationsLog` audit entry. |

**Response `200`:** Updated experiment object with all fields, including `is_outlier`.

**Errors:**
- `409 Conflict` — `experiment_id` is already in use by another experiment; `sample_id` FK constraint fails
- `422 Unprocessable Entity` — validation error (e.g., invalid status enum)

**Side effects:**
- On rename, `ExperimentalConditions.experiment_id` is updated and a `ModificationsLog` entry is written.
- On `is_outlier` change, a `ModificationsLog` entry is written recording the old/new value.

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

### POST /api/results and POST /api/results/scalar — `id_timepoint_days` (issue #81)

If the target experiment's `id_timepoint_days` is set (its ID carries a `-t<days>` token),
the day encoded in the ID is canonical for that vial's timepoint:

- An omitted/blank `time_post_reaction_days` (`POST /api/results`) or `time_post_reaction`
  (the scalar-result creation path shared by the UI and all bulk uploads) is filled from
  `id_timepoint_days`.
- A supplied value that differs from `id_timepoint_days` by more than
  `TIMEPOINT_TOLERANCE_DAYS` (0.0001 days) is rejected with `422 Unprocessable Entity`; the
  error message contains "canonical" and names the conflicting day.
- No change to behavior when `id_timepoint_days` is `NULL` (the common case).

This guard lives in `backend/services/result_merge_utils.py::apply_id_timepoint`, called
from `backend/api/routers/results.py::create_result` and
`backend/services/scalar_results_service.py::create_scalar_result_ex`. The bulk-upload
parsers (Solution Chemistry, Master Results Sync) additionally check this at the
string/row level before results ever reach these functions, so a conflicting row is
reported with a per-row error rather than raising at the API layer — see
`docs/upload_templates/scalar_results.md` and `docs/upload_templates/master_bulk_upload.md`.

**Known bulk-upload limitation:** the New Experiments upload parses and persists
`id_timepoint_days` for each created row but does not copy a parent's conditions/additives
for `-t<days>` IDs — see `docs/user_guide/REPLICATES.md` for the full limitation.

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
      "temperature_c": 200.0,
      "todays_modification": "Swapped stir shaft; topped up catalyst"
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
- `todays_modification` is the `requested_change` of a reactor modification saved for the current UTC day for this card's `(experiment_id, reactor_label)`; `null` if none was saved today. Populated by one batched query — the endpoint remains a single call.

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
| POST | `/api/bulk-uploads/master-results` | Master Results upload. `file` required — the no-file SharePoint sync mode and the GET/PATCH /master-results/config endpoints were removed (issue #74). Runs calc engine on affected `ScalarResults`. Rows may carry either a full replicate ID (`SERUM_001a`) or a base ID plus an optional `Replicate` column (letter `a`–`z`, or `0`/blank for the group parent). Base + letter is resolved to the sibling experiment before upsert; unresolved or conflicting rows produce per-row errors in `errors`/`feedbacks` without aborting the upload. Replicate siblings are never auto-created by result uploads. |
| POST | `/api/bulk-uploads/scalar-results` | Bulk-create/update `ScalarResults` rows from Excel template. Runs calc engine. Rows may carry either a full replicate ID (`SERUM_001a`) or a base ID plus an optional `Replicate` column (letter `a`–`z`, or `0`/blank for the group parent). Base + letter is resolved to the sibling experiment before upsert; unresolved or conflicting rows produce per-row errors in `errors`/`feedbacks` without aborting the upload. Replicate siblings are never auto-created by result uploads. |
| POST | `/api/bulk-uploads/new-experiments` | Create `Experiment` + `ExperimentalConditions` rows in bulk. |
| POST | `/api/bulk-uploads/icp-oes` | Import raw ICP-OES instrument CSV. |
| POST | `/api/bulk-uploads/xrd-mineralogy` | Unified XRD upload — auto-detects Aeris or ActLabs format. |
| POST | `/api/bulk-uploads/timepoint-modifications` | Bulk-set `brine_modification_description` on result rows. Writes audit log. |
| POST | `/api/bulk-uploads/rock-inventory` | Create/update `SampleInfo` records. Normalises sample IDs to uppercase, no underscores. |
| POST | `/api/bulk-uploads/chemical-inventory` | Create/update `Compound` (reagent) records. |
| POST | `/api/bulk-uploads/elemental-composition` | Import wide-format elemental composition into `ElementalAnalysis`. Query param: `default_unit` (auto-creates unknown analytes). |
| POST | `/api/bulk-uploads/actlabs-rock` | Import ActLabs geochemical analysis reports (Excel or CSV). Heuristic header detection. |
| POST | `/api/bulk-uploads/experiment-status` | Per-row status/date/reactor update. HPHT/Core Flood rows set to ONGOING with a reactor_number auto-complete an older occupant in the same reactor (date-gated); no blanket "complete unlisted HPHT" behavior. |
| POST | `/api/bulk-uploads/pxrf` | Import pXRF readings from instrument export. |
| GET | `/api/bulk-uploads/templates/{upload_type}` | Download Excel template. `upload_type`: `scalar-results`, `new-experiments`, `xrd-mineralogy`, `timepoint-modifications`, `rock-inventory`, `chemical-inventory`, `elemental-composition`, `experiment-status`. Returns 404 for types with no template. |
| GET | `/api/experiments/next-ids` | Returns `{"HPHT": N, "Serum": N, "CF": N}` — next experiment number per type. Used by New Experiments card. |

## Interactive Docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
