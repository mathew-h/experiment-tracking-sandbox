# Bulk upload dry-run: show create / rename / overwrite plan before committing

**Type:** feat
**Area:** backend (`backend/services/bulk_uploads/`, `routers/bulk_uploads.py`), frontend (`BulkUploads.tsx`, `BulkUploadRow.tsx`)
**Priority:** high
**Status:** CLOSED 2026-07-29 — all 9 proposal items shipped; 2 acceptance criteria split out to #107 and #108

---

## Closure (2026-07-29)

All nine numbered proposal items below shipped and merged to `develop`. Five of the
seven acceptance criteria are met. The remaining two were split into their own issues
rather than held open under this one, on the user's call.

**Shipped, in order:**

| Item | What | Merged |
|---|---|---|
| 3 | explicit conflict on `old_experiment_id` with falsy `overwrite` (per-row skip) | `dbf959d` |
| 1 | `dry_run: bool = Form(False)` on all 13 endpoints; router decides commit-vs-rollback | `b2b4eab` |
| 2 | structured `UploadPlan` with `fields_changed`, `new-experiments` only | `9b14d65` |
| 4, 5 | conflicts reject the whole file; `plan_hash` preview→commit handshake | `5d342e0` |
| 6–9 | preview-first New Experiments UI (`UploadPlanPanel`, `UploadPlanModal`, `NewExperimentsUploadRow`) | `0b122b8` |

**Acceptance criteria at close:** 2, 3, 4, 5 and 7 met. Criterion 1 met only in part
(`dry_run` on all 13 endpoints, `plan` on 1) → **#107**
(`issue-upload-plan-all-endpoints.md`). Criterion 6 (SERUM_Catalyst replay) unmeetable
as worded — both workbooks are gitignored and absent, the only dump on disk predates the
incident by two months, and the old→new ID mapping is recorded nowhere → **#108**
(`issue-serum-catalyst-rename-replay.md`), which documents what *is* recoverable.

**Two decisions worth carrying forward:**

- **`plan_hash` is verified-when-supplied, not required** (deviation from item 5's
  wording, user-confirmed). Requiring it unconditionally would break every existing
  caller and contradict criterion 7. The UI always sends it, so the preview path gets
  the full guarantee at zero blast radius. A side effect stronger than the stated
  intent: because `overwrites[].fields_changed` records current DB values as `old`, the
  fingerprint covers **database state as well as file bytes** — it also catches another
  researcher editing the underlying experiments between preview and commit.
- **The endpoint returns HTTP 200 for success, gate rejection *and* parser crash**, so
  the client discriminates structurally on
  `plan.conflicts.length > 0 || plan_hash !== sentHash`. It deliberately does **not**
  key on `errors.length > 0`: the success path returns the parser's own row-level errors
  alongside a real commit, so an `errors`-based check would report "nothing was applied"
  about a file that applied 8 of 10 rows.

**One process lesson, from three defects reviews caught in items 6–9:** the spec
specified UI *views* without enumerating which response fields the server actually
populates and where each surfaces. `new_experiments.py` has ~30 `warnings.append` sites
against 5 plan-recording sites, so the plan does not mirror the warnings — an ignored
additives sheet was invisible at preview, and a missing `experiments` sheet returned an
error with a non-null *empty* plan offering an enabled "Commit 0 changes". For the next
spec against a 200-for-everything endpoint, write the field-by-field table at design
time.

**Known gaps at close, not covered by #107 or #108:**

- The legacy Streamlit uploader (`legacy/streamlit_frontend/bulk_uploads.py`) calls
  `bulk_upsert_from_excel` directly and is covered by neither the plan gate nor the hash
  handshake.
- Playwright `02-bulk-upload-experiments.spec.ts` cannot execute on any clean checkout —
  its fixture `docs/sample_data/new_experiments_template.xlsx` is gitignored and absent.
  Pre-existing; documented in a comment at the top of the spec.
