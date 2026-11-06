# Serum Vial H₂ Background Subtraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Link a replicate group to an H₂ background (a whole group or one vial stem), and expose background-adjusted H₂ (µmol, g/t, Fe²⁺ → H₂ %) with propagated SD through two new views, four API routes and the group page.

**Architecture:** A string-keyed link table, `h2_background_links`. All net values are computed in two SQL views (`v_results_h2_bkg_adjusted` and `_rollup`), and nothing derived is stored, following the precedent of `v_core_flood_samples` (`docs/CALCULATIONS.md:200`). A small service module owns link resolution and the queries. Routers stay thin.

**Tech Stack:** PostgreSQL views, SQLAlchemy 2, Alembic, FastAPI and Pydantic v2, React 18, React Query, Recharts, vitest.

**Spec:** GitHub issue #144 (`gh issue view 144`), approved by Mat on 2026-11-06. Sign-off was also given for the new model, for write endpoints that don't call the calculation engine, and for leaving renames out of scope.

## Global Constraints

- No locked file changes: `database/models/` gains a **new file only**, there are no `enums.py` edits, nothing changes under `bulk_uploads/`, and the existing `alembic/versions/` files are untouched.
- Existing view SQL for `v_results_scalar_rollup`, `v_results_h2` and `v_results_scalar` must not change. The new views are appended **after** `v_results_h2` in `_VIEWS`.
- The `-t<days>` SQL pattern is interpolated from `backend.services.replicate_collapse.TIMEPOINT_TOKEN_SQL_PATTERN`. Never write a new copy of it. Python-side stripping uses `database.experiment_id_parser.split_timepoint_token`.
- H₂ molar mass is `2.01588` and Fe molar mass is `55.845`. The Fe factor is `3 × 55.845 / 1e6 / total_ferrous_iron_g × 100`.
- Nothing calls `recalculate()`.
- Never run two pytest processes at once, because they share `experiments_test`.
- Frontend: brand tokens only (`text-status-warning`), no hex values, no inline styles, and React Query for fetching.
- Commit format: `[#144] <imperative, <50 chars>`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use `git commit -F <scratchpad file>`.

## Review Focus

1. **The background vial is flagged outlier after the link is set.** The background n, mean and SD must drop that vial. If every background vial is an outlier, the net values go NULL. Covered in the Task 2 test `test_outlier_background_excluded`.
2. **The background exists but has no bucket that ever matches**, i.e. all its buckets are NULL. Net values are NULL and the page says "background has no H₂ data". Covered in the Task 2 test `test_background_all_null_buckets_gives_null_net` and in the Task 5 copy test.
3. **A link with a vial-mode stem that is itself a `-t` vial ID.** The server must store the stem, never `SERUM_009a-t7`. Covered in the Task 3 test `test_put_vial_mode_stores_stem`.
4. **A sample row with `h2_concentration` set but `h2_micromoles` NULL** (missing gas volume). It appears in the per-row view with NULL net values and never makes the rollup mean NaN. Covered in the Task 2 test `test_null_micromoles_row_null_net`.
5. **The link exists but the GET is made from a lettered experiment's page** (`GroupedResultsView` mounted on ExperimentDetail with a base ID). The net metrics appear there too, because they key on `baseExperimentId`, not the route. Covered in the Task 6 test `shows net metrics when a link exists`.

---

### Task 1: `H2BackgroundLink` model and additive migration

**Files:**
- Create: `database/models/backgrounds.py`
- Modify: `database/models/__init__.py` (import and add to `__all__`)
- Create: `alembic/versions/b7e2d9c4a1f6_h2_background_links.py`
- Test: `tests/models/test_h2_background_link_schema.py`

**Interfaces:**
- Produces: `database.models.H2BackgroundLink` with table `h2_background_links` and columns `id` (Integer PK), `base_experiment_id` (String, NOT NULL, UNIQUE), `background_base_id` (String, NULL), `background_stem_id` (String, NULL), `created_by` (String, NULL), `created_at` and `updated_at` (DateTime(tz), `server_default=func.now()`; `updated_at` also `onupdate=func.now()`).
- CHECK constraints, named exactly:
  - `ck_h2_background_links_one_ref`: `num_nonnulls(background_base_id, background_stem_id) = 1`
  - `ck_h2_background_links_not_self`: `background_base_id IS DISTINCT FROM base_experiment_id`
