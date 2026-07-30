# `components/experiments/AddResultModal.tsx` is dead code

> **Status 2026-07-30 — SHIPPED on `chore/issue-104-remove-dead-addresultmodal`.**
> Both files deleted: `frontend/src/components/experiments/AddResultModal.tsx` and
> `AddResultModal.test.tsx`. Two dead-only behaviors considered for porting to the live
> `AddResultsModal.tsx` and both declined:
> - The `is_primary_timepoint_result` checkbox — not a capability gap. The backend already
>   defaults `is_primary_timepoint_result: bool = True`
>   (`backend/api/schemas/results.py:20`) and demotes any existing primary row in the same
>   timepoint bucket, "newest wins" (`backend/api/routers/results.py:107-118`). The live
>   modal omitting the field already produces what the dead modal's default-checked box
>   produced; the only lost ability is *unchecking* it, which would silently exclude a
>   hand-entered row from the `v_primary_experiment_results` reporting view — a footgun,
>   not a feature.
> - Per-field inline error placement via the `Input` component's `error` prop, versus the
>   live modal's single error banner — presentational only. The live modal's validation is
>   a strict superset (measurement date and day required, three gas fields range-checked,
>   the issue #81 `-t<days>` timepoint lock honored, FastAPI's `detail` surfaced on error).

**Type:** chore
**Area:** `frontend/src/components/experiments/`
**Priority:** medium

---

## Problem

The dead `['results', id]` invalidation at
`frontend/src/components/experiments/AddResultModal.tsx:57` is a symptom, not the bug.
The whole component is unreachable.

`AddResultModal` is imported by exactly one file: its own test,
`components/experiments/AddResultModal.test.tsx`. No page, route, or component mounts it.

The modal that actually runs is `pages/ExperimentDetail/AddResultsModal.tsx` — note the
plural "Results" — and it invalidates the correct key at line 131:

```ts
queryClient.invalidateQueries({ queryKey: ['experiment-results', experimentId] })
```

The dead component invalidates `['results', experimentStringId]`. That key is used by no
`useQuery` in the codebase; the live results key is `['experiment-results', experimentId]`.
So the stale-key defect is real, but fixing the key would just make dead code slightly
less wrong.

## Why it matters

The test file passes, which makes the component look maintained. It will keep showing up
in greps, keep being read as a reference implementation, and keep diverging from the real
modal. It is also a trap for exactly the kind of investigation that produced this list:
someone finds the dead invalidation, "fixes" the key, and ships a no-op.

## Fix

1. Confirm reachability once more (`grep -rn "AddResultModal" frontend/src` should return
   only the component and its test), then delete both:
   - `frontend/src/components/experiments/AddResultModal.tsx`
   - `frontend/src/components/experiments/AddResultModal.test.tsx`
2. Before deleting, diff the two modals. If the dead one contains validation or field
   handling the live one lacks, port it across first and note what moved in the commit
   body. Do not delete a better implementation because it is the unmounted one.
3. Re-run the frontend suite. Coverage will drop by whatever the deleted test covered;
   that is correct, since it was covering nothing that ships.

## Acceptance criteria

- [x] Both files removed, or a written justification recorded here for keeping them
- [x] Any behavior unique to the dead modal either ported to `AddResultsModal.tsx` or explicitly declined in the commit body
- [x] `cd frontend && npm run test` and `npm run lint` pass — **`npm run test` passes; `npm run lint` cannot pass literally.** It runs with
      `--max-warnings 0` and already failed on this branch before this change, with exactly
      6 pre-existing errors, none in the deleted files: `CompoundFormModal.tsx:41,57`
      (rule `react-hooks/set-state-in-effect` was not found, ×2); `pages/ExperimentDetail/AddResultsModal.tsx:96`
      (unused eslint-disable directive); `ConditionsTab.buttons.test.tsx:61,83` and
      `NotesTab.buttons.test.tsx:50` (`@typescript-eslint/no-explicit-any`, ×3). After the
      deletion the set is unchanged — same 6 errors, same files, same rules. None fixed here;
      that is deliberate, out-of-scope cleanup (see
      `docs/superpowers/plans/2026-07-30-issue-104-dead-add-result-modal.md`, "Out of scope"
      section).
- [x] `grep -rn "'results'," frontend/src` returns no query-key usages (the only remaining hit should be the `IMPACT_ROWS` label string in `DeleteExperimentModal.tsx:20`, which is display text, not a key)

## Notes

`DeleteExperimentModal.tsx:20` contains `['results', 'result timepoint', 'result timepoints']`
as part of `IMPACT_ROWS`. That is a label tuple, not a query key. Don't "fix" it.

`docs/superpowers/plans/2026-07-23-issue-70-p2-grouped-ui.md:1833` tells future test
authors to mirror `AddResultModal.test.tsx` for its provider wrapper pattern. That file is
now deleted, and the advice was already wrong before deletion — the test used only
`QueryClientProvider`, never the `ToastProvider` the pointer was about. Left as-is;
historical plan documents are dated records, not live docs.
