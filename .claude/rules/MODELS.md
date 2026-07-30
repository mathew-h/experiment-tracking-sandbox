# Database Schema Documentation

This document provides a comprehensive overview of the database schema for the Experiment Tracking System. The schema is built using SQLAlchemy ORM and deployed on SQLite.

The models are modularized within the `database/models/` directory.

**Reporting intent:** The schema and the SQL views described below are designed to support **dynamic Power BI dashboards**. Views provide flattened, reporting-friendly datasets (one row per experiment timepoint, joined scalars and ICP, additives summary) so Power BI can connect directly to the database and refresh dashboards as data changes, without application-layer ETL.

## Core Experiment Models
Defined in `database/models/experiments.py`.

### `Experiment`
The central hub for all experimental data.
- **Primary Key**: `id` (Integer)
- **Key Fields**:
  - `experiment_id` (String, unique): User-defined identifier (e.g., "Serum_MH_101").
  - `experiment_number` (Integer, unique): Auto-incrementing sequence number.
  - `status`: Enum (`ONGOING`, `COMPLETED`, `CANCELLED`).
  - `sample_id`: FK to `SampleInfo`.
  - `researcher`, `date` (optional).
  - `is_outlier` (Boolean, non-null, default `false`): flags a bad vial (leak, cracked septum). Flagged experiments are excluded from `v_results_scalar_rollup` aggregates **including `n_replicates`**, but remain fully visible in all per-row views (`v_results_scalar`, `v_results_h2`, `v_results_icp`, `v_primary_experiment_results`) and on their own pages.
  - **Bulk deletion path (issue #109):** `POST /api/bulk-uploads/experiment-deletion`
    is the second entry point into the same purge. It parses an `experiment_id`
    column and calls `delete_experiment_cascade` once per row, so every rule below
    applies unchanged. Two things are specific to it:
    `backend/api/routers/bulk_uploads.py::BULK_DELETE_ALLOWED_EMAIL` gates it to a
    single hardcoded address (403 for anyone else — the only access control in
    Phase 1, there is no preview and no `dry_run`), and each row runs inside its
    own SAVEPOINT in
    `backend/services/bulk_uploads/experiment_deletion_bulk.py`. The SAVEPOINT is
    load-bearing, not defensive: `delete_experiment_cascade` commits per row, so a
    session-wide `db.rollback()` on one bad row would discard the experiments the
    batch had already deleted.
  - **Deletion path (issue #99):** `DELETE /api/experiments/{experiment_id}` is a
    **hard** delete available to any approved researcher (no role gate) and returns
    **200 with a body** reporting what was decoupled — not 204. Deletion **purges
    everything the experiment owns**; the one boundary is that it never destroys
    another experiment's data. All orphan prevention lives in
    `backend/services/experiment_deletion.py`, not in the relationship cascades,
    because these references are not handled correctly by
    `cascade="all, delete-orphan"`:
    - `xrd_phases` rows are **deleted**, matched on `experiment_fk` **or** the
      `experiment_id` string. Nulling the FK alone would leave rows whose stale
      string still holds the `uq_xrd_phase_experiment_time_mineral` slot on
      `(experiment_id, time_post_reaction_days, mineral_name)`, blocking
      re-creation of that experiment's XRD data.
    - `scalar_results.background_experiment_id` / `background_experiment_fk` on
      **other** experiments are NULLed — a **DECOUPLING, never a purge**: the row
      and its `background_ammonium_concentration_mM` value both survive. The
      string is the column actually in use (`background_experiment_fk` was set on
      0 of 1056 rows as of 2026-07-29) and it has **no FK**, so nothing at the DB
      level protects it. This is provenance only —
      `background_ammonium_concentration_mM` holds the number the calculation
      engine reads, so no derived field changes and no `recalculate()` is needed.
    - `reactor_change_requests` rows for this experiment are **PURGED**, not
      unlinked (product decision, 2026-07-29). They belong to the experiment, and
      `change_requests` is summed into `total`, which is documented as rows
      destroyed — nulling instead of deleting made that count overstate
      destruction.
    - `elemental_analysis` rows belonging to this experiment's
      `external_analyses` are **PURGED** before `db.delete(exp)`.
      `ElementalAnalysis.external_analysis_id` is `nullable=False` but its
      relationship (`characterization.py:43`) is a bare backref with no cascade
      and no `passive_deletes`, so the ORM would emit
      `UPDATE elemental_analysis SET external_analysis_id=NULL` when the parent
      `ExternalAnalysis` is cascade-deleted → `NotNullViolation` → HTTP 500 and no
      delete at all. The fix is in the service, **not** a `passive_deletes=True`
      on the model: `database/models/` is locked and models are storage-only here.
      (`AnalysisFiles` and `XRDAnalysis` already cascade; `XRDPhase.external_analysis_id`
      is nullable with no reverse collection.)

    Replicate children keep their `base_experiment_id` and `replicate_label`; only
    `parent_experiment_fk` is dropped — also a **DECOUPLING, never a purge**.
    Groups are addressed by the base-ID *string* (issue #87), so the group page and
    `v_results_scalar_rollup` are unaffected — the affected IDs are reported in the
    response so the researcher is told.

    **Impact counts.** `DeleteImpact` counts `conditions`, `results`,
    `scalar_results`, `icp_results`, `result_files`, `notes`, `additives`,
    `external_analyses`, `xrd_phases`, `change_requests`; `total` is their sum.
    `conditions` (the `ExperimentalConditions` setup row — temperature, initial pH,
    rock mass, water volume, reactor number, pressures, `total_ferrous_iron_g`) is
    counted because the ORM cascade hard-deletes it: while it was uncounted, an
    experiment with conditions and nothing else (44 in the dev DB) reported
    `total == 0`, so the dialog said "nothing else is affected" and enabled Delete
    on a single click. Adding a counted field requires all five layers — the
    dataclass, its `total`, `collect_delete_impact`, `DeleteImpactResponse`,
    `_impact_to_response`, the TS `DeleteImpact` interface, and the modal's
    `IMPACT_ROWS` — or the dialog silently under-reports.

    **Audit row.** Every delete writes one `ModificationsLog` row with
    `modification_type='delete'`, `modified_table='experiments'`, `old_values`
    holding the deletion snapshot and `new_values` holding the impact counts.
    **The row must be written with `experiment_fk = NULL`** — that FK is
    `ondelete="CASCADE"`, so a populated value would delete the audit row along
    with the experiment. This row is the only surviving trace of the deletion and
    is what justifies opening the endpoint to any approved researcher.

    The snapshot in `old_values` is a **record of what was deleted, not a restore
    point**: it holds the experiment header row, its conditions row, its additives
    (with compound name) and its note **text**. NOT recoverable from it — all
    `ExperimentalResults` / `ScalarResults` / `ICPResults` / `ResultFiles` values
    (deliberately excluded: bulk-uploadable and unbounded, counts only), purged
    `xrd_phases` rows (`mineral_name`, `amount`, `time_post_reaction_days`, `rwp`),
    `ExternalAnalysis` rows and their metadata/files, note timestamps, the purged
    prior audit history, and lineage (`parent_experiment_fk` is stored as a stale
    integer PK that can no longer be resolved).

    **The experiment's prior `ModificationsLog` history is purged with it** via
    `Experiment.modifications` (`cascade="all, delete-orphan"`) — up to 654 rows
    for a single experiment, 13,374 across the dev DB. Accepted product decision
    (2026-07-29), consistent with purging everything the experiment owns; the
    `experiment_fk = NULL` delete-snapshot row above is what survives.

    **Constraint-parity caveat:** the dev and test DBs are built with
    `Base.metadata.create_all`, which honors the model `ondelete` clauses; the lab
    PC came up through the Alembic chain, whose initial migration declared none.
    The deletion service therefore never relies on DB-level behavior — every
    decoupling is explicit in application code.
- **Lineage Tracking**:
  - `base_experiment_id`: Tracks the root of a series (e.g., "HPHT_001" for "HPHT_001-2").
  - **Group addressing (issue #87):** `base_experiment_id` is a parsed string, not guaranteed to reference an existing `Experiment` row — lettered-only replicate sets (e.g. `SERUM_001a/b/c` with no bare `SERUM_001` row) are the common case. The replicate group is therefore addressed by this base-ID string via `GET /api/experiments/groups/{base_id}` and the `/experiments/groups/{baseId}` UI page, not by an experiment row lookup.
  - `parent_experiment_fk`: FK to the immediate parent experiment.
  - `replicate_label`: Single lowercase letter (`"a"`, `"b"`, `"c"`) identifying this row as a replicate member of a base experiment; `NULL` if this experiment is not a replicate. The bare base ID (or its explicit `S-0`/`S-1` spelling) is "replicate 0" — the group parent — and always has `replicate_label = NULL`.
  - **Known gap:** the `-0`/`-1` group-parent reclassification above only applies going forward, via the live `before_flush` event listener, to experiments created or re-saved after this change landed. It does NOT retroactively reclassify pre-existing `-0`/`-1`-suffixed experiments already in the database, and the one-off `establish_experiment_lineage_006.py` migration script was deliberately left with its original (pre-replicate) classification logic. Any historical experiment ID ending in `-0` or `-1` that was used as an ordinary sequential re-run (not a parent alias) will not be automatically reclassified — check case-by-case before building reporting or UI logic that assumes universal `-0`/`-1` = group-parent semantics.
  - **Parent wiring for letter + sequential re-runs (P5):** an ID like `SERUM_001a-2` (a sequential re-run of lettered replicate `a`) sets `parent_experiment_fk` to the lettered sibling `SERUM_001a` when that experiment exists (including when both are created in the same flush); otherwise it falls back to the group parent (bare stem, then `-0`, then `-1`), as before P5. Any `-N` links to the letter itself (`a-3` → `a`, not `a-2`). Letter + sequential + treatment combos (e.g. `SERUM_001a-2_Desorption`) are excluded and keep the group-parent link. Insertion-order caveat: if `a-2` is created while neither `a` nor the stem exists, it is orphaned; a later insert of the **stem** back-links it to the stem (the orphan pass is letter-unaware), and a later insert of `a` alone does not re-link it.
  - **Self-parent guard + rename-path ordering (issue #86):** `parent_experiment_fk` can never equal the experiment's own `id`. `update_experiment_lineage` (`database/lineage_utils.py`) drops a self-resolved parent to `NULL` (logging a warning) in both the replicate and sequential/treatment branches — a self-referential FK is never valid lineage and raises `CircularDependencyError` at flush. The trigger was the bulk-upload rename path: with `autoflush=False` (production `SessionLocal`), recomputing lineage before the rename was flushed made the group-parent `SELECT` match the row against its own stale (old) ID when old and new normalize alike (e.g. `X_cation_001` → `X_Cation_001a-t5`). The rename path in `backend/services/bulk_uploads/new_experiments.py` now flushes the new `experiment_id` **before** calling `update_experiment_lineage`, so the lookup resolves against the new ID.
  - **Canonical ID parser:** the experiment ID grammar lives in `database/experiment_id_parser.py` (`parse_lineage_fields` / `parse_experiment_id_full`); `database/lineage_utils.py::parse_experiment_id` is a delegating wrapper. `backend/services/experiment_validation.py::extract_lineage_info` is a frozen **legacy** shim whose divergent behavior (naive trailing `-N`, e.g. `CF-015` → sequential 15 of `CF`; combined `-N_Treatment` suffixes never extract the sequential number) is deliberately pinned because locked bulk-upload code depends on it.
  - `id_timepoint_days` (Float, nullable, indexed): day value parsed from a trailing `-t<days>` ID token (e.g. `SERUM_001a-t7` → 7.0; decimals allowed). NULL = not encoded. The ID is canonical for the vial's timepoint: result creation fills a blank time from it and rejects a conflicting one (guards in `create_scalar_result_ex` and `POST /api/results`; string-level checks in the scalar/master bulk parsers). Set by `update_experiment_lineage` via `split_timepoint_token`; the token is stripped before lineage grouping, so `SERUM_001a-t7` groups under base `SERUM_001` with `replicate_label = a` and rolls up per day bucket with no view changes. A letterless `-t` vial (`SERUM_001-t7`) stays a parent-like row (base = stem, parent NULL).
    - **Letter vs vial (issue #98):** a replicate *letter* is the scientific unit; a
      `-t<days>` *vial* is one destructively-sampled instance of it. The two are
      surfaced at different grains, and the collapse key is the timepoint-stripped
      `experiment_id` — never `(base_experiment_id, replicate_label)`, because
      `SERUM_001a-2` (a sequential re-run) shares both base and letter with
      `SERUM_001a` and must stay a separate row.
      - `GET /api/experiments` flat mode: one row per stem. `group_display_id`
        carries the label; `experiment_id` still names the representative row
        (the earliest non-outlier vial), which also supplies the Sample, Reactor,
        Date, Description and Additives columns.
      - `GET /api/experiments` grouped mode: one row per group, labeled by the
        stem, with `replicate_letters` for the badge and `vial_count` for the
        total row count.
      - `GET /api/experiments/groups/{base_id}`: `members`/`member_count` stay
        **per vial**; `replicates`/`replicate_count` are **per letter**.
      - The `-t` token is never rendered on `/experiments`, and a row standing for
        more than one vial shows status read-only, since an inline PATCH would
        reach only the representative.
- **Relationships**:
  - `conditions`: One-to-One with `ExperimentalConditions`.
  - `results`: One-to-Many with `ExperimentalResults`.
  - `notes`: One-to-Many with `ExperimentNotes`.
  - `modifications`: One-to-Many with `ModificationsLog`.
  - `external_analyses`: One-to-Many with `ExternalAnalysis`.
  - `xrd_phases`: One-to-Many with `XRDPhase` (Aeris time-series).

### `ExperimentNotes`
Stores timestamped notes/logs for an experiment.
- **Fields**: `experiment_id`, `experiment_fk`, `note_text`, `created_at`, `updated_at`.
- **Relationships**: Linked to `Experiment`.

### `ModificationsLog`
Audit trail for tracking changes to records.
- **Fields**: `experiment_id`, `experiment_fk`, `sample_id` (String, nullable — bare String ID, no FK, matching `experiment_id` pattern), `modified_by`, `modification_type` (create/update/delete), `modified_table`, `old_values` (JSON), `new_values` (JSON), `created_at`.

---

## Experimental Conditions & Chemicals
Defined in `database/models/conditions.py` and `database/models/chemicals.py`.

### `ExperimentalConditions`
Defines the parameters and setup for an experiment.
- **Key Fields**:
  - `temperature_c`, `initial_ph`, `rock_mass_g`, `water_volume_mL`.
  - `reactor_number`, `stir_speed_rpm`, `room_temp_pressure_psi`, `rxn_temp_pressure_psi`.
  - `experiment_type` (e.g., "Serum", "HPHT"), `particle_size`, `feedstock`.
  - `initial_conductivity_mS_cm`, `core_height_cm`, `core_width_cm`, `core_volume_cm3`.
  - `co2_partial_pressure_MPa`, `confining_pressure`, `pore_pressure`, `flow_rate`.
  - `initial_nitrate_concentration`, `initial_dissolved_oxygen`, `initial_alkalinity`.
- **Derived Fields**:
  - `water_to_rock_ratio` (hybrid/property: `formatted_additives` from chemical_additives).
  - `total_ferrous_iron_g` (Float, nullable): mass of ferrous iron (Fe²⁺) in grams, derived from rock characterization FeO wt% × `FE_IN_FEO_FRACTION` × `rock_mass_g`; see `docs/CALCULATIONS.md` for full formula.
- **Relationships**: `chemical_additives` → One-to-Many with `ChemicalAdditive`.
- **Note**: Legacy fields like `catalyst`, `buffer_system`, `surfactant` are deprecated in favor of `ChemicalAdditive`.

### `Compound`
Inventory of chemical reagents.
- **Fields**: `name` (unique), `formula`, `cas_number`, `molecular_weight_g_mol`.
- **Properties**: `density_g_cm3`, `melting_point_c`, `boiling_point_c`, `solubility`, `hazard_class`.
- **Catalyst Logic**: `preferred_unit`, `catalyst_formula`, `elemental_fraction` for automated catalyst calculations.
- **Metadata**: `supplier`, `catalog_number`, `notes`.

### `ChemicalAdditive`
Join table linking `ExperimentalConditions` to `Compound` with specific quantities.
- **Keys**: `experiment_id` (FK to `experimental_conditions.id`), `compound_id` (FK to `compounds.id`); unique per (experiment, compound).
- **Fields**: `amount`, `unit` (AmountUnit enum: g, mg, mM, ppm, % of Rock, etc.), `addition_order`, `addition_method` (Text, free-text prep/addition description; app-layer bound of 500 chars enforced by `ADDITION_METHOD_MAX_LENGTH` in `database/models/chemicals.py` — the DB column itself is unbounded, per issue #96), `purity`, `lot_number`, `supplier_lot`.
- **Calculated Fields**:
  - `mass_in_grams`, `moles_added`, `final_concentration`, `concentration_units`.
  - For catalysts: `elemental_metal_mass`, `catalyst_percentage`, `catalyst_ppm`.

---

## Experimental Results
Defined in `database/models/results.py`.

### `ExperimentalResults`
Parent table for all result data at a specific timepoint.
- **Key Fields**:
  - `experiment_fk`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `cumulative_time_post_reaction_days`.
  - `is_primary_timepoint_result`: Boolean flag for the main result record of a timepoint (unique per experiment+bucket).
  - `description` (required).
- **Relationships**: `scalar_data` (One-to-One `ScalarResults`), `icp_data` (One-to-One `ICPResults`), `files` (One-to-Many `ResultFiles`).

### `ScalarResults`
Stores solution chemistry measurements.
- **Fields**:
  - `final_ph`, `final_conductivity_mS_cm`, `final_dissolved_oxygen_mg_L`, `final_nitrate_concentration_mM`, `final_alkalinity_mg_L`.
  - `gross_ammonium_concentration_mM`, `background_ammonium_concentration_mM`, `ammonium_quant_method`.
  - `ferrous_iron_yield`, `grams_per_ton_yield`, `sampling_volume_mL`, `measurement_date`.
  - `co2_partial_pressure_MPa`.
- **Hydrogen (H2)** — always stored in **ppm (vol/vol)**:
  - Inputs: `h2_concentration` (ppm), `h2_concentration_unit` (always `'ppm'`), `gas_sampling_volume_ml`, `gas_sampling_pressure_MPa`.
  - **GC source precedence (issue #111):** `h2_concentration` holds a single ppm
    value and there is no stored notion of which GC method produced it. On a
    Master Results upload the parser picks Full Loop over direct injection and
    writes only the winner; the discarded DI reading is reported in the upload's
    per-row feedback (`h2_source`, `h2_di_superseded`) and is not persisted.
    Making that a stored provenance field would be an additive `ScalarResults`
    column and a schema-checklist run.
  - **One row per vial (issue #111):** the v3 Dashboard carries one row per
    unique `experiment_id`; replicate letters are separate vials with their own
    IDs, not columns. The upload rejects two rows sharing an ID and timepoint.
    Cross-replicate mean/SD therefore come from `v_results_scalar_rollup`
    (`mean_h2_ppm` / `sd_h2_ppm`), not from the spreadsheet.
  - Derived (PV = nRT at 20 °C): `h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`.
- **Background**: `background_experiment_id`, `background_experiment_fk` (optional FK to `Experiment`).

### `ICPResults`
Stores ICP-OES elemental analysis data.
- **Fixed Columns**: `fe`, `si`, `mg`, `ca`, `ni`, `cu`, `mo`, `zn`, `mn`, `cr`, `co`, `al`, `sr`, `y`, `nb`, `sb`, `cs`, `ba`, `nd`, `gd`, `pt`, `rh`, `ir`, `pd`, `ru`, `os`, `tl`, `k`, `na`, `s` (Float, ppm).
- **Flexible Data**: `all_elements` (JSON) stores full dataset.
- **Metadata**: `dilution_factor`, `instrument_used`, `detection_limits` (JSON), `measurement_date`, `sample_date`, `raw_label`, `created_at`, `updated_at`.

### `ResultFiles`
Stores paths to files associated with a result (e.g., raw instrument logs).
- **Fields**: `result_id`, `file_path`, `file_name`, `file_type`, `created_at`.

---

## Samples & Inventory
Defined in `database/models/samples.py`.

### `SampleInfo`
Geological sample metadata.
- **Primary Key**: `sample_id` (String).
- **Fields**:
  - `rock_classification`, `state`, `country`, `locality`, `latitude`, `longitude`, `description`.
  - `well_name` (String, nullable): Well or borehole name for core samples (e.g. "Tuscarora Project CT-3").
  - `core_lender` (String, nullable): Organization lending the core sample (e.g. "Geologica").
  - `core_interval_ft` (String, nullable): Depth interval stored as a string (e.g. "895'").
  - `on_loan_return_date` (Date, nullable): Date the core must be returned to the lender.
  - `characterized` (Boolean), `created_at`, `updated_at`.
- **Relationships**: `experiments`, `external_analyses`, `photos` (`SamplePhotos`), `elemental_results` (`ElementalAnalysis`).

### `SamplePhotos`
Photos associated with a sample.
- **Fields**: `sample_id`, `file_path`, `file_name`, `file_type`, `description`, `created_at`.

---

## External Analysis
Defined in `database/models/analysis.py`, `database/models/xrd.py`, and `database/models/characterization.py`.

### `ExternalAnalysis`
Container for external lab reports.
- **Key Fields**: `sample_id`, `experiment_fk`, `experiment_id`, `analysis_type`, `analysis_date`, `laboratory`, `analyst`, `pxrf_reading_no`, `description`, `analysis_metadata` (JSON), `magnetic_susceptibility`.
- **Links**: Can link to `SampleInfo` (characterization) and/or `Experiment` (post-reaction analysis).
- **Relationships**: `analysis_files` (`AnalysisFiles`), `xrd_analysis` (One-to-One `XRDAnalysis`).

### `AnalysisFiles`
Files attached to an external analysis.
- **Fields**: `external_analysis_id`, `file_path`, `file_name`, `file_type`, `created_at`.

### `XRDAnalysis` & `XRDPhase`
- **`XRDAnalysis`**: One-to-One with `ExternalAnalysis`. Stores `mineral_phases` (JSON), `peak_positions`, `intensities`, `d_spacings`, `analysis_parameters` (JSON).
- **`XRDPhase`**: Normalized mineral phases; can link to `sample_id` and/or `external_analysis_id`, or to `experiment_fk`/`experiment_id` for Aeris time-series. Fields: `mineral_name`, `amount` (%), `time_post_reaction_days`, `measurement_date`, `rwp`. Unique on (experiment_id, time_post_reaction_days, mineral_name).

### `PXRFReading`
Raw data from portable XRF scans.
- **PK**: `reading_no` (String).
- **Fields**: Elemental columns (`fe`, `mg`, `ni`, `cu`, `si`, `co`, `mo`, `al`, `ca`, `k`, `au`, `zn`), `ingested_at`, `updated_at`.

### `Analyte` & `ElementalAnalysis`
- **`Analyte`**: Definitional table for elements/oxides; `analyte_symbol` (unique), `unit`.
- **`ElementalAnalysis`**: Links `ExternalAnalysis` to `Analyte` with `analyte_composition` (value in Analyte’s unit). Optional `sample_id`. Unique on (external_analysis_id, analyte_id).

---

## Enumerations
Defined in `database/models/enums.py`.
- **ExperimentStatus**: ONGOING, COMPLETED, CANCELLED, QUEUED.
- **ExperimentType**: Serum, Autoclave, HPHT, Core Flood, Other.
- **FeedstockType**: Nitrogen, Nitrate, Blank.
- **ComponentType**: catalyst, promoter, support, additive, inhibitor.
- **AnalysisType**: pXRF, XRD, SEM, Elemental, Magnetic Susceptibility, Titration, Other.
- **AmmoniumQuantMethod**: NMR, Colorimetric Assay, Ion Chromatography.
- **TitrationType**: Acid-Base, Complexometric, Redox, Precipitation.
- **CharacterizationStatus**: not_started, in_progress, completed, partial.
- **ConcentrationUnit**: ppm, mM, M, %, wt%.
- **PressureUnit**: psi, bar, atm, Pa, kPa, MPa.
- **AmountUnit**: g, mg, μg, kg, μL, mL, L, μmol, mmol, mol, ppm, mM, M, %, wt%, % of Rock.

---

## Reporting Views (Power BI)

SQL views are created at application startup so Power BI (and other reporting tools) can query flattened, one-row-per-primary-result datasets. View creation runs in `database/event_listeners.py` on engine connect: views are dropped and recreated so their definitions stay in sync with the current schema.

### `v_experiment_additives_summary`

One row per experiment: concatenated chemical additives for reporting.

- **Purpose:** Power BI and reports can show “additives” as a single text column (e.g. “Mg(OH)₂ 5 g; Magnetite 1 g”) without joining through conditions and compounds.
- **Definition:** `chemical_additives` → `experimental_conditions` → `experiments`, joined to `compounds`; `GROUP BY e.experiment_id` with `GROUP_CONCAT(c.name || ' ' || amount || ' ' || unit, '; ')` as `additives_summary`.
- **Key column:** `experiment_id`, `additives_summary`.

### `v_experiment_additive_names_summary`

One row per experiment: compound names only, comma-separated and alphabetically sorted.

- **Purpose:** Power BI slicers and text-label columns that need only the additive names (not amounts/units). Avoids fragile string-parsing of `additives_summary` from `v_experiment_additives_summary`.
- **Definition:** `experiments` LEFT JOIN `experimental_conditions` → LEFT JOIN `chemical_additives` → LEFT JOIN `compounds`; `STRING_AGG(c.name, ', ' ORDER BY c.name)` grouped by `e.experiment_id`. `LEFT JOIN` chain ensures experiments with no additives still appear.
- **Key columns:** `experiment_id`, `additive_names` (NULL when experiment has no additives).

### `v_primary_experiment_results`

One row per **primary** result timepoint per experiment, with scalar and ICP data resolved by experiment + time bucket.

- **Purpose:** Dynamic Power BI dashboards can use this as the main fact table: one row per experiment per timepoint, with all key scalars and ICP elements in one place. No need to join `experimental_results`, `scalar_results`, and `icp_results` in the report.
- **Logic:**
  - **Base:** Rows from `experimental_results` where `is_primary_timepoint_result = 1`.
  - **Scalar/ICP resolution:** For each (experiment_fk, time_post_reaction_bucket_days), scalar and ICP rows are picked with `ROW_NUMBER() ... ORDER BY is_primary_timepoint_result DESC, id DESC` so the primary (or latest) result per bucket is chosen.
- **Columns (summary):**
  - Experiment and result: `experiment_id`, `experiment_fk`, `result_id`, `time_post_reaction_days`, `time_post_reaction_bucket_days`, `cumulative_time_post_reaction_days`, `result_description`, `result_created_at`.
  - Scalar: `scalar_result_id`, `gross_ammonium_concentration_mM`, `background_ammonium_concentration_mM`, `grams_per_ton_yield`, `final_ph`, `final_nitrate_concentration_mM`, `ferrous_iron_yield`, `final_dissolved_oxygen_mg_L`, `final_conductivity_mS_cm`, `final_alkalinity_mg_L`, `co2_partial_pressure_MPa`, `sampling_volume_mL`, `ammonium_quant_method`, `background_experiment_fk`, `scalar_measurement_date`.
  - H2: `h2_concentration`, `h2_concentration_unit`, `gas_sampling_volume_ml`, `gas_sampling_pressure_MPa`, `h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`.
  - ICP metadata: `icp_result_id`, `icp_dilution_factor`, `icp_raw_label`, `icp_measurement_date`, `icp_sample_date`, `icp_instrument_used`.
  - ICP elements (ppm): `icp_fe_ppm`, `icp_si_ppm`, `icp_ni_ppm`, … (all fixed ICP element columns with `icp_*_ppm` naming).

**Note on `v_results_scalar`:** its `cumulative_ferrous_iron_yield_h2_pct` running-sum window partitions by `e.experiment_id` (per-vial), not by `COALESCE(base_experiment_id, experiment_id)` — replicate siblings (e.g. `SERUM_001a/b/c`) each accumulate independently and do not sum across each other. A digit-suffixed derivation (e.g. `HPHT_001-2`) also no longer shares its running sum with its root; each `experiment_id` gets its own partition. **`-t<days>` caveat:** a single-timepoint `-t` vial (e.g. `SERUM_001a-t7`) has exactly one result row, so its per-experiment cumulative equals that one row — it never accumulates across sibling timepoints of the same base. Read time courses across `-t` vials at the base/rollup grain (`v_results_scalar_rollup`, grouped by `COALESCE(base_experiment_id, experiment_id)`), not from an individual `-t` vial's own cumulative column.

### `v_results_scalar_rollup`

One row per `(base_experiment_id, time_post_reaction_bucket_days)`: cross-replicate mean/median/std for a replicate set (or `n_replicates = 1` with `NULL` std for a single non-replicate experiment).

- **Purpose:** Power BI dashboards can show replicate-set statistics (e.g. mean +/- std NH₄⁺ across `SERUM_001a/b/c`) without an application-layer aggregation step.
- **Grouping key:** `COALESCE(e.base_experiment_id, e.experiment_id)`, matching the existing pattern in `v_results_scalar` and `v_experiment_additives_summary`.
- **Statistics:** `stddev_samp` (n-1); returns `NULL` for `n_replicates = 1`. Median via `percentile_cont(0.5) WITHIN GROUP`.
- **Scope:** gross/net ammonium, H2 (ppm, micromoles, grams/ton), ferrous iron yield (H2% and NH3%), grams/ton yield, final pH. No ICP element aggregation (permanently out of scope). H2 ppm (`mean_h2_ppm`/`sd_h2_ppm`, issue #90) averages `scalar_results.h2_concentration`, which is meaningful only because the unit is the invariant ppm (vol/vol) documented on `ScalarResults`.
- **Outlier filter (P4):** rows from experiments with `is_outlier = true` are excluded from all aggregates including `n_replicates` (`WHERE … AND NOT COALESCE(e.is_outlier, false)`). Flagged experiments stay present in every per-row view.
- **Columns:** `base_experiment_id`, `time_post_reaction_bucket_days`, `n_replicates`, `mean_gross_ammonium_mM`, `median_gross_ammonium_mM`, `sd_gross_ammonium_mM`, `mean_net_ammonium_mM`, `sd_net_ammonium_mM`, `mean_h2_ppm`, `sd_h2_ppm`, `mean_h2_micromoles`, `sd_h2_micromoles`, `mean_h2_grams_per_ton`, `sd_h2_grams_per_ton`, `mean_fe_yield_h2_pct`, `sd_fe_yield_h2_pct`, `mean_fe_yield_nh3_pct`, `sd_fe_yield_nh3_pct`, `mean_grams_per_ton_yield`, `sd_grams_per_ton_yield`, `mean_final_ph`.
- **Note:** the grouping key (`COALESCE(base_experiment_id, experiment_id)`) does not distinguish letter-suffixed replicates from ordinary sequential derivations — a base experiment with sequential re-runs (e.g. `HPHT_001`, `HPHT_001-2`) but no lettered replicates will still produce `n_replicates >= 2` here, since both share `base_experiment_id`. Only treat this view's stats as "replicate statistics" when you know the group in question is actually a lettered replicate set.
- **Parent inclusion (issue #83 — confirmed intended):** the group parent ("replicate 0") shares the grouping key with its lettered replicates (`COALESCE(base_experiment_id, experiment_id)` resolves to the same base for both), so a parent that has its own results is counted in the group mean/median/std exactly like a lettered member. To exclude a parent whose run should not count as a replicate, flag it `is_outlier` — there is deliberately no separate parent opt-out.
- **Hand-entered rows (issue #83):** `POST /api/results` (the Add Results modal) sets `time_post_reaction_bucket_days` from the resolved time via `normalize_timepoint`, and a data migration backfilled all pre-existing NULL-bucket rows — so UI-entered results aggregate per day here just like bulk-uploaded ones. When a new primary entry lands in a bucket that already has a primary row, the newest entry wins and the older row is demoted to non-primary.
- **Letter vs vial (issue #98):** this view's `n_replicates` counts experiment
  ROWS in the bucket, so a 2-letter × 2-timepoint set yields
  `n_replicates = 2` per day bucket (one vial per letter contributes to each
  bucket) — which happens to match the letter count. The group page's
  individual-replicate overlay draws one series per letter and excludes
  `is_outlier` vials, so the overlay and this view's mean agree on membership.
  **Known gap:** a *letterless* `-t` vial (`SERUM_001-t7`) is counted here but
  is absent from the group page's members table, which requires
  `replicate_label IS NOT NULL`. Tracked separately.

**Where views are created:** `database/event_listeners.py` runs `DROP VIEW IF EXISTS` then `CREATE VIEW` for each view in a `try` block on module import (using the shared `engine`). Failures are ignored so startup is not blocked if the DB is unavailable; views are also recreated in Alembic migrations when dependent tables change (e.g. new ICP columns), so the canonical definitions stay aligned with the schema documented here.
