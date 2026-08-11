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

## 2026-07-09 — `alembic/` is the sole migration history; `database/migrations/` removed

**Decision:** Deleted `database/migrations/` (a second, independently-scaffolded Alembic environment with 48 frozen files). `alembic/` at repo root — the one `alembic.ini`'s active `script_location` actually points to — is the only migration history.

**Why:** `database/migrations/` was added in the same initial commit as `alembic/` (2026-03-16) and never touched again; every subsequent migration (69 files, through 2026-06-16) landed only in `alembic/`. Nothing in the codebase imported or referenced `database/migrations`. It was dead scaffolding from an early duplicate `alembic init`, not a divergent second chain.

**Scope:** Do not create a second Alembic environment anywhere in this repo. All new migrations go in `alembic/versions/` via `alembic revision --autogenerate`.

## 2026-07-09 — Docker dev workflow deprecated; native venv + npm is the only supported local dev path

**Decision:** Local development runs natively (Python venv + `npm run dev`), matching production (Windows Service via NSSM, no Docker). `Dockerfile` / `docker-compose.yml` / `scripts/dev-entrypoint.sh` still exist in the repo but are no longer the documented or supported dev workflow; `README_DEV_SETUP.md` (the Docker Compose guide) was deleted.

**Why:** `docs/deployment/STARTUP_GUIDE.md` and `docs/deployment/PRODUCTION_DEPLOYMENT.md` — the actively-maintained deployment docs — describe only the native NSSM/venv path, and `README.md`'s Quick Start already dropped Docker. `docs/ENVIRONMENT.md` still claimed "Docker Compose is used for local development only," contradicting both.

**Scope:** Don't resurrect the Docker dev guide or point new contributors at `docker-compose up` without raising it with the user first — the lab-PC deployment model (single Windows host, NSSM services) is the one all setup docs should describe.

## 2026-07-09 — `auth/` module split: `user_management.py` is shared, `firebase_config.py` is legacy-only

**Decision:** `auth/user_management.py` (root) remains the single shared implementation of the Firestore `pending_users` approval queue and Firebase Auth user CRUD — used by both `backend/api/routers/auth.py` (`POST /api/auth/register`) and `scripts/manage_users.py` (admin CLI). `auth/firebase_config.py` (root, imports `streamlit`) is legacy-only, used solely by `legacy/streamlit_frontend/auth_components.py`. New backend code initializes Firebase Admin via `backend/auth/firebase_auth.py`, not `auth/firebase_config.py`.

**Why:** The React/FastAPI rewrite moved login itself to the Firebase Web SDK client-side and moved token verification to `backend/auth/firebase_auth.py`, but never touched the registration/approval plumbing — that logic was reused as-is from the Streamlit era. This left one module (`user_management.py`) genuinely live in both stacks and one (`firebase_config.py`) orphaned to the legacy stack only, which `.claude/rules/AUTH.md` didn't reflect until this pass.

**Scope:** Do not import `auth/firebase_config.py` from new backend or frontend code. If `role`/`approved` custom claims (set at approval time but not currently read anywhere) are wired into an access-control decision, update `.claude/rules/AUTH.md` to document where that check lives.

## 2026-07-20 — `reactor_change_requests` unique constraint widened to include `experiment_id`

**Decision:** `ReactorChangeRequest.__table_args__` unique constraint changed from `(reactor_label, sync_date)` to `(reactor_label, experiment_id, sync_date)` (constraint renamed `uq_change_request_reactor_experiment_date`, migration `ca5d57c6b272`). No backfill was performed for existing rows with a null `experiment_id` — Postgres/SQLite both treat `NULL` as distinct under a unique constraint, so those rows remain safe without one.

**Why:** Issue #63 made the modification date user-editable. Under the old 2-column constraint, saving a modification for a new experiment on a reactor for a date that the *previous* occupant of that reactor also logged an entry for would silently overwrite the outgoing experiment's row — the risk existed before this ticket but became much easier to trigger by accident once dates could be backdated. Confirmed with the user to ship the widening in this same pass rather than deferring.

**Consequence:** `backend/services/notion_sync/import_.py::run_import` targeted the old constraint by `index_elements=["reactor_label", "sync_date"]`; updated to target the new constraint by name (`uq_change_request_reactor_experiment_date`). Its dedup helper (`_is_text_unchanged`) still only looks at `reactor_label`, so if that importer ever runs again for a reactor with an unresolved (`None`) `experiment_id`, repeat syncs will no longer dedupe against each other on that column pair alone — rows with a null `experiment_id` never collide with each other under the widened constraint. Not fixed here since Notion sync is understood to be retired; flagging in case it's ever reactivated.

**Scope:** Any future write path to `reactor_change_requests` must use `uq_change_request_reactor_experiment_date` as the conflict target, not a bare `(reactor_label, sync_date)` column list.

## 2026-07-23 — `-0`/`-1` experiment ID suffixes reclassified as "group parent" spellings, not sequential derivations

**Decision:** Any experiment ID ending in `-0` or `-1` (with no treatment variant and no replicate letter) is now classified as an explicit spelling of "the group parent" — `base_experiment_id` set to the stem, `parent_experiment_fk` forced `NULL` — rather than an ordinary sequential derivation (which would otherwise auto-link `parent_experiment_fk` to the bare-stem base). This reclassification is system-wide (any `-0`/`-1` ID, not just ones with lettered replicate siblings) and lives in `database/lineage_utils.py::update_experiment_lineage`'s `is_parent_row` check and the mirrored logic in `database/event_listeners.py`'s `before_flush` listener.

**Why:** Issue #69 (replicate handling) needed a way to spell "the parent of a replicate set" other than the bare stem alone, since some existing/expected data conventions write the parent explicitly as `S-0` or `S-1`. Locked in the issue's own spec.

**Consequence (known gap, not fixed):** This only applies going forward, via the live `before_flush` listener, which processes only `session.new` (rows being newly inserted in the current flush). It does **not** retroactively reclassify any `-0`/`-1`-suffixed experiment already in the database before this change landed, and `database/data_migrations/establish_experiment_lineage_006.py` (the one-off historical backfill/repair script) was deliberately left with its original, pre-replicate classification logic — it still treats `-0`/`-1` as an ordinary sequential derivation. If any historical experiment ID ending in `-1` was genuinely used as "first re-run" (not a parent alias), it will not be automatically reclassified, and re-running the migration script would classify it differently than the live listener would for an equivalent new row. No data corruption results (both paths are internally consistent, just differently scoped), but the two classifications can now disagree for pre-existing data.

**Scope:** Before building P2's grouping UI or any reporting logic that assumes universal `-0`/`-1` = group-parent semantics, check case-by-case whether pre-existing `-0`/`-1` data actually matches the new convention. Documented in `.claude/rules/MODELS.md` under the `Experiment` model's Lineage Tracking section.

## 2026-07-24 — Canonical experiment ID parser; extract_lineage_info frozen as legacy shim; a-N links to the letter itself

