# `components/experiments/AddResultModal.tsx` is dead code

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

- [ ] Both files removed, or a written justification recorded here for keeping them
- [ ] Any behavior unique to the dead modal either ported to `AddResultsModal.tsx` or explicitly declined in the commit body
- [ ] `cd frontend && npm run test` and `npm run lint` pass
- [ ] `grep -rn "'results'," frontend/src` returns no query-key usages (the only remaining hit should be the `IMPACT_ROWS` label string in `DeleteExperimentModal.tsx:20`, which is display text, not a key)

## Notes

`DeleteExperimentModal.tsx:20` contains `['results', 'result timepoint', 'result timepoints']`
as part of `IMPACT_ROWS`. That is a label tuple, not a query key. Don't "fix" it.
