# bug: bulk-upload rename can set an experiment as its own parent (CircularDependencyError), and one failed row poisons the rest of the batch

> **Verified against** `OneDrive - Addis Energy/Documents/01_Software/database_sandbox/experiment_tracking_sandbox`, branch `develop` @ `0660410`. Reproduced against a disposable Postgres savepoint (rolled back, no data touched).

## Summary

Uploading `20260728_SERUM_cation_001_050_renamed_updated.xlsx` through **New Experiments** bulk upload (the `old_experiment_id` + `overwrite=True` rename path) fails the entire file with:

```
This Session's transaction has been rolled back due to a previous exception during flush...
Original exception was: Circular dependency detected.
(ProcessState(ManyToOneDP(Experiment.parent), <Experiment ...>, delete=False), SaveUpdateState(<Experiment ...>))
```

There are **two independent defects**. Either can be fixed without the other.

| | Defect | Location | Effect |
|---|---|---|---|
| **A** | Rename's parent lookup reads its own stale, unflushed row and can resolve the experiment as its own parent | `backend/services/bulk_uploads/new_experiments.py:387-409` | One row raises `CircularDependencyError` |
| **B** | No per-row rollback or savepoint isolation | `backend/services/bulk_uploads/new_experiments.py:460-472` | That one row's failure fails all 50 rows and hides which row was actually bad |

**Both files are in the locked bulk-upload parser path** (`backend/services/bulk_uploads/`, `docs/LOCKED_COMPONENTS.md`). This issue exists to get explicit sign-off before either change is made.

---

## Defect A: rename's parent self-lookup reads a stale row

### Background

`Experiment` is self-referential for lineage (replicates, sequential re-runs, treatment variants):

`database/models/experiments.py:23,38`

```python
parent_experiment_fk = Column(Integer, ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True)
...
parent = relationship("Experiment", remote_side=[id], foreign_keys=[parent_experiment_fk], backref="derived_experiments")
```

The session factory has autoflush **off**, `database/database.py:25`:

```python
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

### The ordering bug

`backend/services/bulk_uploads/new_experiments.py:387-409`, in the rename branch:

```python
experiment.experiment_id = exp_id            # 387: new ID in memory only, NOT flushed
...
update_experiment_lineage(db, experiment)    # 392: parent lookup runs a live SQL query
...
db.flush()                                   # 409: flush happens AFTER the lookup
```

For a lettered-replicate ID, `update_experiment_lineage` (`database/lineage_utils.py:209-291`) calls `find_replicate_group_parent` (`:84-103`), which calls `_find_experiment_by_exact_spelling` (`:45-81`). That helper checks `db.new` and then issues a real `SELECT` for the new ID's base stem.

Because autoflush is off, that `SELECT` runs against a database row that still carries the **old** ID. If the old ID and the new stem normalize to the same string (`_normalize_experiment_id` at `lineage_utils.py:40-42` strips case, `-`, `_`, and spaces), the query matches the row against itself. SQLAlchemy's identity map returns the same in-memory object, so `lineage_utils.py:284` executes:

```python
experiment.parent = parent   # parent IS experiment
```

A literal self-reference on a self-referential FK. SQLAlchemy correctly refuses to order that at flush time and raises `CircularDependencyError`.

Note that the `before_flush` listener at `database/event_listeners.py:679-700` only iterates `session.new`, so it does not recompute lineage for a renamed (dirty) experiment. The explicit call at line 392 is the only lineage recompute on the rename path.

### Why this file hit it exactly once

The workbook renames a flat sequence (`SERUM_cation_001` … `050`) into grouped stems (`SERUM_Cation_001` … `020`) with lettered/timepoint suffixes (`a-t5`, `b-t5`, …). Both numbering schemes restart at `001`, so the normalize-collision can only occur where the old sequential number equals the new group number. Given this mapping, that is row 1 only:

```
SERUM_cation_001  ->  SERUM_Cation_001a-t5
   normalizes to           new stem normalizes to
   serumcation001          serumcation001          <- collision
```

Rows 2 through 50 are fine. They fail for a different reason (Defect B).

---

## Defect B: a single row's exception poisons the whole batch

The per-row `try` block spans `new_experiments.py:180-472`. Its handler, `:460-472`:

```python
except Exception as e:
    error_detail = f"{type(e).__name__}: {str(e)}"
    step_info = f" (during: {current_step})" if 'current_step' in locals() else ""
    warnings.append(f"[experiments] Row {idx+2}: {error_detail}{step_info}")
    ...