**Decision:** `database/experiment_id_parser.py` is the single source of truth for the experiment ID grammar (`parse_lineage_fields`, 4-tuple) and base-stem classification (`classify_base_id`), with `parse_experiment_id_full` returning the complete parse. `database/lineage_utils.py::parse_experiment_id` delegates to it. `backend/services/experiment_validation.py::extract_lineage_info` is retained **verbatim as a frozen legacy shim** — not collapsed — because its algorithm diverges from the canonical grammar on inputs that locked code consumes: (1) it treats ANY trailing `-N` as a sequential number (`CF-015` → `("CF", 15)`; canonical: standalone), which `new_experiments.py`'s `find_parent_for_copy` and its `parsed.sequential_number` warning gate depend on for real Core Flood IDs; (2) the pre-existing combined `-N_Treatment` bug (sequential never extracted) pinned since P1. Both divergences are pinned by `TestLegacyLineageDivergencesPinned`. Additionally, P5's sanctioned parent wiring is interpreted as: any `-N` on a lettered replicate links to the lettered sibling itself (`SERUM_001a-3` → `SERUM_001a`, not `SERUM_001a-2`), and letter+sequential+treatment combos keep the pre-P5 group-parent link.

**Why:** Issue #70 P5 mandated collapsing the two parsers onto one implementation with no behavior change, but the two parsers demand contradictory outputs for identical inputs (both pinned by pre-existing tests), so a literal collapse is impossible. Per the task briefing's pre-authorized default, current behavior was pinned and documented rather than changed.

**Scope:** New code needing an ID parse must use `database/experiment_id_parser.py` (or the `lineage_utils` 4-tuple wrapper) — never `extract_lineage_info`, which exists only for its two legacy consumers. Changing `extract_lineage_info`'s behavior requires an explicit product decision covering `find_parent_for_copy` and the bulk-upload warning gate. `get_or_find_parent_experiment` remains frozen for the data-migration script's sake (decision 2026-07-23).

## 2026-07-28 — Bulk-rename path: flush before lineage recompute; self-parent is always dropped

