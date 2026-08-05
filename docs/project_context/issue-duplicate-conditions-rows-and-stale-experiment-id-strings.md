# bug: duplicate `experimental_conditions` rows via a stale denormalized `experiment_id` string

> **Status 2026-08-05 — SHIPPED.** Branch `fix/issue-109-duplicate-experiment-ids`.
> All figures below were measured against the production dump
> `experiments_20260805_010002.sql` (1012 experiments, 1013 conditions rows).
>
> **Initial framing was wrong.** The issue was opened as "two duplicate
> `experiments` rows" and the bulk-delete parser's `.scalar_one_or_none()` was
> suspected as the culprit. Neither survived contact with the data — see
> "What the initial framing got wrong" below.

## Root cause

`experimental_conditions` carries two identities for the same relationship:
`experiment_fk` (authoritative, non-null FK to `experiments.id`) and a
denormalized `experiment_id` string column. At the time this bug was
investigated, the single-experiment rename path (`PATCH /api/experiments/{id}`)
kept it in sync, but the **bulk** rename path
(`backend/services/bulk_uploads/new_experiments.py:543-575`) did not — it
synced `ExperimentNotes.experiment_id` and `ModificationsLog.experiment_id` on
a rename but not this column, which was the source of new staleness behind
the cleanup below. **That leak is now closed — see Follow-up.** Measured
against the production dump:

- **187 of 1013 conditions rows (18%)** carry a string that is not their
  experiment's real `experiment_id`.
- Of those, **175** name an experiment whose real ID appears on no conditions
  row at all — pure rename debris.
- **12** name a *different* experiment that has its own conditions row, so the
  detail page showed the wrong experiment's conditions.
- **6 strings appear on two rows each** (`AUTO_JW_007`,
  `HPHT_JW_005-3_Desorption`, `HPHT_JW_005-4`, `HPHT_MH_029-6`, `OTHER_JW_001`,
  `SERUM_JW_046`), which made a string-keyed lookup raise `MultipleResultsFound`.
- **Exactly one** experiment had two conditions rows: `SERUM_Cation_011a-t5`
  (experiment id 901) — cond **901** (string `'SERUM_cation_031'`, created
  2026-07-15) and cond **1062** (string `'SERUM_Cation_011a-t5'`, created
  2026-08-04 10:29). Value-identical on every scientific column; each carried
  its own copy of the same Mg(OH)₂ 0.149 g additive (ids 2342 and 2657,
  identical in every field but id, parent and timestamps). No experiment named
  `SERUM_cation_031` exists — it survives only as that stale string.
- `experiments.experiment_id` **does** carry a UNIQUE index in production
  (`ix_experiments_experiment_id`), so two duplicate *experiment* rows were
  never possible.

## Failure chain

1. `frontend/src/pages/ExperimentDetail/index.tsx:66` reads conditions via
   `GET /api/conditions/by-experiment/{id}`.
2. That endpoint filtered on the stale **string**, not `experiment_fk`, so it
   404'd for an experiment that already had a conditions row.
3. The detail page rendered its "no conditions" empty state and offered
   "Add Details".
4. `POST /api/conditions` had **no existence check**, so submitting that form
   inserted a second row for the same `experiment_fk`.

Four consumers then broke on the duplicate:

1. `_build_list_item` in `backend/api/routers/experiments.py` called
   `scalar_one_or_none()` on the conditions lookup → `MultipleResultsFound` →
   **500 on the experiments list page**.
2. The list endpoint's outer join to conditions fanned out for that one
   experiment, and the join's own comment incorrectly claimed that was
   impossible.
3. `v_experiments` / `v_experiment_conditions` LEFT JOIN conditions onto
   experiments → duplicate `experiment_id` key → **Power BI relationship
   rejected**.
4. `serialize_experiment_snapshot` in `backend/services/experiment_deletion.py`
   hit the same `MultipleResultsFound` *inside* `delete_experiment_cascade`,
   so the bulk-delete uploader caught the exception and reported the
   experiment ID in `failed` — the experiment could not be deleted through
   either delete path.

## What the initial framing got wrong

The issue was opened describing **two duplicate `experiments` rows**, with
`backend/services/bulk_uploads/experiment_deletion_bulk.py:140`
(`.scalar_one_or_none()` on `Experiment` filtered by `experiment_id`)
suspected as the point of failure, because "row exists twice, lookup raises
on more than one" was the visible symptom shape.

