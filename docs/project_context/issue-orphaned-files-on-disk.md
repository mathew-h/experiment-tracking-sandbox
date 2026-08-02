# Result and analysis files are never removed from disk when their rows are deleted

**Type:** fix
**Area:** `backend/services/experiment_deletion.py`, `backend/api/routers/results.py`, `backend/api/routers/analysis.py`
**Priority:** medium
**Related:** issue #99 (experiment deletion)

---

## Problem

`backend/services/experiment_deletion.py` counts `ResultFiles` for the impact dialog
(lines 158-159) and deletes the rows, but never touches the filesystem. Same for
`AnalysisFiles` under a purged `ExternalAnalysis`. The uploaded bytes stay on the lab PC
forever with no database row pointing at them.

The codebase already establishes the correct pattern elsewhere.
`backend/api/routers/samples.py:454-478` (`delete_photo`) unlinks before deleting:

```python
file_path = Path(photo.file_path)
if file_path.exists():
    file_path.unlink()
```

So the behavior is inconsistent rather than undecided: sample photos are cleaned up,
result files and analysis files are not.

## Impact

Low urgency, real consequences. The deployment is a single always-on lab PC with local
storage and no object-store lifecycle policy, so orphaned uploads accumulate with nothing
reclaiming them. Raw instrument logs and external lab reports are the largest files the
app stores. Nobody notices until the disk does.

Secondary concern: an orphaned file is undiscoverable. `ResultFiles.file_path` was the
only record of what it was, so once the row is gone the file cannot be attributed to an
experiment, dated, or safely deleted by hand without opening it.

## Proposal

1. In `experiment_deletion.py`, collect `file_path` for every `ResultFiles` and
   `AnalysisFiles` row in scope *before* the DB deletes run, and unlink after the
   transaction commits successfully. Order matters: unlinking before commit means a
   rolled-back transaction has already destroyed the files.
2. Treat unlink failures as non-fatal. A missing or locked file must not fail the delete
   or leave the transaction half-applied. Log each failure with the path and continue.
3. Report the paths in the delete response and in the `ModificationsLog` `old_values`
   snapshot, so the audit row records what was removed from disk as well as from the
   database. Per `MODELS.md`, that snapshot is explicitly "a record of what was deleted,
   not a restore point" — file paths belong in it for the same reason.
4. Apply the same unlink to the single-record delete paths for result files and analysis
   files, wherever they exist, so the two routes agree.
5. Add a reconciliation script (`scripts/find_orphaned_uploads.py`) that walks the
   configured storage roots and reports files with no matching `ResultFiles`,
   `AnalysisFiles`, or `SamplePhotos` row. Run it once to quantify the existing backlog
   from the 2026-07-29 SERUM_Catalyst cleanup and anything earlier. Report only — deleting
   should stay a human decision.

## Acceptance criteria

- [ ] Deleting an experiment with result files removes both the rows and the files
- [ ] Deleting an experiment whose external analysis has attached files removes both
- [ ] A delete whose transaction rolls back leaves all files intact
- [ ] An unlink failure (file already gone, or locked) logs a warning and does not fail the request
- [ ] Removed paths appear in the delete response and the `ModificationsLog` snapshot
- [ ] `scripts/find_orphaned_uploads.py` exists, is read-only, and has been run once against production with the result recorded in `docs/issues/`
- [ ] `pytest tests/ -k deletion -v` passes, including a test asserting files are gone

## Open question

Should deletion move files to a dated quarantine directory instead of unlinking? Given
there is no undo anywhere else in the delete path and `MODELS.md` is explicit that the
audit snapshot is not a restore point, unlinking is consistent. But files are the one
part of a deleted experiment that could be restored cheaply, and a quarantine swept on a
90-day cron is not much more code. Worth a decision before implementing.
