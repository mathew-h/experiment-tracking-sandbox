# 07 — Notes overhaul, phase 2 (issue #122)

**Revised 2026-09-24.** Supersedes the 2026-09-23 session prompt that first lived
here, and absorbs the follow-up issue doc "New-experiment description saves as an
observation; Notes feed cannot retype; Reactor Modifications tab still reads
Notion-era change requests" (Mat, 2026-09-24). Written to be sufficient for a
**cleared Claude Code session** to start the next PR without other context.

## 0. How to start a session from this document

1. Run `/start-task`. Mode: `issue`, issue **#122** (already open; do not open
   another). Branch from `develop` with the branch name given for the PR you
   are starting (§4). PRs target `develop`: `gh pr create --base develop`.
   Stack on an earlier PR only when §4 says it depends on it, and say so in
   the PR body.
2. Read `.claude/rules/MODELS.md` → `ExperimentNotes`, and `backend/services/notes.py`.
   Then read only the §4 subsection for your PR.
3. Follow the conductor workflow (`.claude/skills/conductor.md`): brainstorm the
   gaps the PR section leaves open, write a plan to
   `docs/superpowers/plans/`, execute it with `superpowers:subagent-driven-development`.
   PR-A's plan (`docs/superpowers/plans/2026-09-23-notes-review-queue-pr-a.md`) is
   the house example: TDD steps with verbatim test code, one commit per task.
4. Frontend PRs: the Chrome DevTools MCP is available for the closed-loop UI
   check described in `.claude/skills/frontend-builder.md` (run the app, open
   `http://localhost:5173`, inspect console/network, fix, repeat). Use it for
   the Notes tab, dashboard card and wizard changes before opening the PR.
5. Before `/complete-task`: update the docs in §7, append the issue-log entry,
   and state the verification counts in the PR body.

## 1. Status

