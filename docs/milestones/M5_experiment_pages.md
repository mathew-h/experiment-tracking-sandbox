# Milestone 5: Experiment Management Pages

**Owner:** frontend-builder (primary), api-developer
**Branch:** `feature/m5-experiment-pages`

---

## Pages to Build

### 1. Experiment List (`/experiments`)

**Table columns (in order):**
- Experiment ID (clickable → detail)
- Experiment Description
- Sample ID
- Reactor #
- Status (inline dropdown — clickable and changeable in-place without navigating away)
- Date
- Additives (summary string, e.g. "5 g Mg(OH)₂, 1 g Magnetite")

**Filtering (sidebar or filter bar above table):**
- Status (multi-select chip: ONGOING / COMPLETED / CANCELLED)
- Experiment type (Serum / HPHT / Autoclave / Core Flood)
- Sample ID (text search)
- Date range (date picker)
- Reactor number (text/select)

**Behaviour:**
- Server-side pagination with smart page-size selector (25 / 50 / 100 rows)
- Row click → Experiment Detail
- Status change in-place calls `PATCH /experiments/{id}` and invalidates the row cache — no full page reload
- Additive summary is derived from `ChemicalAdditive` records and formatted as a compact string

---

### 2. New Experiment (`/experiments/new`)

**Design principle:** Minimize visible fields. Show only what is relevant to the selected experiment type. Hide fields that do not apply. The goal is a clean, low-friction entry form for lab users.

#### Service Layer Feature: Auto-Increment Experiment ID

The system must derive the next experiment ID automatically so the user does not need to type it.

**Backend endpoint required:** `GET /experiments/next-id?type={experiment_type}`

Logic:
- Query all existing `experiment_id` values that match the prefix for the selected type (e.g. `HPHT_` for HPHT).
- Extract the numeric suffix from each, find the maximum, and return `{PREFIX}_{max + 1}`.
- Prefix mapping: `HPHT` → `HPHT`, `Serum` → `SERUM`, `Autoclave` → `AUTOCLAVE`, `Core Flood` → `CF`.
- If no experiments exist yet for that type, start at 001 (zero-padded to 3 digits minimum).
- The returned ID is shown to the user as a read-only preview. It is confirmed and written on final submit, not reserved on preview.
- Edge case: if the user submits and the ID was taken by a concurrent insert, the backend returns 409 and the frontend increments and retries once before surfacing an error.

#### Service Layer Feature: Copy from Existing Experiment

A "Copy from existing" toggle or button at the top of the form. When activated:
- A searchable dropdown or text input appears for the user to select or type an existing experiment ID.
- On selection, the API fetches that experiment's conditions and chemical additives and pre-populates all applicable form fields.
- The user can then modify any pre-filled value before submitting.
- The copied experiment ID and the new experiment ID are linked via `parent_experiment_fk` on the new record.
- Endpoint required: `GET /experiments/{id}/copy-template` — returns conditions and additives in the same shape as the creation payload.

#### Multi-Step Form Structure

**Step 1 — Basic Info**

Fields always shown:
- Experiment type (dropdown: Serum / HPHT / Autoclave / Core Flood) — selecting this triggers auto-ID fetch and controls which fields appear in Step 2
- Experiment ID (read-only, auto-populated from the next-ID endpoint after type is selected; displayed so the user can see what will be assigned)
- Sample ID (text input with typeahead against existing `SampleInfo` records)
- Date (date picker, defaults to today)
- Status (dropdown: ONGOING / COMPLETED / CANCELLED, default ONGOING)
- Experiment description / condition note (textarea — saved as the first `ExperimentNotes` entry on create, with `note_type = "condition"` or equivalent per model; check `ExperimentNotes` fields before implementing)

**Step 2 — Conditions**

Show only fields relevant to the selected experiment type. Use a field visibility matrix:

