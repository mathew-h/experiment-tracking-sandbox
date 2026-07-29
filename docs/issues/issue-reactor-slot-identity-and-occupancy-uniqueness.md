# bug: reactor slot identity is derived, not stored — cross-series occupancy collision silently auto-completes running experiments

> **Verified against** `OneDrive - Addis Energy/Documents/01_Software/database_sandbox/experiment_tracking_sandbox`, branch `feat/issue-85-dashboard-kpi-cards` @ `49e5f8f`. All `dashboard.py` and `schemas/dashboard.py` citations below are **post-#85** and will not match `develop`. Every other file cited is identical on both. If #85 lands before this ticket, re-check only those two files.

**Priority: ship this first.** One of the bugs below is live and actively mutating experiment status records without user intent. This is the tactical fix; the structural fix is tracked separately in `issue-reactors-table-entity.md`, which will explicitly supersede the discriminator column added here.

## Summary

A physical reactor slot in this lab is identified by a *pair*: the reactor number and which series it belongs to (HPHT vessel vs. Core Flood rig). `R01` and `CF01` are two different pieces of hardware that happen to share the number 1.

The database stores only half of that pair. `ExperimentalConditions.reactor_number` is a bare `Column(Integer, nullable=True)` — no FK, no unique constraint, no CHECK — and the `R01` / `CF01` label is re-derived from `(reactor_number, experiment_type == "Core Flood")` at read time in three independent places. Every code path that asks "who is in reactor N?" has to remember to also scope by type, and several don't.

That produces four defects, in descending order of severity:

1. **Bulk status upload demotes across series.** Setting a Core Flood to ONGOING finds the HPHT sitting in `R01` and can auto-complete it. Live data corruption.
2. **Bulk new-experiment upload demotes unconditionally, from any experiment type.** A Serum row carrying a stray `reactor_number` will complete the HPHT in that slot, with no date guard and no eligibility gate. Worse than (1) because nothing stops it.
3. **Nothing enforces one-ONGOING-per-slot.** The demotion logic is best-effort, fires on only two of four write paths, and fails open on missing dates.
4. **When a double-booking happens, the dashboard hides it** rather than surfacing it, and the KPI bar undercounts occupied slots.

---

## Background: how slot identity works today

`database/models/conditions.py:17-18`

```python
    experiment_type = Column(String)
    reactor_number = Column(Integer, nullable=True)
```

The label is reconstructed at read time by three separate copies of the same expression:

- `backend/api/routers/dashboard.py:130-137` (reactor cards)
- `backend/api/routers/dashboard.py:339-346` (`GET /reactor-status`)
- `backend/services/notion_sync/export.py:30-40` (`_reactor_label_for`)

```python
        is_cf = exp_type == "Core Flood" if exp_type else False
        label = f"CF{rn:02d}" if is_cf else f"R{rn:02d}"
```

The frontend maintains its own fixed slot lists at `frontend/src/pages/ReactorGrid.tsx:13-14` (`R01`–`R16`, `CF01`–`CF02`). **Note these now disagree with the backend:** #85 added `CF_SLOT_COUNT = 3` at `dashboard.py:45` (CF01–CF03) while `ReactorGrid.tsx:14` is still `['CF01', 'CF02']`. That is a live inconsistency independent of this ticket — flag it on the #85 PR.

The only enforcement that a `reactor_number` may only be set on an occupancy-bearing type lives in the API layer at `backend/api/routers/conditions.py:16-25`:

```python
_REACTOR_ALLOWED_TYPES = {"HPHT", "Core Flood"}
```

applied on POST (line 63) and PATCH (line 87), returning 422. **Both bulk upload paths bypass this entirely.**

Note that the codebase already knows about this hazard in three places — `dashboard.py:144-147` has a comment explaining why `REACTOR_SPECS` must be skipped for CF, `dashboard.py:334` comments "CF01/R01 are separate slots" on the dedup, and `tests/api/test_dashboard.py` has a regression test whose comment documents the historical bug. The knowledge exists; it just hasn't been pushed down into the schema.

