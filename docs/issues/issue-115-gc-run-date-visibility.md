# bug: Dashboard "GC Measurements" KPI card reads 0 while the lab is active

> **Status 2026-07-31 — SHIPPED on `fix/issue-115-gc-run-date-kpi`.**
> All three UI/parser fixes below are shipped. The `overwrite=True` field-wipe
> mechanism this issue's Q2/Q3 were originally written to test for was
> investigated, found **not** to be the cause, and handed off to its own
> ticket: `issue-master-results-overwrite-wipes-unlisted-fields.md`.

## Summary

The Dashboard's "GC Measurements" KPI card (issue #85) counts `scalar_results`
rows whose `gc_run_date` falls in the last 7 workdays. Mat reported the card
reading `0 · 2026-07-23 – 2026-07-31 · across 0 experiments` despite the lab
being clearly active — H2 readings were still coming in on Master Results
uploads. A `0` with no explanation reads as "the lab did nothing," which is
false, so the question was whether the KPI's query, join, or window logic was
wrong, or whether an upload path was silently wiping `gc_run_date` on
overwrite, or whether the column had simply stopped being filled in.

## Diagnosis

Run against the local dev DB (1,056 `scalar_results` rows; real lab data
through ~May 2026 — the `HPHT_901*` / `SERUM_DEMO_901*` rows dated July are
test fixtures from earlier #111/#114 work, not lab data):

| Finding | Number |
|---|---|
| `scalar_results` rows with `gc_run_date` | 115 of 1,056 — all in Mar–May 2026, none after |
| H2-bearing rows carrying a GC run date, by month | Mar 35/51 · Apr 59/61 · May 16/16 · then nothing |
| H2-bearing rows before Mar 2026 with a GC date | 0 of 61 (column added by migration `ddcef00413b9`; expected) |
| Audited `scalar_results` updates, Feb–May 2026 | 9,615 (6,510 in April alone) |
| Of those, any field recorded going non-null → NULL | `gross_ammonium_concentration_mM` ×3, and nothing else |

**Conclusion:** candidate (a) — overwrite re-uploads wiping `gc_run_date` — has
**zero instances** across ~10k audited updates, including the months when 59
of 61 H2 rows carried a date. Candidate (b) — the column simply stopped being
filled in — is what the data supports. The KPI query is correct and was
reporting a real void, not a bug in the count itself.

**Honest limit: this DB's real data ends in May 2026.** It cannot prove what
happened on the lab PC in June–July, which is exactly the window the reported
symptom falls in. The **Production confirmation** section below hands off the
corrected queries to run against the live database.

## What shipped

| # | What | Commit |
|---|---|---|
| 1 | Master Results upload emits one file-level warning naming sheet rows that carry an H2 reading with a blank `GC Run Date`. Silent when the row has no H2 reading. | `191cf5f` |
| 2 | The Results tab's expanded row renders NMR / ICP / GC / XRD run dates from data the API already returned (`ResultWithFlagsResponse`). A blank GC date shows `not recorded` in warning colour, plus an explanatory line, whenever the row has an H2 reading. | `478081b` |
| 2b | Decoupled that block from the scalar fetch's loading state, so the signal is never masked by a slow request. | `c107d2b` |
| 3 | The Dashboard GC card's subtitle now reads `no GC Run Date recorded in this window` when the count is zero (instead of `across 0 experiments`, which read as an idle lab), and a tooltip states what the card counts. | `b1e0f2b` |

Together these answer the issue's suggested next step, branch 3: if nobody has
been filling in `GC Run Date`, surface the field in the UI (item 2 above) plus
a process reminder that fires at the moment of the omission (item 1) rather
than a line in a doc nobody reads until it's too late.

## Acceptance criteria

- [x] Master Results upload warns, once per file, when an H2 reading arrives
      with no `GC Run Date`, naming the affected sheet rows; silent when the
      row has no H2 reading
- [x] The Results tab's expanded row shows the NMR / ICP / GC / XRD run dates
      the API already returns
- [x] A blank GC run date renders visibly (`not recorded`, warning colour)
      when the row has an H2 reading, with a line explaining why the row is
      not counted by the Dashboard card
- [x] The Dashboard GC Measurements card explains a `0` count as "no GC Run
      Date recorded," not "across 0 experiments"
- [x] Dev-DB diagnosis run and recorded (this document), including the
      overwrite-wipe negative evidence and the coverage-cliff timing
- [~] **Production data confirmation** — the queries below have not been run
      against the live lab-PC database from this environment. Marked `[~]`
      rather than left unchecked because this is a deliberate hand-off, not an
      oversight: this DB's real data ends in May 2026 and cannot answer what
      happened on the lab PC in June–July.
- [x] Existing bulk-upload, results-API, and dashboard test suites pass with
      no regression (see Verification below)

## Production confirmation

The issue's original Q2 and Q3 read `scalar_results.created_at` /
`scalar_results.updated_at`. **Neither column exists on `scalar_results`** —
both queries fail with `column does not exist` against the real schema. Q2 and
Q3 below replace them; Q1 and Q1b are unchanged from the issue.

```sql
-- Q1: Is gc_run_date populated anywhere, ever? (unchanged from the issue)
SELECT count(*) FILTER (WHERE gc_run_date IS NOT NULL) AS with_date,
       count(*) AS total_rows
FROM scalar_results;

-- Q1b: When did it stop? Coverage by month, restricted to rows that
-- actually have an H2 reading (i.e. GC was run).
SELECT date_trunc('month', measurement_date)::date AS month,
       count(*) AS h2_rows,
       count(gc_run_date) AS with_gc_date
FROM scalar_results
WHERE h2_concentration IS NOT NULL AND measurement_date IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- Q2 (REPLACES the issue's Q2, which read scalar_results.created_at /
-- updated_at -- neither column exists). The audit trail answers the wipe
-- question directly: every field an update changed is logged with its old and
-- new value, so a date going non-null -> NULL is visible here by name.
SELECT k AS field, count(*) AS times_wiped
FROM modifications_log m, jsonb_each(m.new_values) AS kv(k, v)
WHERE m.modified_table = 'scalar_results'
  AND m.modification_type = 'updated'
  AND jsonb_typeof(v) = 'null'
  AND m.old_values -> k IS NOT NULL
  AND jsonb_typeof(m.old_values -> k) <> 'null'
GROUP BY 1 ORDER BY 2 DESC;

-- Q3 (REPLACES the issue's Q3 -- same missing-column problem). Rows in the
-- KPI window that have an H2 reading but no GC run date: exactly what the
-- new upload warning now names at upload time.
SELECT e.experiment_id, sr.result_id, sr.measurement_date,
       sr.h2_concentration, sr.gc_run_date
FROM scalar_results sr
JOIN experimental_results er ON er.id = sr.result_id
JOIN experiments e ON e.id = er.experiment_fk
WHERE sr.gc_run_date IS NULL
  AND sr.h2_concentration IS NOT NULL
  AND sr.measurement_date >= '2026-07-23'
ORDER BY sr.measurement_date DESC;
```

**What Q2 settles:** a non-empty result — any `field` row for `scalar_results`
with `times_wiped > 0`, especially `gc_run_date` — means the overwrite-wipe
mechanism described in `issue-master-results-overwrite-wipes-unlisted-fields.md`
is live in production, and that hand-off issue should be reprioritised
immediately. An empty result confirms the data-entry reading: the lab simply
stopped filling in `GC Run Date`, and item 1's upload warning is what closes
the loop going forward.

## Verification

Run one at a time — never two pytest processes against the shared test DB at once.

```
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/ tests/api/test_dashboard.py tests/api/test_results.py -q
```
```
cd frontend && npx vitest run
```

Both green as of this branch (see Task 4 report for the exact counts). The
three pre-existing `pg_backup_restore` / full-suite `pytest -q` failures from
`drop_all()` wiping `experiments_test` are unrelated to this branch and also
present on `develop`.

## Notes

**Ruled out, left untouched:** the workday window logic, the KPI's query/join
shape, frontend wiring, and header drift were all sound going in and needed no
change — the count itself was correct the whole time. This ticket is entirely
about making the *input* to that count visible, not about the count.

**Also out of scope by user decision (2026-07-31):** redefining the KPI to
count H2 readings instead of GC run dates. The card keeps counting
`gc_run_date`; this branch makes a blank one visible at the point it goes
blank, so the number stays meaningful without changing what it means.

## Labels

`bug`, `dashboard`, `results`, `needs-validation` (production confirmation
still outstanding — see the `[~]` criterion above)
