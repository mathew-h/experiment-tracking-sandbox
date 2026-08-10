# bug: `v_results_scalar_rollup.n_replicates` is wrong in 32% of groups; 41% of primary results have a NULL timepoint bucket

> **Status 2026-08-01 — FIXES 1, 4, 5 and 6 SHIPPED; 2 and 3 still open.** Branch
> `fix/rollup-replicate-count-mismatch`. All figures below were measured against
> the production backup `docs/sample_data/experiments_20260801_010003.sql`
> (pg_dump -Fc, PostgreSQL 18.3, taken 2026-08-01 01:00) restored into the local
> dev database.
>
> **User decisions (2026-08-01):** backfill NULL buckets *only* where a day token
> is available; day 3 is the truth for the six `-t3` vials; breaking the
> `n_replicates` column name is acceptable.
>
> **What shipped**
> - **Fix 1** — `n_replicates` replaced by `n_vials` / `n_replicate_letters` /
>   `n_values`, LEFT JOIN → INNER. Carried through the API schema, the TS type
>   and the React group page (the column is not Power-BI-only: the app reads it
>   via `replicate_groups.resolve_rollup_rows`). 4 new tests; 1312 backend tests
>   pass, 14 frontend.
> - **Fix 4** — `database/data_migrations/demote_stale_t3_prefix_rows_017.py`.
>   **The investigation below was wrong about the remedy** and the script does not
>   do what Fix 4 originally proposed — see the correction in that section.
> - **Fixes 5 and 6** — documentation, applied.
>
> **Still open:** Fix 2 (`NULLS NOT DISTINCT`, needs schema-checklist sign-off)
> and Fix 3 (the NULL-bucket backfill, whose scope changed materially — see the
> correction in that section).

## Reported symptoms

1. "The rollup table replicate counts is not representative of the totals of the
   raw experiment ids."
2. "I can see all experiments on the data app, but when I try to query them in
   Power BI or SQL I don't see all experiment ids."

Both reproduce. They have **different causes** and symptom 2 is largely not a bug.

## Restored dataset

| Table | Rows |
|---|---|
| `experiments` | 1009 |
| `experimental_conditions` | 1009 |
| `experimental_results` | 1961 (1959 primary) |
| `scalar_results` | 1465 |
| `icp_results` | 969 |
| `modifications_log` | 55,601 |

`alembic_version` = `1c1ef9b555e0` (current head). All 16 reporting views restored.
`reactor_slot` integrity verified intact — 217 slots across HPHT (206) and Core
Flood (11); the 7 `reactor_number > 0` rows without a slot are all Autoclave (6)
and Serum (1), which correctly hold no physical slot.

## Layer-by-layer evidence

| Layer | Rows | Distinct experiment IDs |
|---|---|---|
| `experiments` (raw) | 1009 | **1009** |
| `v_experiments` | 1009 | **1009** |
| `v_dim_timepoints` | 1959 | 717 |
| `v_results_scalar` | 1959 | 717 |
| `v_results_h2` | 466 | 202 |
| `v_results_icp` | 969 | 278 |
| `v_results_scalar_rollup` | 1412 | 564 (base IDs) |

---

## Symptom 2 — "not all experiment IDs in Power BI" — mostly NOT a bug

`v_experiments` exposes **all 1009** experiment IDs. Nothing is being filtered
out of the experiment dimension.

The 717 figure in the result views is correct and expected:

- **292 experiments have no `experimental_results` rows at all.** They are real
  experiments (queued, ongoing, or never sampled) and legitimately have nothing
  to show in a *results* view.
- **0 experiments have results but no primary row** — the primary-flag filter is
  not dropping anyone.
- **78 experiments have results but no `scalar_results`** — these appear in
  `v_dim_timepoints` but are blank/absent in `v_results_scalar`.

**The real defect here is a Power BI modelling trap, not a view bug.** Any visual
whose table comes from `v_dim_timepoints` / `v_results_scalar` / the rollup will
silently drop those 292 experiments. To list all experiments you must build the
visual on `v_experiments` and LEFT-join results onto it. This is worth an explicit
warning in `docs/POWERBI_MODEL.md`, which currently does not mention it.

