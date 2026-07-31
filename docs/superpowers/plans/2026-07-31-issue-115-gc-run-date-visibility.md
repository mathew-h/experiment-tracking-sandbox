# Issue #115 — Make a missing GC Run Date Visible Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a blank `GC Run Date` visible at upload time and in the Results UI, and make the Dashboard's GC Measurements card say what it counts when it reads zero — so the KPI's input stops failing silently.

**Architecture:** Three independent, additive surfaces on an existing data path. The Master Results parser gains one file-level warning when a row carries an H2 reading but no GC run date. The Results tab renders the four instrument run dates that the API already returns (`ResultWithFlagsResponse` → `ResultWithFlags`) but that nothing displays. The Dashboard GC card gains an honest empty state and a tooltip naming its input. No schema change, no migration, no change to how any value is parsed or written.

**Tech Stack:** FastAPI + SQLAlchemy (backend), pandas/openpyxl (parser), React 18 + TypeScript + Tailwind + React Query (frontend), pytest (backend tests), vitest + @testing-library/react (frontend tests).

## Diagnosis this plan is built on

Run against the local dev DB (1,056 `scalar_results` rows; real lab data through ~May 2026 — the `HPHT_901*` / `SERUM_DEMO_901*` rows dated July are test fixtures from the #111/#114 work, not lab data):

| Finding | Number |
|---|---|
| `scalar_results` rows with `gc_run_date` | 115 of 1,056 — **all in Mar–May 2026, none after** |
| H2-bearing rows carrying a GC run date, by month | Mar 35/51 · Apr 59/61 · May 16/16 · then nothing |
| H2-bearing rows before Mar 2026 with a GC date | 0 of 61 (column added by `ddcef00413b9`; expected) |
| Audited `scalar_results` updates, Feb–May 2026 | 9,615 (6,510 in April alone) |
| Of those, any field recorded going non-null → NULL | **`gross_ammonium_concentration_mM` ×3, and nothing else** |

So the issue's candidate (a) — overwrite re-uploads wiping `gc_run_date` — has **zero instances** across ~10k audited updates, including the months when 59 of 61 H2 rows carried a date. Candidate (b) — the column simply stopped being filled in — is what the data supports. The KPI query is correct and is reporting a real void.

**Honest limit:** this DB's real data ends in May 2026, so it cannot prove what happened on the lab PC in June–July. Task 4 hands Mat the corrected queries to confirm against production.

**Two corrections to the issue text:** `scalar_results` has no `created_at` / `updated_at` columns, so the issue's Q2 and Q3 as written fail with `column does not exist`. The `modifications_log` JSONB query in Task 4 answers the wipe question far more directly than either.

**Deliberately out of scope** (user decision, 2026-07-31): the `overwrite=True` field-wipe mechanism is real in the code and worse than the issue frames it — an `Overwrite=TRUE` Master Results upload nulls the eight fields the sheet never carries (`background_ammonium_concentration_mM`, `ammonium_quant_method`, `final_nitrate_concentration_mM`, `final_alkalinity_mg_L`, `co2_partial_pressure_MPa`, `final_dissolved_oxygen_mg_L`, `background_experiment_id`, `ferrous_iron_yield`), and wiping background ammonium silently moves net ammonium. It is **not** what caused the 0/0, and it gets its own issue in Task 4 rather than riding along here.

**Also out of scope** (user decision): redefining the KPI to count H2 readings instead of GC run dates. The card keeps counting `gc_run_date`; this plan makes blanks visible so the number becomes trustworthy again.

## Global Constraints

- Branch: `fix/issue-115-gc-run-date-kpi` (already created off `develop`). PRs use `gh pr create --base develop` — never GitHub's default branch.
- Commit format, every commit: `[#115] <imperative description>`, under 50 chars, imperative mood, no trailing period, followed by a blank line and `- Tests added: yes/no` / `- Docs updated: yes/no`.
- **No new third-party packages.** Nothing in this plan needs one; if you think it does, stop and escalate.
- `backend/services/bulk_uploads/master_bulk_upload.py` is a **locked** bulk-upload parser (`.claude/CLAUDE.md` §5, `docs/LOCKED_COMPONENTS.md`). Task 1 is authorized by the user for **one additive change only**: collecting row numbers and appending one warning string. Do **not** touch `_resolve_h2`, `_parse_date`, `_normalize_headers`, `_HEADER_ALIASES`, the `result_data` dict, the `None`-stripping at line 547, or anything about how a value is parsed or written. If a step seems to require that, stop and escalate.
- Never start, stop, or restart uvicorn (port 8000) or the Vite dev server (port 5173/5174). Assume both are running; if unreachable, report it and move on.
- Frontend: Tailwind utility classes only, no inline styles, no hardcoded hex (tokens from `frontend/src/assets/brand.ts`), no `console.log`, ESLint zero warnings. `text-status-warning` is the existing token for warning-coloured text (9 uses in `frontend/src/`) — use it, do not invent a new one.
- Do **not** run two pytest processes at once — the test DB is shared and an interrupted session leaves a stale schema that `create_all` cannot repair.
- `frontend/package.json` and `package-lock.json` are not touched by this plan. If either changes, something has gone wrong.
- Docs written under `docs/` are copied to `docs/project_context/` automatically by the `PostToolUse` hook. Never write to `docs/project_context/` directly.

---

### Task 1: Master Results upload warns when an H2 reading arrives with no GC Run Date

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (locked — additive warning only; edits at ~501, ~569, ~603)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py` (add `gc_date` kwarg to `_v3_row` at line 760; two new tests at end of file)

**Interfaces:**
- Consumes: `MasterBulkUploadService.from_bytes_ex(db, xlsx) -> MasterUploadResult`; `MasterUploadResult.warnings: List[str]` (dataclass field, line 110); the local alias `warnings = out.warnings` (line 379); loop locals `h2_ppm` (line 520) and `gc_run_date` (line 516); `row_num` from the Phase-2 loop (line 502).
- Produces: one new file-level entry in `MasterUploadResult.warnings`, matching the shape the bulk-upload panel already renders. No new function, no signature change, no new field on `MasterUploadResult`.

**Design notes for the implementer:**

Mirror the `superseded_rows` pattern that issue #114 added directly above — collect row numbers during the loop, emit **one** file-level warning after it. Do not emit one warning per row.

Collect **after** `savepoint.commit()` succeeds, next to `superseded_rows.append(row_num)`. Rows that hit the duplicate-key `continue` (line 503) or raised inside the `try` were never written and must not warn about a missing date.

Do **not** add a per-row flag to the `feedbacks` dict. #114 established that per-row `feedbacks` entries are rendered nowhere, so a flag there would be invisible work.

The warning will fire on nearly every current upload, because the column has been blank since May — that is the point, not a defect. It stays one line per file, and it goes silent the moment the column is filled in again. Say so in the code comment so the next reader doesn't "fix" it by softening the condition.

- [ ] **Step 1: Add a `gc_date` kwarg to the `_v3_row` test helper**

In `tests/services/bulk_uploads/test_master_bulk_upload.py`, the helper at line 760 builds a row in `_V3_HEADERS` order, where index 14 is `"GC Run Date"` — the third `None` in the `None, None, None, None` line. Add the keyword and thread it to that position:

```python
def _v3_row(
    experiment_id: str,
    duration: float | None = 7.0,
    *,
    description: str = "Day 7",
    nh4: float | None = None,
    fl_h2: float | None = None,
    fl_vol: float | None = None,
    fl_psi: float | None = None,
    ph: float | None = 7.0,
    overwrite=None,
    di_h2: float | None = None,
    di_vol: float | None = None,
    di_psi: float | None = None,
    gc_date: str | None = None,
) -> list:
    """Build one Dashboard row in _V3_HEADERS order."""
    return [
        experiment_id, description, None, duration, nh4,
        fl_h2, fl_vol, fl_psi,
        ph, None, None, None,
        None, None, gc_date, None,
        overwrite,
        di_h2, di_vol, di_psi,
    ]
```

Every existing caller uses keywords only and defaults `gc_date=None`, so none of them change behaviour.

- [ ] **Step 2: Write the two failing tests**

Append to the end of `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
# ---------------------------------------------------------------------------
# Missing GC Run Date warning (issue #115)
# ---------------------------------------------------------------------------

def test_warns_when_h2_reading_has_no_gc_run_date(db_session: Session):
    """An H2 reading with a blank 'GC Run Date' is named in one file warning.

    The reading is stored and no error is raised, so nothing else tells the
    researcher that the Dashboard's GC Measurements card (issue #85) will not
    count this row. 115 of 1056 dev-DB scalar rows carry a GC run date and all
    fall in Mar-May 2026 while H2 readings kept arriving -- that silence is the
    bug reported in issue #115.
    """
    _seed_experiment(db_session, "HPHT_GCW01", 8901)
    _seed_experiment(db_session, "HPHT_GCW02", 8902)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_GCW01", 7.0, fl_h2=115.0),                          # H2, no date
        _v3_row("HPHT_GCW02", 7.0, fl_h2=120.0, gc_date="2026-07-29"),    # H2 + date
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 2

    missing = [w for w in result.warnings if "GC Run Date" in w]
    assert len(missing) == 1, (
        f"exactly one file-level warning, not one per row, got: {result.warnings}"
    )
    assert "1 row" in missing[0], missing[0]
    assert "(2)" in missing[0], (
        f"the warning must name the sheet row so it can be found, got: {missing[0]}"
    )
    assert "(3)" not in missing[0], (
        f"row 3 supplied a GC run date and must not be named, got: {missing[0]}"
    )


def test_no_gc_date_warning_when_row_has_no_h2_reading(db_session: Session):
    """A row with no H2 reading did no GC work, so a blank date is not notable.

    Same reasoning as the DI-supersede warning above: a warning that fires on
    ordinary sheets is one researchers learn to ignore.
    """
    _seed_experiment(db_session, "HPHT_GCW03", 8903)

    xlsx = _master_excel_v3([_v3_row("HPHT_GCW03", 7.0, nh4=5.0)])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 1
    assert [w for w in result.warnings if "GC Run Date" in w] == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k gc_date -v`

Expected: `test_warns_when_h2_reading_has_no_gc_run_date` FAILS on `assert len(missing) == 1` (got 0 warnings). `test_no_gc_date_warning_when_row_has_no_h2_reading` PASSES already — it is the guard that keeps Step 4 from over-firing, so a pass here is correct, not a problem.

- [ ] **Step 4: Collect the affected rows**

In `backend/services/bulk_uploads/master_bulk_upload.py`, immediately after the `superseded_rows` declaration (line 501):

```python
    superseded_rows: List[int] = []
    # Rows whose H2 reading landed with no GC Run Date (issue #115).
    missing_gc_date_rows: List[int] = []
```

Then inside the Phase-2 loop's `try`, immediately after the existing `if di_superseded:` block (line 569) and before `feedbacks.append({...})`:

```python
            if h2_ppm is not None and gc_run_date is None:
                missing_gc_date_rows.append(row_num)
```

Placement matters: this sits after `savepoint.commit()`, so a row that hit the duplicate-key `continue` or raised is never named.

- [ ] **Step 5: Emit the file-level warning**

In the same file, immediately after the `if superseded_rows:` block closes (after line 603) and before the `out.errors.extend(...)` line:

```python
    # A blank GC Run Date fails silently in every direction: the H2 reading is
    # stored, no error is raised, and nothing in the app renders the field -- so
    # the Dashboard's GC Measurements card (issue #85) just stops counting the
    # row. That is issue #115: 115 of 1056 dev-DB scalar rows carry a GC run
    # date and every one falls in Mar-May 2026, while H2 readings kept arriving
    # through July. Gated on an H2 reading being present, so a row that did no
    # GC work stays quiet. This WILL fire on most uploads until the column is
    # filled in again -- that is the intended signal, not noise to soften.
    if missing_gc_date_rows:
        shown = ", ".join(str(r) for r in missing_gc_date_rows[:10])
        if len(missing_gc_date_rows) > 10:
            shown += f", and {len(missing_gc_date_rows) - 10} more"
        label = "row" if len(missing_gc_date_rows) == 1 else "rows"
        warnings.append(
            f"'GC Run Date' is blank on {len(missing_gc_date_rows)} {label} "
            f"({shown}) carrying an H2 reading. The reading was stored, but the "
            "Dashboard's 'GC Measurements' card counts GC Run Date entries — "
            "these rows are not counted there until the date is filled in and "
            "the sheet re-uploaded."
        )
```

`warnings` is the local alias for `out.warnings` established at line 379 — do not introduce a second list.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -v`

Expected: both new tests PASS and the whole file's existing tests stay green. Pay attention to the two `#114` warning tests (`test_feedback_records_which_gc_block_was_used`, `test_no_supersede_warning_when_precedence_is_uncontested`) — the second asserts `[w for w in result.warnings if "direct injection" in w] == []` and so is unaffected by a new warning string, but the first counts only supersede warnings and must still see exactly one.

- [ ] **Step 7: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "[#115] Warn on H2 reading with blank GC Run Date

- One file-level warning naming affected sheet rows
- Silent when the row carries no H2 reading
- Tests added: yes
- Docs updated: no"
```

---

### Task 2: Results tab renders the four instrument run dates

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` (`ExpandedRow`, lines 24–94)
- Test: `frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx` (append to the existing `describe`)

**Interfaces:**
- Consumes: `ResultWithFlags` from `@/api/experiments` — already carries `nmr_run_date`, `icp_run_date`, `gc_run_date`, `xrd_run_date` (lines 123–126) and `h2_concentration`. Already populated by `GET /api/experiments/{id}/results` (`backend/api/routers/experiments.py:548-551`) into `ResultWithFlagsResponse` (`backend/api/schemas/results.py:144-147`). **All three backend layers are already shipped — this task is render-only. Do not add backend fields.**
- Consumes: the module-local `fmtDate` (line 13), which returns `'—'` for null and otherwise `iso.slice(0, 10)`.
- Produces: nothing consumed by a later task.

**Design notes for the implementer:**

This is `issue-results-api-missing-run-dates.md` §2, which never shipped. That doc asks for "a read-only display line per instrument, shown only when non-null" — follow it, with one deliberate exception: `GC` renders **even when null** if the row has an `h2_concentration`, because a missing GC date is precisely what a researcher needs to see. A field that only appears when populated cannot show you it is missing.

Put this in `ExpandedRow`, not the main grid row. The main row's badge cell is already `ICP / XRD / MOD` in a fixed `9rem` column of the `GRID` constant (line 22); adding two more badges would crowd it and force a grid-width change that touches every column. The expanded row is where per-timepoint detail already lives.

Render from `result`, not from the `scalar` query — `ResultWithFlags` already has the dates, so the block must not be gated on `scalar &&` (that block waits on a second fetch). Leave the existing XRD badge on the main row alone.

- [ ] **Step 1: Write the failing tests**

Append inside the existing `describe('ResultsTab — H2-first columns', ...)` block in `frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx`. Note the existing `baseResult` already sets all four run dates to `null`, so no fixture change is needed. Rows must be expanded by clicking, since `ExpandedRow` only mounts when the row is open.

```tsx
  it('shows the GC run date in the expanded row when it is set', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_scalar: true, h2_concentration: 512, gc_run_date: '2026-07-29T00:00:00Z' },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    const row = await screen.findByText('T+7')
    row.click()
    expect(await screen.findByText('Instrument Run Dates')).toBeInTheDocument()
    expect(await screen.findByText('2026-07-29')).toBeInTheDocument()
  })

  it('flags a missing GC run date when the row has an H2 reading', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_scalar: true, h2_concentration: 512, gc_run_date: null },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    const row = await screen.findByText('T+7')
    row.click()
    expect(await screen.findByText('not recorded')).toBeInTheDocument()
    expect(
      await screen.findByText(/not counted by the Dashboard's GC Measurements card/)
    ).toBeInTheDocument()
  })

  it('does not flag a missing GC run date when the row has no H2 reading', async () => {
    vi.mocked(experimentsApiModule.experimentsApi.getResults).mockResolvedValue([
      { ...baseResult, has_scalar: true, h2_concentration: null, gc_run_date: null },
    ])
    wrap(<ResultsTab experimentId="HPHT_001" experimentFk={10} />)
    const row = await screen.findByText('T+7')
    row.click()
    expect(screen.queryByText('not recorded')).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx`

Expected: the first two FAIL — `Unable to find an element with the text: Instrument Run Dates` / `not recorded`. The third PASSES already (nothing renders `not recorded` yet); it is the guard against over-firing in Step 3.

- [ ] **Step 3: Render the run-dates block**

In `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`, add this constant just below the `GRID` constant (line 22):

```tsx
/** Instrument run dates carried on ResultWithFlags — provenance, not measurements. */
const RUN_DATE_FIELDS = [
  ['NMR', 'nmr_run_date'],
  ['ICP', 'icp_run_date'],
  ['GC', 'gc_run_date'],
  ['XRD', 'xrd_run_date'],
] as const
```

Inside `ExpandedRow`, above the `return`, derive the two conditions:

```tsx
  // GC renders even when blank if an H2 reading exists: a field that appears
  // only when populated cannot show a researcher that it is missing, which is
  // the whole point here (issue #115).
  const gcMissing = result.gc_run_date == null && result.h2_concentration != null
  const anyRunDate = RUN_DATE_FIELDS.some(([, key]) => result[key] != null)
```

Then add this block inside the returned `<div>`, after the `{scalar && (...)}` block and before `{result.has_brine_modification && (...)}`:

```tsx
      {(anyRunDate || gcMissing) && (
        <div>
          <p className="text-xs font-semibold text-ink-secondary mb-1">Instrument Run Dates</p>
          <div className="grid grid-cols-4 gap-x-4 gap-y-1">
            {RUN_DATE_FIELDS.map(([label, key]) => {
              const missing = key === 'gc_run_date' && gcMissing
              if (result[key] == null && !missing) return null
              return (
                <div key={label} className="text-xs">
                  <span className="text-ink-muted">{label}: </span>
                  <span className={`font-mono-data ${missing ? 'text-status-warning' : 'text-ink-primary'}`}>
                    {missing ? 'not recorded' : fmtDate(result[key])}
                  </span>
                </div>
              )
            })}
          </div>
          {gcMissing && (
            <p className="text-xs text-ink-muted mt-1">
              An H₂ reading is stored for this timepoint but no GC run date, so it is
              not counted by the Dashboard's GC Measurements card.
            </p>
          )}
        </div>
      )}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx`

Expected: all tests in the file PASS, including the two pre-existing XRD-badge tests (the main-row badge is untouched).

- [ ] **Step 5: Lint**

Run: `cd frontend && npx eslint src/pages/ExperimentDetail/ResultsTab.tsx src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx`

Expected: zero errors, zero warnings. If `result[key]` trips a TS index-signature complaint, keep `RUN_DATE_FIELDS` as `as const` and type the tuple's second element as `keyof ResultWithFlags` — do not reach for `any` or a `Record<string, unknown>` cast.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/ResultsTab.tsx frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx
git commit -m "[#115] Render instrument run dates in results row

- Expanded row shows NMR/ICP/GC/XRD dates
- Blank GC date flagged when an H2 reading exists
- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Dashboard GC card explains a zero

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx:76-85` (the `GC Measurements` `MetricCard`)
- Test: `frontend/src/pages/__tests__/Dashboard.test.tsx` (append to the existing `describe('DashboardPage — KPI cards (issue #85)')`)

**Interfaces:**
- Consumes: `MetricCardProps` from `@/components/ui` — `{ label, value, unit?, sub?, className?, title?, children? }` (`frontend/src/components/ui/Card.tsx:54-62`). `sub` and `title` are both `string | undefined`; `title` becomes the `Card`'s HTML title attribute (hover tooltip).
- Consumes: `DashboardData['summary']` fields `gc_measurements_7wd`, `gc_experiments_7wd`, `workday_window_start`, `workday_window_end` — unchanged, no backend edit.
- Produces: nothing consumed by a later task.

**Design notes for the implementer:**

`0 · 2026-07-23 – 2026-07-31 · across 0 experiments` is what Mat reported, and it reads as "the lab did nothing" rather than "no GC run dates were recorded." Say the latter. Keep the number itself as `0` — do not substitute an em dash, which is the loading placeholder and would be a lie about a loaded response.

The existing tests wait on `/2026-07-21 – 2026-07-29/` appearing at least twice as the signal that `data` resolved (see the comment at `Dashboard.test.tsx:66-71`). Changing the GC card's `sub` **removes one of those two occurrences** when the count is zero — but `makeSummary()` defaults to `gc_measurements_7wd: 5`, so the existing tests keep their two matches (GC card and Serum card). Verify that in Step 3 rather than assuming it; if a pre-existing test goes red, the fix is in your new `sub`, not in loosening their assertion.

- [ ] **Step 1: Write the failing tests**

Append inside the existing `describe('DashboardPage — KPI cards (issue #85)', ...)` block in `frontend/src/pages/__tests__/Dashboard.test.tsx`:

```tsx
  it('explains a zero GC count instead of implying an idle lab (issue #115)', async () => {
    vi.mocked(dashboardApi.full).mockResolvedValue({
      summary: makeSummary({ gc_measurements_7wd: 0, gc_experiments_7wd: 0 }),
      reactors: [],
      timeline: [],
      recent_activity: [],
    })
    renderDashboard()
    expect(
      await screen.findByText(/no GC Run Date recorded in this window/)
    ).toBeInTheDocument()
    expect(screen.queryByText(/across 0 experiments/)).not.toBeInTheDocument()
  })

  it('keeps the experiment-count subtitle when the GC count is non-zero', async () => {
    vi.mocked(dashboardApi.full).mockResolvedValue({
      summary: makeSummary({ gc_measurements_7wd: 5, gc_experiments_7wd: 3 }),
      reactors: [],
      timeline: [],
      recent_activity: [],
    })
    renderDashboard()
    expect(await screen.findByText(/across 3 experiments/)).toBeInTheDocument()
    expect(screen.queryByText(/no GC Run Date recorded/)).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run the tests to verify the first fails**

Run: `cd frontend && npx vitest run src/pages/__tests__/Dashboard.test.tsx`

Expected: the first new test FAILS (`Unable to find an element with the text: /no GC Run Date recorded in this window/`). The second PASSES already — it pins the non-zero path so Step 3 cannot regress it.

- [ ] **Step 3: Give the card an empty state and a tooltip naming its input**

Replace the `GC Measurements` `MetricCard` at `frontend/src/pages/Dashboard.tsx:76-85` with:

```tsx
        <MetricCard
          label="GC Measurements"
          value={data?.summary.gc_measurements_7wd ?? '—'}
          sub={
            data
              ? data.summary.gc_measurements_7wd === 0
                ? `${data.summary.workday_window_start} – ${data.summary.workday_window_end} · no GC Run Date recorded in this window`
                : `${data.summary.workday_window_start} – ${data.summary.workday_window_end} · across ${data.summary.gc_experiments_7wd} experiment${data.summary.gc_experiments_7wd === 1 ? '' : 's'}`
              : undefined
          }
          title={
            data
              ? `Counts results whose GC Run Date falls in ${data.summary.workday_window_start} – ${data.summary.workday_window_end}. A row with an H₂ reading but a blank GC Run Date is not counted.`
              : undefined
          }
        />
```

- [ ] **Step 4: Run the full Dashboard suite**

Run: `cd frontend && npx vitest run src/pages/__tests__/Dashboard.test.tsx`

Expected: every test in the file PASSES, including `renders the four new KPI labels` — confirm its `getAllByText(/2026-07-21 – 2026-07-29/)` still finds ≥2 (GC card with count 5, plus Serum card). If it does not, your `sub` ternary dropped the date range from the non-zero branch.

- [ ] **Step 5: Lint**

Run: `cd frontend && npx eslint src/pages/Dashboard.tsx src/pages/__tests__/Dashboard.test.tsx`

Expected: zero errors, zero warnings.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/pages/__tests__/Dashboard.test.tsx
git commit -m "[#115] Explain a zero GC Measurements count

- Empty state names the missing input, not an idle lab
- Tooltip states what the card counts
- Tests added: yes
- Docs updated: no"
```

---

### Task 4: Documentation, findings, and hand-off of the two open threads

**Files:**
- Create: `docs/issues/issue-115-gc-run-date-visibility.md`
- Create: `docs/issues/issue-master-results-overwrite-wipes-unlisted-fields.md`
- Modify: `docs/issues/issue-results-api-missing-run-dates.md` (§2 → shipped; correct the `created_at`/`updated_at` assumption)
- Modify: `docs/user_guide/DASHBOARD.md` (GC Measurements card — what it counts and why it can read 0)
- Modify: `docs/upload_templates/` Master Results doc, if one exists (document the new warning) — check with `ls docs/upload_templates/` first; if there is no Master Results template doc, skip it and say so in the commit body rather than creating one.

**Interfaces:**
- Consumes: the diagnosis table at the top of this plan; the warning string from Task 1 Step 5; the UI behaviour from Tasks 2–3.
- Produces: nothing consumed by a later task. The hook copies every `docs/` write into `docs/project_context/` — do not add those copies to `git add` by hand; check `git status` and include whatever the hook produced.

**Design notes for the implementer:**

`docs/issues/issue-115-gc-run-date-visibility.md` records the diagnosis and what shipped. Use `[~]` — not `[x]` — for any acceptance criterion that cannot be verified from this environment (the production-data confirmation), per the `docs/issues/` convention set by the dry-run doc.

The second doc is the overwrite-wipe hand-off. It must carry: the mechanism (`master_bulk_upload.py:547` strips `None`s → `scalar_results_service.py:129-131` iterates the full field list), the **eight** fields the Master Results sheet never carries and therefore nulls on `Overwrite=TRUE`, the fact that `background_ammonium_concentration_mM` feeds net ammonium, and the negative evidence (0 wipes in 9,615 audited updates — the mechanism is real in code but unobserved in data, so this is latent, not active). State plainly that it was scoped out of #115 by decision on 2026-07-31 because it is not the cause of the 0/0.

- [ ] **Step 1: Write `docs/issues/issue-115-gc-run-date-visibility.md`**

Include, in this order: summary of the reported symptom; the diagnosis table from this plan verbatim, with its "real data ends in May 2026" caveat; the three things that shipped (upload warning, run-date rendering, card empty state); the acceptance criteria with `[x]` / `[~]`; and a **Production confirmation** section holding these corrected queries — the issue's originals reference `scalar_results.created_at` / `updated_at`, which do not exist:

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

Add one line stating what Q2 settles: a non-empty `gc_run_date` row means the overwrite-wipe is live in production and the hand-off issue below should be prioritised; an empty result confirms the data-entry reading.

- [ ] **Step 2: Write `docs/issues/issue-master-results-overwrite-wipes-unlisted-fields.md`**

Per the design notes above. Cross-reference `issue-results-api-missing-run-dates.md` §3 (which first flagged it and asked for reproduction before fixing) and record that the reproduction test it asked for has still not been written — that is the first task for whoever picks this up.

- [ ] **Step 3: Update `docs/issues/issue-results-api-missing-run-dates.md`**

Mark §1 and §2 as shipped (§1 by the earlier schema work, §2 by Task 2 of this plan, naming the branch). In §3, add a line that the mechanism was scoped out of #115 and moved to its own doc, with the 0-of-9,615 negative evidence. Leave the "Open question for the team" section alone — `measurement_date`'s meaning is still unsettled and is not this branch's business.

- [ ] **Step 4: Update `docs/user_guide/DASHBOARD.md`**

Find the GC Measurements card section and state: it counts results whose **GC Run Date** falls in the window; a row with an H₂ reading but a blank GC Run Date is not counted; a `0` therefore means "no GC run dates recorded," not "no GC work"; the Master Results upload now warns when a reading arrives without a date, and the Results tab shows the date per timepoint. Match the file's existing register — it is written for researchers, not developers.

- [ ] **Step 5: Verify the docs hook synced, then commit**

Run: `git status --short`

Expected: your `docs/` edits **plus** hook-generated copies under `docs/project_context/`. Stage both.

```bash
git add docs/issues/ docs/user_guide/DASHBOARD.md docs/project_context/
git commit -m "[#115] Document GC run date diagnosis and fixes

- Records the Mar-May 2026 coverage cliff and the 0-of-9615 wipe evidence
- Corrected production queries (scalar_results has no created_at/updated_at)
- Overwrite field-wipe handed off to its own issue
- Tests added: no
- Docs updated: yes"
```

- [ ] **Step 6: Full-suite verification before any PR**

Run, one at a time — never two pytest processes at once:

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/ tests/api/test_dashboard.py tests/api/test_results.py -q
```
```bash
cd frontend && npx vitest run
```

Expected: green. `pg_backup_restore` and full-suite `pytest -q` have three pre-existing failures unrelated to this work (`drop_all()` wiping `experiments_test`) — if you run the whole suite and see them, confirm they also fail on `develop` before treating them as yours.

- [ ] **Step 7: Ask before anything leaves the repo**

Filing the overwrite-wipe issue on GitHub and posting the diagnosis as a comment on #115 are outward-facing actions. **Stop and ask Mat before running `gh issue create` or `gh issue comment`** — the docs are committed either way, and the GitHub copy is his call, not the implementer's.

---

## Self-Review

**Spec coverage** — the issue's "Suggested next step" has three branches. (1) Run Q1–Q3: done against the dev DB, in the diagnosis section, with corrected SQL for production in Task 4 Step 1. (2) If overwrite-wiping is confirmed → prioritise the §3 fix: not confirmed (0 of 9,615), handed off in Task 4 Step 2 with the evidence. (3) If nobody has been filling in GC Run Date → surface `gc_run_date` in the Results UI (Task 2) plus a process reminder (Task 1's upload warning, which is a better reminder than a doc line because it fires at the moment of the omission). The issue's ruled-out items (workday window, query/join, frontend wiring, header drift) are left untouched, as they should be. The `needs-validation` label's demand is answered as far as this environment allows, with the limit stated rather than papered over.

**Placeholder scan** — no TBDs. Every code step carries the actual code; every test step carries the actual assertions; every run step carries the actual command and its expected output. The one conditional instruction (Task 4's `docs/upload_templates/` check) states explicitly what to do in both branches.

**Type consistency** — `RUN_DATE_FIELDS` / `gcMissing` / `anyRunDate` are named identically in Task 2's Steps 1, 3 and 4. `missing_gc_date_rows` is named identically in Task 1's Steps 4 and 5. `_v3_row(..., gc_date=...)` in Task 1 Step 1 matches its use in Step 2. `MetricCard`'s `sub` and `title` props match `MetricCardProps` at `Card.tsx:54-62`. `fmtDate` is the existing module-local helper, not a new one.

**One risk worth restating:** Task 1's warning will fire on almost every upload until the team resumes filling in the column. That is deliberate and documented in the code comment, but if Mat would rather it stayed quiet until the backlog clears, that is a one-line change to the gate — ask rather than guess.