- On a conflict preview the same message renders three times (server `errors`, server
  `warnings`, and the plan's `conflicts` section) because it arrives in three response
  fields. Repetitive, not wrong.

---

## Problem

Bulk uploads commit on submit. The researcher sees the outcome only after the database
has already changed, in a flat list of `info_messages` and `warnings` mixed together.
There is no way to ask "what would this file do?"

The failure mode this enables is silent duplication. `new_experiments.py:233` gates the
rename path on `old_experiment_id AND overwrite_flag`:

```python
if old_experiment_id and overwrite_flag:
    # match on old_experiment_id, then rename
else:
    # standard normalized matching on the NEW experiment_id
```

If `overwrite` is blank, `FALSE`, or any string outside `{"1","true","yes","y"}`
(`parse_bool`, `new_experiments.py:143-148`), the `old_experiment_id` column is
**silently ignored** and every row falls through to the else branch. The new ID is not
found, so each row is created as a brand-new experiment. The upload reports success.
The INSTRUCTIONS sheet documents this as intended behavior ("silently ignored and the
row is processed as a standard lookup"), which makes it a documented trap rather than
a bug, but a rename sheet turning into a create sheet with zero warnings is not a
recoverable design given there is no delete UI (see
`issue-experiment-deletion-ui.md`).

### Incident, 2026-07-28

Two rename workbooks (`20260728_SERUM_catalyst_001_006_renamed.xlsx`,
`20260728_SERUM_catalyst_007_010.xlsx`) were intended to renumber 80 vials from a
sequential scheme into the planned `SERUM_Catalyst_001-010` array with a/b/c replicates
and `-t1/-t3/-t7/-t20` timepoints. Instead of 80 renames, the result was 80 creations
alongside the 80 originals: 149 rows in the database (80 + 80 with 11 IDs common to
both numbering schemes).

Those 11 collision IDs are the expensive part. `SERUM_Catalyst_003a-t7` exists in the
old scheme as copper/pH 4 and in the new scheme as nickel/pH 9. A single row now carries
one of the two, and determining which required a purpose-built verification script
(`scripts/sql/verify_serum_catalyst_target_state.sql`). A dry-run would have printed
`CHAIN RENAME CONFLICT` or `CREATE (80 new)` and the upload would never have run.

The chain-rename guard at `new_experiments.py:250-271` already detects exactly this
class of collision and emits a detailed warning — but only *during* the commit, and it
`continue`s past the row, leaving a partial result. The detection logic exists; it just
runs too late to be useful.

---

## Proposal

### Backend

0. **Shipped ahead of the rest of this issue (2026-07-29, issue #100 narrow scope):**
   item 3 below — `new_experiments.py`'s experiments-sheet loop now has a dedicated
   `elif old_experiment_id and not overwrite_flag` branch that appends the conflict
   message and `continue`s past the row (added to `failed_experiment_ids`) instead of
   falling through to standard matching and creating a duplicate. This is a per-row
   skip, not the file-level reject described in item 4 below — a workbook with some
   good rows and one blank-overwrite row will still commit the good rows and skip only
   the conflicting one. Items 1, 2, 4, 5 (dry_run plumbing, structured `plan`,
   file-level rejection, plan-hash check) and the frontend items 6-9 are still open.
   Test: `tests/services/bulk_uploads/test_new_experiments.py::test_old_experiment_id_without_overwrite_conflicts_not_creates`.

0.5. **Item 1 shipped (2026-07-29):** every `POST /api/bulk-uploads/*` endpoint in
   `backend/api/routers/bulk_uploads.py` now accepts `dry_run: bool = Form(False)`.
   No parser file changes were needed — the parsers already run their full create/
   update/flush logic to produce real counts and warnings; `dry_run` only changes
   whether the router calls `db.commit()` or `db.rollback()` afterward (helpers
   `_finalize_write`/`_finalize_message` at the top of the router). `UploadResponse`
   gained a `dry_run: bool = False` field and the message is prefixed `[DRY RUN]`.
   `actlabs-rock` needed care: it has three outcomes, not two — Phase 1 preflight-only
   (no conflicts found is NOT the same as "no write": a conflict-free preflight falls
   straight through to `import_excel` + commit in the same request), Phase 1 with
   conflicts (`ConflictCheckResponse`, never writes), and Phase 2 (resolutions
   supplied). `dry_run` applies to both of the first and third; the conflict-response
   path is unaffected since it never writes regardless.
   Discovered along the way (documented, not fixed — pre-existing, out of scope):
   two of the *existing* API-level shape tests were silently testing only their
   exception-fallback path rather than the mocked success path — `actlabs-rock`'s
   test patches `sys.modules`, but `ActlabsRockTitrationService` is imported eagerly
   at router module load time (not lazily inside the endpoint like every other
   service here), so the patch never reaches it; `icp-oes`'s test mocks
   `bulk_create_icp_results` with a stale 2-tuple against the real 3-tuple signature
   from the M8 return-value change. Both "passed" only because the generic
   `except Exception` fallback still satisfies the loose shape assertion. My new
   `dry_run` tests for those two endpoints use the correct mock target/shape so they
   actually exercise the intended path.
   Tests: `tests/api/test_bulk_uploads.py`, 14 new tests (13 endpoints + one flagship
   real round-trip against `new-experiments` proving no row persists with
   `dry_run=true`). Full backend suite: 880 passed, no regressions.

0.6. **Item 2 shipped (2026-07-29), scoped to `new-experiments` only:** the plan
   schema (`creates`/`renames`/`overwrites` with `fields_changed`) is written around
   `new_experiments.py`'s own concepts (rename via `old_experiment_id`, parent-copy,
   overwrite-diffing) — none of the other 12 parsers have renames or parent-copy, and
   most have no natural "fields changed" diff either, so generalizing the schema to
   all 13 upload types was explicitly deferred as a separate, much larger effort.
   `new_experiments.py` gained `PlanCreate`/`PlanRename`/`FieldChange`/`PlanOverwrite`/
   `PlanSkip`/`PlanConflict`/`UploadPlan` dataclasses (mirroring the existing
   `experiment_status.py` dataclass-preview pattern) and a `bulk_upsert_from_excel_ex`
   entry point returning the original 6-tuple plus `plan`. The existing
   `bulk_upsert_from_excel` keeps its exact signature/behavior — its body was extracted
   into a private `_bulk_upsert_from_excel_impl` that both public methods call, so
   **none of its ~26 existing callers needed to change**. `backend/api/schemas/
   bulk_upload.py` gained a Pydantic mirror (`UploadPlan`/`PlanCreate`/etc.) and
   `UploadResponse.plan: Optional[UploadPlan] = None`; the router converts the
   dataclass to the schema via `_plan_to_schema()`, keeping the service layer free of
   API/Pydantic concerns. Only `new-experiments` populates `plan`; every other upload
   type returns `plan: null`.
   `fields_changed` merges diffs from the experiments sheet (`sample_id`, `researcher`,
   `status`, `date`) and the conditions sheet (any updatable `ExperimentalConditions`
   column — this is where the issue's own `initial_ph` 4→9 example lives) into one
   `PlanOverwrite` per `experiment_id`, keyed across both sheet-processing loops via a
   shared `overwrite_plan_by_exp_id` dict. A brand-new conditions row (no prior value)
   is never diffed — there's nothing to have silently overwritten. Renames are reported
   separately (`from_id`/`to_id` only, no `fields_changed`) even though the same code
   path that performs a rename also updates the other four experiments-sheet fields —
   diffing those alongside a rename was judged not useful (the ID change is the
   headline event) and was explicitly scoped out. Additives are a single summary line
   per experiment (`"N additive(s)"` → `"M additive(s) provided"`), not per-compound
   diffed — full additive diffing needs a pre-delete snapshot and was scoped out as
   lower-value, higher-effort for this pass.
   Tests: new `tests/services/bulk_uploads/test_new_experiments_plan.py` (13 tests:
   create, sequential-create parent/copied_from, rename-not-overwrite, experiments-
   field diff, conditions-field diff (the `initial_ph` case), conditions-only overwrite
   with no experiments-sheet diff, brand-new-conditions-not-diffed, skip, three
   conflict kinds, multi-row counts-match-lengths, and a
   bulk_upsert_from_excel-vs-`_ex` parity check); one new API-level test proving the
   plan reaches `UploadResponse.plan` through the real (unmocked) service. Full backend
   suite: 903 passed, no regressions.
   Caught during test-writing: my first draft of the test IDs (`HPHT_PLAN_0NN`)
   accidentally triggered the 3-part `Type_Initials_Index` ID grammar — the parser read
   `"PLAN"` as researcher initials and auto-populated a real (unintended) `researcher`
   field change, breaking the "brand-new conditions is not diffed" and multi-row-counts
   tests. Renamed to 2-part IDs (`HPHT_9NNN`) to avoid the collision — not a bug in the
   plan logic, a test-fixture-naming footgun worth remembering for future ID-parser-
   adjacent tests in this file.

1. Add `dry_run: bool = False` to every `POST /api/bulk-uploads/*` endpoint in
   `backend/api/routers/bulk_uploads.py`. When true, run the full parse and resolution
   inside a transaction that is unconditionally rolled back.
2. Extend `UploadResponse` with a structured `plan` field instead of relying on prose
   in `info_messages`:

   ```
   plan: {
     creates:    [{ row, experiment_id, parent_id, copied_from }],
     renames:    [{ row, from_id, to_id }],
     overwrites: [{ row, experiment_id, fields_changed: [{field, old, new}] }],
     skips:      [{ row, experiment_id, reason }],
     conflicts:  [{ row, kind, detail }],
     counts:     { creates, renames, overwrites, skips, conflicts }
   }
   ```

   `fields_changed` is the highest-value part: an overwrite that silently changes
   `initial_ph` from 4 to 9 is invisible today.
3. Emit an explicit conflict (not a silent fallthrough) when `old_experiment_id` is
   populated but `overwrite` is falsy:
   `Row N: old_experiment_id='X' provided but overwrite is not TRUE. This row would
   CREATE '<new_id>' rather than rename 'X'. Set overwrite=TRUE to rename.`
   This one message would have prevented the incident on its own and is worth shipping
   ahead of the rest of this issue.
4. Reject the whole file when the plan contains conflicts, rather than skipping rows
   and committing the remainder. Partial application is what turned one mistake into a
   149-row reconciliation.
5. Refuse an upload whose plan differs from the previewed plan. Return a hash of the
   plan with the dry-run response and require it on the real submit, so a file edited
   between preview and commit cannot slip through.

### Frontend

6. In `BulkUploads.tsx` / `BulkUploadRow.tsx`, make preview the default path: upload
   renders the plan, and a "Commit N changes" button submits with the plan hash.
7. Render the plan as grouped, color-coded sections with counts in the headers.
   Conflicts first and expanded; creates collapsed by default.
8. Show `fields_changed` diffs inline for overwrites (old struck through, new bold).
9. Disable commit entirely while conflicts are present.

---

## Acceptance criteria

- [~] `dry_run=true` on every bulk upload endpoint returns a plan and leaves the database byte-identical (verify with a row-count and `max(updated_at)` check before/after) — **partial:** `dry_run` and the byte-identical guarantee on all 13; `plan` on `new-experiments` only → **#107**
- [x] A rename workbook with `overwrite` blank produces a conflict naming both IDs, and commit is blocked
- [x] A rename workbook with `overwrite=TRUE` and a genuine target collision reports `CHAIN RENAME CONFLICT` at preview time, with the suggested row ordering
- [x] Overwrite rows list every changed field with old and new values
- [x] Editing the file between preview and commit fails the plan-hash check
- [ ] Replaying the two 2026-07-28 SERUM_Catalyst workbooks against a snapshot of the pre-incident database yields a plan of 80 renames and 0 creates — **unmeetable as worded** (workbooks and pre-incident snapshot both absent) → reconstructed equivalent in **#108**
- [x] Existing bulk upload tests pass unchanged with `dry_run` defaulting to false

## Notes

- `backend/services/bulk_uploads/` parser logic is **locked** per `CLAUDE.md` §5 and
  `docs/LOCKED_COMPONENTS.md`. This issue modifies it and needs explicit sign-off before
  work starts. The safest shape is to add the plan as an accumulator alongside the
  existing `warnings` / `info_messages` lists and gate all writes behind a
  `if not dry_run:` check, leaving matching and resolution logic untouched.
- `master_bulk_upload.py` composes the other parsers; its plan needs to merge theirs
  rather than reimplement.
- Related: `issue-bulk-rename-circular-dependency.md` covers the row-ordering problem
  in renames. A dry-run makes that issue diagnosable but does not fix it.
