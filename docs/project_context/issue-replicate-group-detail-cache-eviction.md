# `['replicate-group-detail', baseId]` survives experiment deletion

**Type:** fix
**Area:** `frontend/src/pages/ExperimentDetail/index.tsx`
**Priority:** high
**Related:** issue #99 (experiment deletion)

---

## Problem

`PER_EXPERIMENT_QUERY_KEYS` (`frontend/src/pages/ExperimentDetail/index.tsx:31-45`) is
the eviction list applied after a successful delete. It contains `'replicate-group'` but
not `'replicate-group-detail'`:

```ts
const PER_EXPERIMENT_QUERY_KEYS = [
  'experiment', 'delete-impact', 'conditions', 'additives',
  'experiment-results', 'changeRequests', 'reactorModificationRecent',
  'xrd', 'external-analysis', 'replicate-group',
] as const
```

React Query matches keys element-by-element, not by string prefix. `['replicate-group']`
therefore does **not** match `['replicate-group-detail', baseId]` — they are two
unrelated first elements. No `invalidateQueries`, `removeQueries`, or `resetQueries`
call anywhere in `frontend/src` references `'replicate-group-detail'`.

Two live queries use that key:

- `pages/ReplicateGroup/index.tsx:275` — `['replicate-group-detail', baseId]`
- `pages/ExperimentDetail/GroupedResultsView.tsx:52` — `['replicate-group-detail', baseExperimentId]`

## Impact

Delete a vial from a replicate set, then open that set's group page. The members table,
`member_count`, `replicate_count`, and the individual-replicate overlay all still show
the deleted vial until the cache entry ages out or the tab is hard-reloaded. The
researcher sees a member that no longer exists and a replicate count that disagrees with
`v_results_scalar_rollup`.

This is worse than an ordinary stale read because deletion is exactly the operation the
group page is most likely to be consulted after — the delete dialog reports which
replicate siblings were decoupled, which invites the user to go look at the group.

## Fix

Add `'replicate-group-detail'` to `PER_EXPERIMENT_QUERY_KEYS`.

That is the whole fix, but note the list is keyed by *experiment* ID while these two
queries are keyed by *base* ID. Evicting `['replicate-group-detail', <deleted exp id>]`
matches nothing. The eviction needs the base ID of the deleted experiment, which is
available in the delete response (the decoupled-replicates payload) or can be derived by
stripping the timepoint token and replicate letter. Simplest correct option: evict the
whole `['replicate-group-detail']` prefix rather than a single entry, since the cache is
small and a group page refetch is one request.

Apply the same reasoning to `'group-rollup'`, which is invalidated elsewhere with a
`baseExperimentId` but is likewise absent from this list.

## Acceptance criteria

- [ ] Deleting a lettered replicate, then navigating to `/experiments/groups/{baseId}`, shows the correct member list on first render with no manual reload
- [ ] `member_count` and `replicate_count` agree with the API immediately after a delete
- [ ] Same verified for the `GroupedResultsView` overlay on the surviving siblings' detail pages
- [ ] `group-rollup` audited for the same gap and fixed or explicitly documented as safe
- [ ] Regression test added to `pages/ExperimentDetail/__tests__/DeleteExperiment.test.tsx`, which already asserts against the key list at line 115

## Notes

The doc comment above `PER_EXPERIMENT_QUERY_KEYS` already reasons about which keys are
unreachable from an experiment ID alone (`['scalar', resultId]`, `['icp', resultId]`) and
explains why they are harmless. Extend that comment to cover the base-ID-keyed queries
rather than leaving the next reader to rediscover the distinction.