**That endpoint cannot raise `MultipleResultsFound`.**
`experiments.experiment_id` is UNIQUE in production
(`ix_experiments_experiment_id`), confirmed against the dump before any code
was written. The duplicate was one table deeper, on `experimental_conditions`,
which had no such constraint. The evidence that redirected the investigation:
querying `experimental_conditions` grouped by `experiment_fk` found exactly one
`HAVING COUNT(*) > 1` group (901/1062 above), while the equivalent query on
`experiments` grouped by `experiment_id` found none. Recorded here explicitly
so the next person who greps for "one or none" while debugging a similar
report is not misled into the same wrong table.

## What shipped

Six commits on `fix/issue-109-duplicate-experiment-ids`:

- `b21f7b7` — `database/data_migrations/dedupe_conditions_and_backfill_ids_018.py`
  (+ tests). Dry-run by default, `--apply` to write. Dedupe runs before
  backfill (backfilling first would make the 6 duplicated strings collide
  further). Selection is rule-based: the survivor is the row whose string
  already equals its experiment's real ID, else the lowest id; a duplicate is
  deleted **only** if value- and additive-equivalent to the survivor,
  otherwise the group is reported **BLOCKED** and left for a human.
- `cebb594` — `GET /api/conditions/by-experiment/{experiment_id}` now resolves
  through `Experiment.experiment_id` → `ExperimentalConditions.experiment_fk`,
  lowest id wins if more than one row exists.
- `b90b7fe` — `POST /api/conditions` returns **409** when a row already exists
  for that `experiment_fk`, with the existing row's id in the `detail` text.
- `4c704a5` + `6061a69` — `_build_list_item` and
  `serialize_experiment_snapshot` take the lowest-id row instead of
  `scalar_one_or_none()`; the same tolerant-read fix applied to the experiment
  detail GET, the rename path and the sample-id path in
  `backend/api/routers/experiments.py`; the list join's incorrect "cannot fan
  out" comment corrected to point at the new constraint.
- `e4fbe8a` + `1fb9a9c` —
  `UniqueConstraint("experiment_fk", name="uq_conditions_experiment_fk")` on
  the model, Alembic revision **`00063a5dd6a8`** (`down_revision`
  `1c1ef9b555e0`) whose `upgrade()` **refuses with a `RuntimeError` listing
  offenders if duplicates remain**, plus `tests/pre_constraint_conditions.py`.

**Verification:** full backend suite **3 failed, 1332 passed, 4 skipped**; the
3 are the documented pre-existing `tests/test_pg_backup_restore.py` baseline,
not a regression. `alembic upgrade → downgrade → upgrade` clean on dev;
constraint confirmed present on dev via psql.

## Known limitations — recorded, not fixed here

1. **Additive equivalence in the 018 script is `(compound_id, amount, unit)`
   only** — it ignores `lot_number`, `purity`, `supplier_lot` and
   `addition_method`. A future duplicate whose additive matches that triple
   but differs in one of those fields would be deleted along with its
   metadata. **User decision, 2026-08-05: keep it as is**, because the two
   additives in the one real duplicate (ids 2342/2657) are identical in every
   one of those fields, so the gap does not affect this cleanup. Documented as
   a known limitation of the script, not closed.
2. **`vial_count` can be inflated pre-constraint.** While a duplicate is
   present, the experiments list join fans out, so flat mode's `vial_count`
   reports 2 for that experiment and — per `.claude/rules/MODELS.md` issue
   #98 — its status cell goes read-only. Row count and IDs stay correct.
   **User decision, 2026-08-05: defer**, because this becomes impossible once
   the 018 cleanup runs and the constraint lands. Recorded as a
   pre-constraint-only symptom, not something requiring its own fix.
3. **`tests/pre_constraint_conditions.py` exists on purpose.**
   `tests/api/conftest.py`'s session fixture and two `tests/models/` module
   fixtures `drop_all` + `create_all` the shared `experiments_test` schema
   from live ORM metadata, so `uq_conditions_experiment_fk` gets baked in
   mid-run. Nine tests deliberately seed a duplicate to prove the tolerant
   readers degrade rather than 500; they wrap their bodies in
   `without_conditions_unique(session)`, which drops and restores the
   constraint on the caller's own session. Anyone adding a tenth such test
   needs that helper — it is not a hack to route around.

Also recorded at `backend/services/experiment_deletion.py:47-64`: a normal
single-row delete relies only on application code, but removing a **second**
conditions row for one experiment depends on the DB-level `ON DELETE CASCADE`
on `experimental_conditions.experiment_fk`, because `Experiment.conditions` is
`uselist=False` and the ORM cascade only reaches one row. That constraint is
present in both the 2026-08-05 production dump and the dev DB.

