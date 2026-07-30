# bug: nothing enforces one ONGOING experiment per reactor slot

> **GitHub issue:** [#112](https://github.com/mathew-h/experiment-tracking-sandbox/issues/112) (filed 2026-07-30, this file is its `--body-file`).
> **Split out from:** `issue-reactor-slot-identity-and-occupancy-uniqueness.md` §4,
> on `fix/issue-97-reactor-slot-identity`. That branch shipped §1–§3 (the
> `reactor_slot` column, its backfill, the event listener, all four occupancy
> comparison sites, both `new_experiments.py` gates, and the `PATCH /status` 409).
> §4 — the PL/pgSQL uniqueness trigger and the `CHECK (reactor_number > 0)` — was
> deliberately deferred and is entirely what this ticket covers.

## Summary

`experimental_conditions.reactor_slot` (issue #97) is now the single, correctly-scoped
key for every occupancy comparison in the codebase. But nothing in the database
stops two ONGOING experiments from sharing the same slot — the application-level
checks are advisory, not enforced, and every write path that bypasses them (direct
DB edits, `database/data_migrations/` scripts using `Query.update()`, a future bug
in application code) can silently double-book a reactor with no error.

This ticket adds the constraint that makes that impossible: a trigger enforcing
one ONGOING experiment per `reactor_slot`, plus a `CHECK` constraint ruling out
`reactor_number <= 0` at the database level.

## Blocked on: the prerequisite data cleanup

**Neither half of the cleanup in `docs/issues/audit-2026-07-28-results-and-cleanup.md`
has been done.** As of 2026-07-30:

- `database/data_migrations/018*` does not exist — Part B (the data migration
  normalizing `experiment_type` and stripping `reactor_number = 0`) has not been written.
- Part A (the ten status-change clicks through the app UI) has not been confirmed done either.
- The dev DB currently has **5 double-booked slots**: `CF01` × 6, `CF03` × 5, `R00` × 8,
  `R01` × 6, `R06` × 2. (These counts are higher than the audit's original 2-slot
  finding because the lab has kept entering data in the interim — re-run the query
  before scoping work, don't assume these numbers are still current either.)
- The dev DB has **13 rows with `reactor_number = 0`**.
- Prod had 2 double-booked slots and 11 zero-rows as of 2026-07-28, per the audit.

**Both verification queries at the bottom of `audit-2026-07-28-results-and-cleanup.md`
must return zero rows before the trigger migration is written.** Re-run them fresh —
do not reuse the counts in this ticket or in the audit file, both are already stale
relative to each other.

### Why the ordering is not optional

`update.ps1` runs `alembic upgrade head` on the lab PC nightly, unattended. A
migration that fails against live data (because the trigger rejects an existing
double-booking, or the CHECK rejects an existing zero) breaks the entire deploy
pipeline until someone fixes it on the lab PC by hand. The cleanup must be run,
committed, and verified clean in its own separate, human-run session — never folded
into the same session as the trigger migration, and never automated as a side
effect of a schema change. (This is the same reasoning `audit-2026-07-28-results-and-cleanup.md`
gives for why Part A/B were split from each other and from this ticket in the first place.)

## What #97 already delivered that this builds on

- `reactor_slot` is populated on every occupancy-bearing row and is the key for
  every occupancy comparison in application code — so the trigger's own logic is a
  one-column equality check, not a two-column derivation.
- `reactor_slot` is already `NULL` for `reactor_number <= 0` (`derive_reactor_slot`
  in `database/reactor_slot.py` rejects zero and negative numbers). So the `R00`
  class of row is already excluded from occupancy logic today — the `CHECK`
  constraint this ticket adds is about data hygiene (stopping a new zero from being
  written), not correctness (a zero can no longer cause an occupancy collision
  regardless).

## The three implementation requirements

Copied verbatim from §4 of the original issue — still binding:

1. **A loud comment in `database/models/conditions.py`** pointing at the migration
   that adds the trigger. A trigger is invisible to anyone reading the SQLAlchemy
   models, and that is its one real weakness. Document it in `.claude/rules/MODELS.md` too.
2. **Readable per-row errors on the bulk-upload paths.** A raw Postgres
   `unique_violation` surfacing as a 500 on a 200-row upload is worse than the bug
   it replaces. `master_bulk_upload.py` and `experiment_status.py` must catch it and
   emit a per-row message naming the slot and the occupying experiment, not a crash.
3. **`SELECT ... FOR UPDATE` on the candidate occupant, not a bare `count(*)`,**
   inside the trigger function. A bare count is racy under concurrent transactions.
   Theoretical at this lab's scale (2–5 concurrent users on a LAN), but the row lock
   costs nothing and removes the caveat entirely.

## The design constraint that rules out a partial unique index

`Experiment.status` and `ExperimentalConditions.reactor_slot` live on different
tables. Postgres partial unique indexes and exclusion constraints are both
single-table, so `CREATE UNIQUE INDEX ... WHERE status = 'ONGOING'` is not directly
expressible across the join. **Decided: a PL/pgSQL trigger** — one function raising
`unique_violation`, wired to `BEFORE INSERT OR UPDATE` on `experiments` (when
`status` becomes `ONGOING`) and on `experimental_conditions` (when `reactor_slot` or
`experiment_type` changes).

**Rejected alternatives, recorded so they are not relitigated:**

- **A claim table** (`active_reactor_occupancy` with `UNIQUE(reactor_slot)`) — airtight
  under concurrency, which is not a real risk at this scale, and adds a fifth thing
  every write path must remember to keep in sync, which is the exact disease this
  ticket is treating. Largely subsumed by `reactors.current_experiment_fk` in the
  separate `issue-reactors-table-entity.md` ticket, if that ever gets built.
- **Denormalizing `status` onto `experimental_conditions`** to make a partial unique
  index work — moves the sync problem rather than solving it, and still needs a
  trigger to keep the denormalized copy current.

## Also required: pass `newer_than` on the new-experiments path

This is the last piece of #97's own §3, deliberately left undone there and now
folded into this ticket because the two share a root cause.

`new_experiments.py` fixed the eligibility gate and the falsy-zero bug at both
occupancy call sites in #97, but deliberately left `newer_than` unpassed. The
issue's own rationale for passing it was "let the trigger be the backstop" — and
there was no trigger yet. Once this ticket's trigger exists, failing open (declining
to demote when a date is missing) produces a **loud row-level error on the upload
instead of silent corruption**, which is the behavior we actually want. So: pass
`newer_than=experiment.date` at both call sites in the same change as the trigger,
and route the resulting `unique_violation` through requirement 2 above.

**Expect a pinned test to need updating when this lands:**
`tests/services/bulk_uploads/test_new_experiments.py::test_reactivation_via_overwrite_demotes_prior_reactor_occupant`
(line 79 as of #97) seeds a dateless occupant and asserts demotion — exactly the
case this guard changes. Update the fixture to carry a date, or update the
assertion to expect the guard now firing; whichever matches the case the test is
meant to cover.

## Two cleanups gated on the constraint landing, not before

- **Delete the `seen_labels` dedup at `dashboard.py:126-140`.** It is dead once
  one-ONGOING-per-slot is enforced, and while it exists it hides constraint
  violations from `_occupancy()` and from the reactor grid. `issue-reactor-slot-identity-and-occupancy-uniqueness.md`
  §2 already says explicitly: delete it only *after* the constraint is verified,
  not before — removing it earlier would just make an existing double-booking
  render twice with no explanation.
- **Re-verify `summary.reactors.empty`** (`backend/api/routers/dashboard.py::_occupancy`).
  It currently reads one too high per double-booked slot because it counts the
  deduped `reactor_cards` list. Once the dedup above is gone and the constraint
  guarantees at most one ONGOING row per slot, confirm the arithmetic
  (`ongoing + queued + empty == total`) actually holds against a live double-booking
  fixture, not just by construction.

## The open question that must be re-settled before scoping the trigger

**Does an Autoclave experiment ever occupy one of the numbered HPHT vessels?**

Answered **"no" for #97's scope, 2026-07-29** (see
`docs/issues/audit-2026-07-28-results-and-cleanup.md`, "NEW open question" section,
and the comment on `_SERIES_BY_TYPE` in `database/reactor_slot.py`): the audit found
`AUTO_JW_022`–`024` carrying historical HPHT vessel numbers, all COMPLETED and
therefore inert, so `#97` left Autoclave out of the occupancy-bearing type set.

This must be **re-confirmed with the team before this ticket fixes the trigger's
scope**, because a trigger scoped to two series (HPHT, Core Flood) will not stop an
Autoclave and an HPHT both claiming `R01` as ONGOING. If the answer changes to
"yes": add `"autoclave": "R"` to `_SERIES_BY_TYPE` in `database/reactor_slot.py`,
add `"Autoclave"` to the dashboard's occupancy `in_(...)` filters, and widen the
trigger's scope to three series. Nothing else in `database/reactor_slot.py` needs
to change — the mapping was built to make this a one-line addition.

## Known gaps this ticket should also close (triaged from the #97 branch ledger)

Two items surfaced during #97 implementation that are specifically dangerous
*because* the constraint doesn't exist yet — they belong here, not in a general
hygiene ticket, because the trigger is what makes them safe to leave alone:

- **The silent `slot is None` early return in `manage_reactor_occupancy`**
  (`experiment_status.py`). A typo'd `reactor_number = 0` gets no occupancy check
  *and* no warning today, because `derive_reactor_slot` returns `None` for it and
  the function returns early with nothing logged. With the `CHECK` constraint in
  this ticket, a zero can no longer be written in the first place, which closes
  this gap as a side effect — but confirm that during implementation rather than
  assuming it, since the early return would still fire silently for any other
  `None`-producing input (e.g. an unparseable `reactor_number`).
- **The widened `try/except Exception` in `manage_reactor_occupancy`** now also
  wraps the derive-fallback and a `.conditions` lazy load, so a
  `DetachedInstanceError` there would be swallowed into `warnings` (never `errors`)
  and the upload would report success while occupancy silently never ran. Worth a
  narrower `except` or an explicit re-raise for that specific failure mode while
  this file is open for the `unique_violation` handling in requirement 2 above —
  they're the same code path.

## Deliberately left to a separate hygiene ticket, not this one

Two more items surfaced on the same branch ledger, but they're pre-existing
repo-wide properties unrelated to reactor occupancy specifically, and bundling them
here would blur what this ticket is actually blocked on:

- **The listener does not fire for a bulk `Query.update()` / Core `UPDATE`.**
  `database/data_migrations/swap_reactor_4_7_015.py:96-109` is the existing
  precedent for that idiom (it predates `reactor_slot` and is unaffected). Any
  future script that changes `reactor_number` or `experiment_type` via bulk update
  must recompute `reactor_slot` explicitly in the same script — this is now
  documented in `.claude/rules/MODELS.md`, and the trigger itself is the real
  backstop against a script that forgets, so it doesn't need its own fix here.
- **No flake8 config exists repo-wide** (a bare run uses the 79-char default; the
  project convention is 120), **and the test suite cannot tolerate two concurrent
  runs against the shared `experiments_test` database** (`Base.metadata.drop_all`
  at five sites, the same fragility behind the three known
  `tests/test_pg_backup_restore.py` failures). Neither is specific to reactor
  occupancy; both deserve their own hygiene ticket.

## Verification

- Both audit queries in `audit-2026-07-28-results-and-cleanup.md` return zero rows
  (re-run fresh, do not trust any count in this ticket or that file).
- Migration round-trip (`upgrade head` → `downgrade -1` → `upgrade head`) clean
  against a Postgres copy seeded with the current dev DB's data shape.
- New test: raw ORM write of a second ONGOING experiment into an already-occupied
  slot, bypassing the service layer entirely, raises. This is the test that proves
  the *database* is doing the work, not just application code.
- New test: `reactor_number = 0` write rejected by the CHECK constraint.
- New test: a bulk upload row that would violate the trigger produces a readable
  per-row error naming the slot and the occupant — not a 500. This is the test that
  stops the trigger being worse than the bug it replaces.
- New test: `new_experiments.py` bulk upload with `newer_than` now passed — the
  updated `test_reactivation_via_overwrite_demotes_prior_reactor_occupant` (or its
  replacement) asserts the new, guarded behavior.
- `seen_labels` dedup removed; `tests/api/test_dashboard.py` double-booking
  fixtures (if any still exist post-cleanup) updated to expect the undeduped count.

## Labels

`bug`, `data-integrity`, `database`
