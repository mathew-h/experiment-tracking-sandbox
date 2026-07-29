# Prod audit results, 2026-07-28 — and the cleanup it unblocks

Ran `docs/issues/audit-queries.sql` against the lab PC Postgres (984 experiments,
newest `created_at` 2026-07-28 14:52, confirmed production).

This file records the results, the decisions Mat made on them, and the cleanup
statements those decisions imply. It unblocks:

- `issue-reactor-slot-identity-and-occupancy-uniqueness.md` §4 (uniqueness constraint)
- `issue-experiment-type-enum-binding.md` (scope was gated on Q2)

---

## Q1 — double-booked ONGOING slots: NOT EMPTY (2 slots)

| slot | ongoing | experiment_ids | types | start dates |
|---|---|---|---|---|
| `CF01` | 3 | `CF_018-2`, `CF_018`, `CF_018-3` | Core Flood ×3 | 2026-07-20, 2026-07-13, 2026-07-24 |
| `R00` | 8 | `SERUM_JW_153` … `SERUM_JW_160` | Serum ×8 | all 2025-12-09 |

**CF01.** Three sequential re-runs of one base experiment, all left ONGOING. All
three carry dates, so the `newer_than` date guard would have demoted the older two
had they arrived via the bulk status path. They didn't — which points at
`PATCH /api/experiments/{id}/status` (`backend/api/routers/experiments.py:519-535`),
which performs no occupancy management whatsoever. This is Defect 4 of the reactor
ticket, observed in production data.

**R00.** `reactor_number = 0`. Not a real slot. Two defects compounding:

1. Serum experiments carrying a `reactor_number` at all. `backend/api/routers/conditions.py:16-25`
   returns 422 for this, but neither bulk-upload path applies that gate.
2. `0` is falsy in Python, so the `if conditions.reactor_number` guard at
   `new_experiments.py:634` and `:706` never fires for these rows. Listed as a
   minor aside in the reactor ticket; it is live.

Mitigating: `_occupancy()` (`dashboard.py:48-63`) filters to the valid `R01`–`R16`
label set, so R00 never reached the dashboard counts. #85's guard did its job.

Also flagged: these eight have been ONGOING since December 2025.

## Q2 — `experiment_type` values: 223 of 984 rows (23%) non-canonical

| value | n | canonical? |
|---|---|---|
| `Serum` | 341 | yes |
| `HPHT` | 332 | yes |
| `SERUM` | 192 | **no** |
| `Autoclave` | 37 | yes |
| `Core Flood` | 30 | yes |
| `Other` | 21 | yes |
| `OTHER` | 17 | **no** |
| `AUTO` | 9 | **no** |
| `AUTOCLAVE` | 4 | **no** |
| `CF` | 1 | **no** |

No NULLs — so `NOT NULL` is achievable after normalization, and §3 of the enum
ticket (nullability decision) resolves to "yes, make it NOT NULL".

### CONFIRMED LIVE BUG: the #85 Serum KPI is undercounting by ~72%

Re-checked 2026-07-29. `SERUM` is not a legacy spelling — it is the **most recently
written value of all ten**, last seen 2026-07-29, more recent than `HPHT` (07-28) or
`Serum` (07-27). Both spellings are in active use.

Within the KPI's own window:

```
 experiment_type |  n
-----------------+-----
 Serum           |  50
 SERUM           | 128
```

`dashboard.py:212` matches `experiment_type == "Serum"` exactly, so the card shows
**50 of 178** serum vials. It has been wrong since #85 shipped.

**Mitigation available today, independent of this ticket:** make that one predicate
case-insensitive. It does not wait on the normalization migration and it does not wait
on the enum ticket.

```python
# dashboard.py:212
.where(func.upper(ExperimentalConditions.experiment_type) == "SERUM")
```

This raises the priority of `issue-experiment-type-enum-binding.md` from tech-debt
cleanup to the root cause of a wrong number on a dashboard the team reads daily.

## Q3 — 18 rows carry a `reactor_number` with a non-HPHT/CF type

