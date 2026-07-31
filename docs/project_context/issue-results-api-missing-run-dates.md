# bug: NMR, ICP, and GC run dates are write-only — populated by bulk upload, readable only in Postgres

> **Status 2026-07-31.** §1 (expose the fields in the API schemas) shipped
> with the earlier #85/schema work. §2 (surface them in the UI) shipped on
> `fix/issue-115-gc-run-date-kpi` — the Results tab's expanded row now renders
> all four run dates, with a deliberate exception for a blank GC date (renders
> even when null, when the row has an H2 reading). §3 (the overwrite-wipe
> adjacent bug) was investigated as part of issue #115, found **not** to be
> the cause of that issue's symptom, scoped out, and moved to its own doc:
> `issue-master-results-overwrite-wipes-unlisted-fields.md`. See that ticket
> for the mechanism, the eight affected fields, and the negative evidence
> (0 wipes across 9,615 audited `scalar_results` updates). The "Open question
> for the team" section below is untouched — `measurement_date`'s meaning is
> still unsettled and was not this branch's business.

> **Verified against** `OneDrive - Addis Energy/Documents/01_Software/database_sandbox/experiment_tracking_sandbox`, branch `feat/issue-85-dashboard-kpi-cards` @ `49e5f8f`. `backend/api/schemas/results.py` is identical on `develop` and on the #85 branch — the three run dates are absent from both.

Smallest and lowest risk of the current reactor/results cluster. No migration, no data change, no cross-cutting refactor. Can ship independently of everything else.

## Summary

`scalar_results` carries five date columns. All five are written by the bulk uploader and by `scalar_results_service.py`. Only two are readable through the REST API.

| Column | Written by bulk upload | Written by service | Exposed in `results.py` schemas |
|---|---|---|---|
| `measurement_date` | yes | yes | yes (3 schemas) |
| `nmr_run_date` | yes | yes | **no** |
| `icp_run_date` | yes | yes | **no** |
| `gc_run_date` | yes | yes | **no** |
| `xrd_run_date` | yes | yes | yes (1 schema) |

So NMR, ICP, and GC run dates enter via bulk upload, land in Postgres, are visible to Power BI through the flattened views, and are invisible in the UI that created them. Nobody can confirm inside the app that a GC run date was recorded correctly without opening a database client.

**Fix all four missing exposures together rather than just one.** The asymmetry is the actual defect — `xrd_run_date` was clearly added to `ResultWithFlagsResponse` for some specific need and the other three were never backfilled, which is how you end up with one instrument's provenance visible and three instruments' invisible for no principled reason.

---

## Evidence

**Model** — `database/models/results.py:84-88`:

```python
    measurement_date = Column(DateTime(timezone=True), nullable=True)
    nmr_run_date = Column(DateTime(timezone=True), nullable=True)
    icp_run_date = Column(DateTime(timezone=True), nullable=True)
    gc_run_date = Column(DateTime(timezone=True), nullable=True)
    xrd_run_date = Column(DateTime(timezone=True), nullable=True)
```

**All five are on the write path** — `backend/services/scalar_results_service.py:14-21`:

```python
SCALAR_UPDATABLE_FIELDS = [
    ...
    'final_conductivity_mS_cm', 'final_alkalinity_mg_L', 'sampling_volume_mL', 'measurement_date',
    'nmr_run_date', 'icp_run_date', 'gc_run_date', 'xrd_run_date',
]
```

Set explicitly on create (lines 168-172) and via the update loops (lines 129-135). Parsed from the sheet by `_parse_date` in `backend/services/bulk_uploads/master_bulk_upload.py:50-65`, read from columns `Sample Date`, `NMR Run Date`, `ICP Run Date`, `GC Run Date`, `XRD Run Date` at lines 196-200, mapped into `result_data` at 216-220.

**Only two are on the read path** — `backend/api/schemas/results.py`:

- `ScalarCreate` (class at line 38) — `measurement_date` at line 50, nothing else
- `ScalarUpdate` (class at line 59) — `measurement_date` at line 68, nothing else
- `ScalarResponse` (class at line 71) — `measurement_date` at line 87, nothing else
- `ResultWithFlagsResponse` (class at line 105) — `scalar_measurement_date` at line 128, `xrd_run_date` at line 131

The only place `xrd_run_date` reaches a client is `ResultWithFlagsResponse`, populated in the `GET /api/experiments/{id}/results` handler at `backend/api/routers/experiments.py:287,290` (response model declared at line 243).

