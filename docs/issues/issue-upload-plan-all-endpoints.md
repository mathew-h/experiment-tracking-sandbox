# Upload plan on every bulk-upload endpoint, not just New Experiments

**Type:** feat
**Area:** backend (`backend/services/bulk_uploads/` — **locked**, `backend/api/routers/bulk_uploads.py`), frontend (`BulkUploads.tsx`, `NewExperimentsUploadRow.tsx`)
**Priority:** medium
**GitHub issue:** #107
**Split from:** #100 (`issue-bulk-upload-dry-run.md`), acceptance criterion 1, which that issue closed without meeting in full

---

## Problem

#100 shipped the dry-run/preview machinery end to end, but only one of thirteen upload
types can actually show a researcher what a file would do.

Current state after #100:

| Capability | Coverage |
|---|---|
| `dry_run: bool = Form(False)` on the endpoint | **all 13** endpoints |
| `UploadResponse.plan` populated | **1** — `new-experiments` only; the other 12 return `plan: null` |
| `UploadResponse.plan_hash` | 1 — same |
| Conflicts reject the whole file | 1 — same |
| Preview-first UI | 1 row of 13 (`NewExperimentsUploadRow`); the other 12 use plain `UploadRow` and commit on drop |

So `dry_run=true` on, say, `scalar-results` rolls back correctly but hands back only
prose in `warnings` / `info_messages` — the same unstructured output the issue set out
to replace. There is nothing for a preview UI to render, which is why the other 12 rows
still commit on drop.

#100's final review judged shipping preview-first on 1 of 13 rows defensible on this
reasoning, which is worth carrying forward as the argument for why this issue is
*medium* and not *high*: New Experiments is the only endpoint that **creates identity or
renames it**. The other twelve upsert into an already-existing identity space and are
correctable by re-uploading a fixed file. The 2026-07-28 incident was only possible
because renames were involved.

## Why this is genuinely large

The plan schema shipped in #100 is written around `new_experiments.py`'s own concepts —
`renames` (`from_id`/`to_id` from the `old_experiment_id` column), `creates.parent_id`
and `creates.copied_from` (parent-copy lineage), and `overwrites.fields_changed`
diffed against `Experiment` + `ExperimentalConditions` columns. **None of the other
12 parsers have renames or parent-copy**, and several have no natural "fields changed"
diff at all. Each needs its own answer to "what are the row-level outcomes here, and
what old→new diff is worth showing?"

The parsers to extend, with sizes, all under the locked `backend/services/bulk_uploads/`:

| File | Lines | Notes |
|---|---:|---|
| `actlabs_titration_data.py` | 551 | already has a two-phase conflict/resolution preflight of its own — reconcile, don't duplicate |
| `rock_inventory.py` | 370 | upserts `SampleInfo`; diffable |
| `experiment_status.py` | 342 | **already has a dataclass preview** (`preview_status_changes_from_excel`) — closest existing precedent |
| `xrd_upload.py` | 326 | |
| `scalar_results.py` | 320 | already uses the `_ex` convention #100 borrowed |
| `quick_upload.py` | 311 | |
| `long_format.py` | 274 | |
| `master_bulk_upload.py` | 257 | **composes the others** — its plan must merge theirs, not reimplement |
| `timepoint_modifications.py` | 224 | |
| `aeris_xrd.py` | 211 | |
| `experiment_additives.py` | 162 | the per-compound additive diffing #100 explicitly scoped out belongs here |
| `metric_groups.py` | 165 | |
| `pxrf_data.py` | 134 | |
| `actlabs_xrd_report.py` | 138 | |
| `chemical_inventory.py` | 90 | smallest — a reasonable first one to do |

Roughly 3,500 lines of locked parser code across 14 files (13 endpoints; `actlabs-rock`
spans two).

## Proposal

Do **not** attempt all 13 in one pass, and do not generalize the schema speculatively.

1. **Decide the schema question first, as a written design step.** Either (a) generalize
   `UploadPlan` so `creates`/`overwrites`/`skips`/`conflicts` are common and
   rename/parent-copy stay `new-experiments`-specific optional fields, or (b) give each
   parser family its own plan type behind a discriminated union. Pick one before
   touching a parser; retrofitting the wrong choice across 12 files is the expensive
   mistake available here.
