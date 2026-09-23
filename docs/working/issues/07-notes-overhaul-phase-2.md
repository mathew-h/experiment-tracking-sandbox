# 07 — Notes overhaul, phase 2 (issue #122)

Saved 2026-09-23 from Mat Hearl's session prompt. This is the working spec for
PR-A (`feat/notes-review-queue`), PR-B (`feat/reactor-mods-as-notes`),
PR-C (`feat/notes-timeline`) and PR-D (`chore/drop-legacy-note-columns`).

Pre-authorizations given 2026-09-23 (Mat, in-session): (1) `event_date` column
+ relaxed `ck_note_scope` on `experiment_notes`; (2) edits to the locked parsers
`scalar_results.py`, `quick_upload.py`, `long_format.py`, `master_bulk_upload.py`
(fallback removal), `icp_service.py`; (3) the three non-additive column drops on
`experimental_results` in PR-D. Still gated regardless: the 021 `--apply` waits
for Mat's audit of the dry-run report, and PR-D does not open until the
production review queue reads 0.

PR-A design calls made in-session (approved 2026-09-23): bulk calls are atomic;
`order` has a `desc` flag; select-all-in-filter means the loaded set (page limit
500 = bulk cap); the nav badge reuses `GET /notes/review?limit=1`.

Where the paste of the original prompt was cut mid-line, the line has been
restored from context; nothing else was changed.

---

Run `/start-task` first. Mode: `issue`. Open a new GitHub issue titled
"Notes overhaul phase 2: review-queue tooling, reactor modifications as notes,
unified notes timeline, legacy column drop" and use its number for commits.
Branch every PR from `develop` per docs/GIT_WORKFLOW.md; stack later PRs on
earlier ones only when they depend on them, and say so in the PR body.

# Task: notes overhaul, phase 2

## Where phase 1 (#118) left things — read before writing anything

Merged to develop and deployed to the lab PC on 2026-09-23 (main `db85cf4`):

- `experiment_notes` carries `note_type` (`description | modification |
  observation | result_note`), `result_id`, `created_by`, `needs_review`, with
  the partial unique index, composite FK and scope CHECK enforced by Postgres.
  `.claude/rules/MODELS.md` → `ExperimentNotes` is the reference.
- `Experiment.description` is a read-only hybrid over the `description` note;
  the experiments list, dashboard and `v_experiments` share its SQL expression.
- `backend/services/notes.py` is the single write path (`add_note`,
  `sync_result_note`). Five legacy paths dual-write: `POST /api/results`,
  `POST /experiments/{id}/notes`, `master_bulk_upload.py`,
  `timepoint_modifications.py`, `new_experiments.py`.
- `reclassify_notes_020.py --apply` ran on production: 1,432 descriptions,
  151 modification notes, **review queue 1,288** (`needs_review = true`).
  38 experiments end with no description because their only note was `'nan'`.
- Readers switched: `GET /experiments/{id}/results` returns
  `has_modification_note` + per-result `notes`; `GET /experiments/notes/review`
  (paginated, `researcher` filter); `PATCH notes/{id}` accepts `note_text`,
  `note_type`, `needs_review`. Views: `v_experiments.description`,
  `v_dim_timepoints.modification_note`, `v_notes`; `v_results_scalar` lost
  `sampling_description`. Report: `docs/issues/reclassify-notes-020-dryrun-2026-09-08.md`.
- Decision record: `docs/working/decisions.md` 2026-09-23 entry. Plan:
  `docs/superpowers/plans/2026-09-08-typed-notes-pr1-pr2.md`.

Still legacy, still dual-written, still in the schema:
`experimental_results.description` (NOT NULL), `brine_modification_description`,
`has_brine_modification` (+ the `sync_brine_flag` validator in
`database/models/results.py`).

