# Locked Components — Do Not Modify Without Explicit User Instruction

These components represent working, production-tested logic. Treat them as read-only unless the user specifically authorizes changes.

## Database Schema (`database/models/`)

The SQLAlchemy models are the authoritative definition of all data structures. They encode years of real lab data. See `MODELS.md` for complete reference.

**Models are storage-only in the new architecture. All business logic and derived field calculations are moved to `backend/services/calculations/`. Do not add `@property` methods or hybrid properties to models for calculated fields.**

Locked models — preserve field names, types, relationships, and constraints exactly:

| Model | File | Notes |
|---|---|---|
| `Experiment` | `experiments.py` | Central entity — all FKs reference this |
| `ExperimentalConditions` | `conditions.py` | One-to-one with Experiment; `water_to_rock_ratio` is a stored derived field |
| `ExperimentalResults` | `results.py` | Timepoint parent record |
| `ScalarResults` | `results.py` | Solution chemistry; yield fields are stored derived fields |
| `ICPResults` | `results.py` | ICP-OES elemental data; JSON fields are intentional |
| `SampleInfo` | `samples.py` | Geological sample metadata |
| `Compound` | `chemicals.py` | Chemical reagent inventory |
| `ChemicalAdditive` | `chemicals.py` | Join table; calculated fields are stored derived fields |
| `ExternalAnalysis` | `analysis.py` | External lab report container |
| `XRDAnalysis` / `XRDPhase` | `xrd.py` | Mineral phase data |
| `PXRFReading` | `analysis.py` | Portable XRF data |
| `Analyte` / `ElementalAnalysis` | `characterization.py` | Elemental composition |
| All enums | `enums.py` | Changing these breaks existing data |

**JSON fields in `ICPResults` (`all_elements`, `detection_limits`) and `XRDAnalysis` (`mineral_phases`) are intentional design decisions.** In PostgreSQL these become `JSONB` columns — do not flatten them without explicit user instruction.

## Derived Fields — Stored, Not Computed on Read

All calculated/derived fields are **written to the database** at create/update time by the calculation engine. They are NOT computed on read via SQLAlchemy properties. This ensures Power BI and any direct SQL consumers see correct values without needing application logic.

Derived fields by table:
- `ExperimentalConditions`: `water_to_rock_ratio`
- `ScalarResults`: `h2_micromoles`, `grams_per_ton_yield`, `h2_grams_per_ton_yield`
- `ChemicalAdditive`: `mass_in_grams`, `moles_added`, `final_concentration`, `elemental_metal_mass`, `catalyst_percentage`, `catalyst_ppm`

## Firebase Authentication

Working in production. Do not modify auth logic. When building the React frontend, integrate using the existing Firebase project credentials stored in environment variables. The FastAPI backend validates Firebase ID tokens on every protected request.

## Bulk Upload Python Parsers (`backend/services/bulk_uploads/`)

These parsers handle real instrument output formats with edge cases accumulated from actual lab use. Do not rewrite parsing logic when rebuilding the UI layer. The task is to wrap these in FastAPI endpoints, not replace them.

| Parser | Handles |
|---|---|
| `new_experiments.py` | Multi-sheet Excel, experiment lineage parsing |¹ ⁴
| `scalar_results.py` | Solution chemistry Excel, partial updates |
| `icp_service.py` | Raw ICP-OES CSV, delimiter detection, dilution correction |³
| `actlabs_titration_data.py` | External titration lab reports |
| `actlabs_xrd_report.py` | External XRD lab reports |
| `xrd_upload.py` | Generic XRD file upload handler |
| `aeris_xrd.py` | Time-series Aeris instrument XRD data |
| `pxrf_data.py` | Portable XRF Excel uploads |
| `rock_inventory.py` | Geological sample bulk upsert |
| `chemical_inventory.py` | Chemical compound database updates |
| `experiment_status.py` | Batch status and reactor assignment updates |
| `experiment_additives.py` | Chemical additive bulk updates |
| `quick_upload.py` | Metric-specific mini-templates |
| `long_format.py` | Long-format LIMS-compatible data |
| `metric_groups.py` | Grouped metric upload templates |
| `timepoint_modifications.py` | Timepoint-level record modifications |
| `master_bulk_upload.py` | Master Results Dashboard sheet parser |²