`nmr_run_date`, `icp_run_date`, and `gc_run_date` appear nowhere in the file.

---

## Proposed Changes

### 1. Expose the three missing fields — **shipped**

Add `nmr_run_date`, `icp_run_date`, `gc_run_date` to `ScalarResponse` alongside `measurement_date`, and add `xrd_run_date` there too — it's currently only in `ResultWithFlagsResponse`, which is an odd place for it to live alone.

Add all four to `ResultWithFlagsResponse` (which already has `xrd_run_date`). Note the naming inconsistency there: `measurement_date` is exposed as `scalar_measurement_date` while `xrd_run_date` keeps its column name. **Match the existing `xrd_run_date` convention** for the three new ones (`nmr_run_date`, not `scalar_nmr_run_date`) — the `scalar_` prefix on `measurement_date` looks like disambiguation against `Experiment.date`, which doesn't apply to instrument run dates. Don't rename `scalar_measurement_date`; it's presumably referenced in the frontend.

Add all four to `ScalarUpdate` so a run date can be corrected through the UI without a re-upload. This is the piece that closes the loop — right now a wrong GC run date can only be fixed by re-uploading the sheet or editing Postgres. Worth checking with the team whether they want this editable at all, but the current state (write-once via spreadsheet, uncorrectable) seems clearly wrong.

`ScalarCreate` is a judgment call. The four run dates are provenance metadata that in practice arrive with bulk instrument data, not with a hand-created scalar row. Recommend adding them for symmetry with `ScalarUpdate`, but it's low-stakes either way.

### 2. Surface them in the UI — **shipped, `fix/issue-115-gc-run-date-kpi`**

Wherever `xrd_run_date` currently renders (grep `frontend/src/` — it comes through `ResultWithFlagsResponse`), the other three should render the same way. The purpose is verification: a user who uploaded a GC sheet should be able to see that the run date landed. A read-only display line per instrument, shown only when non-null, is sufficient — this does not need to be a prominent UI element.

**Shipped with one deliberate exception to "shown only when non-null":** `ResultsTab.tsx`'s `ExpandedRow` renders GC even when it *is* null, when the row carries an `h2_concentration` reading — a field that only appears when populated cannot show a researcher that it is missing, which is the point of issue #115. NMR/ICP/XRD keep the original "only when non-null" behavior. Commits `478081b` + `c107d2b` (the latter decouples the block from the scalar fetch's loading state so the signal is never masked by a slow request).

### 3. Adjacent bug worth fixing in the same PR: blank run-date cells wipe existing values on overwrite — **scoped out of #115, moved to its own doc**

**2026-07-31: investigated as part of issue #115's GC-KPI-reads-0 diagnosis. Not the cause.** 0 of 9,615 audited `scalar_results` updates (Feb–May 2026) show any of the eight affected fields going non-null → NULL — see `issue-master-results-overwrite-wipes-unlisted-fields.md` for the full mechanism, the field list, and the negative evidence. The reproduction test asked for immediately below has still not been written; that doc names it as the first task for whoever picks this up next.

Not part of the original scope, but it's in the same code path and directly undermines the point of exposing these fields.

`master_bulk_upload.py:232` strips `None` values from `result_data`:

```python
result_data = {k: v for k, v in result_data.items() if v is not None or k == "_overwrite"}
```

But the `overwrite=True` branch in `scalar_results_service.py:129-131` iterates the *field list*, not the supplied dict:

```python
            if overwrite:
                for field in SCALAR_UPDATABLE_FIELDS:
                    setattr(scalar_data, field, result_data.get(field))
```

So for an omitted or blank run-date column, `result_data.get(field)` returns `None` and the existing value is silently cleared. An overwrite upload that only intends to correct an ammonium concentration will null out every previously-recorded run date on that row.

The non-overwrite branch (lines 132-135) is correct — it guards on `if field in result_data`.

