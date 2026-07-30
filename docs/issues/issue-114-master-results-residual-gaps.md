# Master Results residual gaps from issue #111's fix wave

> **Status 2026-07-30 — SHIPPED on `chore/issue-114-master-results-residual-gaps`.**
> Items 1, 3, 4 and both addendum consequences shipped. **Item 2 (rename the FL/DI
> column headers to drop the ambiguous `h2` token, e.g. `FL Hydrogen (ppm)`) was
> deliberately not implemented** — deferred to **#113** by user decision
> (2026-07-30), because it and #113's own rename work both need one shared
> false-positive design for the "unmatched H2-like column" warning, and #113 is
> still open and unstarted.

**Type:** chore
**Area:** `backend/services/bulk_uploads/`
**Priority:** medium

---

## Problem

Issue #111 landed the GC source-precedence logic (Full Loop wins over direct
injection) and the one-row-per-vial Master Results format, but its own fix wave
left four residual gaps plus two consequences raised in a later review of that
work:

1. **Silent DI discard.** When a row carries an H2 reading in both GC blocks,
   Full Loop wins and the direct-injection value is dropped with no signal to
   the researcher that a reading was thrown away.
2. **Ambiguous rename risk.** Renaming the `FL`/`DI` H2 columns on the Dashboard
   sheet (e.g. to something without the `h2` token) would silently stop being
   recognized, with no warning that a column went unmatched.
3. **Error ordering.** Row-level upload errors were collected in two phases
   (identity resolution, then upsert) and concatenated in that order, so a
   later-phase error for an early row could print above an earlier-phase error
   for a later row — the list did not read top-down against the spreadsheet.
4. **Dead entry points.** `MasterBulkUploadService.sync_from_path`,
   `MasterBulkUploadService.from_bytes`, `MasterUploadResult.as_tuple`, and
   `settings.master_results_path` (plus its `_default_master_results_path()`
   helper) were left in the codebase after `from_bytes_ex` became the only
   real entry point, following the "Sync from SharePoint" button removal in
   issue #74.

**Addendum** (raised reviewing the above): two further consequences of the
same GC-block logic needed addressing:
- **Consequence 1:** the same-block pairing guard (Full Loop volume/pressure
  must pair with a Full Loop concentration, never a DI one) needed to be
  pinned against the actual measured magnitudes in use, not just arbitrary
  test values — a Full Loop carryover volume (4235 mL) is over 100x a real
  direct-injection sampling volume (30 mL), so mixing blocks would overstate
  gas quantities by roughly that factor.
- **Consequence 2:** a row with no `H2 (ppm)` reading in either GC block was
  still storing `gas_sampling_volume_ml` / `gas_sampling_pressure_MPa` from
  whichever carryover value the sheet happened to display, indistinguishable
  from a real measurement once persisted.

## Fix

Shipped on this branch, in order:

| Item | What | Commit |
|---|---|---|
| 3 | Row errors sorted by sheet row number; file-level errors (no row number) stay first | `82559c4` |
| 1 | One file-level warning naming rows where Full Loop superseded direct injection (up to 10, then "and N more"); renders in the existing bulk-upload warnings list, no frontend change | `c6e4238` |
| addendum C1 | Same-block geometry-pairing guard test strengthened to measured magnitudes (Full Loop carryover 4235 mL vs. DI 30 mL, a 141x overstatement if mixed) | `b9e9016` |
| addendum C2 | A row with no `H2 (ppm)` in either GC block now stores no gas volume or pressure either | `19d2a4e` |
| 4 | Deleted `sync_from_path`, `from_bytes`, `as_tuple`, `settings.master_results_path` and its default-path helper; `from_bytes_ex` is the only entry point | `3fe1dac`, `f70418f` |

**Item 2 is not in this list** — it is deferred to #113, not shipped here.

### Why item 1 is a warning, not a schema column

The discarded DI reading is present in the upload's response (`h2_source`,
`h2_di_superseded` per row in `feedbacks`) but was never persisted anywhere.
Persisting it would mean an additive `ScalarResults` column and a
schema-checklist run. That was measured, not assumed: on the current v3
Dashboard sheet, **0 of 499 rows** carry a reading in both GC blocks, so
precedence is never actually contested today. Building storage for a
discarded value that has not occurred once in the live data was judged
zero-impact, not merely lower-priority — a warning that names the rows if it
ever does happen is the proportionate fix.

### Why `settings.master_results_path` is safe to delete