¹ **Rename-path ordering contract (issue #86, changed with explicit sign-off).** The experiments-sheet loop now (a) flushes a rename's new `experiment_id` **before** recomputing lineage, so the group-parent lookup resolves against the new ID rather than the row's stale old ID (which could otherwise self-match and raise `CircularDependencyError` under the production `autoflush=False` session), and (b) wraps each row in a `db.begin_nested()` SAVEPOINT so a single failed row rolls back only itself instead of poisoning the whole batch with cascading `PendingRollbackError`. Preserve both properties when touching this loop. See the lineage-section note in `MODELS.md` and `tests/services/bulk_uploads/test_new_experiments_rename_lineage.py`.

² **Duplicate-guard contract (changed 2026-08-07 with explicit sign-off).** The Phase-1
duplicate pre-pass keys on `_id_match.normalize_id(experiment_id)` plus the normalized
timepoint — **not** the raw ID string. Keying on the raw string let two spellings that
differ only by case or zero padding both pass the guard and both upsert onto the one
experiment the DB lookup resolves them to, so the later row silently overwrote the
earlier; three such pairs were live in the team's v3 workbook. The accepted converse is
that two genuinely different experiments whose IDs differ only by case/padding would now
both be rejected (0 of 1009 dev-DB experiments share a normalized key, measured
2026-08-07). One error is emitted per collision group, naming every row and every
distinct spelling, anchored at the group's first row so the sheet-order sort holds.
The per-row Duration-vs-`-t`-token warning was aggregated into one file-level coverage
line, tallied in Phase 2 **after** the row is written (matching `h2_reading_rows`) so a
rejected row is never named in a warning claiming its reading was recorded. Each row's
upsert runs in its own `db.begin_nested()` SAVEPOINT, so one failing row rolls back only
itself — a session-wide rollback would discard rows the batch had already committed.
Preserve all six properties when touching this file.

³ **Label timepoint contract (changed 2026-08-07 with explicit sign-off).** The
`Label` column's `_Day<n>` token no longer determines a result's timepoint when the
experiment ID carries a `-t<days>` token: the ID wins, the disagreement is reported
in `warnings`, and no row is rejected. This matches `master_bulk_upload.py` (see ²
and its `:383` comment) and deliberately differs from `POST /api/results`, which
still 400s via `apply_id_timepoint`. Dilution was also unwelded from `Day`, so a
label MAY omit `Day` entirely (`SERUM_Cation_005c-t5_21x`) — previously that
returned `None` and the row was dropped with no error at all, so a file relabelled
this way reported "0 created" with no explanation. Five properties are load-bearing
when touching `extract_sample_info_ex`: (a) the `-t` grammar is delegated to
`database/experiment_id_parser.py::split_timepoint_token` and must never be
re-implemented here, or ICP drifts from lineage; (b) dilution is peeled **before**
the token is split, so `-t<days>` is at end-of-string when that anchored regex runs;
(c) `extract_sample_info` must keep returning exactly three keys, because
`create_icp_result` splats it into `result_data` and stores every unrecognized key
in the `all_elements` JSONB as a fake element; (d) `process_icp_dataframe` and
`parse_and_process_icp_file` must keep their 2-tuple arity — `legacy/streamlit_frontend/bulk_uploads.py:1558,1599`
still calls the latter; (e) the router's early "ICP parse failed" return must pass
`warnings=`, since the all-labels-skipped case is exactly where that warning is the
only explanation available; (f) the disagreement warning's wording must stay a claim
about the **label**, never about persisted data. That tally runs at parse time,
before `bulk_create_icp_results` decides whether each row lands, so a row that
disagrees and is then rejected is named in it too — the post-write phrasing this
warning originally copied from `master_bulk_upload.py` ("each reading was recorded
at the day its ID encodes") contradicted such a row's own error in the same
response. See `docs/working/decisions.md` (2026-08-07, 2026-08-10) and
`tests/test_icp_handling.py::TestICPTimepointTokenPersistence::test_disagreement_warning_never_claims_a_rejected_row_was_written`.
See
`docs/superpowers/specs/2026-08-07-icp-label-timepoint-token-design.md` and
`tests/test_icp_handling.py::TestICPLabelTimepointToken`.

⁴ **Conditions recalculation contract (changed 2026-08-10 with explicit sign-off).**
`water_to_rock_ratio` and `total_ferrous_iron_g` are **stored** derived fields on
`ExperimentalConditions`, written only by `recalculate()`. This parser never called it,
so bulk-created experiments landed with both NULL — and because
`calculate_ferrous_iron_yield_h2` returns NULL when `total_ferrous_iron_g` is NULL, every
Fe²⁺ yield on their scalar results was NULL too (157 production scalar rows, 845 of 1125
conditions rows). The parser now accumulates the primary key of every conditions row it
creates or mutates in `touched_conditions_ids`, and `_recalculate_touched_conditions`
recalculates them in a single pass **once, immediately before the return**, after all
three sheets have finished mutating conditions — deferred so a row reached by both the
conditions and additives sheets is recalculated once, from its final state.

**The load-bearing rule: any new code path in this file that creates or mutates an
`ExperimentalConditions` row must add that row's primary key to
`touched_conditions_ids`.** Omit it and the row's stored derived fields silently stay
NULL, taking every Fe²⁺ yield on its scalar results down with them — with no error, no
warning, and nothing in the response to show it happened. There are three record sites
today (conditions sheet — outside its `if not conditions:` block, so an overwritten
pre-existing row is recorded too; parent auto-copy and additives sheet — inside theirs,
because on those paths a pre-existing row is never mutated). Also preserve: each row is
recalculated inside its own `db.begin_nested()` SAVEPOINT with the `db.get()` inside the
protected region (per ¹ above — a DBAPI failure otherwise raises `PendingRollbackError`
on the next row and discards an otherwise-good upload, and a mid-recalculation failure
otherwise leaves half-applied mutations for the caller to commit while the warning claims
the row was skipped); the helper flushes and commits nothing of its own; and
`bulk_upsert_from_excel` keeps its 6-value return with `_bulk_upsert_from_excel_impl` at
7. See `docs/issues/issue-bulk-upload-never-recalculates-conditions.md`,
`docs/CALCULATIONS.md` (`total_ferrous_iron_g`) and
`tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py`.

## Alembic Migration History

Never delete, rewrite, or squash existing migration files. All new migrations must be additive. Migration files form a chain — breaking it corrupts production upgrade paths.
