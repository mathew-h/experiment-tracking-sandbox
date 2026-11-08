# Plan: formal background flag on experiments (issue #152)

**Branch:** `feat/issue-152-is-background-flag`
**Related:** #151 (report that produces the confirmed background list), #144 (H₂ background subtraction)

## Decisions (Mat, 2026-11-08)

1. **Yields are kept.** No calculation-engine change. Backgrounds keep whatever their row computes but never enter *sample* means. Bad yields on "bg" vials with a rock mass are a data fix (#151 section B).
2. **Rollups exclude backgrounds only from mixed groups.** A group with any non-background member (outliers ignored) averages only its non-background vials. A group made only of backgrounds keeps its own rollup, so it stays visible and usable as a #144 background. The view grain is unchanged, and an `is_background_group` column is added at the end.
3. **Bulk upload gets an `is_background` column.** Mat signed off on the locked-parser change. Blank on create inherits from the derivation parent (`-N` / `_Text`) or is false; blank on overwrite leaves the value unchanged. true/false/yes/no/y/n/1/0 set it; anything else is a row error (the experiments sheet already has a per-row SAVEPOINT).

## Rules

- **Group membership** is `COALESCE(base_experiment_id, experiment_id)`, as everywhere else. "All background" means `bool_and(is_background)` over the group's non-outlier experiments, regardless of whether they have results.
- **#144 background set:** if the linked set (group or stem) contains any non-outlier flagged background, only those vials form the background mean. Otherwise all non-outlier vials do, which is today's behaviour, so unflagged data is unchanged. `_has_usable_background` mirrors this.
- **#144 sample side:** per-row `v_results_h2_bkg_adjusted` keeps every row, as per-row views do for outliers. `v_results_h2_bkg_adjusted_rollup` applies the mixed-group rule.
- **Inheritance:** `create_replicate_experiments` copies the parent's flag. The New Experiment wizard copies it when copying from an experiment. Lineage children created by upload inherit as above.
- **Audit:** PATCH writes a `ModificationsLog` row when the value changes, like `is_outlier`.

## Tasks

1. **Model and migration.**
   - `Experiment.is_background` (Boolean, NOT NULL, default/server default false).
   - Migration `<rev>_add_is_background_to_experiments` (parent `d8a3f5c1e7b2`): add the column. Then drop and recreate `v_experiments` (+ `is_background`), `v_results_scalar_rollup`, `v_results_h2_bkg_adjusted` and `v_results_h2_bkg_adjusted_rollup` with the new SQL. Downgrade restores the old SQL before dropping the column.
   - `_VIEWS` updated. `_OLD`/`_NEW` strings generated from the before/after `_VIEWS` text so they can't drift.
   - Tests: column, parity of each `_NEW` with startup, `_OLD` with the pre-change text, upgrade/downgrade SQL order. Repin `d8a3f5c1e7b2`'s single-head test.
   - Rehearse on `experiments_test`.
2. **View tests** (`tests/views/`, `tests/api/test_h2_background_view.py`): mixed group excludes backgrounds; all-background group keeps its row with `is_background_group = true`; outlier-only interplay; #144 background set prefers flagged vials and falls back to all when none are flagged. Red-check by removing the rule.
3. **API.**
   - Schemas: `is_background` on Create, Update (non-null validator), ListItem, Response, ReplicateGroupMember; `is_background_group` on the rollup row.
   - Router: create; PATCH with audit; `is_background` list filter; list item population.
   - `lineage_utils.create_replicate_experiments` inheritance; `h2_background._has_usable_background` mirror.
   - Tests in `tests/api/`.
4. **Bulk upload.** Parser cell parsing (create, inherit, overwrite diff, row error), template header and INSTRUCTIONS note, tests in `tests/services/bulk_uploads/`.
5. **Frontend.**
   - Types.
   - Experiment Details: "Mark as background" toggle and badge.
   - Wizard checkbox (Step 1) and copy-from.
   - Experiments list: filter and badge.
   - Replicate group page: badge.
   - `GroupedResultsView` overlay applies the mixed-group rule.
   - #144 `H2BackgroundRow` lists flagged backgrounds first with a badge.
   - vitest for each.
6. **Backfill script** `database/data_migrations/set_background_flags_023.py`: reads a file of experiment IDs (one per line or a CSV `experiment_id` column). Dry run by default prints changes; `--apply` writes them with audit rows. Unknown IDs are reported and never fatal. Tests. **Not run** until #151 is answered.
7. **Docs:** `.claude/rules/MODELS*.md` (experiments, views), `docs/POWERBI_MODEL.md`, `docs/CALCULATIONS.md` (rollup membership), `docs/api/API_REFERENCE.md`, `docs/user_guide/BULK_UPLOADS.md`, `docs/user_guide/REPLICATES.md` / `USER_MANUAL.md`.

## Verification

pytest (one process, `.venv`): `tests/services/ tests/regression/ tests/api/ tests/models/ tests/views/ tests/data_migrations/`. vitest full; eslint/tsc at baseline (5 / 3); build. Migration rehearsal on `experiments_test`. Dev DB upgrade. Browser check: toggle a throwaway experiment, check the grouped Results tab and the #144 picker, then delete it.

## Deploy

`alembic upgrade head` on the lab PC (the nightly `update.ps1` does it before the API restarts), then a Power BI refresh for `v_experiments.is_background` and `v_results_scalar_rollup.is_background_group`. Backfill after #151.
