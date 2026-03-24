# Architectural decisions

Append-only lasting decisions from milestone, issue, or inline work (newest at bottom). Summaries may also appear in `docs/working/plan.md` for milestone tasks; this file holds the durable record.

## 2026-03-24 — Shared write helper for ElementalAnalysis; explicit overwrite contract

**Decision:** Both `ElementalCompositionService` and `ActlabsRockTitrationService` delegate all `ElementalAnalysis` writes to the single module-level function `_write_elemental_record(db, ext_analysis_id, sample_id, analyte, value, overwrite)` in `actlabs_titration_data.py`.

**Contract:**
- `overwrite=False` (default): INSERT if no record exists; SKIP if record already exists
- `overwrite=True`: INSERT if no record exists; UPDATE if record already exists
- Null/blank values must never be passed to this function (callers skip nulls before calling)

**Why:** The two services previously duplicated identical `if existing → update / else → create` blocks with no user-controllable behavior. This created an implicit always-overwrite contract that was unsafe for partial re-uploads. The new default (`overwrite=False`) is the safe choice for first-time and incremental uploads; `overwrite=True` is reserved for deliberate data correction.

**Scope:** Any future parser that writes to `ElementalAnalysis` must use `_write_elemental_record` — do not inline a new upsert block.
