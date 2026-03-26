# Milestone 9: Sample Management

**Owner:** frontend-builder (primary), api-developer, db-architect
**Branch:** `feature/m9-sample-management`

**Prerequisite:** M8 (Testing and Docs) must be signed off before this milestone begins.

**Objective:** Migrate and improve the full sample management workflow from the legacy Streamlit
app into the React + FastAPI stack. The legacy app spread sample logic across `new_rock.py`,
`edit_sample.py`, and `view_samples.py` — this milestone consolidates that into a clean API layer
and purpose-built React pages, while filling in gaps the legacy UI left unaddressed (map view,
characterization status automation, photo gallery, pXRF detail, analysis timeline).

---

## Backend Tasks (api-developer + db-architect)

### 9a. API Router — `backend/api/routers/samples.py`

Extend the existing samples router stub (from M3) with full CRUD and relationship endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/samples` | Paginated, filterable list. Filters: `rock_classification`, `country`, `locality`, `characterized`, `has_pxrf`, `has_xrd`, `has_elemental`, free-text `search` on `sample_id` + `description`. |
| GET | `/samples/{sample_id}` | Full detail: core fields + photos + external analyses + elemental results + linked experiments. |
| POST | `/samples` | Create new sample. Validates `sample_id` uniqueness. Sets `characterized=False` on create. |
| PATCH | `/samples/{sample_id}` | Update core fields. Triggers `characterized` auto-evaluation (see 9b). |
| DELETE | `/samples/{sample_id}` | Soft-guarded: returns 409 if linked experiments exist; otherwise deletes with cascade. |
| POST | `/samples/{sample_id}/photos` | Upload one photo (`multipart/form-data`). Saves to `sample_photos/{sample_id}/`. Returns `SamplePhotos` schema. |
| DELETE | `/samples/{sample_id}/photos/{photo_id}` | Deletes DB row and physical file. |
| POST | `/samples/{sample_id}/analyses` | Create an `ExternalAnalysis` record (pXRF, XRD, Magnetic Susceptibility, Elemental). Handles pXRF multi-reading input (comma-separated). Skips duplicates for pXRF. |
| DELETE | `/samples/{sample_id}/analyses/{analysis_id}` | Cascades to `AnalysisFiles`; deletes physical files from storage. |
| GET | `/samples/{sample_id}/analyses` | List all external analyses for a sample, grouped by `analysis_type`. |
| GET | `/samples/geo` | Lightweight endpoint: `sample_id`, `latitude`, `longitude`, `rock_classification`, `characterized` only — for the map view. No pagination; all samples with coordinates. |

All write endpoints log to `ModificationsLog` (table, type, old values, new values) matching the legacy `log_modification` pattern.

File upload endpoints must validate MIME type (photos: `image/jpeg`, `image/png`; analysis reports: `application/pdf`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`). Reject files over 20 MB.

No N+1 queries. The detail endpoint must eager-load `photos`, `external_analyses`, and `elemental_results` in a single joined query. The list endpoint must not load relationships — use a subquery count for `has_pxrf` etc.

### 9b. `characterized` Auto-Evaluation

The legacy app set `characterized=False` on create and left the field as a manual toggle. Replace this with automated logic triggered on every PATCH to a sample and after every analysis create/delete:

```
characterized = True if the sample has at least one of:
  - An ExternalAnalysis of type "XRD" with a linked XRDAnalysis
  - An ExternalAnalysis of type "Elemental" or "Titration" with at least one ElementalAnalysis row
  - An ExternalAnalysis of type "pXRF" linked to a PXRFReading row
```

Implement in `backend/services/samples.py` as `evaluate_characterized(db, sample_id) -> bool`.
Call this function at the end of every sample write endpoint and every analysis create/delete endpoint.
Store the result — do not compute on read.

Manual override must still be possible: if a user explicitly sets `characterized=True` via PATCH
and no analyses exist, honor it and log a `ModificationsLog` entry noting the manual override.

### 9c. Pydantic Schemas — `backend/api/schemas/samples.py`

