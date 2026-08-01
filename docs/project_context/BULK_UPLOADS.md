# Bulk Uploads User Guide

The Bulk Uploads page lets you ingest large datasets into the experiment tracking system
without entering rows one at a time. Each upload type is an accordion row — click a row
header to expand it, drop a file, and submit. Only one row can be open at a time.

The six most-used upload types appear at the top of the page at full size; the
remaining low-use types are collapsed under a **Less-used uploads** section at
the bottom — click it to expand them.

---

## Common behaviour for all upload types

| Behaviour | Details |
|-----------|---------|
| **Auth required** | You must be logged in. Uploads fail silently if your session has expired — refresh the page and re-login. |
| **Result summary** | After processing you see Created / Updated / Skipped counts and an expandable error list. Delete Experiments relabels these to Deleted / Not found. |
| **Atomic transactions** | If the file fails validation mid-way, **zero rows are written**. Fix the file and resubmit. **Exception: Delete Experiments** commits each row on its own, so a partly-failed batch stays partly deleted. |
| **Template download** | Rows that have a template show a download button. Use the template to avoid column name errors. |
| **Calc engine** | Where relevant (scalar results), derived fields (H₂ yield, g/t yield, etc.) are recalculated automatically. |

---

## 1 — Master Results Sync

**Endpoint:** `POST /api/bulk-uploads/master-results`

Drag and drop the team's master tracker spreadsheet to push updates:

`01_R&D\02_Results\Master_Reactor_Sampling_Tracker_v2.xlsx`

