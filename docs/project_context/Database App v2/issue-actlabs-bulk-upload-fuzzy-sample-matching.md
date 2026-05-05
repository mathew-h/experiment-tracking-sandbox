# Fuzzy Sample ID Matching & Duplicate Warning for ActLabs Bulk Upload

## Summary

The ActLabs rock analysis bulk upload feature currently performs no normalization or similarity check on sample IDs before inserting records. This allowed `TAMARACK` and `tamarack` to be ingested as separate samples, producing duplicate entries that cannot be resolved through the UI. The upload should detect near-matches against existing sample IDs and warn the user before committing any records.

---

## Problem

When a user uploads an ActLabs results file, the backend matches incoming sample IDs against existing samples using a case-sensitive (or otherwise strict) string comparison. Because lab instruments and analysts often produce IDs with inconsistent casing, whitespace, or minor typographic variations, the same physical sample can end up registered multiple times under slightly different names.

**Observed failure:**

- Existing sample: `Tamarack`
- Uploaded row: `TAMARACK` → created a new sample instead of matching the existing one
- Uploaded row: `tamarack` → created yet another new sample
- Result: three `Tamarack` entries in the database with disjoint analytical data; no UI path to merge or deduplicate them

---

## Proposed Solution

### 1. Normalize before lookup

Before any database query, apply a canonical normalization function to both the incoming ID and all candidate IDs:

- Strip leading/trailing whitespace
- Collapse internal whitespace runs to a single space
- Uppercase (or lowercase) the entire string

This alone eliminates pure case and whitespace duplicates.

### 2. Fuzzy similarity check

After normalization, run a similarity check between each incoming sample ID and all existing sample IDs. A reasonable starting approach:

- Use **Levenshtein distance** (or a ratio-based metric like `rapidfuzz` `WRatio`) with a configurable threshold (e.g., similarity >= 0.90).
- Flag any existing sample whose normalized ID scores above the threshold as a **potential match**.

### 3. Pre-commit warning response

Before writing any records, the upload endpoint should return a structured warning payload listing every incoming ID that has one or more fuzzy matches:

```json
{
  "status": "warnings",
  "conflicts": [
    {
      "incoming_id": "TAMARACK",
      "normalized": "TAMARACK",
      "candidate_matches": [
        { "sample_id": 42, "name": "Tamarack", "similarity": 1.0 }
      ]
    }
  ],
  "message": "Some uploaded sample IDs closely match existing samples. Review before confirming."
}
```

The frontend should display this warning in a blocking modal — showing the incoming ID alongside each candidate match — and require the user to either:

- **Link to existing sample** — map the incoming ID to the matched sample and continue the upload without creating a new record
- **Create as new** — explicitly acknowledge that a new sample is intended despite the similarity
- **Cancel upload** — abort and correct the source file

Only after the user resolves every conflict should the upload proceed.

### 4. Exact-match short-circuit

If the normalized incoming ID exactly matches a normalized existing ID, treat it as the same sample automatically (no user prompt needed) and associate the results to that existing record. Log this auto-resolution for auditability.

---

## Acceptance Criteria

- [ ] Uploading an ID that differs only in case (e.g., `TAMARACK` vs `Tamarack`) is auto-resolved to the existing sample without creating a duplicate.
- [ ] Uploading an ID with high similarity (>= configurable threshold, default 0.90) to an existing sample triggers a blocking warning modal in the frontend before any records are written.
- [ ] The warning modal displays the incoming ID, the candidate match name, and the similarity score, and requires an explicit user decision per conflict.
- [ ] If the user selects "link to existing," the uploaded results are associated with the matched sample and no new sample record is created.
- [ ] If the user selects "create as new," a new sample record is created and the upload proceeds normally.
- [ ] Exact normalized matches are auto-resolved silently; the resolution is logged to the backend audit log.
- [ ] The similarity threshold is configurable via an environment variable or admin setting (default: 0.90).
- [ ] Uploading a file with no near-matches proceeds identically to the current behavior (no regression).

---

## Technical Notes

- **Library:** `rapidfuzz` (Python) is recommended over `fuzzywuzzy` — faster, no `python-Levenshtein` dep required, and actively maintained. Add to `requirements.txt`.
- **Where to implement:** The normalization + fuzzy check should live in the ActLabs upload service layer (e.g., `backend/services/actlabs_upload.py` or equivalent), not in the route handler, so it can be unit-tested independently.
- **Threshold tuning:** 0.90 is a starting point. Real sample ID sets (e.g., `TMRK-001` vs `TMRCK-001`) may require adjustment after testing against the actual sample name corpus.
- **Performance:** If the sample table grows large, pre-load and cache normalized sample names at request startup rather than querying per row. For the current scale (small team, hundreds of samples), a linear scan is fine.

---

## Labels

`bug`, `upload`, `data-integrity`, `actlabs`, `ux`

## Priority

High — data integrity issue; existing duplicates require manual database intervention to resolve.