- `SampleCreate` — all `SampleInfo` fields except `characterized`, `created_at`, `updated_at`. `sample_id` required; all others optional.
- `SampleUpdate` — all fields optional including `characterized` (for manual override).
- `SampleListItem` — flat projection for list view: no nested objects; include `experiment_count` (int), `has_pxrf` (bool), `has_xrd` (bool), `has_elemental` (bool).
- `SampleDetail` — full nested response: photos list, analyses list (grouped), elemental summary, linked experiment IDs.
- `SampleGeoItem` — minimal: `sample_id`, `latitude`, `longitude`, `rock_classification`, `characterized`.
- `SamplePhotoResponse`, `ExternalAnalysisResponse`, `AnalysisFileResponse`.

### 9d. pXRF Reading Linkage

The legacy app used `split_normalized_pxrf_readings` (delimiter-insensitive normalization) when linking pXRF readings to samples. Preserve this normalization logic in `backend/services/samples.py` as `normalize_pxrf_reading_no(raw: str) -> str`. The POST `/samples/{sample_id}/analyses` endpoint must call this before inserting.

Warn (do not error) if a submitted pXRF reading number does not yet exist in `PXRFReading` — the reading may be uploaded later via bulk upload. Return the warning in the response body under `warnings: list[str]`.

---

## Frontend Tasks (frontend-builder)

### 9e. Sample Inventory Page (`/samples`)

Replace the legacy paginated Streamlit table with a full React page.

**Toolbar:**
- Text search (debounced, 300 ms) across `sample_id` and `description`.
- Filter chips: `Rock Classification` (multi-select dropdown populated from distinct DB values), `Country`, `Characterized` (toggle), `Has pXRF`, `Has XRD`, `Has Elemental`.
- View toggle: Table view / Map view (see 9f).
- `+ New Sample` button → opens the create modal.

**Table columns:** Sample ID, Rock Classification, Locality, Country, Characterized badge, pXRF icon, XRD icon, Elemental icon, Experiment Count, Actions (View, Edit, Delete).

- Characterized: use `StatusBadge` with `variant="success"` for true, `variant="neutral"` for false.
- Analysis presence icons: simple dot indicators using status colors — no text labels needed.
- Row click → `/samples/:sample_id`.
- Delete action: show `ConfirmModal` with 409 error handling ("Sample has linked experiments and cannot be deleted").

Server-side pagination with `PageSize` selector (25 / 50 / 100). URL search params persist filter state so the back button returns to the same filtered view.

### 9f. Map View

Toggled from the inventory toolbar. Uses the `/samples/geo` endpoint.

Render an interactive map (use `react-leaflet` with OpenStreetMap tiles — no API key required) showing all samples with coordinates as pin markers. Marker color: red accent for characterized, muted for uncharacterized. Cluster markers at low zoom using `react-leaflet-markercluster`.

Clicking a marker opens a small popup: `sample_id`, `rock_classification`, `country`, link to detail page.

Samples without coordinates appear in a separate list below the map titled "No Coordinates".

> **Package approval required:** `react-leaflet`, `leaflet`, `react-leaflet-markercluster` — propose to user before installing.

### 9g. New Sample Modal

Triggered from `+ New Sample` on the inventory page. Do not navigate to a separate page — use a `Modal` (size `lg`).

**Fields (two-column layout):**
- Left: `sample_id` (required, real-time uniqueness check via debounced GET), `rock_classification`, `locality`, `state`, `country`, `latitude`, `longitude`, `description`.
- Right: `pXRF Reading No` (optional, comma-separated, help text explaining format), `Magnetic Susceptibility` (optional, units hint: 1x10^-3), `Characterized` toggle (defaults to false, disabled if auto-evaluation logic will set it), photo uploader (JPG/PNG, optional + description field).

On submit: POST `/samples`, then (if photo provided) POST `/samples/{id}/photos`, then (if pXRF/mag susc) POST `/samples/{id}/analyses`. All three are sequential — show a single progress state, not three separate spinners.