Download the file from SharePoint (or use a synced local copy) and drop it into
the upload zone. The former "Sync from SharePoint" button was removed (issue #74)
— the file is now always uploaded manually, and the `file` field is required on
the endpoint.

**One row per vial.** Each unique experiment ID gets its own row. Replicates are
separate vials, so `SERUM_001` with replicates a, b, c sampled at days 1 and 3
is six rows — `SERUM_001a-t1`, `SERUM_001b-t1`, `SERUM_001c-t1`, `SERUM_001a-t3`,
`SERUM_001b-t3`, `SERUM_001c-t3` — not two rows with an a/b/c column each. If two
rows share an experiment ID and Duration, **both are rejected** and listed under
Errors, because there is no safe way to tell which reading you meant to keep.

You no longer put averages or standard deviations on the sheet. Enter each
vial's own reading; the app computes the replicate mean and SD and shows them on
the experiment group page.

**The `-t<days>` token in the ID sets the timepoint.** It is the vial's elapsed
days of record. If the `Duration (Days)` column disagrees with it, the ID wins
and the reading is still uploaded — the disagreement appears under **Warnings**
so you can reconcile the sheet at your leisure. This means you can keep real
sampling dates in the Sampling sheet without a derived duration blocking the
upload. (Hand-entered results via the Add Results modal are stricter: there a
conflicting time is rejected outright, because a single entry has one author who
can correct it.)

**Hydrogen columns.** `FL H2 (ppm)` (Full Loop) is used whenever it has a value;
`DI H2 (ppm)` is used only when the Full Loop cell is blank. Gas volume and
pressure are taken from whichever block supplied the concentration, so do not
mix them by hand. A `0` is treated as a real reading of zero — leave the cell
**empty** if there was no measurement.

If a row has a reading in **both** blocks, Full Loop wins and the
direct-injection value is not stored anywhere. The upload names those rows under
**Warnings** so you can see it happened — the discarded reading cannot be
recovered from the database afterwards.

**Gas volume and pressure need a reading to go with them.** A row with no
`H2 (ppm)` in either block imports no gas volume or pressure either, even when
those cells are filled in. The GC sheets carry values forward from previous runs,
so geometry with no concentration beside it is stale rather than measured, and
nothing is computed from it in any case.

If you rename a Dashboard column, the upload now tells you: any unmatched column
whose name mentions H2 appears under **Warnings** in the result panel rather
than being ignored.

**Errors are listed in sheet order.** Row errors appear in the same order as the
rows in the spreadsheet, so you can work down the list against the file. A
problem with the file as a whole — a missing required column — comes first,
since it has no row number. (The deprecated wide `DI a/b/c H2 (ppm)` columns
are reported under **Warnings**, not Errors — the rest of the file still
uploads.)

### Expected sheet: `Dashboard`

| Column | Required | Notes |
|--------|----------|-------|
| Experiment ID | ✓ | Must match an existing experiment |
| Duration (Days) | ✓ (column) | The **column** must exist; the **value** may be blank. Blank defers to the day in the ID's `-t<days>` token. A cell holding only spaces counts as blank — that is what the Sampling sheet's `=IF(ISBLANK([Date Started]), " ", …)` formula produces for an undated row. Blank *and* no `-t` token → the row is skipped |
| Description | | Free text |
| Sample Date | | Date |
| NMR Run Date | | Date |
| ICP Run Date | | Date |
| GC Run Date | | Date |
| NH4 (mM) | | Ammonium concentration |
| FL H2 (ppm) | | Full Loop H₂ in ppm vol/vol. Takes precedence over `DI H2 (ppm)`. Also accepted: `H2 (ppm)` |
| FL Gas Volume (mL) | | Also accepted: `Gas Volume (mL)` |
| FL Gas Pressure (psi) | | Converted to MPa automatically. Also accepted: `Gas Pressure (psi)` |
| DI H2 (ppm) | | Direct-injection H₂, used only when `FL H2 (ppm)` is blank. Also accepted: `DI avg H2 (ppm)` |
| DI gas volume (mL) | | Used only when the DI reading wins |
| DI gas pressure (psi) | | Used only when the DI reading wins |
| Sample pH | | |
| Sample Conductivity (mS/cm) | | |
| Sampled Solution Volume (mL) | | Volume of production fluid collected at this timepoint (mL) |
| Modification | | Brine modification note |
| OVERWRITE | | `TRUE` / `FALSE` — overwrite existing result row at same timepoint. Also accepted: `Overwrite` |

Rows where both Experiment ID and Duration (Days) are present create or update a
`ScalarResults` record. The calc engine re-runs for every affected row.

**What `OVERWRITE = TRUE` does and does not touch.** It rewrites the columns in
the table above, including clearing one you leave blank — that is how a stale gas
volume is removed when a row's H₂ reading goes away. It does **not** touch fields
this sheet has no column for. Background ammonium, ammonium quant method, final
nitrate, final alkalinity, CO₂ partial pressure, dissolved oxygen, background
experiment ID and ferrous iron yield are entered on the experiment's Results tab,
and an overwrite upload leaves them exactly as they were.

> Before 2026-08-01 an overwrite row nulled all eight (issue #116). Background
> ammonium falls back to 0.2 mM when empty and net ammonium is
> `gross − background`, so a cleared value shifted the reported yield with no
> error shown. If you ran an `OVERWRITE = TRUE` Master Results upload before that
> date, check those fields on the affected timepoints.

**Replicates:** rows may carry either a full lettered ID (`SERUM_001a`) in Experiment ID, or the bare base ID plus the optional `Replicate` column (`a`–`z`; `0` or blank = the group parent). Base + letter is resolved to the sibling experiment before upsert. Unresolved or conflicting rows are skipped with a per-row error — the rest of the file still uploads. See the [Replicates guide](REPLICATES.md#uploading-replicate-results).

---

## 2 — ICP-OES Data

**Endpoint:** `POST /api/bulk-uploads/icp-oes`

Imports raw ICP-OES output CSV files directly from the instrument export.

The parser expects the standard instrument CSV format:
- Column 1: `Sample_ID` matching an existing `ExperimentalResults` row
- Remaining columns: one per element (e.g. `Fe_ppm`, `Si_ppm`, `Mg_ppm`, …)
- Blank rows and rows with `QC` / `BLANK` sample IDs are skipped
- When multiple spectral lines exist for the same element the best intensity is used

No template available — use the raw instrument export.

---

## 3 — XRD Mineralogy

**Endpoint:** `POST /api/bulk-uploads/xrd-mineralogy`
**Template:** available in the download button (ActLabs wide-format)

The XRD upload auto-detects which format your file uses:

| Detected format | How detected | What it does |
|-----------------|-------------|--------------|
| **Aeris** | Sample ID column matches `^\d{8}_.+?-d\d+_\d+$` | Routes to Aeris time-series XRD parser |
| **ActLabs** | First column is `sample_id` with plain sample IDs | Routes to ActLabs XRD report parser |
| **Unknown** | Neither pattern found | Returns an error — no rows written |

**ActLabs wide-format template columns:**

| Column | Notes |
|--------|-------|
| sample_id | Existing sample ID |
| Quartz / Calcite / … | One column per mineral; values are percentages |

Mineral column headers may include a `%` suffix — it is stripped automatically.

**Aeris format:** comes directly from the Aeris diffractometer export. No template
needed; upload the raw `.xlsx` file from the instrument.

---

## 4 — Solution Chemistry

**Endpoint:** `POST /api/bulk-uploads/scalar-results`
**Template:** available

Bulk-creates or updates `ScalarResults` rows (solution chemistry measurements).

| Column | Required | Notes |
|--------|----------|-------|
| experiment_id | ✓ | Must match an existing experiment |
| time_post_reaction_days | ✓ | Float |
| description | ✓ | Short label for the timepoint |
| final_ph | | |
| final_conductivity_mS_cm | | |
| gross_ammonium_concentration_mM | | |
| h2_concentration | | ppm vol/vol |
| gas_sampling_volume_ml | | |
| gas_sampling_pressure_MPa | | MPa |
| overwrite | | `TRUE` overwrites an existing row at the same timepoint |

The calc engine recalculates H₂ yield, g/t yield, and ammonium yield after each write.

**Replicates:** rows may carry either a full lettered ID (`SERUM_001a`) in Experiment ID, or the bare base ID plus the optional `Replicate` column (`a`–`z`; `0` or blank = the group parent). Base + letter is resolved to the sibling experiment before upsert. Unresolved or conflicting rows are skipped with a per-row error — the rest of the file still uploads. See the [Replicates guide](REPLICATES.md#uploading-replicate-results).

---

## 5 — New Experiments

**Endpoint:** `POST /api/bulk-uploads/new-experiments`
**Template:** available — includes next-ID hints before download

Creates `Experiment` records and optional `ExperimentalConditions` rows in bulk.

### Preview before it writes

Dropping a file here does not change anything. It runs the upload against the database
and then rolls it back, so what you get is a **plan**: every experiment that would be
created, every rename, every field that would be overwritten (with its current value
next to the new one), and every row that would be skipped. Nothing is written until you
press **Commit**.

If the plan contains a conflict — most commonly an `old_experiment_id` filled in without
`overwrite=TRUE`, which would silently create a duplicate instead of renaming — Commit is
disabled and the whole file is refused. Fix the workbook and drop it again.

Between previewing and committing, the plan is pinned by a fingerprint. If the workbook
changes on disk, or another researcher edits one of the experiments the plan would
overwrite, the commit is refused and you are shown the new plan to review before you can
proceed.

The expanded card shows **Next ID chips** (e.g. "Next HPHT: 072 · Next Serum: 043 · Next CF: 008")
so you can fill the template with the correct experiment IDs before uploading.

| Column | Required | Notes |
|--------|----------|-------|
| experiment_id | ✓ | e.g. `HPHT_072` |
| experiment_type | ✓ | HPHT / Serum / Autoclave / Core Flood / Other |
| status | | Default ONGOING |
| researcher | | |
| date | | YYYY-MM-DD |
| sample_id | | Must exist in SampleInfo |
| temperature_c | | |
| initial_ph | | |
| rock_mass_g | | |
| water_volume_mL | | |
| reactor_number | | |

---

## 6 — Timepoint Modifications

**Endpoint:** `POST /api/bulk-uploads/timepoint-modifications`
**Template:** available

Bulk-sets the brine modification description on existing result rows.
Use this when you added or replaced chemicals mid-experiment at a specific sampling point.

| Column | Required | Notes |
|--------|----------|-------|
| experiment_id | ✓ | Must match an existing experiment |
| time_point | ✓ | Days (float); must match an existing result row within ±0.0001 day |
| modification_description | ✓ | Text to set as `brine_modification_description` |

Validation rules:
- Duplicate `(experiment_id, time_point)` pairs in one file are rejected — the whole file
  is returned with an error and nothing is written
- If a row already has a modification, it is skipped unless `overwrite_existing=TRUE`

An audit log entry (`ModificationsLog`) is written for every changed row.

---

## 7 — Rock Inventory

**Endpoint:** `POST /api/bulk-uploads/rock-inventory`
**Template:** available

Creates or updates `SampleInfo` records (geological sample metadata).

Sample IDs are normalised to uppercase with spaces and underscores removed
(`S_ROCK_002` → `SROCK002`). The normalised form is stored. Existing records are
found by normalised matching, so format inconsistencies are handled gracefully.

| Column | Required | Notes |
|--------|----------|-------|
| sample_id | ✓ | |
| rock_classification | | e.g. "Dunite", "Basalt" |
| state | | Province/state |
| country | | |
| locality | | Specific collection site |
| latitude / longitude | | Decimal degrees |
| description | | Free text |
| characterized | | `TRUE` / `FALSE` |
| pxrf_reading_no | | Links existing pXRF readings to the sample |
| overwrite | | `TRUE` clears and rewrites all optional fields from this row |

Image files can be attached during upload — file names (without extension) must
match a sample ID to be linked automatically.

---

## 8 — Chemical Inventory

**Endpoint:** `POST /api/bulk-uploads/chemical-inventory`
**Template:** available

Creates or updates `Compound` records in the reagent inventory.
Lookup is by name (case-insensitive) or CAS number.

| Column | Required | Notes |
|--------|----------|-------|
| name | ✓ | Case-insensitive unique identifier |
| formula | | e.g. `Mg(OH)₂` |
| cas_number | | e.g. `1309-42-8` |
| density | | g/cm³ |
| melting_point | | °C |
| boiling_point | | °C |
| solubility | | Free text |
| hazard_class | | |
| supplier | | |
| catalog_number | | |
| notes | | |

> **Known issue:** The service currently ignores the `molecular_weight` column due to a
> column naming mismatch (`molecular_weight` vs `molecular_weight_g_mol`). All other
> fields are processed correctly.

---

## 9 — Sample Chemical Composition

**Endpoint:** `POST /api/bulk-uploads/elemental-composition`
**Template:** available

Imports wide-format elemental composition data into `ElementalAnalysis` rows.

File format: first column `sample_id`; remaining columns are analyte symbols
(e.g. `SiO2`, `Fe2O3`, `MgO`). Values are numeric percentages or concentrations.

- Analyte symbols must match existing `Analyte` records, **or** provide a `default_unit`
  query parameter (`?default_unit=wt%`) to auto-create unknown analytes.
- Rows with unknown `sample_id` are recorded as errors.
- Blank cells for a given analyte are silently skipped.

---

## 10 — ActLabs Rock Analysis

**Endpoint:** `POST /api/bulk-uploads/actlabs-rock`

Imports ActLabs geochemical analysis reports (Excel or CSV).
Use the raw file from the ActLabs client portal — no reformatting needed.

The parser uses heuristic header detection:
- Row 2 (0-indexed row 2): analyte symbols
- Row 3 (0-indexed row 3): unit symbols
- Data starts after the "Analysis Method" row

Values prefixed with `<` or `>` (e.g. `<0.01`) are stored as numeric only.
`nd`, `na`, `n/a` values are treated as blank and skipped.

No template available — upload the ActLabs-exported file directly.

---

## 11 — Experiment Status Update

**Endpoint:** `POST /api/bulk-uploads/experiment-status`
**Template:** available

Set each experiment's status explicitly, per row. Applies to experiments of any
type — Serum, Autoclave, HPHT, Core Flood.

Logic:
- Each row sets its own `status` (`ONGOING`, `COMPLETED`, `CANCELLED`, or `QUEUED`; case-insensitive).
- If `date` is provided, it updates the experiment's start date (`Experiment.date`).
- If `reactor_number` is provided, it updates `ExperimentalConditions.reactor_number`.
- Setting an **HPHT or Core Flood** row to `ONGOING` with a `reactor_number` completes
  an experiment already `ONGOING` in that same reactor, **only if** the occupant's
  start date is older than the incoming row's start date.
- If the reactor is held by a newer-or-equal-dated experiment (or either date is
  missing), nothing is demoted and a warning names both experiments and the reactor.
- Experiment IDs not found in the database are reported as `missing_ids`.
- There is no blanket "complete every unlisted ongoing HPHT" behavior — an
  experiment not referenced in the file is never touched.
- Invalid `status`/`reactor_number`/`date` values, or two rows targeting the same
  `reactor_number`, hard-fail the whole upload with no changes applied. A missing
  `experiment_id` or `status` column does the same.

The endpoint runs preview validation and apply in one request (no separate
confirm step): upload the file and the response reports what was applied.

| Column | Required | Notes |
|--------|----------|-------|
| experiment_id | ✓ | |
| status | ✓ | ONGOING, COMPLETED, CANCELLED, or QUEUED (case-insensitive) |
| reactor_number | | Optional; only meaningful for HPHT / Core Flood experiments |
| date | | Optional; experiment start date (YYYY-MM-DD or Excel date) |

---

## 12 — pXRF Readings

**Endpoint:** `POST /api/bulk-uploads/pxrf`

Imports raw pXRF scan data into `PXRFReading` records.

Use the raw Excel export from the Olympus Vanta or equivalent portable XRF device.
No template available — upload the raw instrument file directly.

---

## 13 — Delete Experiments

**Endpoint:** `POST /api/bulk-uploads/experiment-deletion`

**Restricted to the data owner (`mhearl@addisenergy.com`).** The row is visible to
everyone, but the server refuses the upload with a 403 for any other account. There is
no need to ask for access — this exists to clean up batches of bad entries.

**This is a permanent, irreversible deletion, not an update.** Each listed experiment
and everything it owns is destroyed: conditions, all results (scalar, ICP, H₂), result
files, notes, additives, external analyses, XRD phases and reactor change requests. Two
things belonging to *other* experiments are only unlinked, never deleted: a scalar result
that used a deleted experiment as its ammonium background keeps its background value and
loses only the provenance pointer, and replicate siblings keep their group membership and
lose only the parent pointer. Deleted experiments cannot be restored from the audit log —
it records what was destroyed, not enough to rebuild it.

### Sheet format

| Column | Required | Notes |
|--------|----------|-------|
| experiment_id | ✅ | One experiment ID per row. Nothing else is read. |

Blank rows and repeated IDs are ignored. Download the template for a ready-made sheet.

### What happens on submit

1. Your browser asks you to confirm. For a `.csv` the prompt states how many rows it
   found; for Excel it names the file instead (the count can only be read from a CSV in
   the browser). **Read the prompt — this is the last chance to stop.**
2. Every listed experiment is deleted one at a time, each committed on its own.
3. The result panel reports three lists:
   - **Deleted** — gone.
   - **Not found** — no experiment with that ID; nothing happened. Usually a typo or an
     ID that was already deleted.
   - **Errors** — the row could not be deleted, with the reason. The rest of the batch
     still went through; a single bad row never blocks the others.

Because each row commits separately, a partly-successful batch **stays** partly
successful — re-uploading the same file is safe (already-deleted IDs simply come back
under "Not found").

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "Missing required column" error | Column header typo or wrong template | Download the current template and re-map your columns |
| All rows skipped | `sample_id` or `experiment_id` column values don't match DB | Check for extra spaces, underscores, or capitalisation differences |
| Counts look wrong but no errors | Rows already existed and `overwrite` was not `TRUE` | Set `overwrite = TRUE` in the relevant rows |
| Master Results sync returns "not found" | SharePoint path not accessible from the server | Upload the file manually instead |
| Zero rows written despite valid file | Mid-file validation failure or DB constraint violation — see the errors list | Fix the flagged rows and resubmit |
