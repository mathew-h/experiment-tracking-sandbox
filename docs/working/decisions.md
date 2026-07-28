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