| Field | Serum | HPHT | Autoclave | Core Flood |
|---|---|---|---|---|
| Particle size | Yes | Yes | Yes | Yes |
| Initial pH | Yes | Yes | Yes | Yes |
| Rock mass (g) | Yes | Yes | Yes | Yes |
| Water volume (mL) | Yes | Yes | Yes | Yes |
| Temperature (°C) | Yes | Yes | Yes | Yes |
| Experiment type | Auto-derived from Step 1 — read-only, not re-entered | | | |
| Reactor number | No | Yes | No | Yes |
| Feedstock / nitrogen source | Yes (dropdown: Nitrogen / Nitrate / None, default None) | Yes | Yes | Yes |
| Stir speed (RPM) | Yes | Yes | No | No |
| Initial conductivity | Yes | Yes | Yes | Yes |
| Room temp pressure (psi) | No | Yes | No | Yes |
| Rxn temp pressure (psi) | No | Yes | No | Yes |
| CO₂ partial pressure | No | Yes | No | No |
| Core height | No | No | No | Yes |
| Core width | No | No | No | Yes |
| Confining pressure | No | No | No | Yes |
| Pore pressure | No | No | No | Yes |

Live derived field preview: after `rock_mass_g` and `water_volume_mL` are entered, display `water_to_rock_ratio` inline as a read-only calculated preview (call `GET /experiments/next-id` does not apply here — compute client-side as `water_volume_mL / rock_mass_g` for display only; the stored value is written by the calculation engine on submit).

**Step 3 — Chemical Additives**

Repeatable additive rows. Each row contains:
- Chemical name (searchable dropdown against `Compound` records; typing filters by name)
- Amount (numeric input)
- Unit (dropdown from `AmountUnit` enum: g / mg / mL / mM / ppm / % of Rock / wt% / etc.)
- Remove row button

"Add another additive" button appends a new blank row. Rows can be reordered or removed. At least zero additives is valid — the section is optional.

Calculated fields (`mass_in_grams`, `moles_added`, `catalyst_ppm`, etc.) are not entered by the user and are not shown in this form — they are computed by the calculation engine after submit.

**Step 4 — Review + Submit**

Read-only summary of all entered values grouped by section (Basic Info, Conditions, Additives). A "Back" button returns to any step. "Submit" creates the experiment.

On success: navigate to the new Experiment Detail page. Toast: "Experiment {ID} created."
On 409 conflict: retry with next incremented ID automatically, then show result.

---

### 3. Experiment Detail (`/experiments/:id`)

**Header section:**
- Experiment ID, status badge (StatusBadge component), experiment type, date, sample ID, reactor number (if applicable)
- Quick-action buttons: Edit Status, Add Note, Copy Experiment (links to `/experiments/new` with copy-from pre-filled)

**Tab layout:**

#### Tab: Conditions
- Read-only display of all conditions fields grouped logically (basic parameters, pressure values, core flood dimensions if applicable)
- Derived field `water_to_rock_ratio` shown prominently
- Chemical additives listed with their calculated fields (mass_in_grams, moles_added, catalyst_ppm where available)
- "Edit" button opens a modal to update any conditions field; on save, calculation engine re-runs for affected derived fields

#### Tab: Results
- Top-level table of timepoints. Columns: Time (days), NH₄ Yield (g/t), H₂ Yield (g/t), H₂ (µmol), Final pH, ICP (tick icon if `ICPResults` record exists for this timepoint)
- Each timepoint row is expandable (click the row or a chevron). Expanded view shows:
  - Full scalar results: final pH, conductivity, dissolved oxygen, gross/background/net ammonium concentration, H₂ concentration (ppm), gas sampling pressure
  - ICP panel (only if ICP data exists): elemental table showing fixed columns (Fe, Si, Mg, Ca, Ni, Cu, etc.) plus any additional elements from `all_elements` JSONB; dilution factor and instrument noted
- Primary timepoint result flagged with a subtle indicator

#### Tab: Notes
- Chronological feed of all `ExperimentNotes` entries, newest first
- The first note (experiment condition note from creation) is visually distinguished (e.g. pinned or labelled "Condition Note")
- "Add Note" inline text area + submit button at the top
- Each note shows `created_at` timestamp

#### Tab: Modifications
- Table of `ModificationsLog` entries for this experiment
- Columns: Timestamp, Table Modified, Change Type (create / update / delete), Modified By, Summary of changes (old vs new values for key fields)
- Read-only audit trail

#### Tab: Analysis
- Linked XRD analyses (list with date, laboratory, mineral phases summary)
- Linked pXRF readings (table of elemental values)
- Linked elemental analyses
- Each row links to a detail view or modal

