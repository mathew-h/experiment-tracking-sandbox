# Data Export Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Data Export page where a researcher filters experiments, ticks any number of them, and downloads one Excel workbook (the #141 layout) covering all of them.

**Architecture:** `backend/services/experiment_export.py` (#141) is refactored so its tab builders take an ordered list of `Member`s instead of one `Lineage`; the single-lineage export keeps its exact output. A new `resolve_selection` turns picked IDs into members (always expanding a `-t` stem to its vials, optionally expanding to whole series), and `POST /api/experiments/export` streams the workbook. The page reuses `GET /api/experiments` (flat mode, `limit=500`), which gains an `additive` filter.

**Tech Stack:** FastAPI, SQLAlchemy 2, openpyxl, pytest (`experiments_test` DB); React 18, TanStack Query v5, Tailwind, vitest + Testing Library.

**Spec:** GitHub issue #142 body (rewritten 2026-11-06 with Mat's decisions): `gh issue view 142`. Prior art: #141 entry in `docs/working/issue-log.md`, `docs/api/API_REFERENCE.md` "GET /api/experiments/{experiment_id}/export".

## Global Constraints

- Output is an Excel workbook, never CSV. Same column specs, headers (units in names) and lab-local Excel dates as #141 — reuse `RESULT_COLUMNS`, `CORE_FLOOD_COLUMNS`, `CONDITION_COLUMNS`, `ADDITIVE_COLUMNS`, `NOTE_COLUMNS`, `_write_tab`, `_cell`.
- Values come only from the reporting views (`v_results_scalar`, `v_results_h2`, `v_results_icp`, `v_dim_timepoints`, `v_core_flood_samples`, `v_experiment_conditions`, `v_chemical_additives`, `v_notes`, `v_experiments`). No new formulas, no schema change, no new package.
- The #141 single export (`GET /api/experiments/{id}/export`, `build_workbook`) must produce the same sheets, rows and cells as before. All 15 existing tests in `tests/api/test_experiment_export.py` keep passing unmodified.
- `EXPORT_MAX_EXPERIMENTS = 500`, counted after expansion. Over it → 422.
- Filename `data_export_<YYYY-MM-DD>.xlsx`, lab-local date via `experiment_export.lab_now()` (tests monkeypatch it).
- "Include whole series" defaults to **on** in the UI and in the request schema.
- Sidebar: "Data Export" goes immediately after "Chemicals"; Core Floods and Notes review stay the last two (pinned by `AppLayout.nav.test.tsx`).
- Brand tokens only, no hex in components; React Query for server state; no `console.log`.
- Never run two pytest processes at once (shared `experiments_test`).
- Commit format `[#142] <imperative, < 50 chars>` with `- Tests added:` / `- Docs updated:` lines; commit with `git commit -F <scratchpad file>`.

## Review Focus

1. **Overlapping picks** (`CFE_001` and `CFE_001-2` both ticked, series on) — each experiment and each result appears once. Test: `test_selection_overlapping_picks_dedupe` (Task 1).
2. **Experiment with no conditions row** in a selection — the Experiments tab still lists it, Conditions omits it, nothing crashes, no Core Flood tab is forced. Test: `test_selection_experiment_without_conditions` (Task 1).
3. **A pick that later disappears** (renamed/deleted while still selected on the page) — the server names it in a 422 and the page shows that text in the error toast, not "Request failed with status code 422". Tests: `test_selection_unknown_ids_422` (Task 1), `shows the server's reason when the export is rejected` (Task 4).
4. **Series off on a collapsed stem row** — ticking `SERUM_X_001` (shown once, `vial_count` 3) exports all three `-t` vials but not the sequential `SERUM_X_001-2`. Test: `test_selection_stem_expands_vials_without_series` (Task 1).
5. **Selection survives filter changes** — a row ticked under one filter is still exported after the filter hides it. Test: `keeps a selection when the filter hides it` (Task 4).

---

### Task 1: Multi-experiment export service and endpoint

**Files:**
- Modify: `backend/services/experiment_export.py`
- Modify: `backend/api/schemas/experiments.py` (request model)
- Modify: `backend/api/routers/experiments.py` (new route next to `export_experiment`)
- Test: `tests/api/test_experiment_export.py` (append; reuse its `_experiment`, `_sample`, `_seed_run`, `_lab`, `_table`, `_view`, `reporting_views`, `frozen_now`)

**Interfaces:**
- Produces:
  - `Member` gains `base_id: str` (`base_experiment_id or experiment_id`) and `experiment_type: str | None`; all existing fields unchanged.
  - `Lineage` keeps `base_id`, `members`, `ids`, `fks`; drop the unused `requested_id`.
  - `_load_members(db: Session, exps: list[Experiment]) -> list[Member]` — the member-building half of today's `resolve_lineage` (one conditions query, parent via `selectinload`). Unsorted.
  - `_series_order(members: list[Member]) -> list[Member]` — sort key `(m.base_id, m.date is None, m.date or _EPOCH, m.experiment_id)`. For one lineage `base_id` is constant, so this equals today's order.
  - Tab builders change parameter from `lineage: Lineage` to `members: list[Member]`: `results_rows`, `core_flood_rows`, `condition_rows`, `additive_rows`, `note_rows`. Their bodies already only use `.fks`, `.ids`, `.members`.
  - `_data_tabs(db, members) -> list[tuple[str, list[Column], list[dict]]]` — Results, Core Flood (when any `m.is_core_flood`), Conditions, Additives, Notes; `build_workbook` uses it unchanged in output.
  - `EXPORT_MAX_EXPERIMENTS: int = 500`
  - `class ExportRejected(Exception)` with `.detail: str` (maps to 422).
  - `resolve_selection(db: Session, experiment_ids: list[str], include_series: bool) -> list[Member]`
  - `EXPERIMENT_COLUMNS: list[Column]` — `experiment_id` "Experiment ID", `base_id` "Base ID", `is_variant` "is_variant", `status` "Status", `experiment_type` "Experiment type", `date` "Date", `researcher` "Researcher", `sample_id` "Sample ID", `reactor_number` "Reactor number", `description` "Description".
  - `build_selection_workbook(db: Session, experiment_ids: list[str], include_series: bool, exported_by: str | None = None) -> tuple[str, bytes]`
  - Schema `ExperimentExportRequest(BaseModel)`: `experiment_ids: list[str] = Field(min_length=1, max_length=500)`, `include_series: bool = True`.
  - Route `POST /api/experiments/export` → `StreamingResponse` (`XLSX_MIME`, `Content-Disposition: attachment; filename="..."`); `ExportRejected` → `HTTPException(422, detail=exc.detail)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/api/test_experiment_export.py`)