```

It appends a warning and continues. It never calls `db.rollback()`, and there is no per-row savepoint. After a failed flush SQLAlchemy leaves the session in a pending-rollback state, so the next query or flush on any subsequent row immediately raises `PendingRollbackError`. Rows 2 through 50 each raise it, the router catches it at the top level (`backend/api/routers/bulk_uploads.py:97-102`), rolls everything back, and reports it as the upload's single error.

Net effect: the real `CircularDependencyError` on row 1 is buried under 49 downstream `PendingRollbackError` warnings, and the reported failure message points at the symptom rather than the cause. This will happen for *any* future per-row exception, not just this one.

---

## Reproduction (already done)

Synthetic triplet matching row 1's exact ID shape, run against a disposable Postgres savepoint that was rolled back (`SERUM_cation_*` does not exist in the dev DB):

```
X_cation_001 -> X_Cation_001a-t5
X_cation_002 -> X_Cation_001b-t5
X_cation_003 -> X_Cation_001c-t5
```

- **Unpatched:** row 1 raises `CircularDependencyError`; rows 2 and 3 raise cascading `PendingRollbackError`. Identical to the reported failure.
- **With a candidate fix (flush the pending rename before the parent lookup):** all 3 rows succeed with correct `base_experiment_id` and `replicate_label` (`a`/`b`/`c`), no errors.

---

## Proposed Changes

### A1. Flush the rename before the lineage lookup (`new_experiments.py`)

Move the existing `db.flush()` from line 409 to immediately after the `experiment_id` assignment, so the parent `SELECT` sees the new ID:

```python
experiment.experiment_id = exp_id
db.flush()                                   # persist the rename first
info_messages.append(...)
renamed_experiment_ids.add(exp_id)
update_experiment_lineage(db, experiment)    # now resolves against the new ID
# ... note/modification-log denormalization ...
db.flush()
```

Keep a flush after the denormalization loops so `ExperimentNotes` / `ModificationsLog` updates land before `expire_all()` at line 480 (issue #68).

Check when implementing: the `UNIQUE` constraint on `experiment_id` will now be raised by the *earlier* flush. The existing `except Exception as rename_error` handler at line 410 wraps both flushes, and its chain-rename-ordering message still applies, but confirm the branch is still reached and the warning text is still accurate.

### A2. Defensive self-reference guard (`database/lineage_utils.py`)

`lineage_utils.py` is **not** in the locked bulk-upload path, and this closes the whole class of bug rather than one call site. In `update_experiment_lineage`, before assigning:

```python
if parent is experiment or (parent is not None and parent.id is not None and parent.id == experiment.id):
    parent = None
experiment.parent = parent
```

Same guard belongs in the `else` branch (`get_or_find_parent_experiment` path) at `lineage_utils.py:287-289`. A self-parent is never a valid lineage result, so silently dropping it is correct. Emit a warning-level log when it triggers so a future collision is visible rather than silent.

A2 alone would prevent the crash without touching locked code. A1 alone would fix this file but leave the self-parent path reachable from any other caller. **Recommend both.**

### B. Per-row savepoint isolation (`new_experiments.py`)

Wrap each row in a nested transaction so a failure discards only that row:

```python
for idx, row in df_exp.iterrows():
    savepoint = db.begin_nested()
    try:
        ...                       # existing per-row body
        savepoint.commit()
    except Exception as e:
        savepoint.rollback()      # session is usable again for the next row
        warnings.append(f"[experiments] Row {idx+2}: {error_detail}{step_info}")
```

Implementation notes:

- Rolling back a savepoint expires objects modified inside it. Verify that per-row state carried across iterations (`parent_for_copy`, `renamed_experiment_ids`, `failed_experiment_ids`) stays consistent when a row is discarded, and that a discarded row's `exp_id` is not left in `renamed_experiment_ids`.
- Do the same for the conditions, results, and additives loops (`:513`, `:611`, `:843`) only if it can be done without changing their existing skip/warning semantics. Otherwise scope B to the experiments loop and file the rest separately.
- The router's top-level `except` (`bulk_uploads.py:97`) stays as-is: it is the correct backstop for a genuinely non-recoverable failure.

---

## Tests to add

`tests/services/bulk_uploads/` (or the existing new-experiments upload test module):

1. **A, direct:** rename an experiment where the old ID normalizes to the new ID's stem (`X_cation_001` -> `X_Cation_001a-t5`). Assert no exception, `base_experiment_id == "X_Cation_001"`, `replicate_label == "a"`, `id_timepoint_days == 5.0`, and `parent_experiment_fk != experiment.id`.
2. **A, unit:** call `update_experiment_lineage` directly with a session where the only matching row is the experiment itself. Assert `parent_experiment_fk is None` (A2 guard).
3. **A, sibling group:** the 3-row triplet above. Assert `a`/`b`/`c` labels and a shared `base_experiment_id`.
4. **B:** a two-row sheet where row 1 raises deliberately (any forced exception) and row 2 is valid. Assert row 2 is created, exactly one warning names row 1, and no `PendingRollbackError` appears anywhere in `warnings`.
5. **B, regression:** confirm the reported error message names the failing row and the real exception type, not `PendingRollbackError`.

Also re-run the existing rename tests, especially the chain-rename ordering cases, since A1 moves where the `UNIQUE` violation surfaces.

---

## Acceptance criteria

- [ ] `20260728_SERUM_cation_001_050_renamed_updated.xlsx` uploads with 50 rows updated and zero errors.
- [ ] No code path can produce `experiment.parent_experiment_fk == experiment.id`.
- [ ] A single failing row produces exactly one warning naming that row and its real exception; all other valid rows in the file still commit.
- [ ] No `PendingRollbackError` in any upload response for a file with one bad row.
- [ ] Existing rename, chain-rename, and lineage tests pass unchanged.
- [ ] `docs/LOCKED_COMPONENTS.md` and `MODELS.md` (lineage section) updated if the rename-path ordering contract changes.

---

## Explicitly out of scope

- Retroactive reclassification of historical `-0`/`-1`-suffixed experiments (known gap, see `MODELS.md`).
- Changing `autoflush=False` on `SessionLocal`. Turning autoflush on would mask this bug and would change flush timing across the entire app, including the `before_flush` lineage and calculation listeners. Not worth the blast radius.
- Refactoring `_find_experiment_by_exact_spelling`'s normalize-then-match strategy. The loose matching is intentional and depended on elsewhere.
- The legacy `extract_lineage_info` shim in `backend/services/experiment_validation.py` (deliberately frozen).

---

## Labels

`bug`, `bulk-upload`, `locked-path`, `lineage`, `needs-signoff`

## Notes

Defect B is the higher-value fix long term: it makes every future per-row bulk-upload failure diagnosable instead of presenting as a whole-file error with a misleading message. Defect A is the specific trigger and is a smaller, lower-risk change. Shipping A first restores this upload; B should not be deferred indefinitely.