| type | n | experiment_ids |
|---|---|---|
| `Serum` | 10 | `HPHT_101`, `OTHER_JW_005`, `SERUM_JW_153`–`160` |
| `AUTO` | 6 | `AUTO_JW_022`, `-2`, `AUTO_JW_023`, `-2`, `AUTO_JW_024`, `-2` |
| `Autoclave` | 1 | `AUTOCLAVE_025` |
| `Other` | 1 | `OTHER_MH_019` |

`HPHT_101` is an HPHT run mistyped as Serum (confirmed with Mat). It is not
currently ONGOING, so correcting its type cannot create a new slot collision.

## Q4 — current occupancy

12 HPHT slots occupied (`R01`–`R09`, `R11`, `R13`, `R15`), `CF01` (×3), `CF02`,
plus the 8 phantom `R00` rows. `R10`, `R12`, `R14`, `R16` empty.

---

## Decisions (Mat, 2026-07-28)

1. **CF01** — `CF_018-3` is the live experiment. `CF_018` and `CF_018-2` complete.
2. **R00** — Serum vials should never carry a `reactor_number`. The eight can be
   marked COMPLETED.
3. **Normalization** — `AUTO` and `AUTOCLAVE` are the same thing. Fuzzy ID matching
   should apply generally (see "Fuzzy matching" below — largely already built).
4. **`HPHT_101`** — HPHT run mistyped as Serum; correct the type.

### Resolved 2026-07-29: leave the non-occupancy reactor numbers alone

Full listing of all 18 rows with a `reactor_number` and a non-HPHT/CF type shows two
distinct groups:

- **Meaningless zeros (5 rows, all COMPLETED except the Serum vials):** `AUTOCLAVE_025`,
  `OTHER_JW_005`, `OTHER_MH_019`, plus the eight `SERUM_JW_153`–`160`. Cleanup step 2
  NULLs all of these.
- **Real vessel numbers (7 rows, all COMPLETED):** `AUTO_JW_022` → 1, `AUTO_JW_022-2` → 2,
  `AUTO_JW_023` → 3, `AUTO_JW_023-2` → 5, `AUTO_JW_024-2` → 6, `AUTO_JW_024` → 7, and
  `HPHT_101` → 8.

Those seven are almost certainly accurate history: the autoclave runs appear to have
occupied HPHT vessels R01–R07. **Do not strip them.** They are inert once Defect 3 of the
reactor ticket lands (the eligibility gate stops a non-occupancy type demoting anyone),
and all seven are COMPLETED, so there is no present risk.

### NEW open question this surfaced — settle before writing the trigger

`_OCCUPANCY_TYPES = {"hpht", "core flood"}` (`experiment_status.py:17`) may be wrong.
If autoclave runs genuinely occupy HPHT vessels 1–7, then **Autoclave is an
occupancy-bearing type** and excluding it means:

- the dashboard will not show an autoclave run as occupying a vessel; the slot renders empty
- a type-scoped uniqueness trigger will not stop an Autoclave and an HPHT both claiming
  R01 as ONGOING

Moot today (every `AUTO`/`Autoclave` row with a reactor number is COMPLETED), but it
determines whether the trigger scopes to two types or three. **Ask the team whether
autoclave experiments run in the numbered HPHT vessels.** If yes, add `"autoclave"` to
`_OCCUPANCY_TYPES`, to the dashboard's `in_(...)` filters, and to the trigger's scope.

### Still open

- Whether long-stale ONGOING experiments exist beyond the eight R00 vials.

---

## Cleanup — do NOT hand-run this as psql SQL

**Superseded approach.** An earlier draft of this file presented the statements below as
a psql transaction to run by hand. That was wrong for this repo. Two corrections:

1. **`docs/PSQL_ACCESS.md` §9 forbids psql writes as policy**, and the reasoning is sound:
   raw SQL bypasses `ModificationsLog`, and for calculation-input fields it would leave
   derived values stale because the calculation engine only runs on ORM writes.
