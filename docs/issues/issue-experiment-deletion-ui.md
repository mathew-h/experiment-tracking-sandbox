# Experiment deletion: endpoint exists, UI does not

**Type:** feat
**Area:** frontend (`ExperimentList.tsx`, `ExperimentDetail/`), backend (`routers/experiments.py`)
**Priority:** medium, raised to high by the 2026-07-29 SERUM_Catalyst incident

---

## Problem

There is no way to delete an experiment from the app. When a bad bulk upload creates
rows that shouldn't exist, the only remedies are hand-written SQL against production
or a scripted API loop, both of which require Mat and a `pg_dump` first.

The gap is **not** a missing backend. Deletion is already implemented end to end
except for the button:

| Layer | State |
|---|---|
| `DELETE /api/experiments/{experiment_id}` | Exists — `backend/api/routers/experiments.py:1156-1172` |
| Test coverage | Exists — `tests/api/test_experiments.py:74` (`test_delete_experiment`) |
| Frontend API client | Exists — `frontend/src/api/experiments.ts:284` (`experimentsApi.delete`) |
| UI that calls it | **Missing.** No component in `frontend/src/pages/` or `frontend/src/components/` references `experimentsApi.delete` |

`samplesApi.delete` is wired into `frontend/src/pages/Samples.tsx:41-52` with a
`deleteTarget` confirmation state and a `toastError` handler. Experiments should follow
that pattern.

### Incident that surfaced this

On 2026-07-28 a rename-style bulk upload (`old_experiment_id` + `overwrite`) created
69 duplicate `SERUM_Catalyst_*` experiments under the old sequential numbering
alongside the 80 intended IDs, instead of renaming in place. Cleanup required
generating `scripts/sql/delete_serum_catalyst_leftovers_20260729.sql` (a 300-line
hand-ordered cascade delete) and `scripts/delete_experiments_via_api.ps1`. A
researcher cannot self-serve this, and the SQL path bypasses the ORM cascade entirely.

---

## Cascade correctness (verify before shipping the button)

`delete_experiment` is a bare `db.delete(exp); db.commit()`, so it depends entirely on
the ORM relationship cascades declared in `database/models/experiments.py:30-35`.
Those cover `conditions`, `notes`, `modifications`, `results`, and `external_analyses`
with `cascade="all, delete-orphan"`. Two references are **not** covered:

1. **`XRDPhase.experiment_fk`** (`database/models/xrd.py:72`, `ondelete="SET NULL"`).
   There is no cascading `xrd_phases` relationship on `Experiment`. Deleting an
   experiment that has Aeris time-series phases leaves orphan `xrd_phases` rows whose
   `experiment_fk` is NULL but whose `experiment_id` string still names the deleted
   experiment. The unique constraint on
   `(experiment_id, time_post_reaction_days, mineral_name)` then blocks re-creating
   that experiment's XRD data.

2. **`ScalarResults.background_experiment_fk`** (`database/models/results.py:107`,
   `ondelete="SET NULL"`). If another experiment uses the target as its ammonium
   background, the ORM has no configured cascade and the DB-level `SET NULL` may not
   exist — the initial Alembic migration (`b1fc58c4119d_initial_migration.py`) created
   no FK constraints with `ondelete` clauses at all, so deployed constraint behavior
   does not necessarily match the model declarations. Expect a possible
   `IntegrityError` rather than a clean NULL-out.

Both need explicit handling in `delete_experiment` before the endpoint is exposed to
non-admins.

---

## Proposal

### Backend

1. In `delete_experiment`, before `db.delete(exp)`:
   - Delete `xrd_phases` rows matching `experiment_fk` or `experiment_id`.
   - NULL out `scalar_results.background_experiment_fk` / `background_experiment_id`
     on any *other* experiment referencing this one, and return the affected
     experiment IDs in the response so the caller knows what was decoupled.
   - NULL out `reactor_change_requests.experiment_id` for this experiment.
2. Write a `ModificationsLog` row with `modification_type='delete'`, `modified_table='experiments'`,
   and `old_values` holding a serialized snapshot of the experiment plus its conditions
   and additives. Note that the log row's own `experiment_fk` cascades away with the
   experiment, so this entry must be written with `experiment_fk = NULL` and only the
   `experiment_id` string, or it will delete itself. **This is the audit trail that
   makes deletion acceptable — it should land before the UI does.**
3. Add `GET /api/experiments/{experiment_id}/delete-impact` returning counts of every
   dependent record (results, scalar, ICP, result files, notes, additives, external
   analyses, XRD phases) plus the two decoupling lists above, so the confirmation
   dialog can show consequences rather than a generic warning.
4. Consider gating deletion on the `role: admin` custom claim. Per
   `.claude/rules/AUTH.md`, `role`/`approved` claims are set at approval time but are
   not read by `verify_firebase_token` and are wired into no access-control decision
   today. Deletion is a reasonable first consumer, but that is a separate decision —
   see Open questions.

### Frontend

5. Delete action on `ExperimentDetail` (not the list row, to make it deliberate),
   following the `Samples.tsx` mutation + `deleteTarget` confirmation pattern.
6. Confirmation modal populated from `/delete-impact`, requiring the user to type the
   `experiment_id` to confirm when the impact count is non-zero.
7. Redirect to `ExperimentList` on success and invalidate the `experiments` query key.

### Bulk deletion

8. `ExperimentList.tsx:224` already maintains a selection `Set`. A "Delete selected"
   action reusing it would have handled this incident directly. Scope as a follow-up
   once single delete is proven, and require the typed-ID confirmation per batch.

---

## Acceptance criteria

- [ ] `delete_experiment` removes or decouples `xrd_phases`, `background_experiment_fk`, and `reactor_change_requests` references; no orphan rows remain
- [ ] A `ModificationsLog` delete entry survives the deletion and contains a restorable snapshot
- [ ] `GET /api/experiments/{id}/delete-impact` returns accurate counts for an experiment with results, ICP, files, notes, additives, and XRD phases
- [ ] Deleting an experiment that is another experiment's ammonium background succeeds and reports the decoupled experiment
- [ ] UI requires typed-ID confirmation when impact is non-zero; cancel is a no-op
- [ ] `pytest tests/api/test_experiments.py -v` and the frontend vitest suite pass
- [ ] `MODELS.md` notes the deletion path and its orphan-prevention behavior

## Open questions

1. Admin-only, or any approved researcher? Admin-only means wiring the `role` claim
   into `verify_firebase_token`, which per `AUTH.md` rule 8 requires documenting where
   that check lives. It also means Mat is a bottleneck again, which is the problem this
   issue exists to solve.
2. Hard delete or soft delete (`deleted_at` timestamp)? Soft delete preserves
   recoverability but requires filtering every reporting view in
   `database/event_listeners.py` and every list query — a much larger change, and it
   does not free the `experiment_id` string for reuse, which was the actual need in
   this incident.
