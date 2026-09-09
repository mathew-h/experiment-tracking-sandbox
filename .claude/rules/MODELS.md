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
  - `is_outlier` (Boolean, non-null, default `false`): flags a bad vial (leak, cracked septum). Flagged experiments are excluded from `v_results_scalar_rollup` aggregates **including `n_vials`**, but remain fully visible in all per-row views (`v_results_scalar`, `v_results_h2`, `v_results_icp`, `v_primary_experiment_results`) and on their own pages.
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
    Separate from the parser, `backend/services/bulk_uploads/_id_match.py::normalize_id`
    is the canonical **fuzzy match key** used to resolve a workbook's ID spelling
    against a stored one. It is run-delimited (alpha/digit runs, leading zeros
    stripped per digit run, joined with `_`) — deliberately *not* a plain
    strip-and-concatenate, which collapsed `SERUM_JW_010-2` onto `SERUM_JW_102`
    (13 real pairs). The finders return **all** matches; nothing resolves an
    ambiguous key. See `docs/issues/issue-fuzzy-experiment-id-conflation.md`.
  - `id_timepoint_days` (Float, nullable, indexed): day value parsed from a trailing `-t<days>` ID token (e.g. `SERUM_001a-t7` → 7.0; decimals allowed). NULL = not encoded. The ID is canonical for the vial's timepoint: result creation fills a blank time from it and rejects a conflicting one (guards in `create_scalar_result_ex` and `POST /api/results`; string-level checks in the scalar/master bulk parsers). Set by `update_experiment_lineage` via `split_timepoint_token`; the token is stripped before lineage grouping, so `SERUM_001a-t7` groups under base `SERUM_001` with `replicate_label = a` and rolls up per day bucket with no view changes. A letterless `-t` vial (`SERUM_001-t7`) stays a parent-like row (base = stem, parent NULL).
    - **A letterless `-t` vial is one destructively-sampled instance of the stem
      itself — not a replicate (issue #101, decided 2026-08-11).** `SERUM_pH_002-t1/-t3/-t7`
      is ONE experiment sampled three times, so the set forms a group whose
      members are those vials: `member_count = 3`, `replicate_count = 0`,
      `replicates = []`. `replicate_count == 0` therefore does NOT mean "empty
      group" anywhere — read `member_count`. The letter remains the scientific
      unit *when there is one* (issue #98); this only says a set can have vials
      and no letters, and that per-bucket stats over such a set are a **time
      course**, not replicate statistics (one vial per bucket → `n_vials = 1`,
      `sd` NULL). `backend/services/replicate_groups.py::_member_clause` is the
      single definition, keyed on the timepoint-stripped `experiment_id` (via
      `timepoint_stem_expr`) — NOT on `id_timepoint_days IS NOT NULL`, which
      would also adopt `SERUM_001-2-t0` and `SERUM_001_Desorption-t5`, both of
      which carry the stem as their `base_experiment_id`. A bare-stem row has no
      token, so it stays the `parent` and is never also a member.
    - **ICP-OES upload honors the token but REPORTS rather than rejects (2026-08-07).**
      `extract_sample_info_ex` (`backend/services/icp_service.py`) takes the day from
      the ID's `-t` token and emits one file-level warning when the label's `_Day<n>`
      disagrees — matching `master_bulk_upload.py:383` rather than
      `apply_id_timepoint`, because an ICP label is machine-written by the worklist
      and letting it veto the ID would reject a whole run's readings. A label may
      therefore omit `Day` entirely (`SERUM_Cation_005c-t5_21x`); one with neither a
      `-t` token nor a `Day`/`Time` token is skipped, counted in the response's
      `skipped`, and named in a warning. Note the token is **lowercase `-t` only**, so
      `-T5` and `_t5` land in that reported-skip bucket. See footnote ³ in
      `docs/LOCKED_COMPONENTS.md`.
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
Typed free text about an experiment, optionally scoped to one result row (issue #118).
- **Fields**: `experiment_id` (denormalized string, synced by `denormalized_ids.py`), `experiment_fk`, `note_text`, `note_type`, `result_id`, `created_by`, `needs_review`, `created_at`, `updated_at`.
- **`note_type`** (Postgres enum `note_type`, `NoteType` in `enums.py`, NOT NULL, default `observation`): `description` (the experiment's summary; at most one per experiment, never result-scoped), `modification` (what was done to the vial at a timepoint — the MOD badge; result-scoped), `observation` (free text; valid with or without a result — **deliberately scope-free, do not narrow it**), `result_note` (a remark about one measurement; result-scoped). Member name equals stored value, so raw SQL compares against the lowercase strings.
- **`result_id`** (nullable): scopes the note to one `experimental_results` row.
- **`created_by`** (nullable): Firebase email on API paths; a source tag on bulk paths (`master_bulk_upload`, `new_experiments`, `auto_create_treatment`, or the Timepoint Modifications call's `modified_by`).
- **`needs_review`** (NOT NULL, default false): set by the PR2 backfill on rows it could not place with certainty; the review queue is `WHERE needs_review`.
- **Enforced by the database, not app code:**
  - `uq_one_description_per_experiment` — partial unique index on `(experiment_fk) WHERE note_type = 'description'`.
  - `fk_note_result_same_experiment` — composite FK `(experiment_fk, result_id) → experimental_results (experiment_fk, id)`, `ON DELETE CASCADE`, backed by `uq_results_experiment_fk_id` on the results table. A result-scoped note can only name a result of its own experiment. `MATCH SIMPLE`, so a NULL `result_id` (every experiment-level note) is not checked — intended.
  - `ck_note_scope` — `description` ⇒ `result_id IS NULL`; `modification`/`result_note` ⇒ `result_id IS NOT NULL`; `observation` ⇒ either.
  - Indexes `ix_experiment_notes_result_id`, `ix_experiment_notes_scope (experiment_fk, note_type)`.
- **Relationships**: `experiment` (back-populates `Experiment.notes`); `result` (viewonly) ↔ `ExperimentalResults.notes` (viewonly, ordered by id). Viewonly because the DB cascade owns deletion and `experiment_fk` is shared with the composite FK.
- **Write paths go through `backend/services/notes.py`**, the single definition of the legacy → typed mapping: `add_note` (explicit type/scope — the New Experiments `initial_note` is written with it as `description`, since that column has always been what the app showed as the experiment description) and `sync_result_note` (mirrors a legacy result column into one note *slot* per `(result_id, note_type, created_by)` — re-upload updates in place, clearing the column deletes the note).
- **Dual-write (PR1 of #118, 2026-09-08).** Every legacy write path writes BOTH its old column and a typed note until PR4 drops the columns: `POST /api/results` (`description` → `observation`, `brine_modification_description` → `modification`), the Master Results Dashboard (`Description`/`Observation Note` → `observation`, `Modification`/`Modification Note` → `modification`), Timepoint Modifications (→ `modification`), New Experiments `initial_note` (→ `description`, always), and `POST /experiments/{id}/notes` (optional `note_type`, default `observation`, and `result_id`). `POST /api/results` no longer requires `description` (PR3); a blank gets a server-generated placeholder in the legacy column and no note.
- **Readers (PR3 of #118, 2026-09-09) all resolve the description as the note typed `description`.** `Experiment.description` is a read-only `hybrid_property` over the viewonly `description_note` relationship, with a SQL expression (correlated scalar subquery) the experiments list (`condition_note`, the `description` filter), the dashboard reactor cards and `v_experiments` all use — so the three cannot disagree. This is a **correctness fix**: the old `v_experiments` took the first note by `created_at` (the transaction timestamp, shared by every note a bulk upload wrote in one transaction) while the app took `min(id)`; on the 2026-09-04 production mirror the two disagreed on 16 experiments. `GET /api/experiments/{id}/results` returns `has_modification_note` (EXISTS over `modification` notes — computed in the router, deliberately **not** a calculation-engine field) and the result's `notes`; the legacy `has_brine_modification` left the response. `GET /api/experiments/notes/review` lists `needs_review` rows across experiments (filter `researcher`); `PATCH /experiments/{id}/notes/{note_id}` accepts `note_text`, `note_type` (scope rules → 422, second description → 409) and `needs_review` (`false` resolves a review-queue row). Backfill: `database/data_migrations/reclassify_notes_020.py` (PR2; rehearsed on the mirror 2026-09-09, review queue 1,242).
- **Blank `initial_note` bug fixed (was `docs/issues/issue-blank-initial-note-parses-to-nan.md`):** a blank cell parses to `None`, no `"nan"` note is inserted, and an `overwrite=TRUE` row clears existing notes only when it supplies replacement text — the deleted texts are snapshotted to `ModificationsLog` (`modified_table='experiment_notes'`, `old_values.note_texts`). The four historical `'nan'` notes are handled by the PR2 backfill (`needs_review`, never promoted).

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
  - `reactor_slot` (String(8), nullable, indexed): canonical physical slot label — `R01`–`R16` (HPHT vessels) or `CF01`–`CF03` (Core Flood rigs). **`NULL` means the experiment holds no physical slot**: a non-occupancy `experiment_type` (Serum / Autoclave / Other), a missing `reactor_number`, or `reactor_number <= 0`.
    - **Derived — never set it by hand.** `database/reactor_slot.py::derive_reactor_slot` is the only definition of the mapping; the `before_insert`/`before_update` listener `set_reactor_slot` in `database/event_listeners.py` writes it on every ORM write. A direct assignment is overwritten on the next flush.
    - **This is the key for every occupancy comparison** (issue #97). `reactor_number` alone conflates `R01` with `CF01` — two different vessels sharing the number 1 — which let a Core Flood going ONGOING silently set a running HPHT to COMPLETED. Sites now keyed on it: `experiment_status.py` (both occupant queries and the same-file conflict map), `new_experiments.py` (both occupancy call sites), `PATCH /api/experiments/{id}/status`, `dashboard.py` (reactor cards and `/reactor-status`), `notion_sync/import_.py`, `notion_sync/export.py`.
    - **Pre-flush caveat:** the listener runs *during* flush, so code that has just assigned a new `reactor_number` must call `derive_reactor_slot(...)` rather than read `.reactor_slot`. Production `SessionLocal` sets `autoflush=False`.
    - **Bulk-update caveat:** the listener does NOT fire for a bulk `Query.update()` / Core `UPDATE`, which compiles to SQL without per-row mapper events. `database/data_migrations/swap_reactor_4_7_015.py:96-109` is the existing precedent for that idiom (it predates this column, and the Task 2 backfill left the DB self-consistent). Any future script changing `reactor_number` or `experiment_type` that way must either avoid `Query.update()` for those columns or recompute `reactor_slot` explicitly in the same script. Every other write path in the codebase loads an ORM instance and mutates attributes, which does fire the listener.
    - `reactor_number` is retained unchanged — Power BI views, `database/data_migrations/swap_reactor_4_7_015.py` and the `GET /api/experiments?reactor_number=` filter all read it.
    - **Still not enforced:** nothing prevents two ONGOING experiments sharing a `reactor_slot`. The one-ONGOING-per-slot trigger and `CHECK (reactor_number > 0)` are tracked in `docs/issues/issue-reactor-occupancy-uniqueness-trigger.md`, blocked on the cleanup in `docs/issues/audit-2026-07-28-results-and-cleanup.md`. Until then the `seen_labels` dedup at `dashboard.py:126-140` means a double-booked slot renders as one card, so the *grid* does not show the contention — but `_occupancy()` (`dashboard.py:48-64`) counts that same deduped `reactor_cards` list, so `ongoing` equals the number of distinct occupied slots and `summary.reactors.empty` is **correct**, not one too high. This is why the dedup must stay until the uniqueness constraint lands: removing it would make `ongoing` count experiments against a slot total instead of distinct slots, driving `empty` negative on real double-booked data.
  - `experiment_type` (e.g., "Serum", "HPHT"), `particle_size`, `feedstock`.
  - `initial_conductivity_mS_cm`, `core_height_cm`, `core_width_cm`, `core_volume_cm3`.
  - `co2_partial_pressure_MPa`, `confining_pressure`, `pore_pressure`, `flow_rate`.
  - `initial_nitrate_concentration`, `initial_dissolved_oxygen`, `initial_alkalinity`.
- **Derived Fields**:
  - `water_to_rock_ratio` (hybrid/property: `formatted_additives` from chemical_additives).
  - `total_ferrous_iron_g` (Float, nullable): mass of ferrous iron (Fe²⁺) in grams, derived from rock characterization FeO wt% × `FE_IN_FEO_FRACTION` × `rock_mass_g`; see `docs/CALCULATIONS.md` for full formula. **Stored, so it is only correct if `recalculate()` ran after the row's last mutation** — and `calculate_ferrous_iron_yield_h2` returns NULL whenever it is NULL, taking `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` down with it. The New Experiments bulk upload did not recalculate conditions until 2026-08-10, so 845 of 1125 production conditions rows held NULL and 157 scalar rows had no Fe²⁺ %H₂ despite a computed `h2_micromoles`. **Production has not been backfilled yet** — that runs post-deploy per the runbook in the issue doc; only the dev DB is done. Two passes are needed, not one: `database/data_migrations/backfill_total_ferrous_iron_017.py` filters on `total_ferrous_iron_g IS NULL`, so it cannot reach the ~15 stale scalar rows whose conditions row already held a value — those need `recalculate_all_registry_012.py::_backfill_scalars`. And 845 is not the recoverable count: 77+ rows stay NULL for want of FeO data on the sample and only resolve when rock characterization is uploaded. A NULL `water_to_rock_ratio` on a row with positive rock mass and water volume is the diagnostic for "recalculate never ran here". See `docs/issues/issue-bulk-upload-never-recalculates-conditions.md`.
- **Relationships**: `chemical_additives` → One-to-Many with `ChemicalAdditive`.
- **Note**: Legacy fields like `catalyst`, `buffer_system`, `surfactant` are deprecated in favor of `ChemicalAdditive`.
- **Identity (issue #109 follow-up):** `experiment_fk` is the **only** authoritative
  link to `Experiment`; the `experiment_id` string on this table is a denormalized
  copy. Both rename paths keep it in sync as of 2026-08-05: `PATCH /api/experiments/{id}`
  and the bulk parser (`backend/services/bulk_uploads/new_experiments.py`) both
  call `backend/services/denormalized_ids.py::sync_denormalized_experiment_id`,
  which is the **single definition** of the five-table fan-out
  (`experimental_conditions`, `experiment_notes`, `modifications_log`,
  `external_analyses`, `xrd_phases`). Add a sixth table there, not at a call site.
  `xrd_phases` rows whose new `(experiment_id, time_post_reaction_days,
  mineral_name)` slot is already taken are **left stale and reported** rather
  than renamed — renaming into an occupied `uq_xrd_phase_experiment_time_mineral`
  slot would abort the whole rename with an `IntegrityError`.
  187 of 1013 rows were stale as of 2026-08-05 from the pre-fix bulk path and
  are corrected only by running
  `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py`.
  Never resolve a conditions row by this string — resolve through `experiment_fk`.
  - `UNIQUE (experiment_fk)` (`uq_conditions_experiment_fk`, Alembic revision
    `00063a5dd6a8`) enforces the 1:1 with `Experiment` that `_build_list_item`,
    `serialize_experiment_snapshot`, `v_experiments` and `v_experiment_conditions`
    all assume. Before it, one duplicate row 500'd the experiments list
    (`MultipleResultsFound`), duplicated the Power BI dimension key in the two
    views above, and made the owning experiment undeletable through either delete
    path. The migration's `upgrade()` refuses with a `RuntimeError` (listing the
    offending `experiment_fk`s) if any duplicate remains — the dedupe script above
    must be run with `--apply` first.
  - `POST /api/conditions` returns **409** when a row already exists for the
    submitted `experiment_fk`, with the existing row's id in the `detail` text.
  - `GET /api/conditions/by-experiment/{experiment_id}`, `_build_list_item`, and
    `serialize_experiment_snapshot` all select the **lowest-id** row rather than
    `scalar_one_or_none()`/`.one()`, so a database that predates the constraint
    degrades to "pick one row" instead of 500ing.
  - Full incident record, the production measurements, and the deploy sequence:
    `docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md`.

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
  - `description` (NOT NULL). **Legacy — retired by issue #118, dropped in PR4.** Rendered nowhere in the app and, since PR3, exposed to no view (`v_results_scalar.sampling_description` is gone). Optional at entry since PR3: researcher text is mirrored into an `observation` note on the result, a blank gets a code-generated placeholder (`Day N results`) that is never mirrored.
  - `brine_modification_description` / `has_brine_modification`: **legacy — retired by issue #118, dropped in PR4.** Mirrored into a `modification` note since PR1; since PR3 the MOD badge, the results API and `v_dim_timepoints.modification_note` all read the notes, not these columns.
  - `UNIQUE (experiment_fk, id)` (`uq_results_experiment_fk_id`): target of the notes composite FK; redundant with the PK on its own.
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
- **Fixed Columns**: `fe`, `si`, `ni`, `cu`, `mo`, `ca`, `zn`, `mn`, `cr`, `co`, `mg`, `al`, `sr`, `y`, `nb`, `sb`, `cs`, `ba`, `nd`, `gd`, `pt`, `rh`, `ir`, `pd`, `ru`, `os`, `tl`, `ag`, `ce`, `k`, `la`, `na`, `pb`, `sc`, `th`, `v`, `s` (Float, ppm).
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

### `v_experiments` — `description` (issue #118 PR3)

`description` is the note typed `'description'` (`WHERE n.note_type = 'description'`, at most one per experiment by the partial unique index). It replaced `ORDER BY n.created_at ASC LIMIT 1`, which was **wrong, not merely different**: `created_at` is the transaction timestamp, so every note a bulk upload inserted in one transaction shared it and the `LIMIT 1` was arbitrary. Recreated by Alembic `c4d8f1a2b6e7` and on API startup.

### `v_dim_timepoints` — `modification_note` (issue #118 PR3)

`brine_modification_description` was replaced by `modification_note`: the result's `'modification'` notes, `'; '`-joined in id order when more than one exists (an upload's mirror and a hand-written one can coexist under different `created_by`). NULL when none.

### `v_results_scalar` — `sampling_description` dropped (issue #118 PR3)

The legacy `experimental_results.description` column is no longer exposed anywhere; its researcher-written content lives in `v_notes` as `observation` rows scoped to the result.

### `v_notes` (issue #118 PR3)

One row per experiment note — Power BI's entry point for this domain. Columns: `note_id`, `experiment_id`, `result_id` (NULL for experiment-level notes), `note_type` (enum as text: `description` / `modification` / `observation` / `result_note`), `note_text`, `created_at`, `created_by`, `needs_review`. Join `experiment_id` to `v_experiments`, `result_id` to `v_dim_timepoints` / `v_results_*`. `WHERE needs_review` is the review queue left by the 020 backfill.

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

One row per `(base_experiment_id, time_post_reaction_bucket_days)`: cross-replicate mean/median/std for a replicate set (or `n_vials = 1` with `NULL` std for a single non-replicate experiment).

- **Purpose:** Power BI dashboards can show replicate-set statistics (e.g. mean +/- std NH₄⁺ across `SERUM_001a/b/c`) without an application-layer aggregation step.
- **Grouping key:** `COALESCE(e.base_experiment_id, e.experiment_id)`, matching the existing pattern in `v_results_scalar` and `v_experiment_additives_summary`.
- **Statistics:** `stddev_samp` (n-1); returns `NULL` for `n_vials = 1`. Median via `percentile_cont(0.5) WITHIN GROUP`.
- **Scope:** gross/net ammonium, H2 (ppm, micromoles, grams/ton), ferrous iron yield (H2% and NH3%), grams/ton yield, final pH. No ICP element aggregation (permanently out of scope). H2 ppm (`mean_h2_ppm`/`sd_h2_ppm`, issue #90) averages `scalar_results.h2_concentration`, which is meaningful only because the unit is the invariant ppm (vol/vol) documented on `ScalarResults`.
- **Outlier filter (P4):** rows from experiments with `is_outlier = true` are excluded from all aggregates including `n_vials` (`WHERE … AND NOT COALESCE(e.is_outlier, false)`). Flagged experiments stay present in every per-row view.
- **Counts (revised 2026-08-01):** the former single `n_replicates` column was `COUNT(sr.result_id)` over a LEFT JOIN — it counted scalar *rows*, read 0 for ICP-only timepoints (335 phantom groups in production) and over-counted a vial holding several primary rows; it was wrong in 457 of 1412 groups. Replaced by `n_vials` (distinct experiments), `n_replicate_letters` (distinct letters, 0 when unlettered) and `n_values` (rows behind the stats). The join to `scalar_results` is now **INNER**, so an ICP-only timepoint produces no row here at all. `n_replicate_letters >= 2` is the test for "this really is a lettered replicate set" — 1063 of 1077 production groups are unlettered. See `docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md`.
- **Columns:** `base_experiment_id`, `time_post_reaction_bucket_days`, `n_vials`, `n_replicate_letters`, `n_values`, `mean_gross_ammonium_mM`, `median_gross_ammonium_mM`, `sd_gross_ammonium_mM`, `mean_net_ammonium_mM`, `sd_net_ammonium_mM`, `mean_h2_ppm`, `sd_h2_ppm`, `mean_h2_micromoles`, `sd_h2_micromoles`, `mean_h2_grams_per_ton`, `sd_h2_grams_per_ton`, `mean_fe_yield_h2_pct`, `sd_fe_yield_h2_pct`, `mean_fe_yield_nh3_pct`, `sd_fe_yield_nh3_pct`, `mean_grams_per_ton_yield`, `sd_grams_per_ton_yield`, `mean_final_ph`.
- **Note:** the grouping key (`COALESCE(base_experiment_id, experiment_id)`) does not distinguish letter-suffixed replicates from ordinary sequential derivations — a base experiment with sequential re-runs (e.g. `HPHT_001`, `HPHT_001-2`) but no lettered replicates will still produce `n_vials >= 2` here, since both share `base_experiment_id`. **`n_replicate_letters` now answers this directly** (0 = unlettered sequential set), so it no longer needs checking case-by-case: only treat these stats as "replicate statistics" when `n_replicate_letters >= 2`.
- **Parent inclusion (issue #83 — confirmed intended):** the group parent ("replicate 0") shares the grouping key with its lettered replicates (`COALESCE(base_experiment_id, experiment_id)` resolves to the same base for both), so a parent that has its own results is counted in the group mean/median/std exactly like a lettered member. To exclude a parent whose run should not count as a replicate, flag it `is_outlier` — there is deliberately no separate parent opt-out.
- **Hand-entered rows (issue #83):** `POST /api/results` (the Add Results modal) sets `time_post_reaction_bucket_days` from the resolved time via `normalize_timepoint`, so UI-entered results aggregate per day here just like bulk-uploaded ones. When a new primary entry lands in a bucket that already has a primary row, the newest entry wins and the older row is demoted to non-primary.
- **NULL buckets are NOT all backfilled (corrected 2026-08-01).** This section previously claimed a data migration had backfilled every pre-existing NULL-bucket row. That is **false against production**: 807 of 1959 primary rows (41%) still have `time_post_reaction_bucket_days IS NULL`, all created 2026-02 or earlier. The write path was fixed — zero NULL-bucket primary rows have been created since 2026-03 — but the historical rows were never corrected. They collapse into one `(base, NULL)` group per set, averaging every timepoint together.
  - **The partial unique index is inert on them.** `uq_primary_result_per_experiment_bucket` is `UNIQUE (experiment_fk, time_post_reaction_bucket_days) WHERE is_primary_timepoint_result`, and Postgres treats NULLs as distinct by default — so it never fires on a NULL bucket. Result: 198 `(experiment, NULL)` pairs hold duplicate primary rows (397 excess), while **zero** duplicates exist on any real bucket. Tightening it needs `NULLS NOT DISTINCT` (PG15+) and is blocked on cleaning those duplicates first.
  - Full analysis, backfill sources and proposed fixes: `docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md`.
- **Letter vs vial (issue #98):** this view's `n_vials` counts experiment
  ROWS in the bucket, so a 2-letter × 2-timepoint set yields
  `n_vials = 2` per day bucket (one vial per letter contributes to each
  bucket) — which happens to match the letter count. The group page's
  individual-replicate overlay draws one series per letter and excludes
  `is_outlier` vials, so the overlay and this view's mean agree on membership.
  A *letterless* `-t` vial (`SERUM_001-t7`) is counted here **and** appears in
  the group page's members table as of issue #101 — the two agree. Such a set
  has `n_replicate_letters = 0` and one vial per bucket, so every `sd_*` is
  NULL; the group page renders the mean alone (no error bars, no "± 0.0") and
  draws no individual overlay series, because with one value per bucket the
  series would be the mean line redrawn on itself.

**Where views are created:** `database/event_listeners.py` runs `DROP VIEW IF EXISTS` then `CREATE VIEW` for each view in a `try` block on module import (using the shared `engine`). Failures are ignored so startup is not blocked if the DB is unavailable; views are also recreated in Alembic migrations when dependent tables change (e.g. new ICP columns), so the canonical definitions stay aligned with the schema documented here.