**Verify this reproduces before fixing it** — the interaction between the `None`-stripping at line 232 and the field-list iteration is subtle and I have not run it. Write the failing test first: create a scalar row with `gc_run_date` set, then run an overwrite upload whose sheet has a blank `GC Run Date` cell, and assert the value survives (or doesn't). If it reproduces, the fix is to make the overwrite branch distinguish "explicitly blank, clear it" from "column absent, leave it" — which probably means not stripping `None`s at line 232 and instead using a sentinel, since `overwrite=True` legitimately needs to be able to clear a field.

Note: `issue-new-experiments-overwrite-field-updates-lost.md` is a *different* bug despite the similar name — that one is `db.expire_all()` discarding unflushed ORM changes in the New Experiments uploader, fixed with a `db.flush()`. It shares only the word "overwrite" and its fix does not transfer here. Don't assume the approach carries over.

---

## Open question for the team — not a code change

**What does `measurement_date` mean, now that four instrument-specific run dates exist alongside it?**

It's populated from the `Sample Date` column (`master_bulk_upload.py:216`), which suggests it means "when the sample was drawn," while the four run dates mean "when each instrument analyzed it." If that's the intent, the field is misnamed and the `scalar_measurement_date` alias in `ResultWithFlagsResponse` makes it more confusing, not less.

This matters because the *next* person to build logic on dates here will have to guess. Worth settling before anyone does — five minutes in a standup, not a ticket. Possible outcomes:

- It means sample-draw date → rename to `sample_date` (a migration, separate ticket) or at minimum document it in the model.
- It means "primary analysis date" → then it's redundant with the run dates and should probably be derived.
- It's a legacy field that predates the run dates and no longer means anything specific → say so in a comment so nobody builds on it.

Do not block this ticket on the answer. Exposing the four fields is correct regardless.

---

## Verification

- `GET /api/experiments/{id}/results` returns all four run dates for a row that has them in the database. Compare the response against `SELECT nmr_run_date, icp_run_date, gc_run_date, xrd_run_date FROM scalar_results WHERE result_id = ...`.
- Round-trip: bulk-upload a master sheet with all five date columns populated → all five visible in the API response → all five visible in the UI.
- `PATCH` a single run date via `ScalarUpdate` → persisted, other four unchanged.
- Regression for §3: overwrite upload with a blank run-date cell → previously-recorded value behaves as decided (and the audit trail in `ScalarUpsertResult.fields_updated` / `fields_preserved` reports it honestly, since that's what the change-tracking block at `scalar_results_service.py:137-147` is for).
- Existing results API tests stay green. Adding optional fields to a response model shouldn't break anything, but check any frontend test that asserts on an exact response shape.

---

## Data Model Notes

No schema change. No migration. Pydantic schemas and frontend display only — plus a possible service-layer fix for §3.

| Schema | Change |
|---|---|
| `ScalarResponse` | + `nmr_run_date`, `icp_run_date`, `gc_run_date`, `xrd_run_date` |
| `ResultWithFlagsResponse` | + `nmr_run_date`, `icp_run_date`, `gc_run_date` (already has `xrd_run_date`) |
| `ScalarUpdate` | + all four run dates |
| `ScalarCreate` | + all four run dates (optional; see §1) |

## Labels

`bug`, `api`, `results`, `good-first-issue`

## Notes

Independent of the reactor tickets — no shared files, no shared schema. Take it whenever there's a gap.

**Direct conflict with #85, which is already implemented.** This is no longer hypothetical. On `feat/issue-85-dashboard-kpi-cards`, `dashboard.py:193-201` ships the GC KPI:

```python
    gc_row = db.execute(
        select(
            func.count(ScalarResults.id).label("measurements"),
            func.count(distinct(ExperimentalResults.experiment_fk)).label("experiments"),
        )
        .join(ExperimentalResults, ExperimentalResults.id == ScalarResults.result_id)
        .where(ScalarResults.gc_run_date >= wd_start)
        .where(ScalarResults.gc_run_date < wd_end)
    ).one()
```

surfaced as `gc_measurements_7wd` and `gc_experiments_7wd` on `DashboardSummary` (`schemas/dashboard.py:47-48`). Meanwhile `gc_run_date` is still absent from every schema in `backend/api/schemas/results.py`, on both branches.

So as of `49e5f8f` the dashboard shows a user two numbers derived entirely from a field that the application will not show them anywhere else. If the count looks wrong, there is no in-app way to find out which rows it counted or whether a run date was recorded correctly. `issue-dashboard-kpi-overhaul.md` lists exposing `gc_run_date` as explicitly out of scope; that decision is now shipped behavior.

**Recommendation: fold this ticket into the #85 branch before it merges.** It is four Pydantic fields and a display line, it makes the KPI verifiable on arrival, and it avoids shipping then immediately amending a user-facing card. Whoever does it should also delete the contradicting out-of-scope line from the KPI doc rather than leaving both documents standing.

Flagging rather than deciding unilaterally, since the KPI doc presumably had a reason for the exclusion — but the reason is not recorded, and the cost of including it is very low.