On success: invalidate `['samples']` query, close modal, show toast, navigate to the new sample detail page.

### 9h. Sample Detail Page (`/samples/:sample_id`)

Tabs:

**Overview tab:**
- Read-only card showing all core fields. `Edit` button opens an inline edit mode (same fields as create, same validation).
- `characterized` shown as a `StatusBadge`; if auto-evaluated, show a sub-label "Auto-detected". If manually set, show "Manual override".
- Linked experiments: compact table (Experiment ID, Type, Status, Start Date) with row links to `/experiments/:id`.

**Photos tab:**
- Photo gallery grid (3 columns). Each photo card shows the image, filename, description, upload date, and a delete button with confirmation.
- Upload zone at the top: `FileUpload` component accepting JPG/PNG. Optional description field. Submits to POST `/samples/{id}/photos`.
- Empty state: illustration + "No photos yet. Upload the first one."

**Analyses tab:**
- Grouped by `analysis_type`: pXRF, XRD, Elemental, Magnetic Susceptibility, Titration.
- Each group is a collapsible section (`<details>` or Tailwind-powered accordion).
- pXRF group: shows reading numbers, links to the full `PXRFReading` data (elemental columns in a compact table), measurement date.
- XRD group: shows mineral phases from `XRDAnalysis.mineral_phases` as a horizontal bar chart (use Recharts). Each phase as a labeled bar with percentage.
- Elemental group: table of analyte / composition / unit rows from `ElementalAnalysis`.
- Magnetic Susceptibility group: description text, date.
- Add analysis form inline at the bottom of each group (or a single `+ Add Analysis` button that opens a type-select modal).

**Activity tab:**
- Filtered view of `ModificationsLog` for this sample (`modified_table IN ('sample_info', 'sample_photos', 'external_analyses')`). Chronological feed, newest first. Shows modification type badge, changed fields summary, timestamp.

### 9i. Sample Selector Component

The New Experiment form (M5) currently uses a free-text field for `sample_id`. Replace it with a searchable `SampleSelector` component:

- Combobox-style input: type to search samples by `sample_id` or `locality`.
- Dropdown shows matching samples with `rock_classification` and `characterized` badge.
- "Create new sample" option at the bottom of the dropdown that opens the New Sample modal (9g) inline.
- On selection: stores `sample_id` string, shows a linked chip with a dismiss button.

Export `SampleSelector` from `src/components/ui/index.ts` so it is available to the experiment forms.

---

## Acceptance Criteria

- All CRUD operations round-trip correctly; `ModificationsLog` entries created for every write.
- `characterized` auto-evaluates correctly after analysis creates and deletes; manual override persists.
- Map view renders all samples with coordinates; clusters at low zoom; popup links work.
- New sample flow (create + photo + pXRF) completes in a single modal with one combined progress state.
- Detail page tabs load independently (each tab is a separate query); switching tabs does not re-fetch other tabs.
- pXRF reading number normalization matches legacy `split_normalized_pxrf_readings` behavior exactly — verified by unit tests against known legacy inputs.
- Delete is blocked with a 409 and user-friendly message when linked experiments exist.
- `SampleSelector` in the experiment form resolves `sample_id` correctly and opens the create modal without losing form state.
- Chrome DevTools loop confirms no console errors; map tiles load; photo uploads preview correctly.
- GET `/samples` with 500 samples and all filters active responds in under 300 ms (verify with `EXPLAIN ANALYZE`).

---

**Test Writer Agent:** pXRF normalization unit tests against legacy inputs, `evaluate_characterized` unit tests (all analysis type combinations), API endpoint tests (list filters, detail eager-loading, 409 on delete, photo upload validation), React component tests for `SampleSelector`, map marker render tests, activity feed filter tests.

**Documentation Agent:** `docs/user_guide/SAMPLES.md` (researcher-facing guide: creating, editing, uploading analyses, reading the map view), `docs/developer/SAMPLE_CHARACTERIZED_LOGIC.md` (explains auto-evaluation rules and manual override), update `docs/api/API_REFERENCE.md` with all new sample endpoints.