Not covered by phase 1 at all:
- `reactor_change_requests` (`database/models/notion_sync.py::ReactorChangeRequest`:
  `reactor_label`, `experiment_id` string, `requested_change`, `sync_date`,
  `notion_status`, `carried_forward`, `notion_page_id`). Consumers:
  `backend/api/routers/experiments.py` (three `/change-requests` routes),
  `backend/api/routers/dashboard.py:170-180` (`todays_modification` on reactor
  cards), `backend/services/experiment_deletion.py` (`change_requests` impact
  count + purge), `backend/api/main.py` (Notion scheduler), `notion_sync/import_.py`,
  `frontend/src/pages/ExperimentDetail/ChangeRequestsTab.tsx` (the "Reactor
  Modifications" tab), `frontend/src/api/experiments.ts`,
  `frontend/src/components/experiments/DeleteExperimentModal.tsx` (`IMPACT_ROWS`).
- Legacy `description` writers outside the five paths:
  `backend/services/bulk_uploads/scalar_results.py:129,320`,
  `backend/services/bulk_uploads/quick_upload.py:289-344`,
  `backend/services/bulk_uploads/long_format.py:284`, plus the code-generated
  fallbacks in `scalar_results_service.py::_find_or_create_experimental_result`,
  `result_merge_utils.create_experimental_result_row`, `master_bulk_upload.py`
  (`Master upload — day N`) and `icp_service.py:650`, which seeds a new treatment
  experiment's *description note* with `"Auto-created from ICP upload"`.

Issue #117 (remove the Notion sync integration) is OPEN and owns the removal of
`backend/services/notion_sync/`, the scheduler in `main.py`, and the
`reactor_change_requests` table. Coordinate; do not duplicate.

## Pre-authorization (Mat Hearl to confirm before the session starts)

`.claude/CLAUDE.md` §7 triggers this phase hits — confirm each explicitly or the
session stops at that point:

1. Schema change on `experiment_notes` (`event_date`, relaxed `ck_note_scope`)
   and on `experimental_results` (three column drops) — two models, and PR-D's
   migration is not additive.
2. Edits to LOCKED parsers: `scalar_results.py`, `quick_upload.py`,
   `long_format.py`, `master_bulk_upload.py` (fallback removal), `icp_service.py`.
3. Adding a nullable column to `experiment_notes` is additive; changing the
   CHECK constraint is a drop-and-recreate of a constraint (no data loss).

Hard gates, same as phase 1:
- PR-B's backfill (`migrate_reactor_change_requests_021.py`) is dry-run first.
  Post the report, stop, wait for Mat's audit. Never run `--apply` on your own.
- PR-D (column drop) does not open until `SELECT count(*) FROM experiment_notes
  WHERE needs_review` is **0 on production** and every legacy writer mirrors.
  Tell Mat the count; do not start PR-D on a hope.

## Design decisions (made; do not relitigate)

1. **A reactor modification is a `modification` note anchored to a date, not a
   separate object.** `experiment_notes` gains `event_date DATE NULL`. The scope
   CHECK becomes: `description` ⇒ `result_id IS NULL`; `modification` ⇒
   `(result_id IS NOT NULL OR event_date IS NOT NULL)`; `result_note` ⇒
   `result_id IS NOT NULL`; `observation` ⇒ anything. One type, two anchors. The
   UI label stays "Modification"; the Results tab shows only result-anchored
   ones; the timeline shows both.
2. **`reactor_label` is not carried onto the note.** The dashboard card already
   knows its slot; the backfill writes one `ModificationsLog` snapshot per
   converted row (full original row in `old_values`) so the label, Notion status
   and page id are recoverable but not modelled. If Mat wants the label kept,
   append it to the migrated text as `[R05] ` — ask once in the dry-run report,
   default is no.
3. **The review queue is emptied by people, with tooling; not by a script
   guessing.** Bulk actions operate on rows a researcher has selected. A new
   discard rule (e.g. timepoint tags `t=0`, `Day 7`) is allowed only as a Mat
   ruling recorded as rule 4f in `reclassify_notes_020.py`, applied via a
   one-off `--apply` on production, and reported the same way 4b–4e were.
4. **Nothing becomes required.** No validator replaces a removed one.
5. **"Entry Logs" (the `ModificationsLog` audit tab) stays separate.** Notes are
   content; the audit trail is provenance. Do not merge them.
6. **`observation` stays scope-free.**

## Deliver as four PRs, in order

### PR-A: review-queue tooling — `feat/notes-review-queue`

Unblocks PR-D. No schema change.

Backend:
- `PATCH /api/experiments/notes/bulk` body `{ids: [..], needs_review?: bool,
  note_type?: NoteType}` and `DELETE /api/experiments/notes/bulk` body `{ids}`.
  One `ModificationsLog` row per note (`modified_table='experiment_notes'`),
  scope rules → 422 naming the offending ids, second description → 409, cap 500
  ids per call. Register before the `/{experiment_id}` routes.
- Extend `GET /api/experiments/notes/review` with `note_type`, `q` (ILIKE on
  `note_text`), `experiment_id` filters and `order` (`experiment|created_at|text`).
  Return `distinct_texts: [{text, count}]` for the current filter (top 50) so the
  page can offer "select all 30 rows reading `t=0`".

Frontend:
- New route `/notes/review`, linked from the nav with the open count as a badge.
- Table: experiment (link), researcher, T+day, type badge, text, author, date.
  Filters: researcher, type, text search, distinct-text chips. Row checkboxes,
  select-all-in-filter, and a sticky action bar: Mark reviewed / Retype (select)
  / Delete, each with a confirm that states the count.
- Keep the per-experiment "Review queue only" filter on the Notes tab.

Tests: bulk endpoints (happy, partial 422, 409, cap), review filters,
`frontend/src/pages/__tests__/NotesReview.test.tsx` covering selection and a
bulk action calling the API with the selected ids.

### PR-B: reactor modifications become dated modification notes — `feat/reactor-mods-as-notes`

Schema (additive + constraint swap), Alembic on the single head after #117's
migrations if any (check `alembic heads` first, verify up/down/up on the mirror):
- `ALTER TABLE experiment_notes ADD COLUMN event_date DATE NULL`;
  `CREATE INDEX ix_experiment_notes_event_date ON experiment_notes (event_date)`;
  drop `ck_note_scope`, recreate per decision 1. Model + `tests/models/` tests
  for every new valid/invalid combination.

Backfill `database/data_migrations/migrate_reactor_change_requests_021.py`
(house pattern: dry run default, `--apply`, `DATABASE_URL`, before/after counts,
reasoning docstring, idempotent — skip when a `modification` note with the same
`experiment_fk`, `event_date`, text and `created_by='migrate_change_requests_021'`
exists):
- Each `reactor_change_requests` row → `add_note(note_type=modification,
  event_date=sync_date, note_text=requested_change, created_by='migrate_change_requests_021')`;
  `experiment_id` string → `experiments.id` exactly (no fuzzy match). Rows whose
  experiment no longer exists, or with blank `requested_change`, are **reported,
  not converted**. One `ModificationsLog` snapshot per converted row.
- Dry-run report: total rows, convertible, unresolvable-experiment rows (list),
  blank rows, distinct `reactor_label` vs the experiment's current
  `conditions.reactor_slot` disagreement count (informational), sample of 20.
  **STOP after posting it.**

Readers (after Mat approves and `--apply` runs on the mirror):
- `dashboard.py` `todays_modification`: `modification` notes with
  `event_date = today` for the card's experiment. Also expose
  `latest_modification` (most recent by `event_date`/`created_at`) — the card
  currently shows nothing on a quiet day and that is the field researchers ask for.
- Delete the three `/change-requests` routes, their schemas and TS client
  functions; `ChangeRequestsTab.tsx` is removed and `TABS` in
  `ExperimentDetail/index.tsx` loses "Reactor Modifications". Its add/edit flow
  moves into the Notes tab composer (PR-C) — a `Modification` with a date picker
  defaulting to today when no timepoint is chosen.
- `DeleteImpact`: remove `change_requests` from all layers listed in MODELS.md
  ("Adding a counted field requires all five layers") — the notes count already
  covers the converted rows.
- Leave the `reactor_change_requests` table, `ReactorChangeRequest` model and
  `notion_sync/import_.py` in place; #117 drops them. Comment on #117 that the
  data has been migrated and the table is now unreferenced by the app.

### PR-C: unified notes timeline + description editing — `feat/notes-timeline`

- `NotesTab` becomes one chronological timeline of every note on the experiment:
  experiment-level and timepoint-scoped mixed, newest first, each with a
  type badge (shared `NoteBadge` component used by ResultsTab too — extract it),
  a `T+7` chip when `result_id` is set, a date chip when `event_date` is set,
  author, needs-review marker with Mark reviewed. Filters: type, review-only.
- Composer: type select (`observation`, `modification`, `result_note`,
  `description` when none exists), optional timepoint select (from the experiment's
  results) or date (for a dated modification), text. Uses `POST notes` only.
- Header: the description renders as today; click-to-edit inline (PATCH
  `note_text` on the description note, or POST a `description` when missing —
  this is how the 38 `'nan'` experiments get one). Show "Add description" when
  absent.
- Rename `condition_note` → `description` on `ExperimentListItem` (schema, TS
  type, `ExperimentList.tsx`, tests). Column header stays "Description".
- Results tab: unchanged except it consumes `NoteBadge`.

### PR-D: drop the legacy columns — `chore/drop-legacy-note-columns`

Prerequisites, all verified and stated in the PR body:
1. Production review queue is 0 (paste the query output and date).
2. Every legacy writer mirrors or stops: `scalar_results.py`, `quick_upload.py`,
   `long_format.py` Description columns → `observation` note via
   `sync_result_note` (same slot semantics as master; `created_by` = the parser
   tag); `icp_service.py:650` stops seeding a description — pass `initial_note=None`
   so auto-created treatment experiments get no filler description.
   Master template v4 (`docs/sample_data/Master_Results_Tracker_v4.xlsx`, and
   the team's live copy) has been published with `Observation Note` /
   `Modification Note` headers and the deprecation window for v3 spellings is
   dated in `docs/user_guide/BULK_UPLOADS.md`.
3. `tests/services/bulk_uploads/test_master_bulk_upload.py` still passes
   unchanged after the fallback deletion (the test pinning `Master upload — day`
   is the one exception — update that single assertion and say so).

Then, in one migration (not additive — pre-authorized above; downgrade
recreates the columns nullable and does not attempt to restore data):
- Remove the dual-writes and every fallback (`Master upload — day N`,
  `Analysis results for Day N`, `Day N results`), the `sync_brine_flag`
  validator, `description` from `ResultCreate`/`ResultResponse`/
  `ResultWithFlagsResponse` and the TS types, `_sheet_fields` handling of
  `description` in `create_scalar_result_ex`, the `null_time_match` lookup by
  description in `_find_or_create_experimental_result` (find a replacement key
  or delete the fallback — decide and document).
- `DROP COLUMN experimental_results.description, brine_modification_description,
  has_brine_modification`. Confirm no view references them (`v_results_scalar.sampling_description`
  is dropped at startup and never recreated — remove it from MODELS.md).
- `docs/LOCKED_COMPONENTS.md` footnote ⁶ is rewritten to say the mirror is gone
  and the parsers write notes only.

## Optional, only if time remains and Mat agrees

- Two thin views for Power BI, `v_notes_experiment` (`result_id IS NULL`) and
  `v_notes_result` (`result_id IS NOT NULL`), so the star-schema split is defined
  once server-side instead of in Power Query. Document in `docs/POWERBI_MODEL.md`.
- Data cleanup outside this task's rules, filed as separate issues: experiments
  504 (`experiment_id = 'nan'`) and 701 (`''`); result 1382 at day 46,115.

## Locked-component obligations

Every PR touching `master_bulk_upload.py` states in its body that the six
footnote-² properties still hold and that `test_master_bulk_upload.py` passes
unchanged (PR-D excepted as above). Every parser edit is in a file
`docs/LOCKED_COMPONENTS.md` lists; cite the pre-authorization.

## Docs to update

`.claude/rules/MODELS.md` (`ExperimentNotes`: `event_date`, new CHECK; remove
`ReactorChangeRequest` references once #117 lands; `ExperimentalResults` after
PR-D), `docs/POWERBI_MODEL.md`, `docs/api/API_REFERENCE.md` (+ project_context
copy via the hook), `docs/user_guide/BULK_UPLOADS.md`, the three upload
template docs, `docs/LOCKED_COMPONENTS.md`, `docs/working/issue-log.md`,
`docs/working/decisions.md` (one entry: "a modification is anchored to a result
or a date"), and a dry-run report in `docs/issues/` for 021.

## Definition of done

1. A researcher can empty the review queue from `/notes/review` without touching
   the database; each bulk action is audited per note.
2. `reactor_change_requests` has no reader in `backend/` or `frontend/`
   (`grep -rn "ReactorChangeRequest\|change_requests\|change-requests" backend/api
   backend/services/experiment_deletion.py frontend/src` is empty), the Reactor
   Modifications tab is gone, and the dashboard's `todays_modification` reads notes.
3. The Notes tab shows every note on an experiment in one timeline with the same
   badges the Results tab uses; the header description is editable.
4. `experimental_results.description`, `brine_modification_description`,
   `has_brine_modification` do not exist; `grep -rn "brine_modification\|sampling_description\|Master upload — day"
   backend/ database/ frontend/src` is empty.
5. The 021 dry-run report is attached to PR-B and the post-`--apply` counts match it.
6. `.venv/Scripts/pytest tests/models tests/views tests/api tests/test_icp_handling.py
   tests/services tests/regression tests/data_migrations` passes (reset
   `experiments_test` first, one pytest process); `npx vitest run` and
   `eslint` show only the #106 baseline.

## Working notes from phase 1 (save yourself the hour)

- `experiments_test` is built with `create_all`, which never alters a table. After
  any model column change, `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`
  then `create_all` before running tests. Never run two pytest processes at once.
- Root-level `tests/test_*.py` use a `test_db` fixture that drops all tables at
  teardown — never include them in the same pytest invocation as `tests/services`.
- The dev DB is a mirror of the 2026-09-04 production backup with the 020 backfill
  applied. Refresh it from a newer backup (memory: `restoring-prod-backups-to-dev`)
  before any dry run whose numbers Mat will audit.
- Doc edits made through a Python script bypass the `project_context` sync hook;
  call `sync_docs_to_project_context.full_sync()` afterwards.
- Long Python edit scripts fail in Bash heredocs; write them to the scratchpad
  and run the file.
- `alembic heads` must print one head before every commit that adds a migration;
  the Ti/notes two-head incident is in the issue-log (2026-09-22).
- On the lab PC, use `.venv\Scripts\python.exe` and `.venv\Scripts\alembic.exe`;
  the system `python` has no packages.
- PRs target `develop` (`gh pr create --base develop`); stacked PRs are fine and
  GitHub marks all of them merged when develop is pushed.