2. **Follow the shape #100 proved works** — it is the reason item 2 landed with zero
   breaking changes across ~26 callers of `bulk_upsert_from_excel`: extract the existing
   body into a private `_impl` returning the original tuple **plus** the plan, keep the
   original public function's signature byte-identical as a thin wrapper, and add an
   `_ex` variant that exposes the plan. Instrument the plan as a pure accumulator
   alongside `warnings` / `info_messages`; **do not touch matching or resolution logic.**
3. **Order by value, not by size:** `experiment_status.py` (already has a preview to
   reconcile), then `experiment_additives.py` (real overwrite diffs), then
   `rock_inventory.py` / `chemical_inventory.py` (simple upserts), then the rest.
   `master_bulk_upload.py` last, since it merges the others.
4. **Extend the plan gate and UI per endpoint as each parser lands** — reuse
   `_plan_gate_errors`, `UploadPlan.fingerprint()`, `UploadPlanPanel` and
   `UploadPlanModal` unchanged. Wrapping another row is then a matter of following
   `NewExperimentsUploadRow`, including its `onUploadSuccess` override.
5. **Remove the New-Experiments-only caveat** from the `BulkUploads.tsx` page subtitle
   and `docs/user_guide/BULK_UPLOADS.md` only once every row previews.

## Acceptance criteria

- [ ] A written schema decision (generalize vs. discriminated union) is recorded in this file before any parser is modified
- [ ] `dry_run=true` on every one of the 13 endpoints returns a non-null `plan` whose `counts` match its list lengths
- [ ] Every endpoint returns a `plan_hash`, and a plan that changed between preview and commit is refused
- [ ] Conflicts reject the whole file on every endpoint, not just `new-experiments`
- [ ] `master-results` merges the plans of the parsers it composes rather than producing its own parallel account
- [ ] All 13 rows in `BulkUploads.tsx` preview before committing, and the "New Experiments only" caveat is gone from the page subtitle and the user guide
- [ ] Every existing caller of every modified parser function is unchanged (the `_impl` + thin-wrapper pattern, verified by the existing suites passing untouched)
- [ ] Full backend suite green; `tests/api/test_bulk_uploads.py` and `tests/services/bulk_uploads/` pass with no edits to pre-existing assertions
- [ ] `frontend/src/pages/__tests__/BulkUploads.test.tsx` passes (it is the regression gate proving rows behave)

## Notes

- **`backend/services/bulk_uploads/` is locked** per `CLAUDE.md` §5 and
  `docs/LOCKED_COMPONENTS.md`. This issue modifies 14 files inside it and needs explicit
  user sign-off at `/start-task` scope confirmation, per parser pass, before code.
- This should almost certainly be a **milestone**, not a single issue session. Each
  parser is its own scoped change with its own tests; batching them into one branch
  makes review of locked code impractical.
- **Test-harness trap, still live:** `tests/api/conftest.py` binds its session to a
  connection with an outer transaction already open. A router `db.rollback()` discards
  the test's own seed rows, and a router `db.commit()` consumes the fixture transaction
  so teardown silently no-ops and **rows really land in `experiments_test`**. Any new
  commit-path API test needs its own cleanup fixture — see
  `tests/api/test_bulk_uploads_plan_gate.py` for the pattern, and the
  `api-test-router-commit-leaks-rows` note.
- **Pre-existing test defect to fix while in here** (found during #100 item 1, not
  fixed): `test_actlabs_rock_returns_upload_response_shape` patches `sys.modules` but
  the router imports `ActlabsRockTitrationService` eagerly at module load, so the patch
  never applies; `test_icp_oes_returns_upload_response_shape` mocks
  `bulk_create_icp_results` with a stale 2-tuple against the real 3-tuple signature.
  Both pass only via the generic `except Exception` fallback, so they assert nothing
  about the success path they name.
- The legacy Streamlit uploader (`legacy/streamlit_frontend/bulk_uploads.py`) calls
  `bulk_upsert_from_excel` directly and is covered by neither the plan gate nor the
  hash handshake. Decide explicitly whether it stays uncovered or gets retired.
- Related: `issue-bulk-rename-circular-dependency.md` — the rename row-ordering problem
  a plan makes diagnosable but does not fix.
- Also split from #100: #108 / `issue-serum-catalyst-rename-replay.md` (criterion 6, the
  incident-scale replay test).