---

## Symptom 1 — `n_replicates` is genuinely wrong

**457 of 1412 rollup groups (32%) report an `n_replicates` that does not equal
the number of distinct experiments in that group and bucket.** Three independent
root causes, in order of impact.

### Root cause A — `n_replicates` counts result rows, not experiments

`database/event_listeners.py:529`:

```sql
COUNT(sr.result_id) AS n_replicates
...
LEFT JOIN scalar_results sr ON sr.result_id = er.id
```

`COUNT(sr.result_id)` over a **LEFT** join counts *scalar result rows*, which is
neither the number of replicates nor the number of vials. Two consequences:

- **335 groups report `n_replicates = 0`.** All 335 are ICP-only timepoints: the
  experiment has a primary result row but no `scalar_results` row, so the LEFT
  join contributes NULL and `COUNT` returns 0 — while the group still renders as
  a row with NULL statistics. These are phantom rows in a *scalar* rollup.
  `SERUM_JW_054` alone produces **12 buckets, every one reporting 0 replicates**.
- **162 groups over-count**, because one experiment contributing several primary
  rows to the same bucket is counted once per row rather than once.

The name is also wrong independent of the arithmetic: even when correct, this is a
count of *vials*, not of replicate *letters*. Per `MODELS.md` (issue #98) the
letter is the scientific unit and a `-t<days>` vial is one destructively-sampled
instance of it — so a group with 3 letters × 2 vials each reports 6.

### Root cause B — 41% of primary results have a NULL timepoint bucket

**807 of 1959 primary result rows have `time_post_reaction_bucket_days IS NULL`**
(and `time_post_reaction_days IS NULL`). They collapse into a single `(base, NULL)`
group — 348 such groups — which averages *every timepoint of every replicate*
together as though it were one measurement.

`HPHT_MH_029`: 7 distinct experiments across many timepoints → one NULL-bucket
row reporting `n_replicates = 16`.

**This is legacy data, not an ongoing regression.** NULL-bucket primary rows by
creation month:

| Month | Primary rows | NULL bucket |
|---|---|---|
| 2026-03 … 2026-07 | 751 | **0** |
| 2026-02 | 348 | 25 |
| 2026-01 | 77 | 25 |
| 2025-12 | 58 | 34 |
| 2025-11 | 18 | 16 |
| 2025-10 and earlier | — | rest of the 807 |

The write path was fixed; the historical rows were never backfilled.
**`MODELS.md` currently claims "a data migration backfilled all pre-existing
NULL-bucket rows" — that claim is false against production** and should be
corrected regardless of what else is done here.

Backfill sources, measured:

- from `experiments.id_timepoint_days`: **0 of 807** (all NULL)
- from `cumulative_time_post_reaction_days`: **0 of 807** (all NULL)
- from a `_day<N>_` token in `description`: **206 of 807** (e.g.
  `ICP Analysis - SERUM_JW_054_day14_5x`)

The remaining ~601 rows carry no recoverable timepoint in any column.

### Root cause C — the uniqueness constraint does not fire on NULL buckets

```sql
CREATE UNIQUE INDEX uq_primary_result_per_experiment_bucket
  ON experimental_results (experiment_fk, time_post_reaction_bucket_days)
  WHERE (is_primary_timepoint_result = true);
```

In PostgreSQL `NULL != NULL` in a unique index by default, so this constraint is
**completely inert whenever the bucket is NULL**. Measured consequence:

- **198 `(experiment, NULL-bucket)` pairs hold duplicate primary rows — 397
  excess primary rows.**
- **Zero duplicates exist on any real bucket.**

That split is proof the constraint works exactly as intended when the bucket is
populated and silently fails when it is not. Root cause B is what exposes it.

### Root cause D — 6 stale `-t3` vials sitting in the wrong bucket

Six vials whose ID encodes day 3 hold primary results at day 6–7:

| experiment_id | ID says | bucket says |
|---|---|---|
| `SERUM_pH_001a-t3` | 3 | 7 |
| `SERUM_pH_001c-t3` | 3 | 7 |
| `SERUM_pH_002-t3` | 3 | 7 |
| `SERUM_pH_003a-t3` | 3 | 7 |
| `SERUM_pH_004-t3` | 3 | 6 |
| `SERUM_pH_006-t3` | 3 | 7 |

This inflates `SERUM_pH_001`'s day-7 bucket to `n_replicates = 5` in a group that
has only 3 replicate letters — the clearest instance of the reported symptom.

**The code is already correct.** All 6 rows were created 2026-07-28/29;
`master_bulk_upload.py` was changed to let the ID token win over the Duration
column in commit `9ea8962` on **2026-07-30**. These are 6 stale rows from the
two-day window before that fix, not a live defect. Overall the token path is
healthy: 48 of 54 `-t` vial primary rows sit in the bucket their ID encodes, and
all 167 `-t` experiments have correct `base_experiment_id` with the token
stripped.

---

## Proposed fixes

### Fix 1 — correct `n_replicates` and drop the phantom groups (highest value)

In `database/event_listeners.py`, change the rollup to an INNER join and count
distinct experiments:

```sql
COUNT(DISTINCT e.id)                    AS n_replicates,   -- was COUNT(sr.result_id)
COUNT(DISTINCT e.replicate_label)       AS n_letters,      -- new
COUNT(*)                                AS n_scalar_rows,  -- new, transparency
...
JOIN scalar_results sr ON sr.result_id = er.id             -- was LEFT JOIN
```

**Validated against the restored production data:**

| | current | fixed |
|---|---|---|
| rollup groups | 1412 | 1077 |
| groups reporting `n_replicates = 0` | 335 | **0** |
| groups where `n_replicates` ≠ distinct experiments | 457 | **0** |

The 335 dropped groups are exactly the ICP-only ones, which do not belong in a
scalar rollup. Adding `n_letters` alongside `n_replicates` makes the
letter-vs-vial distinction visible in Power BI for the first time and exposes
root cause D directly (`SERUM_pH_001` day 7 shows 5 vials / 3 letters).

*View-only change — no migration, no model change. Recreated at startup by the
module-level block in `database/event_listeners.py` (there is no
`create_reporting_views()` function; that name was never real).*

### Fix 2 — make the uniqueness constraint fire on NULL buckets

PostgreSQL 15+ (production runs 18.3) supports:

```sql
CREATE UNIQUE INDEX uq_primary_result_per_experiment_bucket
  ON experimental_results (experiment_fk, time_post_reaction_bucket_days)
  NULLS NOT DISTINCT
  WHERE (is_primary_timepoint_result = true);
```

**Blocked on cleaning the existing 198 duplicate pairs first** — the index will
not build while they exist. Requires an Alembic migration; it is a constraint
*tightening*, so it is not purely additive and needs sign-off per
`.claude/rules/schema-checklist.md` Phase 2.

### Fix 3 — backfill the 807 NULL buckets — **SCOPE CORRECTED, STILL OPEN**

User decision: backfill only where a day token is available. That authorises the
206 `_day<N>_` rows and leaves the other ~601 NULL, which is the right call —
those have no recoverable timepoint in any column and inventing one would be
fabrication. In Power BI, label the NULL bucket "unspecified" rather than
plotting it.

**But the 206 are not a simple `UPDATE`, and the original plan above was wrong.**
Checking for unique-index collisions before writing the migration showed:

| | rows |
|---|---|
| clean, collision-free backfills | **16** |
| would collide with a primary row already holding that (experiment, day) | **190** |

The 190 are **re-ingested duplicates**, not new timepoints. Their twin already
sits in the correct bucket; the NULL-bucket copy is an older ingest of the same
measurement, differing only in capitalisation (`SERUM_JW_054_day1_5x` vs
`SERUM_JW_054_Day1_5x`). Measured across all 190:

- 186/190 raw labels match case-insensitively, 186/190 dilution factors match
- **174/190 are value-identical** on Fe and Ni
- 16 differ on some element; only **3** differ materially on Fe (max gap 2.1 ppm)
- 178/190 the NULL-bucket row is the older of the pair

So the remedy for those 190 is **deduplication, not backfill** — demote or delete
the stale copy, as Fix 4 does for its six. **Escalated, not actioned**, because
two things need a human: whether to demote (reversible, keeps the row) or delete,
and which copy wins for the 16 rows whose values disagree. Only the 16
collision-free rows are a mechanical backfill, and they are not worth a migration
on their own.

Deduplicating the 198 NULL-bucket duplicate primary pairs overlaps heavily with
this and should be done in the same pass.

### Fix 4 — the 6 stale `-t3` rows — **SHIPPED, but not as proposed**

The proposal above was to re-bucket the six rows to day 3. **That would have
failed**, and the reasoning behind it was wrong.

Inspecting the vials before writing the migration showed **each of the six
already holds a correct day-3 row** (result_ids 1926–1931, described
"Master upload — day 3.") created after the 2026-07-30 fix, alongside the stale
day-6/7 row. Re-bucketing would have collided with the good row under
`uq_primary_result_per_experiment_bucket`.

It also made the question of "which day is true" moot. The six stale rows are
**empty shells**: every scalar measurement column is NULL
(`gross_ammonium_concentration_mM`, `final_ph`, `h2_concentration`,
conductivity, nitrate, alkalinity, DO, gas volume, yields, sampling volume) and
zero result files are attached. The real H₂ readings live on the day-3 rows. So
nothing is lost by removing them from reporting, and the user's "day 3" answer is
satisfied by the row that already exists.

Shipped as `database/data_migrations/demote_stale_t3_prefix_rows_017.py`, which
**demotes** (`is_primary_timepoint_result = FALSE`) rather than deleting —
every reporting view filters on that flag, so demotion clears the phantom bucket
while leaving the rows recoverable. Rows are selected by rule (empty + a correct
row already exists for the ID's day), not by hardcoded id, and the script is
dry-run by default. Applied to the restored dev copy:
`SERUM_pH_001` now reads 3 vials / 3 letters at every bucket.

**Not yet applied to production.**

### Fix 5 — document the Power BI trap

Add to `docs/POWERBI_MODEL.md`: 292 experiments currently have no results, and
any visual built on a result view silently omits them. Build experiment lists on
`v_experiments`. Also note the rollup covers scalar data only, so ICP-only
timepoints do not appear in it at all.

### Fix 6 — correct the false claim in `MODELS.md`

Remove/replace the statement that a data migration backfilled all pre-existing
NULL-bucket rows. 807 remain.

---

## Recommended order

1. **Fix 1** — view-only, zero risk, removes 335 phantom rows and fixes all 457
   bad counts immediately. Ship first and independently.
2. **Fix 6 + Fix 5** — documentation corrections, no risk.
3. **Fix 3 tier 1** (206 description-derived backfills) with verification.
4. **Fix 4** — after researcher confirmation.
5. **Fix 2** — last, once duplicates are gone.

## Open questions — answered 2026-08-01

1. ~601 unrecoverable NULL-bucket rows → **leave NULL** ("only if a day token is
   available").
2. The 6 `-t3` vials → **day 3**. Resolved without a data edit: the correct
   day-3 rows already existed; the stale rows were empty and are now demoted.
3. Rename `n_replicates`? → **"break it if necessary, no reports have been
   built."** Done. Note the column was *not* Power-BI-only — the React replicate
   group page reads it through the API, so the rename was carried through
   `backend/api/schemas/results.py`, `frontend/src/api/experiments.ts` and
   `GroupedResultsView.tsx` as well.

## Still needing a decision

1. **Fix 3's 190 duplicate rows** — demote (reversible) or delete? And for the 16
   whose values disagree between the two copies, which wins?
2. **Fix 2** — tightening `uq_primary_result_per_experiment_bucket` to
   `NULLS NOT DISTINCT` is a non-additive constraint change, so per
   `.claude/rules/schema-checklist.md` Phase 2 it needs explicit sign-off. It is
   also blocked on Fix 3 clearing the 198 duplicate pairs first.
3. **Applying to production** — the view change lands automatically on app
   restart, but migration 017 must be run against the lab PC deliberately.
