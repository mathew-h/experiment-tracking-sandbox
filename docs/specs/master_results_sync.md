# Spec: Master Results Sync

**Upload card title:** Master Results Sync
**Backend parser:** `backend/services/bulk_uploads/master_bulk_upload.py`
**Template:** None — this is a fixed living file maintained by the lab team

---

## Overview

The Master Results file is a shared Excel workbook that the lab team updates daily.
It is not a one-off import — it is a persistent file on the lab PC that accumulates
rows over time. The upload mechanism is a **sync operation**: the app reads the
current state of the file and upserts any new or changed rows.

Because the file lives on the same LAN machine as the server, it can be read
directly from the filesystem. The user configures the file path once; thereafter
they press "Sync Now" and the backend reads the file from that path.

---

## File Format

- **Format:** Excel (`.xlsx`)
- **Target sheet:** `Dashboard`
- **Row structure:** One row per experiment + timepoint combination

### Column Definitions

| Column Header | Required | Maps To | Notes |
|---|---|---|---|
| `Experiment ID` | Yes | `Experiment.experiment_id` | Must exist in DB |
| `Duration (Days)` | Yes | `ExperimentalResults.time_post_reaction_days` | Numeric; `0` = pre-reaction baseline |
| `Description` | No | `ExperimentalResults` description field | Free text |
| `Sample Date` | No | `ScalarResults.measurement_date` | Date; see parsing rules |
| `NH4 (mM)` | No | `ScalarResults.gross_ammonium_concentration_mM` | Float |
| `H2 (ppm)` | No | `ScalarResults.h2_concentration` | Float |
| `Gas Volume (mL)` | No | `ScalarResults.gas_sampling_volume_ml` | Float |
| `Gas Pressure (psi)` | No | `ScalarResults.gas_sampling_pressure_MPa` | Converted: × 0.00689476 |
| `Sample pH` | No | `ScalarResults.final_ph` | Float |
| `Sample Conductivity (mS/cm)` | No | `ScalarResults.final_conductivity_mS_cm` | Float |
| `Modification` | No | `ExperimentalResults.brine_modification_description` | Free text |
| `NMR Run Date` | No | Stored as metadata on result | Date |
| `ICP Run Date` | No | Stored as metadata on result | Date |
| `GC Run Date` | No | Stored as metadata on result | Date |
| `OVERWRITE` | No | Per-row overwrite flag | `TRUE`/`FALSE`; default `FALSE` |
| `Standard` | No | Ignored by parser | Informational column for lab use only |

**Note on `Standard`:** This column is present in the file for lab team reference
(e.g. flagging whether a row is a calibration standard). The parser must silently
ignore it. It must not be treated as an error if present.

---

## Parsing Rules

### Date parsing (`_parse_date`)
- Accepts Python `datetime`, `date`, Pandas `Timestamp`, ISO strings, and Excel serial dates
- Rejects dates with year ≤ 1900
- Rejects spreadsheet error values (`#DIV/0!`, `#VALUE!`, etc.)
- Returns `None` for blank cells without raising

### Numeric parsing (`_parse_numeric`)
- Accepts floats, integers, and numeric strings (including those with commas)
- Rejects spreadsheet error values
- Returns `None` for blank cells without raising

### Gas pressure conversion
`gas_sampling_pressure_MPa = Gas Pressure (psi) × 0.00689476`

### Overwrite behavior
- Per-row `OVERWRITE` column takes precedence over any global setting
- Truthy values: `TRUE`, `true`, `1`, `yes`, `y`
- If `OVERWRITE = FALSE` and a result already exists for the
  `(experiment_id, time_post_reaction_days)` pair, the row is **skipped** (not an error)
- If `OVERWRITE = TRUE`, the existing scalar result fields are updated

### Row skipping (not errors)
The following rows are silently skipped without counting as errors:
- Blank rows (no `Experiment ID`)
- Rows where `Experiment ID` does not exist in the database (logged as a warning)
- Rows where `Duration (Days)` is not numeric

### Calculation engine
After each successful upsert, call `registry.recalculate(scalar_result, session)`
to recompute yield fields and net ammonium concentration.

---

## UI Behaviour (Master Results card is different from other cards)

The Master Results card does **not** use a drag-and-drop file picker.
It uses a **server-side sync** model:

### First-time setup
A settings panel (accessible via a gear icon on the card) allows the user to
configure the file path on the server:

```
File path: [____________________________________] [Browse]
```

The path is stored in the app's settings table or `.env`-adjacent config.
A "Test connection" button verifies the path resolves to a readable `.xlsx` file.

### Normal operation
Once configured, the card shows:

```
Master Results Sync
Last synced: 2 hours ago (47 rows processed)

[Sync Now]   [View last sync log]
```

Pressing **Sync Now** calls `POST /api/bulk-uploads/master-results` with no file body.
The backend reads the file from the configured path and processes it.

### Response display
After sync:
- Created: N rows
- Updated: N rows
- Skipped: N rows
- Warnings: collapsible list of experiment IDs not found in DB

Errors (unexpected exceptions) are shown prominently in red with the option to
view full server logs.

---

## API Endpoint

```
POST /api/bulk-uploads/master-results
```

- No file body — the backend reads from the configured path
- Returns `UploadResult`
- Requires Firebase auth

```
GET /api/bulk-uploads/master-results/config
PATCH /api/bulk-uploads/master-results/config
```

Reads and writes the configured file path. Requires Firebase auth.
The `PATCH` endpoint validates the path resolves before saving.

---

## Backend Implementation Notes

- File path config should be stored in a small `AppConfig` table (key-value) or
  in a dedicated `.env`-style settings mechanism — not hardcoded
- The endpoint should acquire a read lock (or handle `PermissionError`) gracefully
  in case the lab team has the file open in Excel when sync is triggered
- On `PermissionError`: return a clear user-facing message ("File is open in Excel.
  Please close it and try again.") rather than a 500
- Parsing is delegated entirely to the existing `master_bulk_upload.py` parser;
  do not modify its logic