Add a helper `_post(client, ids, include_series=True)` that POSTs `{"experiment_ids": ids, "include_series": include_series}` to `/api/experiments/export`, asserts 200 and returns `(resp, load_workbook(...))`. Add a seeder `_seed_vials(db)` creating HPHT-type `SERUM_X_001-t1`, `SERUM_X_001-t3`, `SERUM_X_001-t7` (one sample each, cum day = 1/3/7) and `SERUM_X_001-2` (one sample); assert `SERUM_X_001-2`'s `base_experiment_id == "SERUM_X_001"` so the lineage listener did its job.

```python
def test_selection_mixed_matches_views(client, db_session, reporting_views):
    root, seg2, bypass = _seed_run(db_session)
    hp = _experiment(db_session, "HPE_010", experiment_type="HPHT")
    _sample(db_session, hp, 2.0, measured=_lab(2026, 10, 3), ph=6.5)
    resp, wb = _post(client, ["CFE_001-2", "HPE_010"])
    assert resp.headers["content-disposition"] == (
        'attachment; filename="data_export_2026-11-06.xlsx"')
    assert wb.sheetnames == ["Experiments", "Results", "Core Flood", "Conditions",
                             "Additives", "Notes", "Summary"]
    _h, exps = _table(wb["Experiments"])
    assert [r["Experiment ID"] for r in exps] == [
        "CFE_001", "CFE_001-2", "CFE_001-2_Bypass1", "HPE_010"]
    assert [r["is_variant"] for r in exps] == [False, False, True, False]
    assert exps[3]["Experiment type"] == "HPHT"
    assert exps[0]["Description"] == "Olivine core, Ni catalyst"
    fks = [root.id, seg2.id, bypass.id, hp.id]
    view = {r["result_id"]: r for r in _view(
        db_session, "SELECT * FROM v_results_scalar WHERE experiment_fk = ANY(:f)",
        f=fks)}
    _h, rows = _table(wb["Results"])
    assert {r["Result ID"] for r in rows} == set(view)
    assert [r["Experiment ID"] for r in rows][-1] == "HPE_010"
    for r in rows:
        assert r["pH"] == pytest.approx(view[r["Result ID"]]["final_ph"])
    _h, cf = _table(wb["Core Flood"])
    assert {r["Experiment ID"] for r in cf} == {
        "CFE_001", "CFE_001-2", "CFE_001-2_Bypass1"}
```

