# Bulk "Delete selected" on the experiment list

**Type:** feat
**Area:** `frontend/src/pages/ExperimentList.tsx`, `backend/api/routers/experiments.py`
**Priority:** medium
**Related:** issue #99 (single-experiment deletion, shipped)

---

## Problem

Issue #99 shipped single-experiment deletion with an itemized impact dialog and a typed-ID
confirmation gate. It works well for one experiment and does not scale past a handful.

The 2026-07-28 SERUM_Catalyst incident created 69 unwanted vials in one bad bulk upload.
Removing them through the shipped UI means 69 dialogs, each requiring the user to type a
40-character experiment ID. In practice that pushed the cleanup out of the app entirely
and into `scripts/delete_experiments_via_api.ps1`, a PowerShell loop over the same
endpoint. That script is a reasonable stopgap but it is not discoverable, requires the
Firebase web API key and a terminal, and only Mat will ever run it.

The asymmetry is the actual problem: a single upload can create hundreds of experiments in
one action, but removal is one-at-a-time. Any bulk-upload mistake is therefore
disproportionately expensive to undo, which is what makes the upload feel high-stakes.

## Existing groundwork

`ExperimentList.tsx:224` already maintains a selection `Set` (used today for the
grouped/flat row expansion state at minimum). The delete endpoint, impact endpoint, audit
logging, and modal are all in place from #99. This is largely composition.

## Proposal

### Backend

1. `POST /api/experiments/bulk-delete-impact` taking a list of experiment IDs, returning
   the aggregate `DeleteImpact` plus the per-ID breakdown and the union of decoupling
   effects (background references and replicate siblings on experiments *not* in the
   selection). Reuse `collect_delete_impact` per ID rather than reimplementing.
2. `POST /api/experiments/bulk-delete` taking the same list. Delete each in its own
   transaction and return a per-ID outcome array, so one failure does not abandon the
   rest. Do **not** wrap the batch in a single transaction: a 69-row batch that rolls back
   entirely because of one locked row is worse than a partial result plus an accurate
   report.
3. Cap the batch size (100 is generous for a 2-5 user lab) and reject above it, so a
   mis-selection cannot delete the database.
4. One `ModificationsLog` row per experiment as today, plus a batch correlation ID on each
   so the whole operation can be reconstructed from the audit trail.

### Frontend

5. Checkbox column on `ExperimentList`, with select-all applying to the current filter
   result set only. Selecting across pagination is a trap; either scope selection to the
   visible page or make the "all N matching" semantics explicit in the button label.
6. "Delete selected (N)" opens a batch confirmation showing the aggregate impact, the
   per-experiment breakdown behind a disclosure, and the decoupling warnings. Require the
   user to type the count, not an ID — typing 69 IDs is the thing being fixed.
7. Progress feedback during the batch, and a result summary listing failures with reasons.
8. Evict the caches from `PER_EXPERIMENT_QUERY_KEYS` for every deleted ID, including the
   base-ID-keyed group queries — see `issue-replicate-group-detail-cache-eviction.md`.
   **That issue should land first**, or bulk delete will leave a much larger stale-cache
   surface than single delete does.

## Acceptance criteria

- [ ] Selecting N experiments and confirming deletes exactly those N and no others
- [ ] A batch containing one already-deleted ID reports it as skipped and still deletes the rest
- [ ] Aggregate impact counts equal the sum of the individual impacts
- [ ] Decoupling warnings list only experiments outside the selection
- [ ] Batch size above the cap is rejected with a clear message
- [ ] One audit row per experiment, all sharing a batch correlation ID
- [ ] Caches for every deleted ID are evicted, group pages included
- [ ] Replaying the 69-ID SERUM_Catalyst list through the UI produces the same end state as `delete_experiments_via_api.ps1`

## Notes

Once this ships, `scripts/delete_experiments_via_api.ps1` should be deleted rather than
maintained. Two paths to bulk deletion is how the psql script and
`experiment_deletion.py` ended up disagreeing about `external_analyses` and
`modifications_log`.

A dry-run on bulk upload (`issue-bulk-upload-dry-run.md`) prevents this class of mistake;
bulk delete only cleans up after it. If effort is constrained, the dry-run is the higher
-leverage fix.