## Follow-up — CLOSED 2026-08-05

**The bulk rename leak is fixed, so 018's backfill no longer decays.** The
fan-out now has a single definition,
`backend/services/denormalized_ids.py::sync_denormalized_experiment_id`, called
by both rename paths: `PATCH /api/experiments/{id}` and
`backend/services/bulk_uploads/new_experiments.py` (locked file, edited with
user sign-off 2026-08-05). It covers all five tables that carry a denormalized
`experiment_id` — `experimental_conditions`, `experiment_notes`,
`modifications_log`, `external_analyses`, `xrd_phases` — where the bulk path
previously did two and PATCH did four.

Two behavioral notes:

- **`PATCH` now also updates pre-existing `modifications_log.experiment_id`
  rows**, which it did not before; the bulk path always did. Delete-snapshot
  rows (`experiment_fk = NULL`) are never matched, so history for deleted
  experiments is untouched.
- **XRD slot collisions are skipped, not raised.**
  `uq_xrd_phase_experiment_time_mineral` is keyed on the *string*. If another
  row already holds `(new_id, time_post_reaction_days, mineral_name)`, the
  phase row keeps its old string and is reported — in the upload `warnings`
  for the bulk path, and via structlog for PATCH. Renaming into an occupied
  slot would raise `IntegrityError` and take the whole rename down.

`database/data_migrations/dedupe_conditions_and_backfill_ids_018.py` is still
required to correct the 187 rows already stale; nothing new accumulates behind
it. Deploy sequence unchanged — see "Deploy to the lab PC" above.

## Resolved questions

**`_IGNORED_COLUMNS` omits the legacy `total_ferrous_iron` column, but this
does not block the real cleanup.** Verified against the 2026-08-05 dump: conds
901 and 1062 (the one production duplicate group) differ **only** on the
already-ignored columns (`id`, `experiment_id`, `created_at`, `updated_at`);
`total_ferrous_iron` and `total_ferrous_iron_g` are both `NULL` on both rows.
The group is deletable as-is; the gap would only matter for a future
duplicate that actually diverges on that column.

## Deploy to the lab PC

**Warning — do this before the branch reaches `main`, or the nightly deploy
starts failing.** `update.ps1` Step 5 runs `alembic upgrade head`
unconditionally on every nightly run and aborts the whole deploy on a non-zero
exit — before Step 6's frontend rebuild. Once this branch is on `main`, the
migration's pre-flight raises a `RuntimeError` listing the duplicate every
night until the 018 cleanup below has been applied on the lab PC, so every
nightly update fails at Step 5 and the frontend never gets rebuilt. Run steps
1–3 below on the lab PC in the same sitting as the merge, or before the next
nightly window, whichever is sooner.

Order is load-bearing — the migration's pre-flight refuses if duplicates
remain, so the cleanup must run first. The 018 script has **not** yet been
applied to any database, including dev.

```bash
# On the lab PC, after this branch reaches main:
# 1. Preview. Expect 1 duplicate group (SERUM_Cation_011a-t5) and ~187 stale strings.
.venv/Scripts/python database/data_migrations/dedupe_conditions_and_backfill_ids_018.py

# 2. Apply the data cleanup.
.venv/Scripts/python database/data_migrations/dedupe_conditions_and_backfill_ids_018.py --apply

# 3. Only then add the constraint.
.venv/Scripts/alembic upgrade head

# 4. Refresh Power BI and confirm the v_experiments relationship loads.
```

If step 1 reports any **BLOCKED** group, stop and escalate — the two rows are
not equivalent and a human must choose which survives before `--apply` or
`alembic upgrade head` can run.

## Out of scope — recorded, not fixed

Both were found during this investigation and are real. Neither is touched
here.

1. **`_id_match.py::normalize_id` conflates 13 real experiment pairs.** It
   strips punctuation and leading zeros, so `SERUM_JW_010-2` and `SERUM_JW_102`
   both normalize to `serumjw102`; `fuzzy_find_experiment` returns `.first()`
   of whichever it finds, so a bulk upload can attach results to the wrong
   experiment silently. Fixing it touches locked `bulk_uploads` parsers and
   their suites — needs its own `/start-task`.
2. **`backend/services/experimental_conditions_service.py:39` creates a
   conditions row with no existence check.** It is reachable only from
   `legacy/streamlit_frontend/`, which the current app never imports, so the
   new constraint would surface it as an `IntegrityError` rather than a silent
   duplicate. Left alone as dead legacy code.