Further tests (names and assertions):
- `test_selection_without_series_exports_exact_picks`: `_seed_run`; `_post(["CFE_001-2"], include_series=False)` → Experiments IDs `== ["CFE_001-2"]`; Results experiment IDs all `"CFE_001-2"`; Summary `"Include whole series"` == `"No"`.
- `test_selection_stem_expands_vials_without_series`: `_seed_vials`; `_post(["SERUM_X_001-t1"], False)` → Experiments IDs `== ["SERUM_X_001-t1", "SERUM_X_001-t3", "SERUM_X_001-t7"]` (sorted within one series by date then ID; all dates NULL so by ID); with `True` → `["SERUM_X_001-2", "SERUM_X_001-t1", "SERUM_X_001-t3", "SERUM_X_001-t7"]` (`'2' < 't'`; a letterless `-t` vial's base is the stem, per `.claude/rules/MODELS-lineage.md`).
- `test_selection_overlapping_picks_dedupe`: `_seed_run`; `_post(["CFE_001", "CFE_001-2", "CFE_001-2"])` → Experiments has 3 rows; Results `Result ID`s are unique and number 4.
- `test_selection_hpht_only_has_no_core_flood_tab`: HPHT only → sheetnames `["Experiments", "Results", "Conditions", "Additives", "Notes", "Summary"]`.
- `test_selection_experiment_without_conditions`: create an `Experiment` row with no `ExperimentalConditions` plus `_seed_run`; select both → 200, Experiments lists both (the bare one with `Experiment type` None), Conditions rows only for the CFE members.
- `test_selection_unknown_ids_422`: `_seed_run`; POST `["CFE_001", "NOPE_1", "NOPE_2"]` → 422, `resp.json()["detail"] == "Unknown experiment IDs: NOPE_1, NOPE_2"`.
- `test_selection_cap_422`: `monkeypatch.setattr(experiment_export, "EXPORT_MAX_EXPERIMENTS", 2)`; `_seed_run`; POST `["CFE_001"]` → 422, detail == `"Export too large: 3 experiments after expansion (limit 2). Narrow the selection or turn off Include whole series."`
- `test_selection_empty_list_422`: POST `{"experiment_ids": []}` → 422.
- `test_selection_summary`: `_seed_run` + HPHT `HPE_010` with one sample; `_post(["CFE_001", "HPE_010"])`; Summary dict: `"Experiment count"` 4, `"Series count"` 2, `"Base IDs"` `"CFE_001, HPE_010"`, `"Include whole series"` `"Yes"`, `"Side samples (is_variant)"` `"CFE_001-2_Bypass1"`, `"Exported at"` `datetime(2026, 11, 6, 23, 30)`, `"Exported by"` `"test@addisenergy.com"`, `"Rows: Experiments"` 4, `"Rows: Results"` 5.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/api/test_experiment_export.py -q`
Expected: the new tests FAIL (405 Method Not Allowed on POST); the 15 #141 tests PASS.

- [ ] **Step 3: Refactor the builders** (`experiment_export.py`)

Extract `_load_members` and `_series_order` from `resolve_lineage`, switch the five tab builders to `members: list[Member]`, add `_data_tabs`, and have `build_workbook` call them. `results_rows`/`_ordered_by_member` order by member position exactly as today.

- [ ] **Step 4: Run the #141 tests**

Run: `.venv/Scripts/pytest tests/api/test_experiment_export.py -q -k "not selection"`
Expected: 15 passed (refactor is behavior-neutral).

- [ ] **Step 5: Implement selection** (`experiment_export.py`, schema, route)

`resolve_selection`: dedupe the input preserving order; load picks by `experiment_id IN`; missing → `ExportRejected("Unknown experiment IDs: " + ", ".join(missing in input order))`. Expand: experiments whose `timepoint_stem_expr(Experiment)` (from `backend.services.replicate_collapse`) is in the picks' stems (`split_timepoint_token(id)[0]` from `database.experiment_id_parser`). If `include_series`, also every experiment whose `base_experiment_id` is in the non-null `base_experiment_id`s of that expanded set. Count > `EXPORT_MAX_EXPERIMENTS` → `ExportRejected` with the exact message from the cap test (use the module attribute at call time so the monkeypatch applies). Return `_series_order(_load_members(...))`.

`build_selection_workbook`: Experiments tab rows come from `SELECT * FROM v_experiments WHERE experiment_id = ANY(:ids)`, joined in Python to members for `base_id` and `is_variant`, in member order; sheet order Experiments, then `_data_tabs`, then Summary with keys (in order) `Experiment count`, `Series count`, `Base IDs` (distinct `base_id`s in member order, `", "`-joined), `Include whole series` (`"Yes"`/`"No"`), `Side samples (is_variant)` (joined IDs or None), `Exported at`, `Exported by`, then `Rows: <tab>` for every tab except Summary. Log `experiment_export_selection_built` with counts.

Route `export_selection(payload: ExperimentExportRequest, db, current_user) -> StreamingResponse`, decorated `@router.post("/export")`, placed immediately above `export_experiment`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/api/test_experiment_export.py tests/api/test_experiments.py -q`
Expected: all pass (15 + 10 new in the export file).

- [ ] **Step 7: flake8 and commit**

Run: `.venv/Scripts/flake8 --max-line-length 88 backend/services/experiment_export.py tests/api/test_experiment_export.py` → no output. Commit `[#142] Add multi-experiment workbook export`.

---

### Task 2: `additive` filter on `GET /api/experiments`

**Files:**
- Modify: `backend/api/routers/experiments.py` (`list_experiments` signature and filter block)
- Test: `tests/api/test_experiments_additive_filter.py` (new)

**Interfaces:**
- Produces: query param `additive: str | None` — case-insensitive partial match on `Compound.name` over the experiment's `ChemicalAdditive` rows (`ChemicalAdditive.experiment_id` is the **conditions** id). Applied in SQL before pagination like the other filters, so `total` stays right in both flat and grouped mode.

- [ ] **Step 1: Write the failing tests**

Seed (with the plain `client`/`db_session` fixtures from `tests/api/conftest.py`) three experiments: `ADDF_001` with compound `"ADDF Nickel chloride"`, `ADDF_002` with `"ADDF Magnetite"`, `ADDF_003` with conditions but no additives.
- `test_additive_filter_partial_case_insensitive`: `GET /api/experiments?additive=nickel&search=ADDF_` → `[i["experiment_id"] for i in items] == ["ADDF_001"]` and `total == 1`.
- `test_additive_filter_combines_with_other_filters`: `additive=addf&search=ADDF_002` → `["ADDF_002"]`.
- `test_additive_filter_grouped_mode`: `additive=magnetite&search=ADDF_&group_replicates=true` → one row, `ADDF_002`.
- `test_no_additive_param_is_unchanged`: `search=ADDF_` → 3 items.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/pytest tests/api/test_experiments_additive_filter.py -q`
Expected: the filter tests FAIL (param ignored → 2–3 rows).

- [ ] **Step 3: Implement**

`if additive: stmt = stmt.where(exists(select(ChemicalAdditive.id).join(Compound, Compound.id == ChemicalAdditive.compound_id).where(ChemicalAdditive.experiment_id == ExperimentalConditions.id, Compound.name.ilike(f"%{additive}%"))))`, placed with the other filters (before the grouped/flat split).

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/pytest tests/api/test_experiments_additive_filter.py tests/api/test_experiments.py -q` → all pass.

- [ ] **Step 5: Docs and commit**

`docs/api/API_REFERENCE.md`: add `additive` to the `GET /api/experiments` query list. Commit `[#142] Add additive filter to experiment list`.

---

### Task 3: Frontend API client

**Files:**
- Modify: `frontend/src/api/experiments.ts`
- Modify: `frontend/src/utils/download.ts`
- Test: `frontend/src/api/__tests__/experiments.exportSelection.test.ts` (new), `frontend/src/utils/__tests__/download.test.ts` (append)

**Interfaces:**
- Consumes: `POST /api/experiments/export` (Task 1), `additive` (Task 2).
- Produces:
  - `ExperimentListParams.additive?: string`
  - `experimentsApi.exportSelection(experimentIds: string[], includeSeries: boolean): Promise<string>` — POST `/experiments/export` body `{experiment_ids, include_series}` with `{ responseType: 'blob' }`; saves via `saveBlob`, filename from `filenameFromDisposition(..., 'data_export.xlsx')`; resolves to the filename; on failure rejects with `new Error(await blobErrorMessage(err))`.
  - `blobErrorMessage(err: unknown): Promise<string>` in `utils/download.ts` — when `err.response.data` is a `Blob`, parse its text as JSON and return `detail` if it is a string; otherwise fall back to `err.message`, then `'Export failed'`.

- [ ] **Step 1: Write the failing tests**

- `exportSelection POSTs ids and the series flag as a blob`: mock `apiClient.post` resolving `{data: blob, headers: {'content-disposition': 'attachment; filename="data_export_2026-11-06.xlsx"'}}`; `await exportSelection(['CF_027', 'HPHT_001'], false)` → `post` called with `('/experiments/export', {experiment_ids: ['CF_027','HPHT_001'], include_series: false}, {responseType: 'blob'})`, `saveBlob` called with that blob and filename, resolves to the filename.
- `exportSelection surfaces the server detail from a blob error`: reject with `{message: 'Request failed with status code 422', response: {data: new Blob([JSON.stringify({detail: 'Unknown experiment IDs: NOPE'})])}}` → rejects with message `'Unknown experiment IDs: NOPE'`; `saveBlob` not called.
- `blobErrorMessage` cases (in `download.test.ts`): blob with JSON string detail → detail; blob with non-JSON text → `err.message`; no response → `err.message`; non-Error value → `'Export failed'`.

- [ ] **Step 2: Run to verify failure**

Run (in `frontend/`): `npx vitest run src/api/__tests__/experiments.exportSelection.test.ts src/utils/__tests__/download.test.ts` → new tests FAIL.

- [ ] **Step 3: Implement** as specified in Interfaces.

- [ ] **Step 4: Run to verify pass** — same command, all pass.

- [ ] **Step 5: Commit** `[#142] Add export selection API client`.

---

### Task 4: Data Export page, route and sidebar

**Files:**
- Create: `frontend/src/pages/DataExport/DataExportPage.tsx` (state, list query, selection, export mutation)
- Create: `frontend/src/pages/DataExport/ExportFilters.tsx` (controlled filter bar)
- Create: `frontend/src/pages/DataExport/ExportResultsTable.tsx` (checkbox table)
- Create: `frontend/src/pages/DataExport/index.ts`
- Modify: `frontend/src/App.tsx` (route `/data-export`), `frontend/src/layouts/AppLayout.tsx` (nav item after Chemicals)
- Test: `frontend/src/pages/DataExport/__tests__/DataExportPage.test.tsx` (new), `frontend/src/layouts/__tests__/AppLayout.nav.test.tsx` (extend)

**Interfaces:**
- Consumes: `experimentsApi.list` (with `additive`), `experimentsApi.exportSelection` (Task 3).
- Produces:
  - `interface ExportFilterValues { status: string; experimentType: string; search: string; sampleId: string; reactor: string; description: string; additive: string; researcher: string; dateFrom: string; dateTo: string }` and `EMPTY_FILTERS`.
  - `ExportFilters({ value, onChange }: { value: ExportFilterValues; onChange: (v: ExportFilterValues) => void })` — same controls and option lists as `pages/ExperimentList.tsx` (status and type `Select`s; ID, sample, reactor, description inputs; From/To date inputs) plus text inputs **Researcher…** and **Additive…**. Each control has an `aria-label` equal to its placeholder without the ellipsis (`"Additive"`, `"Experiment ID"`, ...).
  - `ExportResultsTable({ rows, selected, onToggle, onToggleAll }: { rows: ExperimentListItem[]; selected: ReadonlySet<string>; onToggle: (row: ExperimentListItem) => void; onToggleAll: () => void })` — columns: checkbox (`aria-label` `Select <label>`), ID (`group_display_id ?? experiment_id`, plus `· N vials` when `vial_count > 1`), Type, Status, Date, Description, Additives. Header checkbox `aria-label="Select all shown"`, checked when every shown row is selected.
  - `DataExportPage()` — exported from `index.ts`.

Behavior pinned by the tests: text filters debounce 300 ms (the `SEARCH_DEBOUNCE_MS` pattern in `CoreFloodListPage.tsx`); the list query is `experimentsApi.list({...filters, limit: 500, group_replicates: false})` under key `['data-export', debouncedFilters]`; selection is a `Map<string, ExperimentListItem>` keyed by `experiment_id`, independent of the filters; a selection bar shows `"<n> selected"` and a **Clear selection** button; "Include whole series" checkbox, default checked; **Export** button (`variant="primary"`, `loading` while pending, disabled with nothing selected) calls `exportSelection([...selected keys], includeSeries)`; success toast `('Export downloaded', filename)`, error toast `('Export failed', err.message)`. When `data.total > data.items.length`, show `Showing <items> of <total>. Narrow your filters to see the rest.`

- [ ] **Step 1: Write the failing tests** (`DataExportPage.test.tsx`; mock `@/api/experiments` with `list` and `exportSelection`; wrap in `MemoryRouter` + `QueryClientProvider` + `ToastProvider`; three list items `CF_027` (Core Flood), `HPHT_001`, and `SERUM_X_001-t1` with `group_display_id: 'SERUM_X_001'`, `vial_count: 3`)

- `lists filtered experiments with vial counts`: rows show `CF_027`, `HPHT_001`, `SERUM_X_001 · 3 vials`; `list` called with `limit: 500, group_replicates: false`.
- `passes the additive filter to the list`: type `nickel` in the `Additive` input → `list` eventually called with `expect.objectContaining({additive: 'nickel'})`.
- `exports the selection with the series flag`: tick `Select CF_027` and `Select SERUM_X_001`, click **Export** → `exportSelection` called with `(['CF_027', 'SERUM_X_001-t1'], true)`; toast `Export downloaded` appears.
- `turning off Include whole series sends false`: untick the checkbox, select one, Export → second arg `false`.
- `select all shown selects every row`: click `Select all shown` → `3 selected`.
- `keeps a selection when the filter hides it`: tick `CF_027`; `list` now resolves to only `HPHT_001`; type `HPHT` in `Experiment ID`; once `CF_027` is gone from the table, `1 selected` still shows and Export sends `['CF_027']`.
- `Export is disabled with nothing selected`, and `Clear selection` returns to that state.
- `shows the server's reason when the export is rejected`: `exportSelection` rejects with `new Error('Unknown experiment IDs: CF_027')` → toast title `Export failed` and that message.
- `warns when results are truncated`: `list` resolves `{items: <3 rows>, total: 812, ...}` → text `Showing 3 of 812. Narrow your filters to see the rest.`
- Nav test: add an assertion that the nav hrefs contain `'/data-export'` immediately after `'/chemicals'`; keep the existing `slice(-2)` assertion.

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/pages/DataExport src/layouts` → FAIL (module not found / nav assertion).

- [ ] **Step 3: Implement** the components, route and nav item (icon: a 16×16 `svg` download arrow over a tray, `stroke="currentColor"` like its neighbours).

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/pages/DataExport src/layouts` → all pass.

- [ ] **Step 5: Full frontend checks**

Run: `npx vitest run` → all pass (was 491); `npm run type-check` → only the 3 known `ResultsTab.columns.test.tsx` errors; `npm run lint` → only the 5 known baseline errors; `npm run build` → succeeds.

- [ ] **Step 6: Docs and commit**

`docs/user_guide/USER_MANUAL.md`: add Data Export to the Main Pages table and a Common Tasks row (filter, tick, Include whole series, Export; 500-experiment limit). `docs/api/API_REFERENCE.md`: add `POST /api/experiments/export` (body, expansion rules, tabs incl. Experiments, Summary keys, 422 messages, filename) to the table and a section after the GET export. Commit `[#142] Add Data Export page`.

---

### Task 5: End-to-end verification and log

**Files:**
- Modify: `docs/working/issue-log.md`

- [ ] **Step 1: Backend regression** (one process)

Run: `.venv/Scripts/pytest tests/services/ tests/regression/ tests/api/ tests/models/ tests/views/ tests/data_migrations/ -q -p no:warnings`
Expected: 0 failed (was 1522 passed before this branch).

- [ ] **Step 2: Real data, read-only** — scratch script calling `build_selection_workbook(db, ["CF_027-2", "CF-015", <one HPHT id from the dev DB>], True)` in a session that is rolled back; record per-tab row counts and file size.

- [ ] **Step 3: Browser** (Chrome DevTools MCP, dev servers already running): `/data-export` — sidebar position; Additive filter narrows the list; tick CF_027 + an HPHT experiment; Export → `POST /api/experiments/export` 200, toast names `data_export_<date>.xlsx`; repeat with series off; console clean. Open the downloaded file and confirm the sheet list.

- [ ] **Step 4: Issue log and commit** — append the `## 2026-11-06 | issue #142 — ...` entry (files, decisions, verification numbers, follow-ups); commit `[#142] Log data export page`.