| PR | Branch | State |
|---|---|---|
| PR-A review-queue tooling | `feat/notes-review-queue` | **Done.** PR #123 open against `develop` (2026-09-24). |
| PR-B0 wizard description + retype control | `fix/notes-entry-and-retype` | Next. No schema change. |
| PR-B reactor modifications become dated notes | `feat/reactor-mods-as-notes` | After B0. Schema + backfill (dry run → **STOP**). |
| PR-C unified timeline + description editing | `feat/notes-timeline` | After B. |
| PR-E remove the Notion sync (absorbs #117) | `chore/remove-notion-sync` | After B (needs the data migrated). Independent of C. |
| PR-D drop the legacy result columns | `chore/drop-legacy-note-columns` | Last. Gated on production review queue = 0. |

### Where phase 1 (#118) left things

Merged to develop and deployed to the lab PC on 2026-09-23 (main `db85cf4`):

- `experiment_notes` carries `note_type` (`description | modification |
  observation | result_note`), `result_id`, `created_by`, `needs_review`.
  Postgres enforces `uq_one_description_per_experiment` (partial unique index),
  `fk_note_result_same_experiment` (composite FK, ON DELETE CASCADE) and
  `ck_note_scope` (`database/models/experiments.py:108-116`):
  `description` ⇒ `result_id IS NULL`; `modification`/`result_note` ⇒
  `result_id IS NOT NULL`; `observation` ⇒ either.
- `Experiment.description` is a read-only hybrid over the `description` note;
  the experiments list, dashboard reactor card (`dashboard.py:96`) and
  `v_experiments` (`event_listeners.py:140`) share its SQL expression.
- `backend/services/notes.py` is the single write path: `add_note(db, experiment,
  note_text, *, note_type, result_id, created_by, needs_review, created_at)` and
  `sync_result_note`. Five legacy paths dual-write the old result columns and a
  typed note: `POST /api/results`, `POST /experiments/{id}/notes`,
  `master_bulk_upload.py`, `timepoint_modifications.py`, `new_experiments.py`.
- `reclassify_notes_020.py --apply` ran on production: 1,432 descriptions,
  151 modification notes, **review queue 1,288**. The dev mirror (2026-09-04
  backup + 020) shows 118 experiments with no `description` note.
- Readers: `GET /experiments/{id}/results` returns `has_modification_note` +
  per-result `notes`; `PATCH /experiments/{id}/notes/{note_id}` accepts
  `note_text`, `note_type` (422 on scope, 409 on second description),
  `needs_review`. Views: `v_experiments.description`,
  `v_dim_timepoints.modification_note`, `v_notes`.
- Decision record: `docs/working/decisions.md` 2026-09-23. Plan:
  `docs/superpowers/plans/2026-09-08-typed-notes-pr1-pr2.md`. Report:
  `docs/issues/reclassify-notes-020-dryrun-2026-09-08.md`.

### What PR-A added (on `feat/notes-review-queue`, PR #123)

- `PATCH /api/experiments/notes/bulk` `{ids ≤500, needs_review?, note_type?}` and
  `DELETE /api/experiments/notes/bulk` `{ids}` — atomic, one `ModificationsLog`
  row per note, 404/422/409 naming offenders. Registered before `/{experiment_id}`.
- `GET /api/experiments/notes/review` gained `note_type`, `q`, `experiment_id`
  (ILIKE, `%`/`_` literal), `order` ∈ {experiment, created_at, text}, `desc`,
  and `distinct_texts` (top-50 histogram over the filter).
- `/notes/review` page (`frontend/src/pages/NotesReview.tsx`), nav item with
  open-count badge (`AppLayout.tsx`, query key `['notes-review','count']`,
  refreshed by invalidating the `['notes-review']` prefix).
- Tests: `tests/api/test_notes_bulk.py` (15), `tests/api/test_notes_review.py`
  (+7), `frontend/src/pages/__tests__/NotesReview.test.tsx` (10),
  `frontend/src/layouts/__tests__/AppLayout.badge.test.tsx` (2).
  Backend 1,391 passed; vitest 247 passed.
- Design calls (approved): bulk calls atomic; `order` + `desc`; select-all =
  the loaded 500-row page (= bulk cap); badge reuses the list endpoint.

### Still legacy, still dual-written, still in the schema

`experimental_results.description` (NOT NULL), `brine_modification_description`,
`has_brine_modification` (+ the `sync_brine_flag` validator in
`database/models/results.py`). Dropped in PR-D.

### The Notion-era reactor change requests (the thing PR-B and PR-E retire)

`reactor_change_requests` (`database/models/notion_sync.py::ReactorChangeRequest`:
`reactor_label`, `experiment_id` **string**, `requested_change`, `sync_date`,
`notion_status`, `carried_forward`, `notion_page_id`; unique on
`(reactor_label, experiment_id, sync_date)`). **The Notion automation is
deprecated and unused** (Mat, 2026-09-08 and 2026-09-24): `notion_token`
defaults to `""` (`backend/config/settings.py:34`), so the scheduler in
`backend/api/main.py:29-38` never starts and `POST /api/admin/notion-sync` 400s.
But the table is still written live from the dashboard: the reactor card's
"Reactor Modification" form (`frontend/src/pages/ReactorGrid.tsx:286-330,
510-550`) calls `getRecentChangeRequests` and `createChangeRequest`
(`POST /experiments/{id}/change-requests`, `experiments.py:1202`, upsert on
reactor + experiment + date).

Dev mirror, 2026-09-24 (2026-09-04 production data):

| Measure | Count |
|---|---|
| `reactor_change_requests` rows | 294 |
| typed on the dashboard (`notion_page_id IS NULL`) | 161 |
| imported from Notion (`notion_page_id IS NOT NULL`) | 133 |
| rows dated 2026-08-01 or later | 115 |
| `experiment_id` string with no matching `experiments` row | 26 |
| blank `requested_change` | 0 |
| `experiment_notes` rows typed `modification` | 141 |

So the feature is in active use and its data must be migrated, not dropped.

Consumers today: `backend/api/routers/experiments.py:1140,1160,1202` (three
`/change-requests` routes; schemas in `backend/api/schemas/notion_sync.py`),
`backend/api/routers/dashboard.py:11,163-180` (`todays_modification`),
`backend/api/schemas/dashboard.py:71`, `backend/services/experiment_deletion.py:80,108,125,162,320-324,373`
(`change_requests` impact count + purge), `frontend/src/pages/ExperimentDetail/index.tsx:16,18,514`
(the "Reactor Modifications" tab → `ChangeRequestsTab.tsx`),
`frontend/src/pages/ReactorGrid.tsx`, `frontend/src/api/experiments.ts:163` and
the change-request client methods, `frontend/src/components/experiments/DeleteExperimentModal.tsx:28`.
Tests: `tests/api/test_change_requests.py`, `tests/api/test_dashboard.py`,
`tests/api/test_experiments.py`, `tests/models/test_notion_sync_model.py`,
`tests/services/test_experiment_deletion.py`, `tests/test_notion_sync_scheduler.py`,
`tests/api/test_notion_sync.py`, `tests/services/test_notion_sync_{client,export,import,integration}.py`,
`frontend/src/pages/ExperimentDetail/__tests__/ChangeRequestsTab.test.tsx`,
`frontend/src/pages/__tests__/{Dashboard,ReactorGrid}.test.tsx`,
`DeleteExperimentModal.test.tsx`, `experiments.deleteExperiment.test.ts`,
`ExperimentDetail/__tests__/DeleteExperiment.test.tsx`.

### Three defects found 2026-09-24 (fixed by PR-B0 and PR-B)

1. **The wizard's description is saved as an observation.**
   `frontend/src/pages/NewExperiment/index.tsx:133` calls
   `experimentsApi.addNote(exp.experiment_id, step1.note)` with no `note_type`,
   so `NoteCreate.note_type` defaults to `observation`. Every reader resolves
   the description by `note_type = 'description'`, so wizard-created experiments
   since #118 show no description on the reactor card, the detail header, or
   `v_experiments`. `onSuccess` (`index.tsx:189`) also refreshes only
   `['experiments']`, never `['dashboard']`. (The dev mirror predates the
   deploy, so it has 0 such rows; production will have some.)
2. **The Notes feed cannot retype a note.** `PATCH notes/{id}` supports
   `note_type`, but `NotesTab.tsx`'s `editNote` sends only `note_text` and the
   type is a read-only badge. Fixing item 1's rows by hand needs this.
3. **The Reactor Modifications tab shows a different object than modification
   notes, from a Notion-era table**, and the dashboard form still writes that
   table (see above). `v_dim_timepoints.modification_note` reads only typed
   notes, so the two paths disagree in Power BI.

## 2. Pre-authorizations and hard gates

Given by Mat in-session on 2026-09-23 (still valid; cite them in PR bodies):

1. Schema change on `experiment_notes`: nullable `event_date` column (additive)
   and a drop-and-recreate of `ck_note_scope` (no data loss).
2. Edits to the LOCKED parsers `scalar_results.py`, `quick_upload.py`,
   `long_format.py`, `master_bulk_upload.py` (fallback removal), `icp_service.py`
   — PR-D only.
3. The three non-additive column drops on `experimental_results` — PR-D only.

Given 2026-09-24: (4) absorb #117 — delete the Notion sync code — as PR-E.

**Not yet authorized** (stop and ask when reached): `DROP TABLE
reactor_change_requests` and deleting `ReactorChangeRequest`. It is
non-additive and must wait until the 021 backfill has run on **production**.
Never delete migration files under `alembic/versions/`.

Hard gates:
- PR-B's backfill (`migrate_reactor_change_requests_021.py`) is dry-run first.
  Post the report, **stop**, wait for Mat's audit. Never run `--apply` on your own.
- PR-D does not open until `SELECT count(*) FROM experiment_notes WHERE
  needs_review` is **0 on production** and every legacy writer mirrors. Tell Mat
  the count; do not start PR-D on a hope.
- `alembic heads` must print exactly one head before any commit that adds a
  migration (the current head is `c4d8f1a2b6e7`).

## 3. Design decisions (made; do not relitigate)

1. **A reactor modification is a `modification` note anchored to a result OR a
   calendar date, not a separate object.** `experiment_notes` gains
   `event_date DATE NULL`. `ck_note_scope` becomes: `description` ⇒
   `result_id IS NULL`; `modification` ⇒ `(result_id IS NOT NULL OR event_date
   IS NOT NULL)`; `result_note` ⇒ `result_id IS NOT NULL`; `observation` ⇒
   anything. One type, two anchors. The UI label stays "Modification"; the
   Results tab shows only result-anchored ones; the timeline shows both.
   **Confirmed 2026-09-24 over the alternative** of snapping a date to the
   latest primary result on or before it with an `observation` fallback: that
   records a day-5 change as "at the day-3 timepoint", loses the Modification
   type before the first timepoint, and cannot migrate the 294 existing rows
   faithfully.
2. **`reactor_label` is not carried onto the note.** The card already knows its
   slot; the backfill writes one `ModificationsLog` snapshot per converted row
   (full original row in `old_values`) so label, Notion status and page id are
   recoverable but not modelled. If Mat wants the label kept, prefix the
   migrated text with `[R05] ` — ask once in the dry-run report; default no.
3. **The review queue is emptied by people, with tooling; not by a script
   guessing.** A new discard rule is allowed only as a Mat ruling recorded as
   rule 4f in `reclassify_notes_020.py`, applied via a one-off `--apply` on
   production, and reported the same way 4b–4e were.
4. **Nothing becomes required.** No validator replaces a removed one.
5. **"Entry Logs" (the `ModificationsLog` audit tab) stays separate.** Notes are
   content; the audit trail is provenance.
6. **`observation` stays scope-free.**
7. **The wizard's Step 1 description is the `description` note.** Blank ⇒ no
   note. Existing mistyped rows are fixed forward by hand with the retype
   control; there is no backfill for them.
8. **Any approved user may retype a note**, limited to the types
   `ck_note_scope` allows for its anchor. The DB constraints are unchanged;
   the UI mirrors them. A retype writes one `ModificationsLog` row (existing
   PATCH behaviour).
9. **Dashboard modification saves are append-only.** Each save is a new
   `modification` note with `event_date`; corrections happen in the Notes tab.
   The old per-date upsert and per-date pre-populate are dropped. (Considered
   and rejected: `sync_result_note`-style slot semantics keyed on
   `(result_id, 'modification', created_by)` — it would silently overwrite a
   modification the same researcher wrote via Add Results for that timepoint.)
10. **No dedicated reactor-modification endpoint.** `POST /experiments/{id}/notes`
    gains `event_date`; the dashboard form calls it with
    `note_type: 'modification'`. The snapping logic that would have justified a
    separate route is not wanted (decision 1).
11. **The Notion sync is removed, not preserved** (PR-E). The
    `reactor_change_requests` table and model outlive the code only until the
    production backfill is confirmed; their drop is a separately authorized
    follow-up.
12. **This reverses one line of the 2026-09-08 decision record** ("the Reactor
    Modifications tab keeps its own name; they are different objects"). The tab
    was a different object, but its source is Notion-era and superseded by
    typed modification notes. Record this in `docs/working/decisions.md`.

## 4. The PRs

### PR-B0: wizard description + retype control — `fix/notes-entry-and-retype`

Small, no schema change, no locked file. Ships first because every experiment
created in the wizard since the deploy is missing its description.

**1. Type the wizard note.** `frontend/src/pages/NewExperiment/index.tsx:133` →
`experimentsApi.addNote(exp.experiment_id, step1.note, { note_type: 'description' })`
(the third argument already exists: `addNote(experimentId, text, opts)`). The
experiment is brand new, so `uq_one_description_per_experiment` cannot fire.
Add `queryClient.invalidateQueries({ queryKey: ['dashboard'] })` to `onSuccess`
(`index.tsx:189`). Blank `step1.note` still writes no note (`if (step1.note)`
guard at line 132 stays).

**2. Retype control in `NotesTab.tsx`.** Replace the read-only type `Badge` on
each note with a compact `<select>` (Tailwind classes as the existing
`new-note-type` select) offering only the types valid for the note's anchor,
mirroring `ck_note_scope`:
- experiment-level (`result_id == null`): `observation`, `description`
- timepoint (`result_id != null`): `observation`, `modification`, `result_note`

When another note on the experiment is already the description, disable the
`description` option with the label "(already set)", exactly as the add form
does (`ADDABLE_TYPES` / `hasDescription`). On change call
`experimentsApi.patchNote(experimentId, n.id, { note_type })`; show the
server's 422/409 `detail` in the error toast (the Axios interceptor in
`frontend/src/api/client.ts` already lifts `detail` into `error.message`). On
success invalidate `['experiment', id]` **and** `['dashboard']` (retyping to or
from description changes the reactor card). Keep the `aria-label="Note type"`
on the select so tests can find it.

**Acceptance**
- [ ] Creating an experiment in the wizard with a description produces one
  `experiment_notes` row with `note_type='description'`, `result_id IS NULL`;
  the text shows on the dashboard reactor card without a reload and in the
  detail header.
- [ ] Creating one with the description blank writes no note.
- [ ] In the Notes tab an experiment-level observation can be retyped to
  Description when none exists; the option is disabled and labelled
  "(already set)" when one does.
- [ ] A timepoint note's menu never offers Description; an experiment-level
  note's menu never offers Modification or Result note.
- [ ] A retype from the UI path writes one `ModificationsLog` row
  (`modified_table='experiment_notes'`) — assert via the mocked `patchNote`
  call shape on the frontend and the existing backend PATCH tests.

**Tests**: new `frontend/src/pages/NewExperiment/__tests__/NewExperiment.description.test.tsx`
(mock `experimentsApi.create/addNote` + `conditionsApi.create`; assert
`addNote` called with `{ note_type: 'description' }` and NOT called when blank;
assert `['dashboard']` invalidated). Extend
`frontend/src/pages/ExperimentDetail/__tests__/TypedNotes.test.tsx`: menu
scoping for both anchors, disabled Description, `patchNote` called with
`{ note_type }`, toast on a rejected promise. Backend: nothing new (PATCH is
already covered by `tests/api/test_notes_review.py`).

**Docs**: `docs/user_guide/USER_MANUAL.md` (Notes tab: type can be changed
inline), issue-log entry.

### PR-B: reactor modifications become dated modification notes — `feat/reactor-mods-as-notes`

Depends on nothing in B0 at the code level, but land B0 first so the mirror's
wizard rows are typed before the backfill report is audited.

**Schema** (pre-authorized). One Alembic revision off `c4d8f1a2b6e7` (verify
`alembic heads` is that single head first; verify upgrade → downgrade → upgrade
on `experiments_test` per memory `migration-rehearsal-on-experiments-test`):
- `ALTER TABLE experiment_notes ADD COLUMN event_date DATE NULL`;
  `CREATE INDEX ix_experiment_notes_event_date ON experiment_notes (event_date)`.
- Drop `ck_note_scope`, recreate per decision 1:
  `(note_type = 'description' AND result_id IS NULL) OR (note_type =
  'modification' AND (result_id IS NOT NULL OR event_date IS NOT NULL)) OR
  (note_type = 'result_note' AND result_id IS NOT NULL) OR (note_type =
  'observation')`. Downgrade restores the old expression and drops the column;
  it must first NULL-anchor-check: a `modification` row with `event_date` and
  no `result_id` violates the old CHECK, so the downgrade deletes those rows
  **only if** `--x-allow-data-loss` style confirmation is impossible — instead,
  make the downgrade refuse with a `RuntimeError` naming the count when such
  rows exist (house pattern from `00063a5dd6a8`).
- Model (`database/models/experiments.py`): `event_date = Column(Date,
  nullable=True, index=True)` with a docstring; update the class docstring's
  constraint list; update the `CheckConstraint` text. `tests/models/` tests for
  every valid/invalid `(note_type, result_id, event_date)` combination —
  9 rows: description ± result (valid/invalid), modification with result only /
  date only / both / neither (invalid), result_note with/without result,
  observation with date only.
- `NoteCreate`, `NoteUpdate`, `NoteResponse` (`backend/api/schemas/experiments.py`),
  `add_note` (`backend/services/notes.py`) and the TS `ExperimentNote` /
  `NoteCreate` / `NotePatch` gain `event_date: date | None`. `POST` and `PATCH`
  scope pre-checks (`experiments.py`, `post_note` and `patch_note`) and the
  bulk `_check_bulk_retype` mirror the new rule as 422 text: "A 'modification'
  note must be scoped to a result or carry an event_date." `v_notes` gains an
  `event_date` column; `v_dim_timepoints.modification_note` is unchanged (it
  is per result). Recreate the views in `event_listeners.py` **and** in the
  same Alembic revision (house pattern from `c4d8f1a2b6e7`).

**Backfill** `database/data_migrations/migrate_reactor_change_requests_021.py`
(house pattern: dry run default, `--apply`, `DATABASE_URL`, before/after
counts, reasoning docstring, idempotent — skip when a `modification` note with
the same `experiment_fk`, `event_date`, `note_text` and
`created_by='migrate_change_requests_021'` already exists):
- Each `reactor_change_requests` row → `add_note(db, exp, requested_change,
  note_type=modification, event_date=sync_date, created_by='migrate_change_requests_021',
  created_at=<row created_at if the table has one, else sync_date at 00:00 UTC>)`.
  Resolve `experiment_id` string → `experiments.experiment_id` **exactly** (no
  fuzzy match; do not use `_id_match.normalize_id`). Convert both
  dashboard-typed and Notion-imported rows — both are real modifications.
  Rows whose experiment does not exist (26 on the mirror) or with blank text
  (0) are **reported, not converted**. One `ModificationsLog` snapshot per
  converted row (`modified_table='reactor_change_requests'`,
  `modification_type='update'`, `old_values` = the full original row,
  `new_values` = `{note_id}`), `experiment_fk` set (these rows should die
  with the experiment).
- Dry-run report to `docs/issues/migrate-change-requests-021-dryrun-<date>.md`:
  total rows, convertible, unresolvable-experiment rows (list the 26 ids),
  blank rows, distinct `reactor_label` vs the experiment's current
  `conditions.reactor_slot` disagreement count (informational), duplicates
  that would collapse under the idempotency key, sample of 20. **Refresh the
  dev DB from a newer production backup first** (memory
  `restoring-prod-backups-to-dev`); the numbers above are from the 2026-09-04
  mirror. **STOP after posting the report.** Ask the decision-2 label question
  there.
- Tests: `tests/data_migrations/test_migrate_change_requests_021.py` — converts,
  skips unresolvable, idempotent second run, snapshot shape, dry run writes
  nothing.

**Readers and writers** (after Mat approves and `--apply` runs on the mirror):
- `backend/api/routers/dashboard.py:163-180`: `todays_modification` becomes the
  `modification` note(s) with `event_date = today` (UTC, unchanged) for the
  card's experiment, `'; '`-joined in id order if several. Add
  `latest_modification: {note_text, event_date, created_at} | None` — the most
  recent `modification` note by `COALESCE(event_date, created_at::date)` then
  `id` — to `ReactorCardData` (`schemas/dashboard.py`) and the TS type. One
  batched query, keeping the endpoint's "no N+1" contract. Drop the
  `ReactorChangeRequest` import.
- `frontend/src/pages/ReactorGrid.tsx`: `crMutation` calls
  `experimentsApi.addNote(card.experiment_id, text, { note_type: 'modification',
  event_date: crDate })`; on success clear the textarea, invalidate
  `['dashboard']` and `['experiment', card.experiment_id]`, toast "Modification
  saved for <date>". Delete the `reactorModificationRecent` query and the
  per-date pre-populate effect (`:286-299`). The "previous entry" block
  (`:513-523`) renders `card.latest_modification`. The date input stays,
  defaulting to today.
- `frontend/src/pages/ExperimentDetail/index.tsx`: remove `'Reactor Modifications'`
  from `TABS` (`:18`), the render branch (`:514`) and the import (`:16`). Delete
  `ChangeRequestsTab.tsx` and `__tests__/ChangeRequestsTab.test.tsx`. The
  existing Notes tab already renders `modification` notes; PR-C adds the date
  chip and the composer's date picker.
- `DeleteImpact`: remove `change_requests` from **all** layers MODELS.md lists —
  the dataclass field and `total` (`experiment_deletion.py:108,125`),
  `collect_delete_impact` (`:162`), `DeleteImpactResponse`,
  `_impact_to_response` (`:373`), the TS `DeleteImpact` (`api/experiments.ts:163`),
  `IMPACT_ROWS` (`DeleteExperimentModal.tsx:28`), and their tests. **Keep the
  purge statement** (`:320-324`) until PR-E removes the model import; it is
  harmless and keeps the dead table from accumulating orphans.
- Mark the three `/change-requests` routes deprecated in their docstrings and
  in `docs/api/API_REFERENCE.md:29-31` ("Deprecated 2026-09; removed by PR-E.
  Data migrated to `experiment_notes` by 021."). Do not delete them here.
- `MODELS.md`: `ExperimentNotes` gains `event_date` + the new CHECK text; the
  deletion section loses `change_requests` from the impact list.

**Acceptance**
- [ ] `(modification, result_id NULL, event_date set)` inserts; `(modification,
  NULL, NULL)` is rejected by the DB and by `POST`/`PATCH`/bulk as 422.
- [ ] Saving a modification from the dashboard card creates one `modification`
  note with `event_date` = the picked date, `created_by` = the caller's email.
  It appears in the Notes tab and in `v_notes` with its date. No row is
  written to `reactor_change_requests` from any UI path.
- [ ] The card shows today's modification(s) and the latest prior one, from
  notes.
- [ ] The detail page has no Reactor Modifications tab; Notes and Entry Logs
  are unchanged.
- [ ] Delete-experiment dialog no longer lists reactor change requests; totals
  still sum correctly (`tests/services/test_experiment_deletion.py`).
- [ ] The 021 dry-run report is attached to the PR and the post-`--apply`
  counts on the mirror match it.
- [ ] `grep -rn "ReactorChangeRequest\|change_requests\|change-requests"
  backend/api/routers/dashboard.py frontend/src` returns only the deprecated
  client methods (removed in PR-E).

**Tests**: models (9 combinations), `tests/api/test_notes.py` (POST with
`event_date`; 422 for modification with neither anchor), `tests/api/test_notes_bulk.py`
(retype to modification allowed when `event_date` set), `tests/api/test_dashboard.py`
(today's + latest from notes; change-request assertions removed), views
(`tests/views/test_typed_notes_views.py`: `v_notes.event_date`), data migration
tests, `frontend/src/pages/__tests__/ReactorGrid.test.tsx` (save calls `addNote`
with `note_type: 'modification'` and `event_date`; previous block reads
`latest_modification`), `Dashboard.test.tsx`, `DeleteExperiment*.test.tsx`.

### PR-C: unified notes timeline + description editing — `feat/notes-timeline`

Depends on PR-B (date chip, date picker). Stack on it if B is not yet merged.

- `NotesTab` becomes one chronological timeline of every note on the
  experiment: experiment-level and timepoint-scoped mixed, newest first by
  `COALESCE(event_date, created_at)`, each with a type badge (extract a shared
  `NoteBadge` component — `frontend/src/components/experiments/NoteBadge.tsx` —
  used by `ResultsTab` and `NotesReview` too, replacing the three local
  `typeBadgeVariant` copies), a `T+7` chip when `result_id` is set, a date
  chip when `event_date` is set, author, needs-review marker with Mark
  reviewed, the PR-B0 retype select, edit and delete. Filters: type,
  review-only (keep the existing "Review queue only" checkbox).
- Composer: type select (`observation`, `modification`, `result_note`,
  `description` when none exists), optional timepoint select (from
  `GET /experiments/{id}/results`, labelled `T+N`) **or** a date picker
  (enabled for `modification`; defaults to today when no timepoint is chosen),
  text. Uses `POST notes` only. The type/anchor combination is validated
  client-side to the same rule as `ck_note_scope`, and the server's 422/409 is
  shown verbatim on failure.
- Header: the description renders as today; click-to-edit inline (PATCH
  `note_text` on the description note, or POST a `description` when missing —
  this is how the description-less experiments get one). Show "Add
  description" when absent. Invalidate `['experiment', id]`, `['experiments']`
  and `['dashboard']`.
- Rename `condition_note` → `description` on `ExperimentListItem` (Pydantic
  schema, TS type, `ExperimentList.tsx`, tests). Column header stays
  "Description".
- Results tab: unchanged except it consumes `NoteBadge`.

**Acceptance**
- [ ] Every note on an experiment appears once in the Notes tab with the same
  badge the Results tab and `/notes/review` use.
- [ ] A dated modification shows its date chip; a result-scoped one shows `T+N`.
- [ ] The composer can create each of the four types with a valid anchor and
  refuses invalid combinations before the request is sent.
- [ ] An experiment with no description shows "Add description"; saving it
  creates the `description` note and the reactor card updates.
- [ ] `condition_note` no longer appears in `backend/`, `frontend/src`, or the
  API reference.

**Tests**: `TypedNotes.test.tsx` (timeline ordering, chips, composer anchors),
`NotesTab.buttons.test.tsx`, a new `ExperimentDetail/__tests__/DescriptionEdit.test.tsx`,
`ExperimentList.test.tsx` (field rename), `tests/api/test_experiments.py`
(`description` on the list item).

### PR-E: remove the Notion sync integration (absorbs #117) — `chore/remove-notion-sync`

Depends on PR-B being merged (no code may still read `reactor_change_requests`
through the routes being deleted). Two parts; only the first is authorized now.

**E1 — code removal (no schema change).** Delete, per #117's scope table:
`backend/services/notion_sync/` (client, export, import_, sync, `__init__`);
`backend/api/routers/notion_sync.py`; the scheduler lifespan block in
`backend/api/main.py:29-38` and its shutdown, the `notion_sync` entry in the
router import tuple (`:17`) and `include_router`; `notion_token`,
`notion_database_id`, `notion_data_source_id`, `notion_sync_hour` from
`backend/config/settings.py:34-37`; `apscheduler` and `notion-client` from
`requirements.txt` once no import remains; the three `/change-requests` routes
(`experiments.py:1140,1160,1202`), `backend/api/schemas/notion_sync.py`, the TS
client methods (`getChangeRequests`, `getRecentChangeRequests`,
`createChangeRequest`) and the `ChangeRequestEntry` type; the model import and
purge in `experiment_deletion.py:80,320-324`; tests `tests/api/test_notion_sync.py`,
`tests/services/test_notion_sync_{client,export,import,integration}.py`,
`tests/test_notion_sync_scheduler.py`, `tests/api/test_change_requests.py`;
docs `docs/NOTION_SYNC.md`, `docs/notion_sync/NOTION_SYNC.md`,
`docs/project_context/NOTION_SYNC.md`; update `docs/DIRECTORY_STRUCTURE.md`
(`:32`) and the `project_context` copy. Historical references in
`docs/superpowers/plans/` and `docs/issues/` stay. Comment on and close #117.

Before merging E1: check `notion_token` in the lab PC's `.env`. If it is set,
confirm with the team nobody reads the Notion reactor page, unset it, run one
day, then merge (this is #117's verification step).

**E2 — table drop (NOT authorized; ask).** After the 021 `--apply` has run on
production and the post-apply counts match the report: a migration that
`DROP TABLE reactor_change_requests`, deletion of
`database/models/notion_sync.py` and `tests/models/test_notion_sync_model.py`,
MODELS.md cleanup. Requires explicit §7 sign-off for a non-additive migration.
Its three historical migrations (`9c358174ea54`, `ca5d57c6b272`,
`13fc77a07865`) are never deleted.

**Acceptance (E1)**
- [ ] `grep -rn "notion" backend/ frontend/src requirements.txt` returns only
  `database/models/notion_sync.py` and its model test.
- [ ] `grep -rn "ReactorChangeRequest\|change_requests\|change-requests"
  backend/api backend/services frontend/src` is empty except the model file.
- [ ] The app starts with no scheduler; `pip check` clean after the requirement
  removals; full pytest passes without the deleted test files.

### PR-D: drop the legacy result columns — `chore/drop-legacy-note-columns`

Prerequisites, all verified and stated in the PR body:
1. Production review queue is 0 (paste the query output and date).
2. Every legacy writer mirrors or stops: `scalar_results.py:129,320`,
   `quick_upload.py:289-344`, `long_format.py:284` Description columns →
   `observation` note via `sync_result_note` (same slot semantics as master;
   `created_by` = the parser tag); `icp_service.py:650` stops seeding a
   description — pass `initial_note=None` so auto-created treatment experiments
   get no filler. Master template v4
   (`docs/sample_data/Master_Results_Tracker_v4.xlsx` and the team's live copy)
   is published with `Observation Note` / `Modification Note` headers, and the
   deprecation window for v3 spellings is dated in `docs/user_guide/BULK_UPLOADS.md`.
3. `tests/services/bulk_uploads/test_master_bulk_upload.py` still passes
   unchanged after the fallback deletion (the test pinning `Master upload — day`
   is the one exception — update that single assertion and say so).

Then, in one migration (non-additive, pre-authorized; downgrade recreates the
columns nullable and does not restore data):
- Remove the dual-writes and every fallback (`Master upload — day N`,
  `Analysis results for Day N`, `Day N results`), the `sync_brine_flag`
  validator, `description` from `ResultCreate`/`ResultResponse`/
  `ResultWithFlagsResponse` and the TS types, `_sheet_fields` handling of
  `description` in `create_scalar_result_ex`, the `null_time_match` lookup by
  description in `_find_or_create_experimental_result` (find a replacement key
  or delete the fallback — decide and document).
- `DROP COLUMN experimental_results.description, brine_modification_description,
  has_brine_modification`. Confirm no view references them
  (`v_results_scalar.sampling_description` is already gone — remove it from
  MODELS.md).
- `docs/LOCKED_COMPONENTS.md` footnote ⁶ is rewritten to say the mirror is gone
  and the parsers write notes only.

## 5. Optional, only if time remains and Mat agrees

- Two thin views for Power BI, `v_notes_experiment` (`result_id IS NULL`) and
  `v_notes_result` (`result_id IS NOT NULL`), documented in `docs/POWERBI_MODEL.md`.
- Data cleanup outside this task's rules, filed as separate issues: experiments
  504 (`experiment_id = 'nan'`) and 701 (`''`); result 1382 at day 46,115.
- Backport the bulk-delete's six-field audit snapshot to the single-note
  `delete_note` (`experiments.py`, currently snapshots `note_text` only).
- `placeholderData: keepPreviousData` on the `/notes/review` list query so a
  filter change does not flash-clear the selection.

## 6. Locked-component obligations

Every PR touching `master_bulk_upload.py` states in its body that the six
footnote-² properties still hold and that `test_master_bulk_upload.py` passes
unchanged (PR-D excepted as above). Every parser edit is in a file
`docs/LOCKED_COMPONENTS.md` lists; cite pre-authorization 2. `database/models/`
edits are limited to PR-B's `event_date` + CHECK (pre-authorization 1) and the
E2 deletion once authorized.

## 7. Docs to update

`.claude/rules/MODELS.md` (`ExperimentNotes`: `event_date`, new CHECK, PR-B;
deletion-impact list, PR-B; remove `ReactorChangeRequest` references, E2;
`ExperimentalResults` after PR-D), `docs/POWERBI_MODEL.md` (`v_notes.event_date`),
`docs/api/API_REFERENCE.md` (+ `project_context` copy via the hook — use the
Edit tool, or call `sync_docs_to_project_context.full_sync()` after a scripted
edit), `docs/user_guide/USER_MANUAL.md`, `docs/user_guide/BULK_UPLOADS.md` and
the three upload template docs (PR-D), `docs/LOCKED_COMPONENTS.md` (PR-D),
`docs/DIRECTORY_STRUCTURE.md` (PR-E), `docs/working/issue-log.md` (every PR),
`docs/working/decisions.md` (one entry after PR-B: "a modification is anchored
to a result or a date; the Reactor Modifications tab is retired"), and the 021
dry-run report in `docs/issues/`.

## 8. Definition of done (phase)

1. A researcher can empty the review queue from `/notes/review` without
   touching the database; each bulk action is audited per note. **(PR-A, done.)**
2. A wizard-created experiment has a `description` note; any note's type can be
   changed in the Notes tab within its scope. **(PR-B0.)**
3. `reactor_change_requests` has no reader or writer in `backend/api`,
   `backend/services` or `frontend/src`; the Reactor Modifications tab is gone;
   the dashboard card reads and writes `modification` notes with `event_date`;
   the 021 dry-run report is attached to PR-B and the post-`--apply` counts
   match it. **(PR-B, PR-E.)**
4. The Notes tab shows every note on an experiment in one timeline with the
   same badges the Results tab and `/notes/review` use; the header description
   is editable. **(PR-C.)**
5. The Notion sync code, scheduler, settings and dependencies are gone; #117
   is closed. **(PR-E.)**
6. `experimental_results.description`, `brine_modification_description`,
   `has_brine_modification` do not exist; `grep -rn "brine_modification\|sampling_description\|Master upload — day"
   backend/ database/ frontend/src` is empty. **(PR-D.)**
7. Every PR: `.venv/Scripts/pytest.exe tests/models tests/views tests/api
   tests/test_icp_handling.py tests/services tests/regression tests/data_migrations`
   passes (reset `experiments_test` after any model change; one pytest
   process); `npx vitest run`, `npx eslint src --ext .ts,.tsx` and `npx tsc
   --noEmit` show only the #106 baseline (5 eslint problems, 3 tsc errors in
   `ResultsTab.columns.test.tsx`).

## 9. Working notes (save yourself the hour)

From phase 1:
- `experiments_test` is built with `create_all`, which never alters a table.
  After any model column change: `DROP SCHEMA public CASCADE; CREATE SCHEMA
  public;` then `create_all` before running tests. Never run two pytest
  processes at once.
- Root-level `tests/test_*.py` use a `test_db` fixture that drops all tables at
  teardown — never include them in the same pytest invocation as `tests/services`.
  Put new backend tests under `tests/api/`, `tests/models/`, etc., not at root.
- The dev DB is a mirror of the 2026-09-04 production backup with the 020
  backfill applied and PR-A's code exercised against it. Refresh it from a
  newer backup (memory `restoring-prod-backups-to-dev`) before any dry run
  whose numbers Mat will audit.
- Doc edits made through a Python script bypass the `project_context` sync
  hook; call `sync_docs_to_project_context.full_sync()` afterwards.
- Long Python edit scripts fail in Bash heredocs; write them to the scratchpad
  and run the file. `git commit -F <file>` for multi-line messages.
- On the lab PC use `.venv\Scripts\python.exe` and `.venv\Scripts\alembic.exe`;
  the system `python` has no packages.

From PR-A (2026-09-24):
- Under `tests/api/conftest.py` every row a test creates shares one
  `created_at` (one outer transaction, Postgres `now()`), so any ordering test
  on `created_at` is really testing the `id` tiebreak. Set `created_at`
  explicitly when the primary sort matters.
- A negative test for LIKE escaping must use a row that ONLY a wildcard
  reading would match (e.g. `"yield 5X at tQ0"` against `q="5% at t_0"`);
  otherwise the test passes with the escaping deleted.
- A "hidden when zero" UI test must wait for the query to resolve (two-phase:
  show at N, refetch to 0, assert gone); asserting absence before the fetch
  passes vacuously.
- Frontend `onError` handlers on bulk mutations must invalidate and close the
  confirm, or a stale-id 404 under concurrent editing becomes a retry loop.
- Subagent implementers: `sonnet` floor; verify every DONE report with
  `git status`/`git log` before dispatching a reviewer; run the final
  whole-branch review on the most capable model — it found the two Important
  items the per-task reviews missed.
- `ExperimentNotes.note_text` is `Column(Text)` — nullable; zero NULL rows in
  practice. Do not write code that assumes NOT NULL, and do not call the NULL
  guard "impossible".
- A subagent can die mid-review on an expired login; re-dispatch it fresh,
  nothing is lost but the review.
