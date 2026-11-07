---
paths:
  - "backend/services/experiment_deletion.py"
  - "backend/services/bulk_uploads/experiment_deletion_bulk.py"
  - "backend/api/routers/experiments.py"
  - "backend/api/routers/bulk_uploads.py"
  - "frontend/src/components/experiments/DeleteExperimentModal*"
  - "tests/**/*delet*"
  - "frontend/src/**/*elete*"
---

# Experiment Deletion

> Part of the schema reference split out of `.claude/rules/MODELS.md` (the index). Field lists live in the model files; this file keeps what the code cannot tell you.

Defined across `backend/services/experiment_deletion.py` (single) and `backend/services/bulk_uploads/experiment_deletion_bulk.py` (bulk). Model: `Experiment` in `database/models/experiments.py`.

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
    - The Notion-era reactor change-request rows an experiment once owned were
      **PURGED** by this service from 2026-07-29 until issue #122 PR-E E1
      (2026-10-06) removed the purge; E2 (Alembic `a7d3e9f1c2b4`, 2026-10-09)
      dropped the table itself after the production 021 run converted its rows
      (357 rows, 331 converted, 26 orphaned). That data now lives in
      `experiment_notes` (`note_type='modification'`, `event_date`,
      `created_by='migrate_change_requests_021'`) and is counted under `notes`;
      each converted row's original is in `modifications_log.old_values`
      (`modified_table='reactor_change_requests'`).
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
    `external_analyses`, `xrd_phases`; `total` is their sum. `change_requests`
    was dropped from this list in issue #122 PR-B (2026-09-24): reactor
    modifications are `experiment_notes` rows and already counted under
    `notes`, so a separate count would double-report them. The source table
    itself was dropped in PR-E E2 (2026-10-09); see the deletion-path bullet above.
    `conditions` (the `ExperimentalConditions` setup row — temperature, initial pH,
    rock mass, water volume, reactor number, pressures, `total_ferrous_iron_g`) is
    counted because the ORM cascade hard-deletes it: while it was uncounted, an
    experiment with conditions and nothing else (44 in the dev DB) reported
    `total == 0`, so the dialog said "nothing else is affected" and enabled Delete
    on a single click. Adding a counted field requires all five layers — the
    dataclass, its `total`, `collect_delete_impact`, `DeleteImpactResponse`,
    `_impact_to_response`, the TS `DeleteImpact` interface, and the modal's
    `IMPACT_ROWS` — or the dialog silently under-reports.

    **List fields (`background_for`, `h2_background_for`, `replicate_children`)** are
    decoupled references, not destroyed rows, so they stay out of `total`; the same
    five layers apply to them (dataclass field, `collect_delete_impact`,
    `DeleteImpactResponse`, `_impact_to_response`, TS `DeleteImpact`), plus the
    modal's typed-ID gate and notice instead of `IMPACT_ROWS`.
    `h2_background_for` (issue #144) is the list of sample group keys whose
    `h2_background_links` row resolves to the deleted experiment's group key
    (`background_base_id`) or `-t`-stripped stem (`background_stem_id`); it is
    filled by `h2_background.groups_using_background`. Link rows are **not**
    deleted (string-addressed, other vials may remain, no FK): if the background
    ends up with no H₂ data the group's net values go NULL and its page shows
    "background has no H₂ data". Deleting a *sample* group's experiments likewise
    leaves its own link row in place.

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
