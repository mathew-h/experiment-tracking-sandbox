# Bulk-upload preview-first UI — design

**Date:** 2026-07-29
**Issue:** [#100](https://github.com/mathew-h/experiment-tracking-sandbox/issues/100), items 6–9
**Scope:** frontend only — no backend file is modified
**Branch:** `feat/issue-100-preview-ui`

---

## Context

Items 1–5 of issue #100 shipped in four prior passes (`dbf959d`, `b2b4eab`, `9b14d65`,
`5d342e0`). The backend now has everything needed for a safe preview:

- `dry_run: bool = Form(False)` on all 13 `POST /api/bulk-uploads/*` endpoints — the
  parser runs in full, the router rolls back instead of committing.
- A structured `UploadPlan` (`creates` / `renames` / `overwrites` with `fields_changed` /
  `skips` / `conflicts` / `counts`) on `UploadResponse.plan`, populated for
  `new-experiments` only.
- Any conflict in the plan rejects the **whole** file, returning HTTP 200 with zeroed
  counts, one `errors` entry per conflict, and the plan still fully populated.
- `UploadResponse.plan_hash` — a sha256 over the five plan lists. Passing it back as a
  `plan_hash` form field on the real submit requires the freshly computed plan to match.
  Verified-when-supplied, not required.

**None of it is reachable from the app.** A researcher still cannot ask "what would this
file do?" before it commits — which is the entire point of the issue. This design closes
that gap.

## Goals

Issue items 6–9:

6. Preview is the default path for New Experiments: upload renders the plan, and a
   "Commit N changes" button submits with the plan hash.
7. The plan renders as grouped, colour-coded sections with counts in the headers.
   Conflicts first and expanded; creates collapsed by default.
8. `fields_changed` diffs render inline for overwrites — old struck through, new bold.
9. Commit is disabled entirely while conflicts are present.

## Non-goals

- **A plan on the other 12 endpoints** (acceptance criterion 1 in full). They return
  `plan: null` and keep today's one-shot behaviour. Generalising the plan schema across
  12 more locked parsers is a separate, much larger effort.
- **Per-compound additive diffing.** The backend summarises additives as
  `"N additive(s)" → "M additive(s) provided"`; the UI cannot show more than it is given.
- **Any backend change.** No file under `backend/` or `database/` is touched, so no
  CLAUDE.md §5 locked-component sign-off is required.
- **Raising `BulkUploadRow`'s `max-h-[900px]` cap.** The plan lives in a modal, whose
  body is already `flex-1 overflow-y-auto` inside `max-h-[85vh]`.

## Decisions

Four decisions were settled with the product owner before design, each with the
alternatives that were rejected.

### D1 — Preview is mandatory, and only on New Experiments

Dropping a file on the New Experiments row **always** previews. The only path that writes
is the Commit button. There is no "skip preview" affordance.

*Rejected:* an opt-out checkbox (leaves reachable the exact bypass that caused the
2026-07-28 incident, and costs a second code path); preview on all 13 rows (12 of them
have no plan, so their preview would show only counts and warnings — a click for
near-zero information).

### D2 — The plan is reviewed in a modal, not inline in the row

Preview opens a dedicated review modal. Commit and Cancel live in its footer.

This follows `DeleteExperimentModal`, the codebase's established "review before a
destructive action" pattern, and it gets real screen space: the 2026-07-28 incident
workbooks carried 80 renames each. It also sidesteps the fact that `BulkUploadRow`'s
expanded panel is `max-h-[900px] overflow-hidden` — an 80-row plan rendered inline would
be **silently clipped**, with content simply absent and no scrollbar to hint at it.

*Rejected:* inline rendering in the expanded row (needs the cap replaced with an internal
scroll region, and makes the page very tall).

### D3 — A stale plan requires explicit re-arming

When Commit is rejected because the plan changed since preview, the modal shows an amber
banner, swaps in the **new** plan, and keeps Commit disabled until the researcher ticks
*"I've reviewed the updated plan"*.

The hash gate exists so that nobody commits a plan they have not looked at.
Auto-re-arming Commit with the new hash would let a reflexive second click do exactly
that, which defeats the mechanism.

