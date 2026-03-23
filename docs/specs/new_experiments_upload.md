# Spec: New Experiments Upload

**Upload card title:** New Experiments
**Backend parser:** `backend/services/bulk_uploads/new_experiments.py` (locked — no changes)
**Template:** Generated dynamically via `openpyxl` at download time

---

## Overview

Creates or updates Experiments, ExperimentalConditions, and ChemicalAdditives from
a structured multi-sheet Excel workbook. The parser logic is unchanged from the
existing implementation. This spec covers UI additions and the template download feature.

---

## Next-ID Helper

Before the user fills out the template, they need to know what experiment numbers
are available. The card displays a "next available number" row for each experiment
type, sourced from `GET /api/experiments/next-ids`.

### UI layout

```
New Experiments Upload
─────────────────────────────────────────────────────────
Next available IDs (as of now):
  HPHT   →  072      Serum  →  043      CF  →  008

[Download Template]   [↑ Upload filled template]
─────────────────────────────────────────────────────────
```

The next-ID chips update on every page load. They use a React Query with
`staleTime: 60_000` so they do not re-fetch on every render.

### API endpoint

```
GET /api/experiments/next-ids
```

Response:
```json
{
  "HPHT": 72,
  "Serum": 43,
  "CF": 8,
  "Autoclave": 15
}
```

Logic per type:
```python
SELECT COALESCE(MAX(experiment_number), 0) + 1
FROM experiments
WHERE experiment_type = :type
```

Returns all types defined in `ExperimentType` enum. Returns `1` for types with
no experiments yet.

---

## Template Download

The template is generated at download time (not a static file) so that it can
embed the current next-ID hints as placeholder text in the first data row.

### Sheet structure

**Sheet 1: experiments**

| experiment_id * | sample_id | date | status | initial_note | overwrite | researcher |
|---|---|---|---|---|---|---|
| _(e.g. HPHT_072)_ | | | ONGOING | | | |

The first data row is pre-filled with a hint value in the `experiment_id` column
based on the type most recently used (or `HPHT_072` as default). This is a hint
only — the user overwrites it.

**Sheet 2: conditions**

Headers matching `ExperimentalConditions` fields. Includes a comment on each
column header cell explaining the field and its expected units.

**Sheet 3: additives**

| experiment_id * | compound * | amount * | unit * | order | method |
|---|---|---|---|---|---|

**Sheet 4: INSTRUCTIONS**

Plain-text guide explaining the experiment ID format rules:
- 3-part: `ExperimentType_ResearcherInitials_Index` (e.g. `Serum_MH_101`)
- 2-part: `ExperimentType_Index` (e.g. `HPHT_072`)
- Suffixes: `-N` = sequential, `_TEXT` = treatment variant

---

## Parser (unchanged)

The existing `new_experiments.py` parser handles all parsing. Key behaviors:
- Auto-copies conditions from parent for sequential and treatment variant experiments
- Renames via `old_experiment_id` + `overwrite=True`
- Experiment type auto-populated from parsed `experiment_id`
- Missing compounds in additives sheet are auto-created

See `docs/upload_templates/new_experiments.md` for full parser reference.

---

## Calculation Engine

After each experiment, conditions, and additives creation:
- `registry.recalculate(conditions, session)` → computes `water_to_rock_ratio`
- `registry.recalculate(additive, session)` → computes additive-level calculated fields

---

## API Endpoint

```
POST /api/bulk-uploads/new-experiments
```

- `multipart/form-data`: `file` (required)
- Returns `UploadResult`
- Requires Firebase auth

```
GET /api/experiments/next-ids
```

- No auth required (read-only, non-sensitive)
- Returns `dict[str, int]`