2. **`database/data_migrations/` is the established pattern** for exactly this, with 17
   numbered precedents. `swap_reactor_4_7_015.py` is the closest analogue — it corrects
   `reactor_number` values in bulk, with `--dry-run` / `--confirm` gates, a nested
   savepoint for preview, and a test in `tests/data_migrations/`.

**Scope note on the calculation-engine concern:** it does not apply to this particular
cleanup. The persisted derived fields are ammonium yield, H₂ yield, ferrous iron yield and
catalyst loadings; their inputs are rock mass, FeO wt%, concentrations and gas volumes.
`experiment_type`, `reactor_number` and `experiments.status` feed none of them, so nothing
here leaves a derived value stale. The `ModificationsLog` concern is real and is why the
work is split below.

### Split the work

**Part A — status changes, through the app UI.** Ten clicks, goes through the ORM, lands
in `ModificationsLog` properly. Do not automate this.

- Mark `CF_018` and `CF_018-2` COMPLETED (keep `CF_018-3` ONGOING).
- Mark `SERUM_JW_153`–`SERUM_JW_160` COMPLETED.

**Part B — field corrections, as data migration `018`.** Hand to Claude Code, following
the `swap_reactor_4_7_015.py` pattern exactly: module docstring with background and run
instructions, `--dry-run` using `db.begin_nested()`, `--confirm` required for live, summary
counts printed, and a test under `tests/data_migrations/`.

- Normalize `experiment_type` to the five canonical values.
- `reactor_number = 0` → `NULL` (11 rows).
- `HPHT_101.experiment_type` `'Serum'` → `'HPHT'`.

The statements below are the **specification** for Part B, not something to paste into a
terminal.

> **Row counts drift — do not assert on them.** Re-checked 2026-07-29: the table grew from
> 984 to 1016 experiments in two days, `SERUM` moved 192 → 179 and `Serum` 341 → 386. The
> lab enters data continuously. The migration should print counts, not assert fixed ones.
> **The two verification queries at the bottom are the real gates.**

```sql
BEGIN;

-- 1. CF01: keep CF_018-3 ONGOING, complete the two superseded runs.
UPDATE experiments
SET status = 'COMPLETED', updated_at = now()
WHERE experiment_id IN ('CF_018', 'CF_018-2')
  AND status = 'ONGOING';
-- expect: UPDATE 2

-- 2. reactor_number = 0 is not a slot. Strip it. Scoped by = 0 so it cannot
--    touch a real slot.
--    NOTE: this hits 11 rows, not 8. Besides the eight SERUM_JW vials, three
--    COMPLETED rows also carry zero: AUTOCLAVE_025, OTHER_JW_005, OTHER_MH_019.
--    Zero is meaningless for all of them, and the CHECK constraint in the reactor
--    ticket fails until every one is NULL.
UPDATE experimental_conditions ec
SET reactor_number = NULL
WHERE ec.reactor_number = 0;
-- expect: UPDATE 11

UPDATE experiments e
SET status = 'COMPLETED', updated_at = now()
WHERE e.experiment_id IN (
  'SERUM_JW_153','SERUM_JW_154','SERUM_JW_155','SERUM_JW_156',
  'SERUM_JW_157','SERUM_JW_158','SERUM_JW_159','SERUM_JW_160'
) AND e.status = 'ONGOING';
-- expect: UPDATE 8

-- 3. Normalize experiment_type to the five canonical ExperimentType values.
UPDATE experimental_conditions SET experiment_type = 'Serum'      WHERE experiment_type = 'SERUM';
UPDATE experimental_conditions SET experiment_type = 'Other'      WHERE experiment_type = 'OTHER';
UPDATE experimental_conditions SET experiment_type = 'Autoclave'  WHERE experiment_type IN ('AUTOCLAVE', 'AUTO');
UPDATE experimental_conditions SET experiment_type = 'Core Flood' WHERE experiment_type = 'CF';
-- expect: 192, 17, 13, 1

-- 4. HPHT_101 was mistyped as Serum.
UPDATE experimental_conditions ec
SET experiment_type = 'HPHT'
FROM experiments e
WHERE e.id = ec.experiment_fk AND e.experiment_id = 'HPHT_101';
-- expect: UPDATE 1

-- ── VERIFY ───────────────────────────────────────────────────────────────
-- (a) only canonical values remain, no NULLs
SELECT experiment_type, count(*) FROM experimental_conditions GROUP BY 1 ORDER BY 2 DESC;

-- (b) zero double-booked slots — this is the gate on the uniqueness constraint
SELECT
  CASE WHEN ec.experiment_type = 'Core Flood' THEN 'CF' ELSE 'R' END
    || lpad(ec.reactor_number::text, 2, '0') AS slot,
  count(*), array_agg(e.experiment_id)
FROM experiments e
JOIN experimental_conditions ec ON ec.experiment_fk = e.id
WHERE e.status = 'ONGOING' AND ec.reactor_number IS NOT NULL
GROUP BY 1 HAVING count(*) > 1;
-- expect: 0 rows

-- COMMIT;    -- uncomment only after both checks look right
-- ROLLBACK;
```