#### Tab: Files
- List of `ResultFiles` associated with results on this experiment
- File name, associated timepoint, download link

---

## Backend Endpoints Required (api-developer)

The following endpoints are new or modified relative to the M3 router spec and must be implemented before the frontend tasks begin:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/experiments/next-id?type={type}` | Returns the next auto-incremented experiment ID for the given type |
| `GET` | `/experiments/{id}/copy-template` | Returns conditions + additives payload shaped for the creation form |
| `PATCH` | `/experiments/{id}/status` | Inline status update from the list view |
| `GET` | `/experiments/{id}/results` | Timepoint list with scalar and ICP existence flag per row |

The `next-id` endpoint must be idempotent (read-only, no reservation). Concurrency is handled at write time with a 409 response.

---

## Field Visibility Rules — Implementation Notes

Field visibility in Step 2 is driven by the `experiment_type` value selected in Step 1. Implement as a config object in the frontend (not hardcoded per field). Example shape:

```typescript
const FIELD_VISIBILITY: Record<ExperimentType, Set<ConditionField>> = {
  Serum:      new Set(['particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL', 'temperature_c', 'feedstock', 'stir_speed_rpm', 'initial_conductivity']),
  HPHT:       new Set(['particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL', 'temperature_c', 'reactor_number', 'feedstock', 'stir_speed_rpm', 'initial_conductivity', 'pressure_room_temp_psi', 'pressure_rxn_temp_psi', 'co2_partial_pressure']),
  Autoclave:  new Set(['particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL', 'temperature_c', 'feedstock', 'initial_conductivity']),
  CoreFlood:  new Set(['particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL', 'temperature_c', 'reactor_number', 'feedstock', 'initial_conductivity', 'pressure_room_temp_psi', 'pressure_rxn_temp_psi', 'core_height', 'core_width', 'confining_pressure', 'pore_pressure']),
}
```

This object is the single source of truth for what renders in the form. Adding a new field to the form means adding it to this config, not hunting through JSX.

---

## Acceptance Criteria

- Auto-ID endpoint returns correct next number for each experiment type, including first-ever experiment of a type
- Copy-from-existing pre-fills all conditions and additives fields correctly
- New experiment creation round-trips: experiment written to DB, conditions written, additives written, calculation engine runs, derived fields populated, first note saved
- Step 2 shows only the fields defined in the visibility matrix for the selected type
- Experiment list table filters all work server-side; status updates in-place without page reload
- Experiment detail timepoint table correctly shows NH₄ and H₂ yield values from stored derived fields; ICP tick renders only when ICP data exists; expanding a row reveals full scalar and ICP data
- Notes tab shows the condition note from creation at the top of the feed
- All filters work; derived fields display from stored DB values; lineage visible; Chrome DevTools loop confirms no console errors and no N+1 queries

---

## Implementation Progress

| Chunk | Description | Status |
|-------|-------------|--------|
| A | Commit run-date migration | ✅ Complete (2026-03-19) |
| B | Backend schema + endpoint extensions | ✅ Complete (2026-03-19) |
| C | ExperimentList page rewrite | ✅ Complete (2026-03-19) |
| D | New Experiment 4-step form | ✅ Complete (2026-03-19) |
| E | Experiment Detail tabs | ✅ Complete (2026-03-19) |
| F | Documentation update | ✅ Complete (2026-03-19) |

---

## Agent Responsibilities

**api-developer:** Implement the four new/modified endpoints listed above before frontend work begins on Steps 1-2. Verify `next-id` logic handles zero-padded IDs and concurrent inserts. Ensure `copy-template` endpoint returns a payload the creation form can consume directly.

**frontend-builder:** Implement field visibility config object before building Step 2. Apply `frontend-design` skill before committing to form layout. Use `useQuery` for auto-ID fetch and `useMutation` for submit. Chrome DevTools loop required on form steps and detail tabs.

**Test Writer Agent:** Form validation tests (required fields, type-conditional fields), auto-ID increment tests (including first-ever and concurrent), copy-from-existing pre-fill tests, API integration tests for all four new endpoints, filter logic tests, ICP tick/expand render tests, lineage display tests.

**Documentation Agent:** User-facing guide for creating and managing experiments, including field-by-field explanation of the conditions form organized by experiment type.