`backend/config/settings.py` uses `SettingsConfigDict(extra="ignore")`, so a
leftover `MASTER_RESULTS_PATH=` line in the lab PC's `.env` file (from the
issue #74 SharePoint-sync era) is silently ignored on load rather than raising
at startup. Neither `.env.example` nor `docs/ENVIRONMENT.md` ever documented
this variable, so removing the field required no edit to either.

## Acceptance criteria

- [x] Row-level upload errors are returned sorted by sheet row number; file-level errors (missing columns, deprecated wide DI columns) stay first with no row number
- [x] A Master Results row with both GC blocks populated produces one warning naming the affected rows, rendered in the existing bulk-upload panel warnings list, with zero frontend code changed
- [x] The same-block geometry-pairing guard is tested against real measured magnitudes (4235 mL Full Loop carryover vs. 30 mL DI), not arbitrary values
- [x] A row with no `H2 (ppm)` in either GC block stores neither `gas_sampling_volume_ml` nor `gas_sampling_pressure_MPa`
- [x] `MasterBulkUploadService.sync_from_path`, `.from_bytes`, `MasterUploadResult.as_tuple`, and `settings.master_results_path` (with its default-path helper) are deleted; `from_bytes_ex` is the only entry point
- [~] Item 2 (rename FL/DI column headers to drop the `h2` token) — **not implemented, deferred to #113** by user decision: both this warning and #113's rename work need one shared false-positive design, and #113 is unstarted. Marked `[~]` rather than left unchecked because it is a deliberate, recorded deferral, not an oversight.
- [x] Existing bulk-upload test suite passes with no regression: `tests/services/bulk_uploads/`, `tests/integration/test_master_results_sync_endpoint.py`, `tests/api/test_bulk_uploads.py` all green (355 passed)
- [x] No new frontend consumer of `feedbacks` was added (item 1 shipped with zero frontend change, confirmed by grep)
- [x] This branch changes no schema (`database/models/`, `alembic/`, `database/event_listeners.py` diff against `develop` is empty)

## Notes

**Addendum consequence 1 needed no new test.** The guard it strengthens —
`test_di_wins_ignores_stray_full_loop_gas_geometry` — already existed from
issue #111's original fix wave. This branch retuned its fixture values to the
measured magnitudes (4235 mL vs. 30 mL) rather than adding new coverage. Do
not read this as "a test was added" in any summary of this branch; one was
strengthened.

**Power BI / reporting consumers — corrected note.** An earlier draft of this
paragraph claimed `v_primary_experiment_results` exposes these two columns and
that a re-upload would blank them for Power BI. Both parts were wrong.
`v_primary_experiment_results` does not exist in the current schema —
`database/event_listeners.py:661` unconditionally drops it on every startup
and it is absent from the view-creation list; this staleness is tracked
separately in `docs/working/issues/05-models-md-stale-v-primary-experiment-results.md`.
The two columns are actually exposed by `v_results_h2`
(`database/event_listeners.py:569-590`) — but that view's own
`WHERE sr.h2_concentration IS NOT NULL` filter excludes exactly the rows
consequence 2 affects (no H2 reading in either GC block), so it never
surfaces a stale-vs-cleared distinction for them either way. And even for a
report querying `scalar_results` directly, the claim only holds when the
re-uploaded row has `Overwrite=TRUE`: `backend/services/scalar_results_service.py:120-135`
nulls unpresent fields only on that path, while an ordinary re-upload
(`Overwrite` blank, the default) leaves previously-stored stale geometry
untouched — `master_bulk_upload.py:543` strips the now-`None`
`gas_sampling_volume_ml`/`gas_sampling_pressure_MPa` keys out of `result_data`
before the service call, so the non-overwrite path never even sees them to
clear. Net effect: this fix stops *new* stale geometry from being written; it
does not retroactively clear geometry already stored, unless that row is
explicitly re-uploaded with Overwrite checked.

**Test-count reconciliation.** The implementation plan estimated the
pre-#114 `tests/services/bulk_uploads/` count at 244 passed, expecting
244 + 4 new − 2 deleted = 246. The actual post-branch count is **266**.
Reconciled: only `test_master_bulk_upload.py` changed in that directory (all
other files are untouched between `develop` and this branch); collecting that
one file at the `develop` revision gives 54 tests, and at this branch's
revision gives 56 (the same 4-added/2-deleted delta the plan expected, net
+2). The remaining, unchanged files in the directory total 210, for a true
`develop` baseline of 264 — not 244. 264 + 2 = 266, which matches. The plan's
"244" baseline was simply stale; the net change introduced by this branch is
correctly +2 test functions in one file.

Only `b9e9016` (addendum consequence 1) is test-only with no user-visible
behavior change; the other four commits each ship an observable change
described above.
