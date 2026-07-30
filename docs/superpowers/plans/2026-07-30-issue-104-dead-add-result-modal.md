# Issue #104 — `components/experiments/AddResultModal.tsx` is dead code

**Type:** chore · **Branch:** `chore/issue-104-remove-dead-addresultmodal` (cut from `develop`)
**Source spec:** `docs/issues/issue-dead-add-result-modal.md` (identical to GitHub #104)

---

## Context

`frontend/src/components/experiments/AddResultModal.tsx` (singular "Result") is unreachable.
It is imported by exactly one file — its own test. No page, route, or component mounts it.

The modal that actually ships is `frontend/src/pages/ExperimentDetail/AddResultsModal.tsx`
(plural "Results"), mounted at `ResultsTab.tsx:213`.

**Provenance (verified, not assumed).** The dead component was built by issue #8
(`docs/superpowers/plans/2026-03-25-issue-8-experiment-fk-result-writes.md`, commits
`1379675`, `fef1c1c`, `545c23e`) as a *structural demonstration* that a modal taking
`experimentPk: number` makes passing the URL string as `experiment_fk` impossible. The
demonstration was never wired into a page. Two later plans already noticed it was dead and
deliberately skipped it — issue #81 (Decision Point 10) and the #81 issue-log entry, which
also recorded the stale `['results', id]` invalidation as pre-existing.

## The modal diff — settled before any deletion

The live modal is strictly the stronger implementation:

| | dead `AddResultModal` | live `AddResultsModal` |
|---|---|---|
| Writes | `ExperimentalResults` only | result **+** `ScalarResults` (two-step POST) |
| Fields | description, day, primary checkbox | date, day, description, NH₄, H₂, gas pressure/volume, pH, conductivity, sampling mod |
| Unit handling | none | psi → MPa (`PSI_TO_MPA`) |
| Timepoint lock | none | issue #81 `-t<days>` lock + mismatch message |
| Required | description | date, day, description |
| Range checks | day is-a-number | day + 3 gas fields must be ≥ 0 |
| Server error | `error.message` | FastAPI `response.data.detail` |
| Cache key | `['results', …]` — **used by no `useQuery`** | `['experiment-results', …]` — correct |

**Two things exist only in the dead modal. Both are declined, not ported:**

1. **`is_primary_timepoint_result` checkbox.** Not a capability gap.
   `backend/api/schemas/results.py:20` declares `is_primary_timepoint_result: bool = True`,
   and `backend/api/routers/results.py:107-118` demotes any existing primary row in the same
   bucket ("newest wins"). The live modal omitting the field therefore produces exactly the
   outcome the dead modal's default-checked box produced. The only lost ability is
   *unchecking* it — which would create a hand-entered row silently excluded from
   `v_primary_experiment_results`. That is a footgun, not a feature.
2. **Per-field inline error placement** via the `Input` component's `error` prop, versus the
   live modal's single error banner. Presentational only; the live modal's validation is a
   strict superset. Porting it means restyling a working modal — outside this issue.

## Global Constraints

- **`npm run lint` has 6 pre-existing errors and cannot "pass" as the issue's criterion
  literally reads.** Measured on this branch before any change (2026-07-30):
  `CompoundFormModal.tsx:41,57` (rule `react-hooks/set-state-in-effect` not found ×2),
  `ExperimentDetail/AddResultsModal.tsx:96` (unused eslint-disable directive),
  `ConditionsTab.buttons.test.tsx:61,83` and `NotesTab.buttons.test.tsx:50`
  (`no-explicit-any` ×3). **None are in the two files being deleted.** The real standard:
  the count stays at exactly 6 and the file list is unchanged. Do not fix any of them —
  including the one in the live `AddResultsModal.tsx`. That is separate scope.
- **Deletion only.** Do not edit `AddResultsModal.tsx`, `ResultsTab.tsx`, or any other
  component. No behavior change ships on this branch.
- **Do not touch `DeleteExperimentModal.tsx:20`.** Its
  `['results', 'result timepoint', 'result timepoints']` is an `IMPACT_ROWS` label tuple,
  not a query key. The issue says explicitly: don't "fix" it.
- **Do not rewrite historical plan documents** under `docs/superpowers/plans/`. They are
  dated records of what was done at the time, not live documentation.
- Repo standards: `docs/CODE_STANDARDS.md`, `frontend/CLAUDE.md`. Never start or stop the
  Vite dev server.

---

## Task 1: Delete both files and verify nothing depended on them

**Files to delete:**
- `frontend/src/components/experiments/AddResultModal.tsx`
- `frontend/src/components/experiments/AddResultModal.test.tsx`

**Steps:**

1. **Re-confirm reachability before deleting.** From the repo root, search
   `frontend/src` for `AddResultModal`. Every hit must fall inside the two files above.
   A hit anywhere else means the premise is wrong — stop and report BLOCKED.
   Note that `AddResultsModal` (plural) is a *different, live* component: match carefully,
   since the singular name is a substring of the plural one. Report both hit lists.
2. **Capture the pre-deletion test baseline:** `cd frontend && npm run test`. Record the
   passed count and file count. Also record how many tests live in
   `AddResultModal.test.tsx` specifically (expected: 8).
3. Delete both files with `git rm`.
4. **Verify the deletion had no compile-time dependents:** `npm run type-check`
   (`tsc --noEmit`) must be clean. This is the real proof no source file imported the
   component.
5. **Re-run `npm run test`.** Expected: the same number of passing tests minus the deleted
   file's cases, and one fewer test file. Zero failures. If any *other* test fails, stop —
   that is a real dependency and the premise needs revisiting.
6. **Re-run `npm run lint`.** It will exit non-zero. Confirm the output is byte-identical in
   substance to the 6-error baseline in Global Constraints — same files, same rules, same
   count. Do not fix anything.
7. **Confirm the issue's query-key criterion.** Search `frontend/src` for `'results',`.
   The only remaining hit must be `DeleteExperimentModal.tsx:20`. Leave it alone.
8. **Commit** on the current branch:

```
[#104] Delete dead AddResultModal component

- AddResultModal.tsx + its test were reachable only from that test; no page
  or route mounted them. Built as a structural demo in #8 (1379675, fef1c1c)
  and never wired up. The live modal is
  pages/ExperimentDetail/AddResultsModal.tsx.
- Declined to port is_primary_timepoint_result: ResultCreate already defaults
  it True (schemas/results.py:20) and routers/results.py:107-118 demotes the
  prior primary in the bucket, so live behavior already matches the dead
  modal's default. Unchecking it would only create a row excluded from
  v_primary_experiment_results.
- Declined to port per-field inline error placement: presentational, and the
  live modal's validation is a strict superset (requires date + day, range
  checks 3 gas fields, honors the #81 -t timepoint lock, surfaces FastAPI
  detail).
- Removes the stale ['results', id] invalidation, a key no useQuery reads.
- Tests added: no (deletes 8 tests that covered nothing shipped)
- Docs updated: no
```

**Verification (report actual command output, not claims):**
- [ ] `AddResultModal` returns zero hits under `frontend/src`
- [ ] `npm run type-check` clean
- [ ] `npm run test` — zero failures; test count down by exactly the deleted file's cases
- [ ] `npm run lint` — still exactly the 6 baseline errors, same files/rules
- [ ] `'results',` search leaves only `DeleteExperimentModal.tsx:20`
- [ ] `git status` clean after commit; `git show --stat HEAD` shows exactly 2 deletions

---

## Task 2: Record the outcome in the local issue doc

**File to edit:** `docs/issues/issue-dead-add-result-modal.md`

The GitHub issue's acceptance criteria say "Both files removed, **or a written justification
recorded here**". Both were removed, so record that resolution in the local spec, matching
how `docs/issues/` files were annotated on issues #97 and #111 (a status blockquote at the
top, original problem text left intact below it).

