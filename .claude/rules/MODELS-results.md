---
paths:
  - "database/models/results.py"
  - "backend/services/scalar_results_service.py"
  - "backend/services/icp_service.py"
  - "backend/services/core_flood_service.py"
  - "backend/services/result_merge_utils.py"
  - "backend/services/calculations/**"
  - "backend/services/bulk_uploads/master_bulk_upload.py"
  - "backend/services/bulk_uploads/scalar_results.py"
  - "backend/services/bulk_uploads/quick_upload.py"
  - "backend/api/routers/results.py"
  - "backend/api/routers/core_floods.py"
  - "backend/api/schemas/results.py"
  - "tests/**/*result*"
  - "tests/**/*icp*"
  - "tests/**/*scalar*"
  - "tests/**/*core_flood*"
  - "tests/**/*master*"
---

# Experimental Results

> Part of the schema reference split out of `.claude/rules/MODELS.md` (the index). Field lists live in the model files; this file keeps what the code cannot tell you.

Defined in `database/models/results.py`.

### `ExperimentalResults`
Parent table for all result data at a specific timepoint.
- **Key Fields**:
  - `experiment_fk`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `cumulative_time_post_reaction_days`.
  - `is_primary_timepoint_result`: Boolean flag for the main result record of a timepoint (unique per experiment+bucket).
  - **Legacy free-text columns dropped (issue #122 PR-D, Alembic `b8c4e2d7f9a1`, 2026-10-14):** `description`, `brine_modification_description` and `has_brine_modification` no longer exist. Their content lives in `experiment_notes` (`observation` / `modification` notes scoped to the result; the 020 backfill moved the historical text). The scalar and quick-upload parsers mirror their `Description` column into an `observation` note signed with the parser tag via `ScalarResultsService.create_scalar_result_ex`'s `_note_source` control key; Timepoint Modifications writes the uploader's `modification` slot only. A re-upload with a time never adopts a legacy NULL-time row (the description-keyed fallback went with the column).
  - `UNIQUE (experiment_fk, id)` (`uq_results_experiment_fk_id`): target of the notes composite FK; redundant with the PK on its own.
  - **Per-sample core flood columns (issue #132, Alembic `f3b7c2a9d4e1`, 2026-11-03; Mat's sign-off 2026-11-03, additive columns on a locked model).** Five nullable columns, none read by the calculation engine:
    - `sample_tube_number` (Integer, **any experiment type**): the physical centrifuge tube. The number is reused across dates (21 values repeat in the tracker), so it is not a key. Exposed in `v_dim_timepoints`. The Master Results upload fills it from an optional `Tube Number` Dashboard column (issue #135): set directly on the result inside the vial-day SAVEPOINT, deliberately outside `result_data`/`_sheet_fields` (those name `ScalarResults` fields), 0 = blank, and a blank clears only on OVERWRITE with the column present. See `docs/upload_templates/master_bulk_upload.md`.
    - **Core Flood only, NULL elsewhere** (like `core_height_cm` on conditions): `flow_rate_mL_min`, `nitrogen_flow_rate_mL_min`, `inlet_pressure_psi`, `outlet_pressure_psi` (Float). `flow_rate_mL_min` is the rate over the interval **ending** at that sample; `0` means a hold, so a flow change or hold needs no new experiment. Inlet/outlet pressure are stored for a future permeability (Darcy) calculation (pressure drop, with flow and core geometry); nothing computes it yet. Pore pressure is **not** a result column: it stays `experimental_conditions.pore_pressure`.
    - **Design decision (Mat, 2026-11-03):** the spec first proposed a separate `core_flood_results` 1:1 table; Mat revised it to columns on this table, because four fields don't justify a child table, a model and a cascade. Because they are columns on `experimental_results`, deleting an experiment needs no new purge logic.
    - Quote the mixed-case names in raw SQL: `er."flow_rate_mL_min"`, `er."nitrogen_flow_rate_mL_min"`. Cross-sample values (cumulative volume, pore volumes, cumulative H2, H2 per day) are view columns in `v_core_flood_samples`, not stored.
    - **`permeability_flow_rate_mL_min` (Float, issue #140, Alembic `a1c5e8f2b9d3`, 2026-11-06; Mat's sign-off, one additive column on a locked model).** Inlet/outlet pressures are recorded only when permeability is intentionally tested, at `flow_rate_mL_min` or at a separate test rate. The presence of this column is what marks a sample as a permeability test and is the sole trigger for any future permeability computation; nothing computes it yet. `flow_rate_mL_min` keeps its meaning (rate over the interval ending at the sample, 0 = hold). No backfill: 0 of 183 dev core flood samples carried a pressure. Exposed in `v_core_flood_samples` right after `outlet_pressure_psi`; quote it in raw SQL.
    - Purely additive; no backfill. Downgrade drops `v_core_flood_samples` first and restores the old `v_dim_timepoints` / `v_experiment_conditions` before dropping the columns.

### `ScalarResults`
Stores solution chemistry measurements.
- **Hydrogen (H2)** — always stored in **ppm (vol/vol)**:
  - Inputs: `h2_concentration` (ppm), `h2_concentration_unit` (always `'ppm'`), `gas_sampling_volume_ml`, `gas_sampling_pressure_MPa`.
  - **GC source precedence (issue #111):** `h2_concentration` holds a single ppm
    value and there is no stored notion of which GC method produced it.
    On a Master Results upload the parser picks Full Loop over direct
    injection and writes only the winner. The upload's `warnings` name the
    affected rows ("Full Loop reading used instead of direct injection on
    3 rows (2, 5, 9)"), which the bulk-upload panel already renders, so a
    researcher can see that a DI reading was discarded (issue #114 item 1).
    The per-row `h2_source` / `h2_di_superseded` records in the response's
    `feedbacks` are still not rendered anywhere. Neither the source nor the
    discarded value is persisted — making that a stored provenance field
    would be an additive `ScalarResults` column and a schema-checklist run.
  - **One row per vial-day, but not one SHEET row (issue #111; merge added
    2026-08-11):** replicate letters are separate vials with their own IDs, not
    columns. Several sheet rows may describe one vial-day, though — gas is drawn
    and run on one date and the liquid/solid fraction is collected later, so each
    fraction gets its own row. Rows sharing a `(normalize_id, timepoint)` key are
    **merged field by field** into one stored result; matching on the
    `_id_match.normalize_id` key rather than the raw string is what makes
    `SERUM_cation_001c-t5` and `SERUM_Cation_001c-t5` one vial-day (before
    2026-08-07 both passed and the later row silently overwrote the earlier).
    Only a field two rows fill with **different** values is a conflict, and that
    vial-day is then rejected **whole** — never partially — with every row,
    field and value named in one error anchored at the group's first row. On the
    team's workbook (2026-08-11) this merges 72 rows into 36 vial-days and leaves
    four genuine conflicts. `created + updated` therefore no longer equals the
    sheet row count; a file-level warning states the merge count.
    Cross-replicate mean/SD still come from `v_results_scalar_rollup`
    (`mean_h2_ppm` / `sd_h2_ppm`), not from the spreadsheet.
  - **`measurement_date` is the sample COLLECTION date, `gc_run_date` is the
    instrument run date.** They are different events and disagree on 116 of the
    270 workbook rows carrying both (measured 2026-08-11), so neither
    substitutes for the other in reporting. The collection date comes from the
    `Sample Collection Date` column (aliases: `Sample Date`,
    `Liquid/Solid Sample Date`, `HPHT + Liquid/Solid Date Sampled`); when a
    vial-day spans several rows, the date from a row that carried a liquid/solid
    measurement wins, falling back to any dated row rather than discarding —
    185 rows carry a date with no liquid measurement. A sheet with no
    recognized date column now warns instead of silently storing none; three
    renames on 2026-08-11 each dropped every date on the sheet, and on an
    `OVERWRITE=TRUE` row a stored date was actively cleared.
  - **Overwrite is bounded by the source's own columns (issue #116):** on the
    `overwrite=True` branch, `create_scalar_result_ex` clears only the fields
    named in the optional `_sheet_fields` key of `result_data`. Absent that key
    it iterates all of `SCALAR_UPDATABLE_FIELDS`, which is what let an
    `Overwrite=TRUE` Master Results row null the eight entries that sheet has no
    column for — `background_ammonium_concentration_mM` among them, which
    defaults to 0.2 mM when NULL and therefore moved net ammonium and
    `grams_per_ton_yield` silently. `master_bulk_upload.py` now derives
    `_sheet_fields` from the keys of its own `result_data` literal, so adding a
    sheet column cannot leave the new field unclearable. A declared column left
    blank still clears — required, or an overwrite re-upload re-asserts the
    stale GC carryover geometry issue #114 removed. `scalar_results.py` and
    `quick_upload.py` also reach this branch and declare nothing, so they keep
    the whole-list behavior and the same latent bug; tracked separately.
  - **Geometry requires a reading (issue #114):** a Master Results row with no
    `H2 (ppm)` in either GC block stores no `gas_sampling_volume_ml` or
    `gas_sampling_pressure_MPa` either. Those sheet columns carry the previous
    run's values (207 of 499 rows on the v3 Dashboard, 2026-07-30), and nothing
    was ever computed from them without a concentration — but persisted, they
    were indistinguishable from a real measurement.
  - Derived (PV = nRT at 20 °C): `h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`.
- **Background**: `background_experiment_id`, `background_experiment_fk` (optional FK to `Experiment`).

### `ICPResults`
Stores ICP-OES elemental analysis data.
- **Fixed element columns** (Float, ppm; full list in `database/models/results.py`):
  - `ti` (Titanium) added 2026-09-22 by Alembic `5840d41bf18d`, which also backfills it
    from `all_elements` (120 rows already held a Ti reading on the 2026-09-04 production
    mirror).
  - **Which elements reach a fixed column is decided at upload time by
    `ICP_FIXED_ELEMENT_FIELDS`, not by the model.** `backend/services/icp_service.py`
    imports that list from `frontend.config.variable_config`, a Streamlit-era module that
    no longer exists; the ICP-OES route in `backend/api/routers/bulk_uploads.py` fabricates
    the module at request time, so the list it installs is what production stores. Until
    2026-09-22 that was a 27-element literal predating `ag ce k la na pb sc th v` (2026-05)
    and `s` (2026-06): every one of those readings landed in `all_elements` only and the
    fixed columns were NULL on all 1171 production rows (so `v_results_icp.na_ppm` etc.
    were all NULL in Power BI — the 2026-08-13 issue-log claim that they were populated was
    wrong). The route and `tests/conftest.py` now both take the list from
    `backend/api/schemas/results.py::ICP_ELEMENTS`, and `5840d41bf18d` backfills those ten
    columns from JSONB too (NULLs only, numeric-looking values only, clamped at 0 to match
    `458f344f73d8`). `tests/models/test_icp_ti_column.py` pins `ICP_ELEMENTS` to the model's
    element columns, to `ICPCreate`, and to the view — **adding a fixed element column means
    the model, `ICP_ELEMENTS`, `ICPCreate`, `v_results_icp`, and a migration, or that test
    fails.**
- **Flexible Data**: `all_elements` (JSON) stores full dataset.
