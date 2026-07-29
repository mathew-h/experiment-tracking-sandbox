# Bulk upload dry-run: show create / rename / overwrite plan before committing

**Type:** feat
**Area:** backend (`backend/services/bulk_uploads/`, `routers/bulk_uploads.py`), frontend (`BulkUploads.tsx`, `BulkUploadRow.tsx`)
**Priority:** high

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

- [ ] `dry_run=true` on every bulk upload endpoint returns a plan and leaves the database byte-identical (verify with a row-count and `max(updated_at)` check before/after)
- [ ] A rename workbook with `overwrite` blank produces a conflict naming both IDs, and commit is blocked
- [ ] A rename workbook with `overwrite=TRUE` and a genuine target collision reports `CHAIN RENAME CONFLICT` at preview time, with the suggested row ordering
- [ ] Overwrite rows list every changed field with old and new values
- [ ] Editing the file between preview and commit fails the plan-hash check
- [ ] Replaying the two 2026-07-28 SERUM_Catalyst workbooks against a snapshot of the pre-incident database yields a plan of 80 renames and 0 creates
- [ ] Existing bulk upload tests pass unchanged with `dry_run` defaulting to false

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