**Steps:**

1. Add a status blockquote directly under the H1, before `**Type:** chore`. State: shipped
   2026-07-30 on branch `chore/issue-104-remove-dead-addresultmodal`; both files deleted;
   the two dead-only behaviors declined with the one-line reason for each (see the plan's
   modal-diff section — reuse that reasoning, do not invent new justifications).
2. Tick the four acceptance-criteria checkboxes, and annotate the lint one in place: it
   cannot pass literally — 6 pre-existing errors remain, unchanged and unrelated, none in
   the deleted files.
3. Add one line under `## Notes` recording a stale pointer left behind on purpose:
   `docs/superpowers/plans/2026-07-23-issue-70-p2-grouped-ui.md:1833` tells future test
   authors to mirror `AddResultModal.test.tsx` for its provider wrapper. That file is now
   gone — and the advice was already wrong, since the test used only
   `QueryClientProvider`, never the `ToastProvider` the pointer was about. Historical plan
   documents are deliberately not rewritten.
4. Leave the original Problem / Why it matters / Fix sections unchanged.
5. The `PostToolUse` hook syncs this file to `docs/project_context/` automatically — do not
   write there directly, and do not be surprised when it shows up in `git status`.
6. **Commit:**

```
[#104] Record #104 resolution in local issue doc

- Status blockquote, ticked criteria, lint-baseline caveat, stale-pointer note
- Tests added: no
- Docs updated: yes
```

**Verification:**
- [ ] `git status` clean after commit
- [ ] `git show --stat HEAD` includes both `docs/issues/issue-dead-add-result-modal.md` and
      its hook-synced `docs/project_context/` copy

---

## Out of scope — discovered, deliberately not fixed

1. `ExperimentDetail/AddResultsModal.tsx:96` carries an unused
   `eslint-disable-next-line react-hooks/exhaustive-deps` — one of the 6 baseline lint
   errors, and a one-line fix in the sibling live file. Not touched: this branch is a
   deletion, and editing the live modal would mean a behavior-adjacent change riding along
   with a chore.
2. The other 5 baseline lint errors (`CompoundFormModal.tsx` ×2, `no-explicit-any` ×3).
3. The live modal cannot create a non-primary result row at all. That is the pre-existing
   product behavior, not a regression introduced here.