**Decision:** Two invariants now hold on the New-Experiments bulk-upload rename path (issue #86, changed with explicit user sign-off since `backend/services/bulk_uploads/new_experiments.py` is a locked parser). (1) The rename branch flushes the new `experiment_id` **before** calling `update_experiment_lineage`, so the group-parent `SELECT` resolves against the new ID rather than the row's stale old ID. (2) `database/lineage_utils.py::update_experiment_lineage` now drops any self-resolved parent to `NULL` (logging a warning) in both the replicate and the sequential/treatment branches, so `parent_experiment_fk` can never equal the experiment's own `id`. Additionally, each experiments-sheet row runs inside a `db.begin_nested()` SAVEPOINT so a single failed row rolls back only itself.

**Why:** Under the production session (`SessionLocal`, `autoflush=False`), recomputing lineage from an unflushed rename made the loose normalize match resolve the row against itself when the old ID and the new replicate stem normalized alike (e.g. `X_cation_001` → `X_Cation_001a-t5`, both `xcation001`), producing a self-referential FK and `CircularDependencyError` at flush. Because the per-row handler never rolled back, that one failure left the session pending-rollback and every later row raised `PendingRollbackError`, failing the whole file and hiding the real cause. `autoflush=False` was deliberately **not** changed (out of scope) — turning it on would mask the bug and shift flush timing across the whole app.

**Consequence:** The chain-rename `UNIQUE`-constraint violation now surfaces at the earlier flush; the existing `except rename_error` handler still wraps it and its ordering-guidance warning text is unchanged. Savepoint scope is the experiments loop only; conditions/results/additives loops are unchanged (their skip/warning semantics were not touched). A row discarded by savepoint rollback is removed from `renamed_experiment_ids`.

**Scope:** Any future edit to the experiments-sheet loop in `new_experiments.py` must preserve both the flush-before-lineage ordering and the per-row savepoint. Documented in `docs/LOCKED_COMPONENTS.md` (parser footnote) and `.claude/rules/MODELS.md` (lineage section). Covered by `tests/services/bulk_uploads/test_new_experiments_rename_lineage.py`.

## 2026-07-28 — Dedicated `reporting_reader` role for direct SQL access, separate from the app's DB user and any Power BI credential

**Decision:** Direct psql/reporting access for the team goes through a new, purpose-built read-only PostgreSQL role (`reporting_reader`, proposed in `docs/PSQL_ACCESS.md` §12 as documentation + copy-pasteable SQL for Mat to run on the lab PC — not executed by any script or migration). It has `LOGIN`, `NOSUPERUSER`/`NOCREATEDB`/`NOCREATEROLE`, `CONNECT` on `experiments`, `USAGE` on `public`, `SELECT` on all tables and views (PostgreSQL's `GRANT ... ON ALL TABLES IN SCHEMA` already covers views, so one grant suffices), and `ALTER DEFAULT PRIVILEGES` so future tables/views need no re-grant. LAN-only reachability is via `pg_hba.conf` scoped to the lab subnet plus a Windows Firewall rule — never `0.0.0.0/0`.

**Why:** No dedicated read-only role existed anywhere in the repo; the only prior `GRANT` (`scripts/init-db.sql`) hands `experiments_user` (the app's own read-write user) ALL PRIVILEGES, and `docs/POWERBI_MODEL.md` never specified what credential Power BI itself uses. Giving researchers psql access through the app's write-capable user, or inventing per-person ad hoc grants, would have made the "read-only" guarantee unenforceable and each new user a bespoke grant to remember.

**Scope:** Any future direct-SQL consumer (Power BI, a BI tool, a new teammate) should be pointed at `reporting_reader` rather than a new role, unless a genuine need for different permissions arises — in which case treat it as a new decision, not a silent grant change on this role.

## 2026-07-29 — Free-text bulk-upload fields: truncate-with-warning at the parser layer, reject at the API layer

**Decision:** For `ChemicalAdditive.addition_method` (issue #96), and as a pattern for any future free-text field shared between a bulk-upload parser and a single-object API endpoint, the two layers now handle an over-length value differently on purpose: the bulk parsers (`new_experiments.py`, `experiment_additives.py`) truncate to `ADDITION_METHOD_MAX_LENGTH` and record a per-row warning/error so the row's quantitative data (amount/unit/compound) still persists, while the Pydantic API schemas (`ChemicalAdditiveUpsert`/`AdditiveUpdate`/`AdditiveCreate`) reject the same over-length value outright with a 422. The DB column itself (`Text`) enforces neither bound — `ADDITION_METHOD_MAX_LENGTH = 500`, defined once in `database/models/chemicals.py`, is the single source of truth both layers import.

**Why:** A bulk upload processes many rows in one pass; failing an entire row (or the whole batch) over one cosmetic field would reproduce exactly the all-or-nothing failure mode issue #96 was filed to fix. A single-object API call has no such batch to protect, and a clear validation error is more useful to a human filling out a form than a silently truncated value. Reusing the same constant for both keeps the two layers' bounds from drifting apart, even though their failure behavior deliberately differs.

**Consequence (accepted, not fixed):** `experiment_additives.py`'s truncation notice goes into its `errors` list per its existing per-row reporting convention; its only current caller (`legacy/streamlit_frontend/bulk_uploads.py`, retired) treats any non-empty `errors` as a full-batch rollback, so today a truncation notice from that file still discards an otherwise-successful legacy upload. Not changed — the return signature is locked by this same issue's plan, and the retired caller has zero live reachability (no FastAPI route wraps this service). A comment in `experiment_additives.py` above the truncation check records this for whoever eventually gives this service a live caller: treat `errors` non-fatally per-row (mirroring how `new_experiments.py`'s API layer already treats its separate `warnings` list), not as a blanket batch failure.

**Scope:** Any new free-text field shared between a bulk parser and an API schema should follow this same split (truncate-and-warn in the parser, reject in the schema) rather than picking one behavior for both layers. Migration precedent: widening a `String(N)` column that a reporting view selects directly requires dropping and recreating that view around the `ALTER COLUMN` (Postgres blocks retyping a column a view's `_RETURN` rule depends on) — see `alembic/versions/293d0ea59422_widen_addition_method_to_text.py`, following the same pattern as `a1f2c3d4e5b6`.

## 2026-07-29 — Replicate identity is the timepoint-stripped experiment ID; the list collapses by stem, the group page nests by letter

**Decision:** Rows that differ **only** by a trailing `-t<days>` token are one logical replicate and collapse into one row. The collapse key is the timepoint-stripped `experiment_id` — computed in SQL by `backend/services/replicate_collapse.py::timepoint_stem_expr` and in Python by reusing the canonical `split_timepoint_token` — and explicitly **not** `(base_experiment_id, replicate_label)`. Two grains now coexist on the same API surfaces and must not be conflated: `members`/`member_count`/`vial_count` are **per vial**, while `replicates`/`replicate_count`/`replicate_letters` are **per replicate letter**. The Experiments list collapses by *stem*; the group page nests by *letter*. New fields were added rather than existing ones redefined.

**Why:** `parse_lineage_fields("SERUM_001a-2")` returns `("SERUM_001", 2, None, "a")`, so a sequential re-run of a lettered replicate shares **both** base and letter with `SERUM_001a`, and there is no persisted derivation-number column to separate them. Keying on `(base, letter)` — the shape the issue originally proposed — would silently merge a distinct re-run into its replicate. Keying on the stem is a literal reading of "differs solely by timepoint" and additionally handles letterless `-t` vials with no special case. Adding fields rather than redefining `member_count` avoided changing the meaning of a shipped field while `members` still held vials.

**Consequence:** The stem key is duplicated three ways — the canonical Python regex (`database/experiment_id_parser.py`), the TypeScript mirror (`frontend/src/utils/experimentId.ts`), and the POSIX form for Postgres — guarded by `tests/services/test_replicate_collapse.py::test_sql_and_python_agree`. Separately, `_bucket_key_expr` (SQL) has a **hand-written Python mirror** in the grouped item loop of `backend/api/routers/experiments.py`; a divergence between that pair during implementation caused the branch's worst defect (a letterless `-t` vial hid its lettered siblings from the list response entirely, fixed in `a76659e`). Any future edit to either must change both. The list's bucket-membership predicate wraps `experiment_id` in `regexp_replace` inside a `CASE`, so it cannot use the `experiment_id`/`base_experiment_id` indexes — accepted at LAN/single-lab-PC scale, revisit if the table grows. The asymmetry in D12 means a group whose letter also has a sequential re-run shows a badge counting letters (`2 replicates: a, b`) that expands to three rows; the extra row is self-identifying by its `-2` suffix.

**Scope:** Any new surface presenting replicate groups must state which grain it uses. Inline status editing follows a related rule: the Experiments list offers the Status dropdown **iff the displayed label names the row that would be PATCHed** (`group_display_id === experiment_id`) — never gated on `vial_count`, which includes the parent and would silently strip the affordance from every parent-led group. Still open and tracked separately: a letterless `-t` vial (`SERUM_001-t7`) is counted in `v_results_scalar_rollup`'s `n_replicates` but absent from the group page's members table, because `_fetch_members` requires `replicate_label IS NOT NULL` — draft at `docs/working/issues/06-letterless-t-vial-group-membership.md`.

## 2026-07-29 — Experiment deletion: any approved researcher, hard delete, single-experiment only

**Decision:** Three product calls for issue #99, settled with the user before implementation:

1. **Any approved researcher may delete an experiment — no admin role gate.** The `role` custom claim stays unwired, per `.claude/rules/AUTH.md`.
2. **Hard delete, not soft delete.**
3. **Single-experiment delete only.** No "Delete selected" bulk action in this pass.

**Why:**

1. The issue exists to remove a single-person bottleneck (previously only Mat could delete an experiment). The controls that make an unrestricted delete safe are the server-side audit snapshot (`ModificationsLog`, `experiment_fk=NULL`, full old-values snapshot) and the UI's typed-exact-ID confirmation gate — not a role check.
2. Soft delete would not free the `experiment_id` string for reuse, which was the actual need behind the 2026-07-28 SERUM_Catalyst incident, and would require filtering every `v_*` reporting view in `database/event_listeners.py` plus every list/detail query for a soft-deleted flag.
3. Bulk "Delete selected" (reusing the existing selection `Set` in `ExperimentList.tsx:224`) would have handled the 69-row SERUM_Catalyst incident directly, but is deferred to a follow-up issue until single delete is proven in the lab.

**Supporting decision (partly superseded by the fix wave below — see the parenthetical):** All orphan prevention (deleting `xrd_phases` and, as of the fix wave, `elemental_analysis` children; NULLing `background_experiment_id`/`background_experiment_fk` and `parent_experiment_fk`; and — no longer NULLing, now purging, `reactor_change_requests` rows outright) lives in application code (`backend/services/experiment_deletion.py`), not in a migration normalizing FK `ondelete` clauses. Dev/test DBs are built via `Base.metadata.create_all` (which honors the model `ondelete` clauses); the lab PC came up through the Alembic chain, whose initial migration declared none — so constraint parity with production is unverified, and app-level handling is correct regardless of what the DB does underneath it.

**Whole-branch final review (2026-07-29, run on the most capable model over the full 12-commit branch) found two Critical defects in the implementation of decision 2 above:**

1. **Critical 1 — latent 500 on delete.** `ElementalAnalysis.external_analysis_id` is `nullable=False` (`database/models/characterization.py:25`) but its relationship is a bare backref with no cascade and no `passive_deletes` (`characterization.py:43`). On `db.delete(exp)` the ORM tried to NULL that child FK before the DB-level `ON DELETE CASCADE` could act, raising `psycopg2.errors.NotNullViolation` → HTTP 500, so the delete never succeeded. Reproduced empirically against `experiments_test`. Live exposure was zero (0 experiment-linked `external_analyses` in the dev DB), so it was latent — but it was exactly the unhandled-reference class the service claimed to have fully enumerated.
2. **Critical 2 — the dialog lied and skipped its own safeguard.** `experimental_conditions` is hard-deleted by the ORM cascade but was not one of the counted impact fields, so for an experiment with conditions and nothing else `total == 0`: the dialog rendered "No dependent records — nothing else is affected" and did not require the typed-ID confirmation, meaning one click destroyed a full conditions record (temperature, initial pH, rock mass, water volume, reactor number, pressures, `total_ferrous_iron_g`). 44 experiments in the dev DB were in exactly that state.

Two Important findings were also raised: the experiment's prior `ModificationsLog` history is destroyed by the `cascade="all, delete-orphan"` on `Experiment.modifications` (13,374 rows in the dev DB, up to 654 for a single experiment); and the deletion snapshot is not genuinely "restorable" as originally documented.

**Product owner decisions (2026-07-29), governing principle: "if we delete an experiment we might as well purge/delete all other related columns and rows" — deletion purges everything the experiment *owns*:**

4. `reactor_change_requests` rows are now **purged**, not unlinked (previously `experiment_id` was set to NULL and the row survived).
5. The experiment's prior audit history is **allowed to purge** with it — no code was added to preserve it.
6. The deletion-snapshot `ModificationsLog` row (written `experiment_fk=NULL`) **still survives** — it is the only trace a deletion occurred, and it is what justifies leaving the endpoint open to any approved researcher with no admin role gate (decision 1, above).
7. The snapshot's "restorable" claim was **corrected in wording** rather than the capture being extended: it is a record of what was deleted, not a restore point. Not recoverable from it: results/ICP/scalar values, result files, purged `xrd_phases` rows, external-analysis rows and files, note timestamps, the purged prior audit history, and lineage (`parent_experiment_fk` is a stale integer PK once nulled).
8. **A hard boundary was set and verified to hold:** "owns" stops at rows belonging to *this* experiment. A deletion never destroys another experiment's data — where another experiment's `scalar_results` cites this one as its ammonium background, the citation is cleared but the row and its `background_ammonium_concentration_mM` survive, and lettered replicate siblings survive with only `parent_experiment_fk` dropped. These two remain decouplings, not purges, unchanged from the initial pass.

**Why (fix wave):** The whole-branch review's premise was that the service's own claim — "all unhandled references have been enumerated" — was untested against two real gaps (a NOT NULL child FK, and a hard-deleted but uncounted field). The product owner's response generalized past patching just those two gaps: rather than leave a growing list of case-by-case exceptions, "owns" was defined once (rows belonging to this experiment) and applied uniformly, with the snapshot's guarantees corrected to match what it actually captures rather than expanding capture to match the original claim.

**Fix wave (single commit `83e40f1`) implemented all eight items above:** purge of `elemental_analysis` children (in the service, not a model change, since `database/models/` is locked); `conditions` added as a counted impact field threaded through five layers (service dataclass, its `total` property, `collect_delete_impact`, `DeleteImpactResponse`, `_impact_to_response`, the TypeScript `DeleteImpact` interface, and the modal's `IMPACT_ROWS`); the typed-ID gate widened to also fire when `background_for` or `replicate_children` is non-empty; purge of `reactor_change_requests`; eviction of ten per-experiment query caches via `removeQueries`; and the wording corrections. A scoped re-review confirmed all six work items addressed, the ownership boundary held, and no new breakage.

**Side benefit:** `change_requests` was already summed into the impact `total` (documented to the user as "rows destroyed"), but before the fix wave the service only nulled those rows rather than deleting them — so `total` had been overstating destruction. Purging (item 4) makes the count truthful.

**Scope:** Do not gate `DELETE /api/experiments/{experiment_id}` on `role`/`approved` claims without a fresh product decision and an update to `.claude/rules/AUTH.md`. Do not add a soft-delete flag to `Experiment` without revisiting every `v_*` view. A future bulk-delete endpoint should reuse `backend/services/experiment_deletion.py::delete_experiment` per-row rather than duplicating its orphan-handling logic. Any future "this experiment owns X" addition to the delete path should extend `scan_delete_impact`'s counted fields and the modal's `IMPACT_ROWS` together, per Critical 2 above — an owned row that is destroyed but not counted silently defeats the typed-ID gate. Two related but out-of-scope staleness gaps were found and left as follow-up tickets, not fixed here: `['replicate-group-detail', baseId]` (`GroupedResultsView.tsx:52`) is reached by neither the eviction loop nor `invalidateQueries(['replicate-group'])` (TanStack Query matches key elements exactly), and `AddResultModal.tsx:57` invalidates a key (`['results', id]`) no query uses (closed by #104, 2026-07-30). Manual verification in the running app has not been performed for any of this — automated test coverage only.

## 2026-07-29 — Evict per-experiment query caches AFTER navigating away, never before

**Decision:** any handler that deletes an entity and then leaves its detail page must navigate
first and perform the cache eviction/invalidation afterwards, deferred past the React commit
(`setTimeout(…, 0)`). See `onDeleted` in `frontend/src/pages/ExperimentDetail/index.tsx`.

**Why:** React Query refetches a query the moment it is removed or invalidated *if that query
still has an active observer*. The experiment detail page actively observes `['experiment', id]`,
`['conditions', id]` and `['replicate-group', id]` — all of which the delete handler evicts. Doing
the eviction while the page is mounted therefore triggers refetches of an experiment the server has
just deleted, producing a burst of `404`s (4 per delete, observed in the browser). Navigating first
unmounts the observers, so nothing is left to refetch. A microtask is not enough — it can run
before React commits the navigation — hence the macrotask.

**Scope:** applies to any future delete-then-redirect flow, including the deferred bulk-delete
follow-up. The eviction itself must stay `removeQueries`, not `invalidateQueries`, because a hard
delete frees the `experiment_id` string for reuse and a stale-but-present entry would render the
dead experiment's data (see the issue #99 entry above).

**Guard:** `DeleteExperiment.test.tsx` asserts the detail page is already unmounted at the moment
the first eviction runs. Note the 404 burst itself does NOT reproduce under jsdom, so the test
pins the ordering rather than the symptom — a symptom-based test here passes even without the fix.

## 2026-07-30 — A batch loop over a helper that commits per row must isolate each row with a SAVEPOINT, never `db.rollback()`

**Decision:** any service that iterates over a helper which commits internally must wrap each
iteration in `db.begin_nested()` and unwind failures with `savepoint.rollback()`. Never
`db.rollback()` in the per-row `except`. See the loop in
`backend/services/bulk_uploads/experiment_deletion_bulk.py::delete_experiments_from_file`,
which calls `experiment_deletion.delete_experiment_cascade` (that function commits) once per row.

**Why:** two independent reasons, and the naive version fails both.

1. *Correctness.* After a failed statement Postgres refuses every subsequent statement until the
   transaction is unwound, so something must unwind it — one bad row would otherwise poison the
   whole remaining batch. But `db.rollback()` unwinds to the start of the session's transaction,
   discarding every row the batch had already committed. A single unusable row would silently turn
   a 50-row cleanup into a no-op while still reporting the other 49 as deleted. The issue's own
   wording ("call `delete_experiment_cascade` inside a `try/except`") reads as sufficient and is
   not.
2. *Testability.* Under the test fixtures (`tests/api/conftest.py`,
   `tests/services/conftest.py`, `tests/services/bulk_uploads/conftest.py`) the Session joins an
   external transaction in `rollback_only` mode, so a session-wide `db.rollback()` erases seed data
   committed earlier in the same test — see the 2026-07-29 issue #99/#100 notes and
   `issue-log.md`. The "one row failed, the others still deleted" assertion is therefore
   *unwritable* against a `db.rollback()` implementation: the surviving rows come back as
   `missing` instead of `deleted`.

Probed before implementing, not assumed: `begin_nested()` → helper's own `commit()` releases the
savepoint and persists the row, leaves the outer transaction usable, and a later
`savepoint.rollback()` undoes only its own row. So one implementation is correct both in
production (no external transaction) and under the fixtures.

**Scope:** applies to the checkbox-driven bulk delete in `issue-bulk-delete-selected.md` and to any
future bulk wrapper around a committing single-item service. Guard `savepoint.rollback()` with
`if savepoint.is_active` — if the helper already committed, the savepoint is released and rolling
back would raise. Because the naive `db.rollback()` *reads* as the more careful choice, the reason
is stated in a comment at the call site and in the module docstring so it is not "fixed" back.

**Guard:** `tests/services/bulk_uploads/test_experiment_deletion_bulk.py::test_delete_isolates_a_failing_row_from_the_rest_of_the_batch`
patches the inner helper to raise for one specific ID and asserts the remaining rows still deleted.
That test fails against a `db.rollback()` implementation.

## 2026-07-30 — The lab PC deploy stops the service before pulling, and resets to HEAD (never origin/main)

**Decision:** `update.ps1` stops `ExperimentTracker` before any git operation and starts it
again on every exit path; it discards a dirty working tree with `git reset --hard HEAD` plus
`git clean -fd`; and it verifies `HEAD == origin/main` after the pull.

**Why each, and why the obvious alternative is wrong:**

- **Stop before pull.** On Windows a running Python process holding open handles can make a
  pull apply only partially, leaving files updated but the index unmoved — the state the lab
  PC was found in. The cost is that a failure now leaves the app OFFLINE rather than stale,
  so `Abort` itself calls `Start-TrackerService` and a failed start logs `CRITICAL` with the
  manual recovery command. Do not add an early `exit` that bypasses it.
- **Reset to `HEAD`, never `origin/main`.** This is the subtle one. `reset --hard origin/main`
  advances HEAD, so the script's own `git pull` becomes a no-op, `$headBefore -eq $headAfter`,
  the "no new commits" branch fires, and Step 6 never rebuilds the frontend. The deploy logs
  SUCCESS while serving a stale `frontend/dist` — which is indistinguishable, from the user's
  side, from the feature never having been written.
- **`clean -fd`, never `-fdx`.** `-x` deletes ignored files: `.venv` (holding the very
  `pip.exe`/`alembic.exe` the script invokes), `.env`, `frontend/.env.local`, `node_modules`,
  `frontend/dist`. None are in the repo.
- **Verify HEAD after pulling.** Silent partial success is the failure mode that let ten days
  of drift go unnoticed.

**Scope:** the lab PC checkout is a deploy target and must never hold local work. Nothing
should edit tracked files there, and no coding agent should be pointed at it with write
access. `.claude/settings.local.json` is now gitignored for exactly this reason — while
tracked it conflicted on pull in both the 2026-07-20 and 2026-07-30 incidents. Project-wide
Claude settings belong in the tracked `.claude/settings.json`.

**Guard:** `tests/deployment/test_update_script.py` asserts every property above, including
the two negative ones (`reset --hard origin/` and `clean -*x*` must not appear in executable
lines). Note these are static assertions plus a PowerShell parse — the script cannot be
executed under pytest, so **the first run after any change must be attended, on the lab PC**,
confirming `frontend:yes` in `updates.log` and that the service returns.

## 2026-07-30 — Reactor slot identity is a stored, derived column; occupancy keys on it, never on `reactor_number`

**Decision:** `experimental_conditions.reactor_slot` (`String(8)`, nullable, indexed) stores the
canonical physical slot label (`R01`, `CF02`). Every occupancy comparison and every label render
keys on that column. `reactor_number` stays, unchanged, for Power BI views, the
`?reactor_number=` list filter and the data-migration scripts — it is no longer an identity.

**Why:** a slot is a *pair* — series (HPHT vessel vs Core Flood rig) and number. `R01` and `CF01`
are different hardware sharing the number 1. The label was re-derived from
`(reactor_number, experiment_type)` at read time in three places, so every query asking "who is in
reactor N?" had to remember to also scope by series, and several didn't. A bulk status upload
setting a Core Flood to ONGOING on rig 1 would find the HPHT in `R01`, pass the date guard, and
mark that running experiment COMPLETED. Storing the pair collapses three predicate pairs to one
predicate and makes the mistake unavailable.

**Rejected:** a `reactor_series` enum (still a two-column key — the same forgettable mistake); and
offsetting CF numbering (`CF01` → 101), which makes `reactor_number` not mean what it says and
leaves the derivation logic in place.

**`NULL` means "holds no physical slot"** — a non-occupancy `experiment_type` (Serum / Autoclave /
Other), a missing `reactor_number`, or `reactor_number <= 0`. This is load-bearing, not a
convenience: an occupancy query filtered on `reactor_slot` cannot see a Serum vial *even if the
calling code forgot to check the type*. It makes the eligibility gate structural rather than
remembered. It also neutralises the eight phantom `R00` rows in production, which existed because
`0` is falsy in Python and slipped past `if conditions.reactor_number`.

**Maintained by a mapper-level listener, not by each write site.** `set_reactor_slot`
(`database/event_listeners.py`, `before_insert`/`before_update`) derives the value on every ORM
instance write, so both bulk-upload parsers, the conditions router, the conditions service and the
legacy Streamlit app stay correct without knowing the column exists. "Every path that writes
`reactor_number` must remember to also update the slot" is precisely the disease being treated.

**Its two documented blind spots.** The listener does not fire for (a) a bulk `Query.update()` /
Core `UPDATE` — precedent at `database/data_migrations/swap_reactor_4_7_015.py:96-109` — or (b) a
raw Core `INSERT`, which is how `scripts/migrate-sqlite-to-postgres.py` loads rows. (b) is the
sharper one: the documented "load a new `experiments.db`, then `alembic upgrade head`" workflow
leaves the column entirely NULL and the upgrade cannot repair it, because the DB is stamped at the
migration that would have backfilled it. Warned about in `database/CLAUDE.md`. A Postgres
**generated column** would close this class permanently and is the recommended eventual design;
it survives Core INSERTs, `Query.update()`, `psql` and future migrations alike.

**Autoclave is not occupancy-bearing** (2026-07-29). Only HPHT and Core Flood hold vessels, despite
`AUTO_JW_022`–`024` carrying historical HPHT vessel numbers — all COMPLETED, therefore inert. Revisit
only if the team confirms autoclave runs occupy the numbered vessels.

## 2026-07-30 — `PATCH /api/experiments/{id}/status` rejects a double-booking with 409; it never demotes

**Decision:** a transition to ONGOING is refused with 409 when another ONGOING experiment already
holds the target slot. The error names the slot, the occupant and its start date. The occupant is
left alone. Only the transition *to* ONGOING is gated; an experiment holding no slot is never
blocked; re-asserting ONGOING on a slot you already hold is not a self-collision.

**Why not demote:** this endpoint cannot distinguish "I am advancing a sequential re-run" from "I
picked the wrong reactor from a dropdown," and only one of those should close a colleague's running
experiment. The bulk-upload paths demote because a status *file* carries that intent explicitly;
a dropdown does not. `CF_018`, `-2` and `-3` were all simultaneously ONGOING in `CF01` in
production precisely because this handler previously had no check at all.

**Consequence accepted:** until a confirm-and-supersede dialog exists (deliberately deferred), the
researcher must complete the occupant manually first. The 409 is surfaced as a toast on both status
controls; before this branch, both mutations had no `onError` at all and swallowed it silently.

## 2026-07-30 — The one-ONGOING-per-slot trigger is deferred, and three things follow from that

**Decision:** issue #97 §4 — a PL/pgSQL trigger enforcing one ONGOING experiment per
`reactor_slot`, plus `CHECK (reactor_number IS NULL OR reactor_number > 0)` — is **not** in this
work. Tracked as GitHub **#112**, blocked on the data cleanup in
`audit-2026-07-28-results-and-cleanup.md`.

**Why:** both would fail against current data, and the lab PC runs `alembic upgrade head` nightly.
A migration that can fail there breaks the entire deploy pipeline until someone fixes it by hand on
that machine. Auto-completing experiments as a side effect of a schema change is also the exact bug
this work exists to prevent.

**Three consequences, each deliberate:**

1. **`newer_than` is still not passed** on `new_experiments.py`'s occupancy call sites. The issue
   asks for it, but its own rationale is "let the trigger be the backstop." With no trigger,
   failing open would leave real double-bookings behind nothing but a warning — strictly worse than
   demoting unconditionally. Pass it in the same change that adds the trigger, not before.
2. **The `seen_labels` dedup in `dashboard.py` stays.** The issue says delete it, but explicitly
   *after* the constraint is verified. It is also load-bearing for a reason the issue got backwards:
   `_occupancy` counts the *deduped* card list, so `ongoing` equals the number of distinct occupied
   slots and `empty` is **correct**. Removing the dedup would count experiments against a slot total
   and drive `empty` negative. What the dedup costs is that the *grid* shows one card per slot, so
   contention is invisible — not a wrong count.
3. **Nothing at the database level prevents a double-booking.** Every entry point is narrower, but
   none is closed. Prod had 4 genuinely contended slots on 2026-07-30.

---

## 2026-08-01 — Upload warnings must not assert stored state from a sheet-cell gate (issue #115)

**Decision:** a bulk-upload warning derived from a *spreadsheet cell* may describe only what the
sheet supplied. It must never tell the researcher what is or isn't in the database as a result.

**Why:** the #115 missing-`GC Run Date` warning got this wrong twice, in two different clauses,
and both were caught in review rather than by tests.

1. First wording: *"these rows are not counted there until the date is filled in."* The gate is
   `h2_ppm is not None and gc_run_date is None` — a fact about the cell. On the **non-overwrite**
   path a blank cell is stripped by the None-filter and the stored `gc_run_date` is **preserved**,
   so the row may well still be counted. Worse, the Results tab reads *stored* state, so it would
   render that date normally with no flag — the upload panel and the experiment page would tell the
   researcher opposite things about the same vial.
2. Replacement wording: *"(any date already recorded is left untouched)."* True on the
   non-overwrite path, **false on `Overwrite=TRUE`** — there the stripped blank makes the service's
   overwrite branch `setattr(gc_run_date, None)` and the stored date is wiped. The code comment
   scoped the claim correctly; only the user-facing string dropped the scoping.

**How to apply:** state what the sheet did ("this upload supplied no run date for it") and what a
downstream consumer's *rule* is ("the card counts entries falling in the last 7 workdays"). Do not
state what the row now holds. The parser cannot see it — each row carries its own `Overwrite` flag,
so any stored-state claim is at best true for a subset of the rows the warning names.

**Related:** the same asymmetry is why the KPI's rolling window makes the reported gap
unrecoverable — a warning that promises "fill it in and re-upload" would be advertising a remedy
the window cannot deliver. Both corrections shipped in `654c8d9`.

## 2026-08-05 — `experiment_fk` is the only identity of a conditions row; the `experiment_id` string is never a lookup key (issue #109 follow-up)

**Decision:** `experimental_conditions` has exactly one authoritative link to `Experiment` —
`experiment_fk`. The `experiment_id` String on that table is a denormalized display copy. No code
may resolve, join, or match a conditions row by it. `UNIQUE (experiment_fk)`
(`uq_conditions_experiment_fk`, Alembic `00063a5dd6a8`) now enforces the 1:1 that the codebase had
been assuming in four places and enforcing in none.

**Why:** no rename path kept that string current — 187 of 1013 production rows (18%) held a value
that was not their experiment's ID. `GET /api/conditions/by-experiment` resolved by it, so it
404'd for an experiment that *did* have conditions; the detail tab then rendered its "no
conditions" empty state, and `POST /api/conditions` — which had no existence check — inserted a
second row. That one duplicate 500'd the entire experiments list (`_build_list_item`), fanned out
the list join under a comment asserting it could not, duplicated the `experiment_id` key in
`v_experiments`/`v_experiment_conditions` so Power BI rejected the relationship, and raised inside
`delete_experiment_cascade` (`serialize_experiment_snapshot`), making the experiment undeletable
through both delete paths. The same string lookup in the additives endpoints was worse than a
crash: for the 12 rows whose string names a *different* experiment, `PUT` wrote the additive onto
that other experiment's conditions row.

**How to apply:** resolve conditions as `Experiment.experiment_id` → `ExperimentalConditions
.experiment_fk`. On a database that predates the constraint, read defensively —
`.order_by(ExperimentalConditions.id).scalars().first()`, never `scalar_one_or_none()`/`.one()` —
so a legacy duplicate degrades to "pick the oldest row" instead of a 500. Any new write path that
creates a conditions row must first check for an existing one and return 409, not rely on the
constraint to produce a 500. A test that deliberately needs a duplicate must wrap itself in
`tests/pre_constraint_conditions.py::without_conditions_unique(session)`; nine do.

**Related:** the constraint is added by a migration whose `upgrade()` refuses with a `RuntimeError`
rather than half-applying, so `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py
--apply` must run first — and because `update.ps1:228` runs `alembic upgrade head` unconditionally
and aborts on failure, that ordering is a deploy prerequisite, not a preference. Still open: bulk
rename (`new_experiments.py:543-575`) syncs notes and `modifications_log` but not this string, so
the backfill decays until that locked parser is fixed.

## 2026-08-07 — A duplicate guard must key on the same identity the lookup resolves through

**Decision:** The Master Results duplicate pre-pass keys on
`_id_match.normalize_id(experiment_id)` plus the normalized timepoint — never the raw ID
string. Any future guard that decides "are these two inputs the same record?" must key on
the same identity function the write path will resolve through, not on the spelling the
source happened to use.

**Why:** the guard keyed on the raw string while `fuzzy_find_experiment` resolves through
`normalize_id`, so two spellings differing only by case or zero padding
(`SERUM_cation_001c-t5` vs `SERUM_Cation_001c-t5`) produced two different keys, both passed
the guard, and both upserted onto the one experiment they resolve to. The later row
silently overwrote the earlier — no error, no warning, and no trace in the response. Three
such pairs were live in the team's v3 workbook. A guard keyed on a different identity than
the writer is not a weak guard; it is absent for exactly the inputs it exists to catch.

**How to apply:** when adding a collision check, find the function the write path uses to
resolve the record and key on its output. Where the two identities genuinely must differ,
say so in a comment and state what the gap admits. Note the converse this accepts here: two
genuinely different experiments whose IDs differ only by case or zero padding, each with its
own sheet row, are now both rejected. Measured 0 of 1009 dev-DB experiments share a
normalized key (2026-08-07), and a loud stop beats a silent overwrite — but the invariant to
re-check if that ever changes is `NORM = RAW + <known variant pairs>`, not the absolute
collision count, which moves whenever the live workbook grows.

**Related:** recorded as footnote ² of `docs/LOCKED_COMPONENTS.md`; the parser is locked and
was changed under explicit sign-off. `_id_match.normalize_id` itself is run-delimited for
the same class of reason — see the 2026-08-05 ID-conflation work.

## 2026-08-07 — A message describing what was stored is tallied after the store, not before

**Decision:** Counters behind any upload warning that asserts something about persisted data
are incremented in the write phase, after the row commits — not in the earlier phase where
the condition is first detected. `master_bulk_upload.py`'s `comparable_rows` /
`disagreement_rows` follow `h2_reading_rows` in this.

**Why:** the Duration-vs-`-t`-token tally was first written in Phase 1, at comparison time.
A row that disagreed *and* was then rejected — as a duplicate, or by a failing upsert — was
still counted and named in a warning reading "each reading was recorded at the day its ID
encodes", while that same row's own error said "No row for this vial-day was written". Two
messages in one response contradicting each other about one row is worse than either alone:
it makes a researcher distrust both. The overlap was not hypothetical — the workbook's
re-entry block both disagrees and duplicates.

**How to apply:** ask what tense the message is in. A warning about the *sheet* ("this
column disagrees with that one") may be tallied at detection. A warning about the *database*
("this reading was recorded at day N") must be tallied after the write, behind the same
`continue` and `except` paths that decide whether a row lands. When in doubt, write the
sentence out and check whether it is still true of a row that was rejected.

**Related:** found by the Task 3 code review as a plan-mandated finding; the plan had
specified the Phase-1 placement and the human overruled it. The warning's wording was
deliberately left unchanged — the fix was to make the count true, not the claim vaguer.

## 2026-08-10 - A detection-time tally must word its warning as a claim about the source, not the database

**Decision:** When a warning's counter is incremented in the parse phase, the sentence it
produces must assert something about the *input* (a label, a cell, a column), never about
what was persisted. If the sentence needs to assert persistence, the counter moves to the
write phase instead. The ICP-OES `Day`-vs-`-t` disagreement warning takes the first option:
it reports the label mismatch and points at `errors` for anything that failed to load.

**Why:** this is the 2026-08-07 decision applied to a second parser, and it caught a live
defect during the pre-merge pass. `icp_service.py`'s disagreement warning was written by
copying the wording of its post-write sibling in `master_bulk_upload.py` - "each reading was
recorded at the day its ID encodes". But the ICP tally lives in
`process_icp_dataframe_ex`, at parse time, and `bulk_create_icp_results` runs afterward and
can reject any of those rows. Measured on a real request: a label
`ZZZNOPE_999a-t5_Day12_21x` produced `errors: ["Sample 1: Experiment with ID
'ZZZNOPE_999a-t5' not found and could not be auto-created."]` alongside a warning claiming
its reading had been recorded. Nothing was written.

**How to apply:** copying a warning's wording between parsers is not safe, because the
wording encodes which phase the counter lives in. Before reusing a sentence, check where the
new tally is incremented relative to the write. Rewording to a source-level claim is
usually cheaper and more honest than restructuring the phase - and for ICP it is also more
useful, since the researcher's actual problem is the label, which is true whether or not the
row landed.

**Related:** `docs/working/decisions.md` 2026-08-07 (the original, `master_bulk_upload.py`);
footnote 3 property (f) in `docs/LOCKED_COMPONENTS.md`; pinned by
`tests/test_icp_handling.py::TestICPTimepointTokenPersistence::test_disagreement_warning_never_claims_a_rejected_row_was_written`.

## 2026-08-10 — A stored derived field is only correct if every write path recalculates it

**Decision:** the New Experiments bulk upload now records the primary key of every
`ExperimentalConditions` row it creates or mutates and recalculates them in ONE pass
before returning, rather than calling `recalculate()` inline at each of the three write
sites. The contract is recorded as footnote 4 in `docs/LOCKED_COMPONENTS.md`.

**Why:** `water_to_rock_ratio` and `total_ferrous_iron_g` are stored, not computed on
read. Every other write path already called `recalculate()`; this uploader called it only
for `ChemicalAdditive`. Because `calculate_ferrous_iron_yield_h2` returns None when
`total_ferrous_iron_g` is None, the omission silently removed BOTH Fe2+ yield percentages
from every scalar result under a bulk-created experiment - 845 of 1125 production
conditions rows, 157 affected scalar rows. Nothing failed, nothing logged; the numbers
were simply absent from Power BI.

**Why one deferred pass and not three inline calls:** the three write sites sit in three
different error contexts (a per-row `try`/`except` in the conditions loop, no handler at
all in the parent auto-copy pass, and a savepoint-wrapped body in the additives loop), so
inline calls would need three separate correctness arguments. A single pass after all
three sheets have finished mutating has one, runs against each row's FINAL state, and
recalculates a row reached by two sheets only once.

**Keyed on primary keys, not ORM instances,** because it deduplicates cheaply. Note the
two rationales that sound plausible and are FALSE: `db.expire_all()` runs *before* all
three record sites, and site 3's record is *outside* the additives savepoint - so neither
can invalidate a recorded handle. The `conditions is None` skip is defensive only.

**Each row gets its own SAVEPOINT.** A bare `try`/`except` around `recalculate()` is not
enough: a DBAPI error aborts the transaction, so the *next* iteration's `db.get()` raises
`PendingRollbackError` and escapes into the router's blanket handler, discarding an
upload that was otherwise fine. Worse, on a non-DB exception the half-applied mutations
stay dirty and get committed while the warning claims the row failed. `savepoint.commit()`
is RELEASE SAVEPOINT, which flushes and can itself raise, so that is contained too. This
is the same lesson as footnote 1 on this file and the additives loop.

**How to apply:** when you add a field that the calculation registry writes, enumerate
every path that mutates its parent row and confirm each one recalculates - the API
routers are easy to find, the bulk parsers are not. The cheap diagnostic for "did this
ever run here?" is a second derived field on the same row: if both are NULL where both
are computable, the recalculation never happened, and no amount of checking the inputs
will tell you that. Deploying the code does not repair existing rows; a backfill is a
separate, explicit step.

**Related:** `docs/issues/issue-bulk-upload-never-recalculates-conditions.md` (root
cause, production measurements, Lab PC runbook); footnote 4 in
`docs/LOCKED_COMPONENTS.md`; `docs/CALCULATIONS.md` (the full list of paths that
recalculate); pinned by
`tests/services/bulk_uploads/test_new_experiments_conditions_recalc.py`.


---

## 2026-08-11 â€” A vial-day is the write unit, not a spreadsheet row

**Decision:** the Master Results Dashboard's unit of work is the **vial-day**
(`normalize_id(experiment_id)`, exact normalized timepoint), not the sheet row. Several
rows may describe one vial-day and are merged field by field into one `ScalarResults`
write; only a field two rows fill with *different* values is a conflict, and that
vial-day is then rejected **whole**. Sign-off: Mat, 2026-08-11 (locked parser).

**Why:** gas is drawn and run on one date and the liquid/solid fraction is collected
later, so the two fractions legitimately arrive as two rows naming the same vial and
the same day. The previous rule â€” one row per vial-day, both rejected on collision â€”
was a correct reading of the v3 sheet's *intent* and a wrong reading of how the lab
actually records sampling. It silently wrote nothing for 72 of the workbook's rows.

**How to apply:** every Dashboard column belongs to exactly one merge class
(measurement / collection date / provenance / directive), declared as a module
frozenset, so adding a column forces an explicit choice rather than defaulting into
one. Classify on the RAW CELL, before `_resolve_h2`, so GC precedence and the #114
geometry rule run once over the merged view and cannot drift between paths.

**The lesson worth carrying, and it is not about merging:** the field-class sets encode
a claim about what a blank cell looks like in a real workbook, and that claim cannot be
validated by unit tests. Every `_merge_group` test passed while the merge was rejecting
35 legitimate vial-days, because the Excel template writes **0** into the gas
volume/pressure columns on a row that did no gas sampling â€” the same "0 means blank"
trap already known for pH and conductivity, in columns nobody had thought to check. It
surfaced only on the first run against the real file, where the count was 39 conflicts
against a spec that predicted 4. **A parser change whose correctness depends on what the
source file actually contains is not verified until it has been run against that file.**
The spec's habit of publishing a measured expected outcome (72 rows, 36 vial-days, four
named conflict groups) is what turned a silent 35-row data loss into a caught defect;
keep doing that.

Corollary, same session: 0 is not uniformly a blank. `H2 (ppm) = 0` is a real reading (a
GC that measured no hydrogen produced a result); `gas volume = 0` never happened. The
distinction is physical, not typographic, and belongs in a named constant with the
measurement behind it.

**Related:** footnote 5 in `docs/LOCKED_COMPONENTS.md`;
`docs/superpowers/specs/2026-08-11-master-results-row-merge-design.md`;
`docs/superpowers/plans/2026-08-11-master-results-row-merge.md` (Task 8 is the
real-workbook verification); pinned by the `_merge_group` tests in
`tests/services/bulk_uploads/test_master_bulk_upload.py`.

---

## 2026-08-11 â€” A truthy NaN is a data-integrity bug, not a formatting one

**Decision:** text read from a pandas DataFrame goes through `_parse_text()`, never
`str(cell or "").strip()`.

**Why:** `pandas` reads an empty Excel cell as `float('nan')`, which is **truthy**, so
the idiom yields the literal string `'nan'`. This is not cosmetic. It made the generated
`"Master upload â€” day N"` description unreachable, and via
`ExperimentalResults.sync_brine_flag` â€” a `@validates` hook that sets
`has_brine_modification` from `bool(value and str(value).strip())` â€” it flagged
timepoints as brine-modified that had no modification at all. 12 of the 141 flagged rows
in the 2026-08-10 production backup (8.5%) are false positives, on an indexed column
exposed in a reporting view and the Results tab.

**How to apply:** the danger is a truthiness test on a value that can be NaN. Check
`isinstance(val, float) and pd.isna(val)` first, as `_parse_float` already did â€” the
numeric helpers in this file were always NaN-safe; only the text reads were not. When a
string field feeds a `@validates` hook or a boolean flag, a garbage string does not stay
in its own column: it propagates. And a raw-SQL backfill does **not** fire `@validates`,
so any repair must set the derived flag explicitly.

**Related:** `database/data_migrations/fix_nan_text_fields_019.py` (dry-run first;
production runbook in `docs/working/issue-log.md`);
`database/data_migrations/zero_ph_conductivity_016.py` (same bug class, earlier
instance â€” an Excel template blank stored as a value).

---

## 2026-08-11 — A letterless `-t` vial is an instance of the stem, not a replicate

**Decision:** an experiment ID that is a bare stem plus a timepoint token
(`SERUM_pH_002-t1`, no `a`/`b`/`c`) denotes **one destructively-sampled instance of that
stem**. A set of them is a replicate group whose members are those vials, with
`replicate_count = 0` and `replicates = []`. Membership therefore no longer requires a
replicate letter (`backend/services/replicate_groups.py::_member_clause`).

**Why:** this was issue #101's blocking open question — parent, unlettered replicate, or
something else — and it had to be answered because issue #98's list-page collapsing had
already committed to treating these vials as one row. That row's only link was its
representative vial, and both `/groups/{base_id}` routes 404'd on a letterless set, so
there was no page anywhere that showed the other vials or the cross-timepoint rollup —
which `v_results_scalar_rollup` had been computing correctly all along, since it groups
on `COALESCE(base_experiment_id, experiment_id)` and never looked at the letter. The
collapsing and the group gate disagreed, and the researcher lost data visibility in the
gap: 13 stems in the dev DB, 8 with more than one vial.

**How to apply:** two consequences that are easy to get wrong.

1. **`replicate_count == 0` does not mean "empty group".** Read `member_count`. Any UI
   that says "N replicates" needs a vial-count branch, and any consumer treating a zero
   letter count as absence will silently hide real data.
2. **Per-bucket stats over such a set are a time course, not replicate statistics.** One
   vial per bucket means `n_vials = 1` and every `sd_*` NULL. Rendering `sd ?? 0` prints
   "± 0.0", which asserts a measured spread of zero on a single reading — show the mean
   alone, and draw no error bars and no individual overlay series (with one value per
   bucket the series is the mean line redrawn on itself).

Membership is keyed on the **timepoint-stripped `experiment_id`**, not on
`id_timepoint_days IS NOT NULL`: `SERUM_001-2-t0` (a vial of a sequential re-run) and
`SERUM_001_Desorption-t5` both carry the stem as their `base_experiment_id` and would
otherwise be adopted into the wrong group. Compare that expression by **equality**, never
`LIKE base_id || '-t%'` — `_` is a single-character LIKE wildcard, and stems here contain
underscores (`SERUM_pH_002`).

**Related:** issue #101, split from #98; `docs/working/issues/06-letterless-t-vial-group-membership.md`;
`.claude/rules/MODELS.md` (`id_timepoint_days`, `v_results_scalar_rollup`);
issue #105, whose stale-cache exposure this widened from two query consumers to four.