(Minor, while you're in there: the comment at `dashboard.py:145` still says "CF01/CF02" after #85 raised the CF count to three.)

---

## Defect 1 — bulk status upload searches for occupants without scoping by series

**Where:** `backend/services/bulk_uploads/experiment_status.py`, two queries.

Preview path, lines 240-251:

```python
            exp_type = exp.conditions.experiment_type if exp.conditions else None
            if not _is_eligible_for_occupancy(exp_type):
                continue

            occupants = db.query(Experiment).join(
                ExperimentalConditions,
                Experiment.id == ExperimentalConditions.experiment_fk,
            ).filter(
                Experiment.id != exp.id,
                Experiment.status == ExperimentStatus.ONGOING,
                ExperimentalConditions.reactor_number == r["reactor_number"],
            ).all()
```

Apply path, `manage_reactor_occupancy`, lines 383-390:

```python
            conflicting_experiments = db.query(Experiment).join(
                ExperimentalConditions,
                Experiment.id == ExperimentalConditions.experiment_fk
            ).filter(
                Experiment.id != new_experiment.id,
                Experiment.status == ExperimentStatus.ONGOING,
                ExperimentalConditions.reactor_number == reactor_number
            ).all()
```

The *incoming* experiment is gated by `_is_eligible_for_occupancy` (line 241). The *occupant search* is not gated at all. So:

**Reproduction.** `HPHT_209` is ONGOING in `R01`, started 2026-05-01. Bulk-upload a status file setting a Core Flood experiment to ONGOING on rig 1 with date 2026-07-20. The occupant query returns `HPHT_209` (its `reactor_number` is also 1), the date guard passes (`2026-05-01 < 2026-07-20`), and `HPHT_209.status` is set to `COMPLETED`. A running HPHT experiment is silently closed out because an unrelated Core Flood rig was loaded. It works in the other direction too.

Compare with `backend/services/notion_sync/import_.py:44-67`, which *does* get this right — it parses the `CF`/`R` prefix off the label and builds a `type_filter` before querying:

```python
    if label_upper.startswith("CF"):
        reactor_number = int(label_upper[2:])
        type_filter = ExperimentalConditions.experiment_type == "Core Flood"
    elif label_upper.startswith("R"):
        reactor_number = int(label_upper[1:])
        type_filter = ExperimentalConditions.experiment_type != "Core Flood"
```

(Worth fixing while you're here: the `!=` on the `R` branch is NULL-unsafe in SQL. A row with `experiment_type IS NULL` matches neither branch, so it can never be resolved as an `R*` occupant. Use `IS DISTINCT FROM` or an explicit `IN (...)`.)

## Defect 2 — same-file conflict detection keys on the bare integer

`experiment_status.py:196-197` and `219-228`:

```python
        reactor_targets: Dict[int, str] = {}
        ...
                existing = reactor_targets.get(r["reactor_number"])
                if existing is not None:
                    conflict_errors.append(
                        f"Reactor {r['reactor_number']} is targeted by multiple rows in "
                        f"this file: '{existing}' and '{exp.experiment_id}'"
                    )
```

A legitimate upload that starts an HPHT in `R01` and a Core Flood in `CF01` in the same file is rejected with a spurious `"Reactor 1 is targeted by multiple rows in this file"`. Note this is a hard rejection — `conflict_errors` short-circuits the entire preview at lines 230-231, so one false positive blocks the whole upload.

## Defect 3 — bulk new-experiment upload has no eligibility gate and no date guard

`backend/services/bulk_uploads/new_experiments.py:599-610` (and an identical second call site at `673-681`, the auto-copied-from-parent conditions path):

```python
                        if conditions.reactor_number and experiment.status == ExperimentStatus.ONGOING:
                            marked, reactor_warnings = ExperimentStatusService.manage_reactor_occupancy(
                                db, experiment, conditions.reactor_number, commit=False
                            )
```

Two problems, both worse than Defect 1:

- **No `_is_eligible_for_occupancy` check.** A Serum or Autoclave row with a stray `reactor_number` will demote the HPHT occupant. `apply_status_changes` blocks this (line 321) and the conditions router 422s it (`conditions.py:19-25`), but this path doesn't. There is already a test asserting the *correct* behavior on the status path — `tests/services/bulk_uploads/test_experiment_status.py:506` `test_apply_no_demotion_for_serum_type_even_with_reactor_number` — with no equivalent on this path.
- **`newer_than` is omitted entirely**, so the `_UNSET` sentinel leaves `guard_active = False` (`experiment_status.py:377`) and demotion is unconditional. The occupant's start date is not consulted at all. This is deliberate and documented in the docstring as preserving legacy behavior, but combined with the missing type gate it means the highest-volume write path is also the least guarded.
- Minor: `if conditions.reactor_number` is falsy for `reactor_number == 0`. Use `is not None`.

## Defect 4 — no uniqueness anywhere, and the dashboard hides violations

There is no database constraint preventing two ONGOING experiments from both carrying `reactor_number = 5`. The application-level demotion logic is the only defense, and it has three holes:

- **It doesn't run on the status dropdown.** `PATCH /api/experiments/{experiment_id}/status` (`backend/api/routers/experiments.py:359-375`) is the entire handler:

  ```python
      exp.status = payload.status
      db.commit()
      db.refresh(exp)
  ```

  No occupancy check, no warning. Setting two experiments to ONGOING via the dashboard dropdown double-books the slot with no complaint. `manage_reactor_occupancy` is called from exactly three non-test sites (`experiment_status.py:324`, `new_experiments.py:602`, `new_experiments.py:674`) plus the legacy Streamlit frontend — the REST status endpoint is not among them.

- **The date guard fails open.** `_occupant_is_older` (`experiment_status.py:31-35`) and the equivalent inline check at `experiment_status.py:396-400` both decline to demote when either date is missing:

  ```python
                    if incoming_date is None or occ_date is None or occ_date >= incoming_date:
                        warnings.append(
                            _not_demoted_message(reactor_number, exp.experiment_id, new_experiment.experiment_id)
                        )
                        continue
  ```

  A warning is emitted, which is the right instinct, but the double-booking is then permitted to persist in the database.

- **The dashboard conceals the result.** `dashboard.py:115-123` orders by `(reactor_number, ONGOING-first, created_at desc)`, then lines 126-140 dedup on the derived label:

  ```python
      seen_labels: set[str] = set()
      for row in reactor_rows:
          ...
          if label in seen_labels:
              continue
  ```

  The second ONGOING experiment in a slot silently vanishes from the grid. No badge, no warning, no console log.

- **And #85's new occupancy KPI inherits the concealment.** This bullet changed shape while this ticket was being written, so read carefully.

  On `develop`, the defect was an unscoped `count(distinct reactor_number)` that collapsed `R01` and `CF01` into one value. **#85 removed that.** `DashboardSummary` no longer has `reactors_in_use`; it now carries `reactors: SlotOccupancy` and `core_floods: SlotOccupancy` (`schemas/dashboard.py:36-52`), computed by `_occupancy()` at `dashboard.py:48-63` from the already-built `reactor_cards` list, filtered against the valid label set per prefix. Series separation is now correct, and `_occupancy`'s docstring even notes that no CHECK constraint exists on `reactor_number` and guards against `empty` going negative because of it. That is good work and this ticket should not undo it.

  What survives is the *other* half: `_occupancy` counts `reactor_cards`, and `reactor_cards` is the **deduped** list. So a double-booked slot still contributes exactly one `ongoing`, and `empty = total - ongoing - queued` still reads one too high. The invariant the docstring promises (`ongoing + queued + empty == total`) holds while being wrong about the lab. The undercount moved from the SQL into the dedup; it did not go away.

  This is the strongest argument for the constraint in §4 rather than more read-path patching. #85 correctly fixed the symptom it could see from inside `get_dashboard`; the remaining error is unreachable from there, because by the time `_occupancy` runs the duplicate has already been discarded. Once one-ONGOING-per-slot is enforced in the database, the dedup at 126-140 becomes dead code and can be deleted, and `_occupancy` becomes correct by construction.

---

## Proposed Changes

### 1. Store slot identity instead of deriving it

Add a single stored discriminator to `experimental_conditions` and make it the key for every occupancy comparison and every label render.

**Recommended: a `reactor_slot` string column** holding the canonical label (`"R01"`, `"CF02"`), nullable, maintained on write, backfilled from `(reactor_number, experiment_type)`.

Rationale over the alternatives:
- A `reactor_series` enum (`HPHT` / `CF`) still requires every comparison site to use a two-column key, which is exactly the mistake being fixed — easy to forget one column.
- Offset CF numbering (CF01 → 101) is the smallest diff but makes `reactor_number` no longer mean what it says, and the three label-derivation sites still need the offset logic.
- A single string column collapses all four occupancy comparisons to one-column equality, and makes the eventual FK in `issue-reactors-table-entity.md` a drop-in replacement (`reactor_slot` → `reactor_id`, with `reactors.label` matching the backfilled values 1:1).

Keep `reactor_number` in place for this pass — Power BI views, `database/data_migrations/swap_reactor_4_7_015.py`, `database/event_listeners.py:119,151`, and the `GET /api/experiments?reactor_number=` filter (`experiments.py:132-135`) all read it. Do not remove it here; that's the reactors-table ticket's job.

Backfill: `reactor_slot = CASE WHEN experiment_type = 'Core Flood' THEN 'CF' ELSE 'R' END || lpad(reactor_number::text, 2, '0')` for rows where `reactor_number IS NOT NULL`. **Run the audit query in the Verification section before writing the migration** — if there are rows with a non-null `reactor_number` and a NULL or non-canonical `experiment_type`, decide explicitly whether they backfill to `R*` (matching current read-time behavior) or to NULL (flagged for manual cleanup). Current read paths treat them as `R*`; matching that is the safe default, but the count matters.

### 2. Fix the four unscoped comparison sites

| File | Line(s) | Change |
|---|---|---|
| `backend/services/bulk_uploads/experiment_status.py` | 244-251 | Occupant query filters on `reactor_slot`, not `reactor_number` |
| `backend/services/bulk_uploads/experiment_status.py` | 383-390 | Same, in `manage_reactor_occupancy` |
| `backend/services/bulk_uploads/experiment_status.py` | 196-197, 219-228 | Key `reactor_targets` on the slot label; update the conflict message to say `CF01` / `R01` rather than `Reactor 1` |
| `backend/api/routers/dashboard.py` | 48-63 | `_occupancy()` — no change needed to the series logic (#85 got it right); it becomes correct once the constraint lands and the dedup is deleted |
| `backend/api/routers/dashboard.py` | 126-140 | Delete the `seen_labels` dedup. It is dead once one-ONGOING-per-slot is enforced, and while it exists it hides constraint violations from `_occupancy`. **Do this last**, after the constraint is verified. |
| `backend/services/notion_sync/import_.py` | 44-67 | Resolve directly on `reactor_slot == label_upper`; deletes the NULL-unsafe `!=` branch entirely |
| `backend/api/routers/dashboard.py` | 130-137, 339-346 | Read `row.reactor_slot` instead of rebuilding the label |
| `backend/services/notion_sync/export.py` | 30-40 | `_reactor_label_for` becomes a plain column read |

### 3. Close the write-path gaps

- `new_experiments.py:634` and `:706` — add `_is_eligible_for_occupancy(conditions.experiment_type)` to both guards, and change `if conditions.reactor_number` to `is not None`. **The falsy-zero half of this is confirmed live in production data:** the eight `R00` rows in the 2026-07-28 audit exist because `reactor_number = 0` is falsy, so occupancy management never ran for them. See `audit-2026-07-28-results-and-cleanup.md`.
- **Pass `newer_than` on the new-experiments path.** Previously flagged as needing a team call, now resolved by the trigger decision in §4. The concern was that failing open (declining to demote when a date is missing) would silently permit a double-booking. Once the trigger exists, failing open produces a **loud row-level error on the upload instead of silent corruption**, which is the behavior we want. So pass `newer_than=experiment.date` and let the trigger be the backstop. The bulk-upload error handling must catch the trigger's `unique_violation` and surface it as a readable per-row message rather than a 500.
- `PATCH /api/experiments/{experiment_id}/status` (`experiments.py:519-535`) — **decided: return 409, do not demote.** Reject the transition to ONGOING when the target slot is occupied, with the occupying `experiment_id` and its start date in the error detail so the caller can act on it.

  The frontend confirm dialog ("R01 is occupied by HPHT_222, started Jul 24. Complete it and start HPHT_230?") is **deliberately deferred to a follow-up ticket.** The backend is identical with or without it, so shipping the rejection first costs nothing in rework and closes the hole today. Until the dialog exists, the user completes the occupant manually first.

  Rationale for rejecting rather than demoting: `CF_018`, `-2` and `-3` all went ONGOING through this endpoint with nothing objecting, which is how CF01 ended up triple-booked. Silent demotion would have produced the correct result in that specific case, but the endpoint cannot distinguish "I am advancing a sequential re-run" from "I picked the wrong reactor from a dropdown," and only one of those should close someone else's running experiment.

### 4. Add the uniqueness constraint

This is the important half of the ticket, because it converts a silent corruption path into a loud error.

**Design constraint:** the two columns needed are on different tables. `Experiment.status` lives on `experiments`; `reactor_slot` lives on `experimental_conditions`. Postgres partial unique indexes and exclusion constraints are both single-table, so `CREATE UNIQUE INDEX ... WHERE status = 'ONGOING'` is **not** directly expressible.

**Decided (2026-07-28): PL/pgSQL trigger.** One function raising `unique_violation`, wired to `BEFORE INSERT OR UPDATE` on `experiments` (when `status` becomes ONGOING) and on `experimental_conditions` (when `reactor_slot` or `experiment_type` changes).

Rationale: the failure mode in the production data is un-gated code paths and direct writes, and only a trigger covers those. A claim table's advantage is airtightness under concurrency, which is not a real risk at 2-5 users on a LAN; its cost is that every write path must remember to update it, which is precisely the disease this ticket is treating.

Rejected alternatives, recorded so this isn't relitigated: an `active_reactor_occupancy` claim table with `UNIQUE(reactor_slot)` (self-documenting and gets a real index, but adds a fifth thing to keep in sync, and is largely subsumed by `reactors.current_experiment_fk` in the follow-up ticket); and denormalizing `status` onto `experimental_conditions` to make a partial unique index work (moves the sync problem and needs a trigger anyway).

**Three things the trigger implementation must get right:**

1. **A loud comment in `database/models/conditions.py`** pointing at the migration. A trigger is invisible to anyone reading the SQLAlchemy models, and that is its one real weakness. Document it in `MODELS.md` too.
2. **Readable errors on the bulk-upload paths.** A raw Postgres `unique_violation` surfacing as a 500 on a 200-row upload is worse than the bug. `master_bulk_upload.py` and `experiment_status.py` must catch it and emit a per-row message naming the slot and the occupying experiment.
3. **Take a row lock, not just a `SELECT count(*)`.** A bare count inside the trigger is racy under concurrent transactions. Theoretical at your scale, but `SELECT ... FOR UPDATE` on the candidate occupant costs nothing and removes the caveat.

**Also add: `CHECK (reactor_number IS NULL OR reactor_number > 0)`** — decided 2026-07-28. The eight `R00` rows in the audit exist because zero was permitted, and zero being falsy is what hid them from the occupancy logic (see §3). An upper bound is deliberately *not* added here: the ceiling differs by series (16 HPHT vs 3 CF) and cannot be expressed cleanly without the reactors table, where the foreign key gives you both bounds free.

**Migration ordering — this matters.** Both the trigger and the CHECK will fail against current production data. The prerequisite cleanup is specified in `audit-2026-07-28-results-and-cleanup.md` and must be run, committed, and verified (zero double-booked slots, zero `reactor_number = 0`) **in a separate session, by a human, before this migration runs.** Do not fold the cleanup into the migration: auto-completing experiments as a side effect of a schema change is the exact bug this ticket exists to fix.

---

## Verification

### Prerequisite: DONE (2026-07-28)

Both audit queries were run against the lab PC Postgres. Results, decisions, and the
required cleanup are in **`audit-2026-07-28-results-and-cleanup.md`**. Summary:

- **Q1 returned 2 double-booked slots**, not zero: `CF01` (3 ONGOING Core Flood runs)
  and `R00` (8 ONGOING Serum vials on `reactor_number = 0`). The constraint cannot be
  added until the cleanup in that file has been run and committed.
- **Q2 returned 223 of 984 rows (23%) with a non-canonical `experiment_type`.** No NULLs.
  The `reactor_slot` backfill must therefore run *after* normalization, or classify
  `SERUM`/`OTHER`/`AUTO`/`AUTOCLAVE`/`CF` explicitly. Simplest is to sequence this ticket
  after the cleanup, which normalizes them.

The original queries are retained below for re-running after cleanup.

### The queries

```sql
-- Existing double-bookings, by resolved slot. Must be empty before the constraint lands.
SELECT
  CASE WHEN ec.experiment_type = 'Core Flood' THEN 'CF' ELSE 'R' END
    || lpad(ec.reactor_number::text, 2, '0') AS slot,
  count(*)                        AS ongoing_count,
  array_agg(e.experiment_id)      AS experiment_ids,
  array_agg(ec.experiment_type)   AS types,
  array_agg(e.date)               AS start_dates
FROM experiments e
JOIN experimental_conditions ec ON ec.experiment_fk = e.id
WHERE e.status = 'ONGOING' AND ec.reactor_number IS NOT NULL
GROUP BY 1
HAVING count(*) > 1
ORDER BY 1;

-- Rows the backfill can't classify confidently.
SELECT ec.experiment_type, count(*)
FROM experimental_conditions ec
WHERE ec.reactor_number IS NOT NULL
  AND (ec.experiment_type IS NULL
       OR ec.experiment_type NOT IN ('HPHT', 'Core Flood'))
GROUP BY 1;
```

The second query overlaps with `issue-experiment-type-enum-binding.md` — if it returns rows, read that ticket before proceeding, because the backfill rule depends on what those values are.

### Tests to add

Extend `tests/services/bulk_uploads/test_experiment_status.py` (existing occupancy suite, ~560 lines) and `tests/api/test_dashboard.py`:

- ONGOING HPHT in `R01`; bulk status upload sets a Core Flood to ONGOING on rig 1 with a *newer* date → HPHT stays ONGOING. This test fails on `main` today; it is the regression test for the headline bug.
- Same, reversed (ONGOING CF in `CF01`, incoming HPHT on `R01`).
- Same-file upload starting an HPHT in `R01` and a Core Flood in `CF01` → preview succeeds, no `conflict_errors`. Also fails on `main`.
- `new_experiments` bulk upload: Serum row with `reactor_number = 3` while an HPHT is ONGOING in `R03` → HPHT stays ONGOING. Mirror of `test_apply_no_demotion_for_serum_type_even_with_reactor_number` (line 506) on the other path.
- `PATCH /status` to ONGOING on an occupied slot → **409**, occupant unchanged, occupying `experiment_id` present in the error detail.
- `PATCH /status` to ONGOING on an *empty* slot → 200, no regression.
- `reactor_number = 0` write → rejected by the CHECK constraint.
- Bulk upload whose row would violate the trigger → readable per-row error naming the slot and occupant, **not** a 500. This is the test that stops the trigger being worse than the bug.
- `summary.reactors.ongoing` with one ONGOING HPHT in `R01` and one ONGOING CF in `CF01` → 1 each in `reactors` and `core_floods`, `empty` correct in both. #85 already covers this; keep its assertion.
- Constraint-level: attempt to create a second ONGOING experiment in the same slot via raw ORM writes (bypassing the service layer) → raises. This is the test that proves the constraint, not the application logic, is doing the work.

Existing tests that should keep passing and are relevant to read first: `tests/api/test_dashboard.py:440` (`test_cf01_does_not_inherit_hpht_reactor_1_hardware_specs`), `:542` (`test_cf_and_hpht_in_same_reactor_number_each_get_own_slot`), `tests/api/test_conditions.py:134-216` (the 422 validation suite), `tests/services/test_notion_sync_import.py:200-265`.

---

## Data Model Notes

| Field | Change |
|---|---|
| `experimental_conditions.reactor_slot` | New, nullable `String(8)`. Canonical label (`R01`–`R16`, `CF01`–`CF02`). Indexed. Backfilled. |
| `experimental_conditions.reactor_number` | Unchanged this pass. Retained for Power BI views, the `?reactor_number=` list filter, and the data-migration scripts. |
| `experimental_conditions.experiment_type` | Unchanged this pass. See `issue-experiment-type-enum-binding.md`. |
| Occupancy uniqueness | New PL/pgSQL trigger enforcing one ONGOING experiment per `reactor_slot`. Decided 2026-07-28. |
| `experimental_conditions.reactor_number` | Gains `CHECK (reactor_number IS NULL OR reactor_number > 0)`. Decided 2026-07-28. Upper bound deferred to the reactors-table FK. |

Alembic: current single head is `daae92e908f1` (`alembic/versions/daae92e908f1_backfill_result_timepoint_buckets.py`). Branch from there. Note the repo also has a separate hand-rolled mechanism under `database/data_migrations/` — use Alembic for this, not that.

---

## Explicitly out of scope

- The `reactors` table. Tracked in `issue-reactors-table-entity.md`, which supersedes the `reactor_slot` column added here. Do not start it as part of this ticket.
- Binding `experiment_type` to the enum. Tracked in `issue-experiment-type-enum-binding.md`. The backfill here reads `experiment_type` as a string and must tolerate whatever is currently in prod.
- Removing the three dead `hasattr(row.experiment_type, "value")` blocks. They're harmless; they get deleted by the enum ticket.
- Reactor-level maintenance/out-of-service state. Needs the reactors table.

## Labels

`bug`, `data-integrity`, `database`, `bulk-upload`, `dashboard`, `priority:high`

## Relationship to #85 (`feat/issue-85-dashboard-kpi-cards`)

#85 is in flight and touches `dashboard.py` heavily (113 lines) plus `schemas/dashboard.py`. It does **not** conflict with this ticket's substance, and it already fixed the unscoped occupancy count on its own. Two consequences:

- **Let #85 land first, or rebase this onto it.** Do not fix `reactors_in_use` as part of this ticket; that field no longer exists.
- The dedup deletion in §2 should be the *last* commit here, because #85's `_occupancy` reads `reactor_cards` and its new tests in `tests/api/test_dashboard.py` (+471 lines) assert against that list. Removing the dedup before the constraint exists would make those tests non-deterministic on double-booked fixtures.

## Notes

The reason this is priority:high rather than a cleanup ticket is Defect 1 combined with Defect 3: both bulk paths can set `status = COMPLETED` on an experiment nobody touched, and Defect 4's dashboard dedup means the resulting inconsistent state is invisible in the UI. Any past occurrence would have to be found by reading the audit log in `database/event_listeners.py`. Worth running the first audit query above regardless of when this gets scheduled, just to know whether it has already happened.