*Rejected:* re-arm immediately (one fewer interaction, but restores the failure mode);
discard and force a re-drop (throws away a plan the server already computed and hides
what changed).

### D4 — The commit outcome is shown in the modal, not the row

After a successful commit the modal switches to a result view (counts, errors, warnings)
with a Close button, rather than pushing the result back into the row's summary badges.

The outcome lands in the same focused surface where it was approved. This is also what
keeps the `UploadRow` change to a single prop: the row never needs to render a
controlled result.

## Architecture

A wrapper component owns the two-phase state; `UploadRow` stays generic. This mirrors
`ActlabsUploadRow.tsx`, which already wraps `UploadRow` for its conflict-resolution flow.

| File | Change | Role |
|---|---|---|
| `src/api/bulkUploads.ts` | edit | TS mirror of the plan schema; `dryRun` / `planHash` options |
| `src/components/bulkUploads/UploadPlanPanel.tsx` | new | Pure presentational plan renderer |
| `src/components/bulkUploads/UploadPlanModal.tsx` | new | Review surface — three views, Commit gating, re-arm |
| `src/pages/NewExperimentsUploadRow.tsx` | new | State owner: preview mutation, commit mutation, stale detection |
| `src/pages/BulkUploadRow.tsx` | edit | One new optional prop, `onUploadSuccess` |
| `src/pages/BulkUploads.tsx` | edit | Swap the wrapper in for the New Experiments row |

### Unit boundaries

- **`UploadPlanPanel`** — given an `UploadPlan`, renders it. No data fetching, no
  mutation, no knowledge of commit. Its only state is which sections are expanded.
  Independently testable against a literal plan object.
- **`UploadPlanModal`** — given a plan, a view state, and callbacks, renders the review
  surface. Owns only its local re-arm checkbox and delegates all async work upward.
- **`NewExperimentsUploadRow`** — owns every mutation and all async state. The only unit
  that talks to the API.

### The single `UploadRow` change

`UploadRow` gains `onUploadSuccess?: (data: BulkUploadResult | ConflictCheckResult) => void`.
When supplied, the row delegates instead of setting its own `result` state and firing its
own toast.

This is necessary, not cosmetic: **a dry run returns real counts.** The parser genuinely
creates, updates and flushes before the router rolls back, so a preview response carries
`created: 5, updated: 2`. Without this prop, today's row would badge "Created: 5" and
toast "Upload complete — 5 created" for an upload that persisted nothing.

The prop is symmetric with the `onUploadError` override the component already has
(`BulkUploadRow.tsx:50`). The other 11 rows supply neither and are behaviourally
untouched.

## Data flow

```
drop file → POST /bulk-uploads/new-experiments  dry_run=true
          → 200 { plan, plan_hash, dry_run:true }        → modal opens in `review`

Commit    → POST /bulk-uploads/new-experiments  plan_hash=<the previewed hash>
          → 200 committed { created, updated, skipped }  → `done`
          → 200 rejected  { 0,0,0, errors[], fresh plan + fresh hash } → `stale`
```

Both requests send the same in-memory `File`. Because the preview rolled back, the commit
re-parse sees identical DB state and recomputes an identical plan — so the hash matches
in the normal case.

### Discriminating the three 200 responses

The endpoint returns HTTP 200 for success, gate rejection, **and** parser crash, so the
body has to be read. The test must be **structural**, mirroring the only two things that
populate `_plan_gate_errors` (`bulk_uploads.py:68`) — a conflict, or a hash mismatch:

```ts
const rejected =
  res.plan != null &&
  (res.plan.conflicts.length > 0 || (sentHash != null && res.plan_hash !== sentHash))
```

| Condition | Meaning | UI |
|---|---|---|
| `plan == null` | parser crash (`bulk_uploads.py:189`) | toast, no modal |
| `rejected` per above | gate rejection | `stale` |
| otherwise | committed | `done` |

**Do not test on `errors.length > 0`.** The success path returns the parser's own row-level
`errors` alongside a real commit (`bulk_uploads.py:211`), so a file that committed 8 rows
and errored on 2 has non-empty `errors` *and* a non-null `plan` — testing on `errors`
would report "Nothing was applied" for an upload that applied 8 rows. Nor are the
all-zeros counts a discriminator: a file whose every row errored also commits as `0,0,0`.