**Do not add the uniqueness constraint in the same session.** Run this, confirm
verification (b) returns zero rows, commit, then let the reactor ticket's migration
add the constraint as a separate, reviewable change.

---

## Fuzzy matching — already built, coverage is the gap

Decision 3 asked for fuzzy experiment-ID matching, with the example
`SERUM_pH_001` = `sErumpH001` = `serum_pH_001`.

**This already exists** and produces exactly that result.
`backend/services/bulk_uploads/_id_match.py::normalize_id` lowercases, strips all
non-alphanumeric characters, then strips leading zeros from numeric segments. All
three of those spellings normalize to `serumph1`. It exposes `fuzzy_find_sample`
and `fuzzy_find_experiment`, each trying an exact indexed match first and falling
back to a normalized scan. Origin: `docs/superpowers/plans/2026-03-27-issue-14-fuzzy-matching-master-upload.md`.

So this is not a build. Three real gaps:

1. **Coverage.** Only five modules import it: `actlabs_titration_data.py`,
   `actlabs_xrd_report.py`, `timepoint_modifications.py`, `notion_sync/import_.py`,
   `scalar_results_service.py`. Notably **absent**: `new_experiments.py`,
   `master_bulk_upload.py`, `experiment_status.py`, and every API router. The
   highest-volume upload paths do not use it.

2. **`AUTO` is missing from the abbreviation map.**
   `database/experiment_id_parser.py:37-48` (`EXPERIMENT_TYPE_ABBREVIATIONS`) has
   `serum`, `autoclave`, `hpht`, `coreflood`, `core flood`, `cf`, `other`, `ac` —
   but no `auto`. That is why `AUTO_JW_022` never had its type inferred and the
   raw prefix landed in the column. Add `"auto": ExperimentType.AUTOCLAVE`.

3. **Performance.** `fuzzy_find_experiment`'s fallback loads every `Experiment` row
   and normalizes in Python, so it is O(n) per miss. Fine at 984 rows; a 100-row
   upload of non-matching IDs is ~98k normalizations. Worth a note, not urgent.
   `pg_trgm` is already installed (`scripts/init-db.sql`) if this ever needs to
   move into SQL.

**Important limit to be explicit about.** `experiments.experiment_id` is
`unique=True` (`database/models/experiments.py:12`). Fuzzy matching resolves *input*
to an existing row; it cannot merge rows that already exist. If both
`SERUM_pH_001` and `serum_pH_001` are stored as separate experiments today, that is
a data problem fuzzy matching will not fix. Worth checking:

```sql
SELECT lower(regexp_replace(experiment_id, '[^A-Za-z0-9]', '', 'g')) AS norm,
       count(*), array_agg(experiment_id)
FROM experiments
GROUP BY 1 HAVING count(*) > 1;
```

(Looser than `normalize_id` — it skips the leading-zero strip — so it will catch
case and separator collisions but not `HPHT_001` vs `HPHT_1`.)

Recommend a separate ticket for gaps 1 and 2. Gap 2 is a one-line change and
belongs with the enum ticket.