- Migration revision `b7e2d9c4a1f6`, with `down_revision = "a1c5e8f2b9d3"`. `upgrade()` creates the table. `downgrade()` runs `DROP VIEW IF EXISTS v_results_h2_bkg_adjusted_rollup` and then `DROP VIEW IF EXISTS v_results_h2_bkg_adjusted` **before** `op.drop_table`. The docstring explains why: `event_listeners.py` recreates the views at API import.

- [ ] **Step 1: Write the failing tests.** Model them on `tests/models/test_core_flood_permeability_schema.py`:
  - `test_revision_parent`: the down_revision is `a1c5e8f2b9d3`.
  - `test_single_head`.
  - `test_columns`: nullability as listed above.
  - `test_one_ref_check`: with the `db_session` fixture, inserting both refs NULL raises `IntegrityError`, and so does inserting both set.
  - `test_not_self_check`: `base_experiment_id='S1'` with `background_base_id='S1'` raises `IntegrityError`.
  - `test_unique_base`: a second row for the same base raises `IntegrityError`.
  - `test_downgrade_drops_views_first`: the downgrade source contains both `DROP VIEW IF EXISTS` lines, the rollup first, and both appear before `drop_table`. Check this with `inspect.getsource` index ordering.
- [ ] **Step 2:** Run `.venv/Scripts/pytest tests/models/test_h2_background_link_schema.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement the model, the `__init__` export and the migration.
- [ ] **Step 4:** Run the tests again. Expected: PASS. Then run `.venv/Scripts/pytest tests/models/ -q`. Expected: all pass, and only one head.
- [ ] **Step 5: Rehearse the migration on `experiments_test`.** Follow the memory note "Rehearsing migrations on experiments_test": `create_all` has already made the table, so drop it, `alembic stamp a1c5e8f2b9d3`, then `upgrade` → `downgrade -1` → `upgrade`, and restore the stamp afterwards. Record the outputs.
- [ ] **Step 6: Commit.** Message: `[#144] Add H2 background link model`.

### Task 2: Background-adjusted H₂ views

**Files:**
- Modify: `database/event_listeners.py`. Add a module-level import of `TIMEPOINT_TOKEN_SQL_PATTERN`, then insert two `_VIEWS` entries directly after `v_results_h2`.
- Test: `tests/api/test_h2_background_view.py`. Reuse the `reporting_views` fixture pattern from `tests/api/test_core_flood_view.py`.

**Interfaces:**
- Consumes: `h2_background_links` (Task 1).
- Produces: view `v_results_h2_bkg_adjusted`, with exactly these columns:
  - Identity and background: `result_id, experiment_id, experiment_fk, base_experiment_id, time_post_reaction_bucket_days, background_mode, background_ref, bkg_time_bucket_days, bkg_time_gap_days, bkg_n_values, bkg_mean_h2_ppm, bkg_mean_h2_micromoles, bkg_sd_h2_micromoles, h2_micromoles`
  - Net and uncertainty: `net_h2_micromoles_unclamped, net_h2_micromoles, u_bkg_h2_micromoles, net_h2_mass_ug, net_h2_grams_per_ton_unclamped, net_h2_grams_per_ton, u_bkg_h2_grams_per_ton, net_fe_yield_h2_pct_unclamped, net_fe_yield_h2_pct, u_bkg_fe_yield_h2_pct, below_background`
- Produces: view `v_results_h2_bkg_adjusted_rollup`, with exactly these columns: `base_experiment_id, time_post_reaction_bucket_days, n_values, bkg_time_bucket_days, bkg_time_gap_days, bkg_n_values, bkg_mean_h2_micromoles, bkg_sd_h2_micromoles, mean_net_h2_micromoles, sd_net_h2_micromoles, mean_net_h2_grams_per_ton, sd_net_h2_grams_per_ton, mean_net_fe_yield_h2_pct, sd_net_fe_yield_h2_pct, below_background`.

**SQL shape.** The spec fixes the math. These are the decisions it leaves open:
- **Per-row population:** primary results joined to `scalar_results` with `sr.h2_concentration IS NOT NULL`, which is the same filter as `v_results_h2`. Join to `h2_background_links l ON l.base_experiment_id = COALESCE(e.base_experiment_id, e.experiment_id)`. `LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id`. Outlier rows are included.
- **Background stats CTE:** keyed by `(l.base_experiment_id, bucket)`.
  - Experiments match on `(l.background_base_id IS NOT NULL AND COALESCE(e.base_experiment_id, e.experiment_id) = l.background_base_id) OR (l.background_stem_id IS NOT NULL AND regexp_replace(e.experiment_id, '{pattern}', '') = l.background_stem_id)`.
  - Filters: primary, `h2_micromoles IS NOT NULL`, bucket NOT NULL, `NOT COALESCE(e.is_outlier, false)`.
  - Outputs: `COUNT(*)`, `AVG(h2_concentration)`, `AVG(h2_micromoles)`, `stddev_samp(h2_micromoles)`.
- **Nearest bucket:** `LEFT JOIN LATERAL (SELECT … FROM bkg b WHERE b.sample_base = s.base AND s.bucket IS NOT NULL ORDER BY abs(b.bucket - s.bucket), b.bucket LIMIT 1) m ON true`.
- **Mode columns:** `background_mode = CASE WHEN l.background_base_id IS NOT NULL THEN 'group' ELSE 'vial' END` and `background_ref = COALESCE(l.background_base_id, l.background_stem_id)`.
- **Zero rock mass and zero Fe(II):** the g/t and Fe columns use `NULLIF(rock_mass_g, 0)` and `NULLIF(total_ferrous_iron_g, 0)`, matching Python's `> 0` guard.
- **Rollup source:** reads from the per-row view, joined to `experiments` on `experiment_fk`, `WHERE NOT COALESCE(e.is_outlier,false) AND time_post_reaction_bucket_days IS NOT NULL`, grouped by `(base_experiment_id, time_post_reaction_bucket_days)`.
  - Counts: `n_values = COUNT(net_h2_micromoles_unclamped)`.
  - Background columns: `MIN(...)`, since they are constant within a sample bucket.
  - `below_background = AVG(net_h2_micromoles_unclamped) < 0`.
  - SD columns use the spec formula: NULL when both terms are NULL.
- The pattern goes into the SQL through an f-string. Escape the braces in the regex: `{{` and `}}` are not needed for `-t[0-9]+(\.[0-9]+)?$`, but the backslash must reach Postgres intact, so check this with `test_stem_pattern_matches_python`.

- [ ] **Step 1: Write the failing tests.** Fixtures:
  - `_exp(db, exp_id, number, base=None, rock=1.0, fe=None, outlier=False)` creates an Experiment and its conditions.
  - `_h2(db, exp, bucket, umol, ppm=100.0)` creates a primary result and a ScalarResults row with `h2_concentration=ppm` and `h2_micromoles=umol` set directly. The calc engine is not used.
  - `_link(db, base, bg_base=None, stem=None)`.

  Tests (spec values exact):
  - `test_group_mode_t7`: sample a/b/c (10, 12, 14) against background (2, 3, 4) at bucket 7, rock 1.0. Per-row net is `[7, 9, 11]`. Rollup: `mean_net_h2_micromoles == approx(9.0)`, `sd_net_h2_micromoles == approx(5**0.5, abs=1e-3)`, `mean_net_h2_grams_per_ton == approx(18.143, abs=1e-3)`, `sd_net_h2_grams_per_ton == approx(2.01588*5**0.5, abs=1e-3)`.
  - `test_clamp`: sample 1, 2, 3 against background 2, 3, 4 (mean 3, sd 1). Rollup mean 0, SD `approx(1.414, abs=1e-3)`. Per-row net `[0, 0, 0]`, and `below_background` is `[True, True, False]`.
  - `test_nearest_match`: sample buckets 1, 3, 7 against background buckets 0, 7 give `bkg_time_bucket_days` `[0, 0, 7]` and gaps `[-1, -3, 0]`. `test_nearest_tie_goes_earlier`: sample 3 against background 2, 4 matches 2.
  - `test_vial_mode`: the stem `SERUM_009a` covers `SERUM_009a-t3` and `SERUM_009a-t7` and excludes `SERUM_009b`. With n=1 in a bucket, `bkg_sd_h2_micromoles is None`, and the rollup SD equals the sample `stddev_samp` alone.
  - `test_stem_pattern_matches_python`: for `SERUM_009a-t7.5`, `regexp_replace` via the view's stem gives the same result as `split_timepoint_token`'s stem.
  - `test_outlier_background_excluded` (Review Focus 1): the background mean, SD and n drop the outlier vial.
  - `test_background_all_null_buckets_gives_null_net` (Review Focus 2).
  - `test_null_bucket_sample_null_net`.
  - `test_null_micromoles_row_null_net` (Review Focus 4): the row is present and its net values are NULL, and the rollup mean comes only from the other rows.
  - `test_sql_python_agreement`: for rock 2.5 and Fe 0.8, `net_fe_yield_h2_pct == calculate_ferrous_iron_yield_h2(net_umol, 0.8)`, and `net_h2_grams_per_ton == 1e6 * (net_umol*2.01588/1e6) / 2.5`.
  - `test_unlinked_group_absent`: a group with no link has no rows.
  - `test_existing_views_untouched`: the `_VIEWS` SQL for `v_results_scalar`, `v_results_h2` and `v_results_scalar_rollup` matches the `develop` copies. Read the `develop` file with `subprocess.run(["git","show","develop:database/event_listeners.py"], capture_output=True, text=True)`, extract each view's text between `("<name>", """` and the closing `"""`, and compare the `_norm`'d text to `dict(_VIEWS)[name]`.
- [ ] **Step 2:** Run `.venv/Scripts/pytest tests/api/test_h2_background_view.py -v`. Expected: FAIL (the view doesn't exist).
- [ ] **Step 3:** Implement both views. Then check that `.venv/Scripts/python -c "import database, database.event_listeners"` imports cleanly, with no circular import.
- [ ] **Step 4:** Run the view tests. Expected: PASS. Then run `tests/api/test_core_flood_view.py tests/api/test_experiment_rollup.py tests/models/`. Expected: PASS, which confirms the parity chain is intact.
- [ ] **Step 5: Commit.** Message: `[#144] Add background-adjusted H2 views`.

### Task 3: Service and API routes

**Files:**
- Create: `backend/services/h2_background.py`
- Modify: `backend/api/schemas/experiments.py`
  - Add `H2BackgroundLinkResponse`, `H2BackgroundSetRequest` and `H2BackgroundRollupResponse`.
  - Add the field `h2_background: Optional[H2BackgroundLinkResponse] = None` to `ReplicateGroupDetailResponse`.
- Modify: `backend/api/routers/experiments.py`. Put three routes beside `/groups/{base_id}/rollup`, before any `/{experiment_id}` route, and populate `h2_background` in `get_replicate_group_detail`.
- Test: `tests/api/test_h2_background_link.py`. Extend `tests/api/test_replicate_group_detail.py`.

**Interfaces (`backend/services/h2_background.py`):**
- `group_key(exp: Experiment) -> str`: returns `exp.base_experiment_id or exp.experiment_id`.
- `get_link(db, base_id: str) -> H2BackgroundLink | None`
- `link_mode(link) -> Literal["group", "vial"]` and `link_ref(link) -> str`
- `set_link(db, base_id: str, experiment_id: str, mode: Literal["group","vial"], user_email: str) -> H2BackgroundLink`
  - Raises `LookupError` when the experiment is unknown.
  - Raises `ValueError(msg)` on self-reference, which is when `group_key(bg_exp) == base_id`, in either mode.
  - Raises `ValueError` when the background has no primary row with `h2_micromoles IS NOT NULL`, a non-null bucket and a non-outlier experiment.
  - In vial mode, the stem is `split_timepoint_token(experiment_id)`'s stem.
  - Upserts the link and adds one `ModificationsLog` row: `experiment_id=base_id`, `experiment_fk=None`, `modified_by=user_email`, `modification_type` is `create` or `update`, `modified_table='h2_background_links'`, `old_values` is `None` or `{mode, background_ref}`, and `new_values` is `{mode, background_ref}`. It does **not** commit.
- `clear_link(db, base_id: str, user_email: str) -> bool`: deletes the link and logs `delete`. Returns False if there was no link, in which case nothing is logged. It does not commit.
- `rollup_rows(db, base_id: str) -> list[Mapping]`: `SELECT * FROM v_results_h2_bkg_adjusted_rollup WHERE base_experiment_id = :b ORDER BY time_post_reaction_bucket_days`.
- `groups_using_background(db, exp: Experiment) -> list[str]`: sorted `base_experiment_id` values of links where `background_base_id = group_key(exp)` or `background_stem_id = stem(exp.experiment_id)`.

**Routes:** check the group's existence with `group_exists` first in every route.
- `PUT /groups/{base_id}/h2-background` takes an `H2BackgroundSetRequest{experiment_id: str, mode: Literal["group","vial"]}` and returns `H2BackgroundLinkResponse`. The router maps `LookupError` → 404 and `ValueError` → 422, then commits.
- `DELETE /groups/{base_id}/h2-background` returns 204. It is 404 only when the group is unknown.
- `GET /groups/{base_id}/h2-background/rollup` returns `list[H2BackgroundRollupResponse]`.
- `H2BackgroundLinkResponse` fields: `mode`, `background_ref`, `created_by: Optional[str]` and `updated_at: Optional[datetime]`.

- [ ] **Step 1: Write the failing tests.** Seed the data the way `test_replicate_group_detail.py` does. Note the memory rule "a router rollback wipes your seed": assert on state through the same session.
  - `test_put_group_mode_creates_link`: 200, `mode=='group'`, and `background_ref` is the background group key.
  - `test_put_vial_mode_stores_stem` (Review Focus 3): a PUT with `SERUM_009a-t7` stores `SERUM_009a`.
  - `test_put_self_reference_422`: a group-mode PUT on the group's own member gives 422, and a vial-mode PUT on a stem inside the group also gives 422.
  - `test_put_background_without_h2_422`.
  - `test_put_unknown_group_404` and `test_put_unknown_experiment_404`.
  - `test_second_put_replaces`: one row remains, with the new ref.
  - `test_put_and_delete_each_log_once`: count `ModificationsLog` rows where `modified_table='h2_background_links'`. The count goes 1 → 2 → 3 for put, put, delete.
  - `test_delete_204` and `test_delete_unknown_group_404`.
  - `test_rollup_endpoint_ordered`.
  - `test_group_detail_includes_h2_background`, added to `test_replicate_group_detail.py`: the field is None without a link and populated with one.
  - `test_put_does_not_recalculate`: patch `backend.services.calculations.registry.recalculate` and assert it was not called.
- [ ] **Step 2:** Run `.venv/Scripts/pytest tests/api/test_h2_background_link.py tests/api/test_replicate_group_detail.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement the service, schemas and routes.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5: Commit.** Message: `[#144] Add H2 background link endpoints`.

### Task 4: Delete-impact `h2_background_for`

**Files:**
- Modify: `backend/services/experiment_deletion.py`. Add the field `h2_background_for: list[str]` to `DeleteImpact`, excluded from `total`, and fill it with `groups_using_background`.
- Modify: `backend/api/schemas/experiments.py` (the delete-impact schema, `:330` area) and `backend/api/routers/experiments.py:1555` (pass-through).
- Modify: `frontend/src/api/experiments.ts` (`DeleteImpact.h2_background_for: string[]`) and `frontend/src/components/experiments/DeleteExperimentModal.tsx`. Add a line that mirrors `background_for`: "Used as the H₂ background for groups: …". Also include it in the `:80` "has decouplings" condition.
- Test: extend the existing delete-impact API test file. Find it with `grep -rl delete-impact tests/api`. Also extend `DeleteExperimentModal.test.tsx` and the `EMPTY_IMPACT` fixtures in the three frontend test files that build a `DeleteImpact`.

- [ ] **Step 1: Failing tests.**
  - API: deleting `SERUM_009a-t3` while a vial link points to `SERUM_009a` gives `h2_background_for == ['SERUM_010']`. A group link to `SERUM_009` gives the same for any member of that group. The link row still exists after the cascade delete.
  - Modal: renders the group list.
- [ ] **Step 2:** Run the tests and see them fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the backend file and `npx vitest run src/components/experiments src/api src/pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx`. Expected: PASS.
- [ ] **Step 5: Commit.** Message: `[#144] Show H2 background links in delete impact`.

### Task 5: Group page background row and modal

**Files:**
- Modify: `frontend/src/api/experiments.ts`. Add these types: `H2BackgroundLink {mode: 'group'|'vial'; background_ref: string; created_by: string|null; updated_at: string|null}`, `H2BackgroundRollup` (fields as in Task 2's rollup) and `ReplicateGroupDetail.h2_background: H2BackgroundLink | null`. Add these methods: `setGroupH2Background(baseId, {experiment_id, mode})`, `clearGroupH2Background(baseId)` and `getGroupH2BackgroundRollup(baseId)`, all with `encodeURIComponent`.
- Create: `frontend/src/pages/ReplicateGroup/H2BackgroundRow.tsx`. It exports `H2BackgroundRow({ baseId, link })` and contains the modal.
- Modify: `frontend/src/pages/ReplicateGroup/index.tsx`. Render `<H2BackgroundRow>` in the header only when `experimentType === 'Serum'`. Reword `READ_ONLY_NOTICE` to `'Replicates are edited individually; only the H₂ background is set here.'`
- Test: `frontend/src/pages/ReplicateGroup/__tests__/H2Background.test.tsx`

**Behavior:**
- **Row text:** "H₂ background:" followed by one of:
  - `"<ref> · whole group"` in group mode
  - `"<ref> · single vial"` in vial mode
  - `"None"`
- **Buttons:** **Set** when there's no link. **Change** and **Clear** when there is one.
- **Modal search:** an Input bound to `experimentsApi.list({ search, experiment_type: 'Serum' })` through React Query, enabled when the input has at least 2 characters. Picking a result shows radios:
  - "Whole group (<groupKey>, n vials)", where n is the count of search results sharing that key. If that is ambiguous, show just "Whole group (<groupKey>)".
  - "This vial only (<stem> and its -t vials)"
- **Stem in the UI:** use `frontend/src/utils/experimentId.ts`'s existing helper. Don't add a new regex.
- **Save:** a 422 shows the server's `detail` inside the modal. On success or clear, invalidate `['replicate-group-detail', baseId]`, `['group-rollup', baseId]` and `['group-h2-bkg-rollup', baseId]`.
- **Missing data:** when a link exists and the rollup has no row with non-null `bkg_n_values`, show "background has no H₂ data" in `text-status-warning`.

- [ ] **Step 1: Failing tests.**
  - Renders "None" and Set.
  - Renders "SERUM_009 · whole group" with Change and Clear.
  - Set flow: search, pick, then the group radio calls `setGroupH2Background('SERUM_010', {experiment_id:'SERUM_009a', mode:'group'})`.
  - Vial mode sends `mode:'vial'`.
  - A 422 detail is shown.
  - Clear calls `clearGroupH2Background`.
  - On the group page, a non-Serum `experiment_type` renders no Set button. Put this in `ReplicateGroupPage.test.tsx`.
  - "background has no H₂ data" copy (Review Focus 2).
- [ ] **Step 2:** Run `npx vitest run src/pages/ReplicateGroup`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `npx vitest run src/pages/ReplicateGroup src/api`. Expected: PASS. Then run `npx tsc --noEmit` and check for no new errors against the baseline of 3.
- [ ] **Step 5: Commit.** Message: `[#144] Add H2 background control to group page`.

### Task 6: Net metrics in `GroupedResultsView`

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx`
- Test: `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`. Find the existing file and extend it, or create it.

**Design:**
- `MetricDef` gains an optional `source: 'rollup' | 'bkg'`, which defaults to `'rollup'`.
- Three net metrics are appended only when `group?.h2_background`:
  - `net_h2_umol` with label "Net H₂ (µmol)"
  - `net_h2_gpt` with label "Net H₂ (g/t)"
  - `net_fe_h2` with label "Net Fe²⁺ → H₂ (%)"
- Their means and SDs are read from a `Map<bucket, H2BackgroundRollup>` built from `useQuery(['group-h2-bkg-rollup', baseExperimentId], getGroupH2BackgroundRollup, { enabled: !!group?.h2_background })`, and `individual` returns `null`, so no per-letter series is drawn.
- The default metric stays `h2_ppm`. If the link is cleared while a net metric is selected, fall back to `h2_ppm`.
- When a link exists, the table gains the columns "Net H₂ (µmol)", "Net H₂ (g/t)", "Net Fe²⁺ → H₂ (%)" and "Background":
  - When `bkg_time_gap_days !== 0`, the Background cell shows a `text-status-warning` chip reading `bkg day <bkg_time_bucket_days>`.
  - It shows `≤ bkg` when `below_background`.
  - It shows `background SD unavailable (n=1)` when `bkg_n_values === 1`.

- [ ] **Step 1: Failing tests.**
  - `shows net metrics when a link exists` (Review Focus 5): the options include the three labels, and the default is still "H₂ (ppm)".
  - Without a link, no net options appear and no bkg request is made.
  - The gap chip `bkg day 0` renders for a row with a gap of −3.
  - `≤ bkg` appears.
  - The n=1 note appears.
- [ ] **Step 2:** Run `npx vitest run src/pages/ExperimentDetail`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full `npx vitest run`, then `npx eslint src --ext .ts,.tsx` and `npm run build`. Expected: all pass, with type-check and lint errors equal to the baseline (3 / 5).
- [ ] **Step 5: Commit.** Message: `[#144] Show background-adjusted H2 in grouped view`.

### Task 7: Docs, data checks, full verification

**Files:** `docs/CALCULATIONS.md`, `docs/POWERBI_MODEL.md`, `docs/api/API_REFERENCE.md`, `.claude/rules/MODELS.md` (or the topic file it indexes), `docs/working/issue-log.md`.

- [ ] **Step 1: Docs.** Make every edit with the Edit tool so the sync hook copies it to `docs/project_context/`.
  - `docs/CALCULATIONS.md`: a "Background-adjusted H₂ (view columns)" section. Include the formulas, the rule that the mean is clamped and the SD is propagated from unclamped values, and the note that the average of the per-row clamped values can differ from the rollup mean.
  - `docs/POWERBI_MODEL.md`: both views, their relationships and the bucket filter note.
  - `docs/api/API_REFERENCE.md`: the four routes.
  - `.claude/rules/MODELS.md` or the indexed topic file: the table.
- [ ] **Step 2: Data checks.** Run the four checks from the issue's "Data checks" against the dev DB, read-only, following `docs/PSQL_ACCESS.md`. Note that the dev DB is the 2026-10-26 prod backup, not the 2026-11-06 one. Record the counts in the issue log.
- [ ] **Step 3: Full backend run.** Run `.venv/Scripts/pytest tests/services/ tests/regression/ tests/api/ tests/models/ tests/views/ tests/data_migrations/ -q` as one process. Expected: 0 failures, against the 1546 baseline from #143.
- [ ] **Step 4: Browser check.** Use Chrome DevTools on a real Serum group in the dev DB. Set a link, confirm the net columns and chips, then clear it, so the dev DB is left unchanged.
- [ ] **Step 5: Issue log and commit.** Add the issue-log entry, then commit with the message `[#144] Document H2 background views and API`.