Parser row errors are therefore surfaced in the `done` view, not treated as a rejection.

## The three modal views

**`review`** — `UploadPlanPanel` plus a footer of `Cancel` / `Commit N changes`, where
N is the total of creates + renames + overwrites. Commit is disabled whenever
`plan.conflicts.length > 0` (item 9), with the reason stated beside it. Conflicts are not
an error state: the plan renders in full so the researcher can see what to fix in the
workbook.

**`stale`** — `review` plus an amber banner reading *"Nothing was applied — the plan
changed since you previewed it"*, the new plan swapped in, and a required *"I've reviewed
the updated plan"* checkbox that arms Commit. The tick resets on every new stale
response. If the new plan carries conflicts, the conflict gate still wins and Commit
stays disabled regardless of the checkbox.

**`done`** — final `created` / `updated` / `skipped` counts, plus the `errors` and
`warnings` lists; footer is a single `Close`.

## Plan panel

Five sections in fixed order: **conflicts, renames, overwrites, creates, skips**. Each
header carries its count. Conflicts start expanded, every other section collapsed
(item 7). Empty sections are omitted entirely rather than rendered as "0".

Each section truncates at **10 rows** with a "Show N more" toggle — the pattern
`BulkUploadRow.tsx:199` already uses at 5, loosened because a modal has more room.

Overwrites render each `fields_changed` entry as `field:` then the old value struck
through, an arrow, and the new value in bold (item 8). This is where the issue's own
`initial_ph` 4 → 9 example becomes visible.

Colours reuse the existing `Badge` variants and the `bg-<colour>-500/5
border-<colour>-500/20` idiom already used in `BulkUploadRow`: conflicts red, renames
blue, overwrites amber, creates green, skips grey. No new hex values, per
`frontend/CLAUDE.md`.

## Error handling

| Failure | Behaviour |
|---|---|
| Preview HTTP/network error | Existing `UploadRow` `onError` toast; modal never opens |
| Preview returns errors with no plan (crash) | Toast the error; modal never opens |
| Commit HTTP/network error | Toast; modal stays on `review` so the plan is not lost |
| Commit rejected by the gate | `stale` view per D3 |
| Plan contains conflicts | Commit disabled with the reason shown; plan still fully rendered |

## Testing

vitest, in `src/components/bulkUploads/__tests__/` and `src/pages/__tests__/`:

**`UploadPlanPanel`** — section order; counts in headers; conflicts expanded and creates
collapsed by default; `fields_changed` renders old and new; truncation at 10 with a
working "Show N more"; empty sections omitted.

**`UploadPlanModal`** — Commit disabled when conflicts are present and enabled when not;
the stale banner renders and its checkbox arms Commit; a stale plan **with** conflicts
leaves Commit disabled even when the box is ticked; `done` shows counts, errors and
warnings.

**`NewExperimentsUploadRow`** — a file drop sends `dry_run=true` and never commits;
Commit sends the hash that came back from the preview; a conflict response renders
`stale` and does **not** toast success; a response whose `plan_hash` differs from the one
sent renders `stale`; a successful commit invalidates `['nextIds']`.

One test exists specifically to pin the discriminator defect found during spec review: a
**committed** response carrying parser row `errors` (e.g. 8 created, 2 rows errored) must
render `done` with those errors listed — never `stale`.

The `['nextIds']` invalidation is a live bug being fixed in passing: creating experiments
moves the next-ID chips, and today nothing invalidates that key after an upload, so the
chips (`staleTime: 60_000`) can sit stale for a minute.

**Regression** — the existing `BulkUploads.test.tsx` must pass unchanged, which is what
proves the other 12 rows still commit in one shot.

**E2E** — `frontend/e2e/journeys/02-bulk-upload-experiments.spec.ts:26` waits for
`Created:` badges immediately after the file drop. Preview-first breaks that
assertion; the spec is rewritten to drop → assert the modal → Commit → assert counts.

**Manual** — Chrome DevTools closed loop against the running app (explicitly enabled for
this task), covering the clean-preview → commit path and the conflict-blocked path. The
issue-log entries for #99 record two real defects that the 152-test suite missed and only
a manual walkthrough caught, so this is not optional polish.
