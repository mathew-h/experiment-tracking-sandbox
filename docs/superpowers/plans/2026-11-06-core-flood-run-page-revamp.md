# Core Flood Run Page Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the in-app Core Floods pages a fast "open a run, see every sample, add or fix one" tool: experiment and sample notes on screen, a grouped sample form, an explicit permeability test flow rate, and ICP per sample plus an ICP-vs-time chart.

**Architecture:** One additive column (`experimental_results.permeability_flow_rate_mL_min`) carried through a new migration that recreates `v_core_flood_samples`. The core flood service gains result-scoped notes on every sample row, a `result_note` write path on sample create/edit, a run description on list items, and a read-only ICP endpoint per run. The React run page is reorganised around the samples table; secondary sections collapse to the bottom; a Recharts line chart plots ICP against cumulative days.

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy + Alembic + PostgreSQL; React 18 + TanStack Query + Tailwind + Recharts 3 (already a dependency — no new packages); pytest, vitest + Testing Library.

**Spec:** No separate design document — Mat chose to go straight from the brainstorming session (2026-11-06) to this plan. The **Design** section below is the spec. Mockups (untracked): `.superpowers/brainstorm/22229-1793986868/content/` (`run-list-and-page.html`, `sample-form.html`, `icp-views.html`).

## Design (settled with Mat, 2026-11-06)

1. **Who/why.** Researchers open Core Floods in the lab to check recent data, fix a value, or add the latest sample. The page's main job: open a base run and see all historical samples. KPI tiles and segments are rarely needed.
2. **List page.** Each run shows its experiment description. Columns: Run, Description, Rig, Samples, Last sample, Status. Segment count, cumulative H₂ and warnings count leave the list (*my call, shown in the mockup, not objected to*). Run description = the root segment's `description` note (non-variant, no parent; earliest date wins; fall back to the first segment that has one). Search also matches the description.
3. **Run page order.** Header (base ID, run description, rig, ongoing segment chip, **+ Add sample**) → Samples table → collapsed sections at the bottom: Side samples, ICP chart (open by default when the run has ICP data, absent when it has none), Segments, Data checks (the existing CleanupPanel), Run totals (cumulative H₂ to date, pore volumes to date — the old KPI tiles). Rig/ongoing move into the header.
4. **Samples table.** Newest first. Columns: expander, Date, Day, Tube, Result note | **GC**: H₂ ppm, H₂ g/t | **Solution**: pH, Cond., Liq mL | **Core flood**: Flow, Perm. flow, Inlet psi, Outlet psi — with GC/Solution/Core flood group header row. Cumulative columns (Cum. H₂, g/t/day, pore volumes, H₂ µmol) leave the table (*my call*; they live in Run totals and Power BI). HOLD badge stays on flow 0; a PERM badge marks rows with a permeability test flow rate.
5. **Sample notes.** "Sample description" = result-scoped `experiment_notes`. The Result note cell shows `result_note` and `observation` texts (historical uploads wrote `observation`), joined with " · ", full text on hover; a MOD badge when a `modification` note exists. The form's **Result note** box reads and writes the sample's **first** `result_note` (lowest id, any author): edit in place, blank deletes it, absent creates one signed with the user's email. Other result-scoped notes are listed read-only under the box (*my call*).
6. **Sample form layout.** Top row: Segment (add only), Sample date, Day, Tube #; then Result note (full width). Below, three columns: **GC** — H₂ (ppm), Gas pressure (psi), Gas volume (mL), GC run date. **Solution** — pH, Conductivity (mS/cm), Liquid sample volume (mL). **Core flood** — "Hold since last sample" checkbox, Flow rate, Permeability test flow rate, Inlet pressure, Outlet pressure, N₂ flow.
7. **Hold checkbox.** Checked ⇔ flow rate `0`. Checking sets flow to `0`, disables the flow input and focuses the permeability field; unchecking restores the flow value from before checking (blank if none). Flow rate keeps its meaning: rate over the interval ending at the sample; 0 = hold.
8. **Permeability rule (Mat).** Inlet/outlet pressures are recorded only when permeability is intentionally tested, at either the flow rate or a separate test rate. **The presence of `permeability_flow_rate_mL_min` is what marks a sample as a permeability test and is the sole trigger for any future permeability computation.** Nothing computes permeability in this plan.
   - New samples no longer copy the previous sample's inlet/outlet pressure (only flow and N₂ flow carry forward).
   - Typing a pressure while the test rate is blank and untouched fills the test rate with the current non-zero flow rate.
   - The form blocks save when pressures are entered without a test rate, or a test rate without any pressure. The server does not enforce the pairing (*my call*: PATCH is partial, and bulk paths never write these fields).
   - Dev DB (2026-11-06): 0 of 183 core flood samples carry a pressure, so there is nothing to backfill.
9. **ICP.** Per sample on request: an expander on rows that have ICP, showing non-null element ppm values. Run chart: option **B** — lines vs `cumulative_time_post_reaction_days`, one line per selected element, element picker chips (only elements present in the run), log-scale toggle, dashed reference line at each non-variant segment's first sample, labelled with the segment ID. Variant (side) samples are excluded from the chart. Default selection: those of `ca, si, fe, cu, ni` present; if none, the first five present in `ICP_ELEMENTS` order. ICP is matched by `icp_results.result_id = v_core_flood_samples.result_id`. Dev DB: 86 core flood samples on 14 runs have ICP.

## Global Constraints

- `database/models/` is locked: the only model change is the one nullable `Float` column `permeability_flow_rate_mL_min` on `ExperimentalResults`, no default, no server default (Mat's sign-off: this plan).
- Migrations are additive with a working `downgrade`; never edit or delete `f3b7c2a9d4e1` (its *test file* is updated, not the migration).
- Quote mixed-case column names in raw SQL: `er."permeability_flow_rate_mL_min"`.
- No new npm or pip packages. `frontend/package.json` must not change.
- Never run two `pytest` processes at once (shared `experiments_test`).
- Do not touch `backend/services/bulk_uploads/`.
- Every write path flushes and lets the router commit; audit rows go to `ModificationsLog`.
- Commits: `[#140] <imperative, < 50 chars>` + `Tests added` / `Docs updated` lines + the Co-Authored-By trailer. Multi-line messages via `git commit -F <scratchpad file>`.
- Edits to `docs/*.md` made via Bash/Python bypass the project_context sync hook — use Edit/Write, or run the sync script with `--all` afterwards.

## Review Focus

1. **Editing a sample whose only result-scoped note is an upload `observation`** — the Result note box starts empty, the observation is listed read-only, and saving with text creates a new `result_note` without touching the observation. Test: Task 2 `test_patch_result_note_leaves_observation`.
2. **Clearing the Result note box on edit** deletes exactly that one `result_note` and audits the old text; an unchanged box sends nothing. Tests: Task 2 `test_patch_result_note_blank_deletes_and_audits`, Task 5 `omits result_note when unchanged`.
3. **Log scale with zero ppm readings** — Recharts log axes break on `<= 0`; points `<= 0` must be dropped from log-mode series, not plotted. Test: Task 7 `drops non-positive values in log mode`.
4. **Hold toggled on an edited historical sample** — unchecking restores the original flow, and the PATCH body contains no `flow_rate_mL_min` when the net change is nothing. Test: Task 5 `hold toggle round-trip leaves patch empty`.
5. **Run with variant (side) samples that have ICP** — expander still works in the side table, but variants never appear in the chart. Tests: Task 3 `test_icp_rows_include_variants_flagged`, Task 7 `excludes variant rows`.

---

### Task 0: Start the task

- [ ] **Step 1:** Run `/start-task` in **issue** mode. Create a GitHub issue "Core flood run page revamp" (body: link this plan, list Design items 2–9) and branch `feat/issue-140-core-flood-revamp` from `develop`. Replace `<issue>` in every commit below with `140`.
- [ ] **Step 2:** Commit this plan file: `git add docs/superpowers/plans/2026-11-06-core-flood-run-page-revamp.md` → `[#140] Add core flood revamp plan`. Add `.superpowers/` to `.gitignore` in the same commit.

---

### Task 1: Permeability column, migration and view

**Files:**
- Modify: `database/models/results.py:39-42` (add column after `outlet_pressure_psi`)
- Create: `alembic/versions/a1c5e8f2b9d3_core_flood_permeability_flow_rate.py`
- Modify: `database/event_listeners.py` (`v_core_flood_samples` in `_VIEWS`, ~lines 754-757 and ~804-807)
- Create: `tests/models/test_core_flood_permeability_schema.py`
- Modify: `tests/models/test_core_flood_schema.py:95-99`
- Docs: `.claude/rules/MODELS-results.md` (core flood bullet), `.claude/rules/MODELS-views.md` (`v_core_flood_samples`), `docs/POWERBI_MODEL.md` ("Core Flood Run View"), `docs/CALCULATIONS.md` ("Core flood run values": permeability trigger rule, nothing computed yet)

**Interfaces:**
- Produces: column `ExperimentalResults.permeability_flow_rate_mL_min: Float | None`; view column `v_core_flood_samples."permeability_flow_rate_mL_min"` placed immediately after `outlet_pressure_psi` in both the `s` CTE and the final SELECT. Migration module constants `_V_CORE_FLOOD_SAMPLES_OLD` (verbatim `f3b7c2a9d4e1._V_CORE_FLOOD_SAMPLES`) and `_V_CORE_FLOOD_SAMPLES` (new).

- [ ] **Step 1: Write the failing tests** in `test_core_flood_permeability_schema.py` (reuse `_load_migration` / `_norm` / `_script_dir` patterns from `test_core_flood_schema.py`; `REVISION = "a1c5e8f2b9d3"`, `PARENT = "f3b7c2a9d4e1"`):

```python
def test_permeability_column_nullable_float():
    col = ExperimentalResults.__table__.columns["permeability_flow_rate_mL_min"]
    assert isinstance(col.type, Float) and col.nullable is True
    assert col.default is None and col.server_default is None

def test_revision_parent():
    assert _script_dir().get_revision(REVISION).down_revision == PARENT

def test_view_matches_startup():
    assert _norm(mod._V_CORE_FLOOD_SAMPLES) == _norm(dict(_VIEWS)["v_core_flood_samples"])

def test_old_view_is_predecessor():
    assert _norm(mod._V_CORE_FLOOD_SAMPLES_OLD) == _norm(prev._V_CORE_FLOOD_SAMPLES)

def test_new_view_is_old_plus_column():
    col = 'er."permeability_flow_rate_mL_min",'
    assert mod._V_CORE_FLOOD_SAMPLES.count('"permeability_flow_rate_mL_min"') == 2
    assert _norm(mod._V_CORE_FLOOD_SAMPLES.replace(col, "")
                 .replace('"permeability_flow_rate_mL_min",', "")) == _norm(mod._V_CORE_FLOOD_SAMPLES_OLD)
```

Change `test_core_flood_schema.py::test_core_flood_view_matches_startup` to compare `f3b7c2a9d4e1._V_CORE_FLOOD_SAMPLES` with the new migration's `_V_CORE_FLOOD_SAMPLES_OLD` (rename it `test_core_flood_view_matches_successor_old`) — only the newest migration compares to `_VIEWS`.

- [ ] **Step 2:** `pytest tests/models/test_core_flood_permeability_schema.py tests/models/test_core_flood_schema.py -v` → FAIL (missing column / module).
- [ ] **Step 3: Implement.** Model column with a comment stating Design item 8's rule. Migration: `upgrade` = `add_column` then `_recreate("v_core_flood_samples", _V_CORE_FLOOD_SAMPLES)`; `downgrade` = `_recreate(..., _V_CORE_FLOOD_SAMPLES_OLD)` **before** `drop_column`. Module docstring explains the order (startup recreates the view selecting the column). Update `_VIEWS` to the same SQL.
- [ ] **Step 4:** `pytest tests/models/ -v` → all PASS.
- [ ] **Step 5: Rehearse the migration on `experiments_test`** following memory note *migration-rehearsal-on-experiments-test* (seed via ORM, drop the new column, stamp `f3b7c2a9d4e1`, `upgrade head`, `downgrade -1`, `upgrade head`, clean up). Expected: all three commands exit 0 and `\d+ v_core_flood_samples` lists the column after the last upgrade. Then `alembic upgrade head` on the dev DB.
- [ ] **Step 6:** Update the four docs listed above. Commit: `[#140] Add permeability flow rate column and view`.

---

### Task 2: API — permeability field, sample notes, run description

**Files:**
- Modify: `backend/api/schemas/core_floods.py`
- Modify: `backend/services/core_flood_service.py`
- Modify: `backend/api/routers/core_floods.py` (POST/PATCH responses attach notes)
- Test: `tests/api/test_core_floods.py`
- Docs: `docs/api/API_REFERENCE.md` (core floods section)

**Interfaces:**
- Consumes: Task 1 column.
- Produces (schemas):
  - `CoreFloodSampleNote(BaseModel)`: `id: int`, `note_type: Literal["observation", "result_note", "modification"]`, `note_text: str`, `created_by: Optional[str]`.
  - `CoreFloodSample` gains `permeability_flow_rate_mL_min: Optional[float] = None` and `notes: list[CoreFloodSampleNote] = []`.
  - `_CoreFloodSampleFields` gains `permeability_flow_rate_mL_min: Optional[float] = Field(None, gt=0)` and `result_note: Optional[str] = Field(None, max_length=2000)`.
  - `CoreFloodRunListItem` gains `description: Optional[str] = None`.
- Produces (service):
  - `RESULT_FIELDS` includes `"permeability_flow_rate_mL_min"`.
  - `attach_notes(db: Session, rows: list[dict]) -> list[dict]` — adds `notes` (ordered by note id) to each row; one query over `result_id IN (...)` and the three types.
  - `run_description(segments: list[CoreFloodSegment]) -> Optional[str]` — Design item 2 rule.
  - `_apply_result_note(db, exp, result, text: Optional[str], user_email: str) -> None` — Design item 5 semantics: `None`/blank after strip → delete the first `result_note` if any; text → update first `result_note` in place (and call `notes_service.release_upload_slot(note, user_email)`) or `notes_service.add_note(..., note_type=NoteType.result_note, result_id=result.id, created_by=user_email)`. Writes one `ModificationsLog` row (`modified_table="experiment_notes"`, `old_values={"note_text": ...}` / `new_values`) only when something changed.
  - `create_sample` calls `_apply_result_note` only when `payload.result_note` is non-blank. `update_sample` calls it only when `"result_note" in payload.model_dump(exclude_unset=True)`; `result_note` is excluded from `RESULT_FIELDS`/`SCALAR_FIELDS` handling.
  - `get_run` and both router write responses pass rows through `attach_notes`. `list_runs` sets `description` and its `q` filter also matches `description` (case-insensitive substring).

- [ ] **Step 1: Write the failing tests** (use existing `_cf_experiment`, `_sample`, `_post`, `_patch`, `_seed_posted_sample`, `_log_count` helpers; add notes via `ExperimentNotes(...)` like `_cf_experiment` does):
  - `test_create_with_permeability_flow_persists` — POST with `permeability_flow_rate_mL_min=0.05` → 201, response field `== 0.05`, DB column `== 0.05`.
  - `test_create_permeability_zero_422` — `permeability_flow_rate_mL_min=0` → 422, `_result_count` unchanged.
  - `test_create_with_result_note` — POST with `result_note=" Pulled after hold "` → response `notes == [{"note_type": "result_note", "note_text": "Pulled after hold", "created_by": <test user email>, "id": ...}]`.
  - `test_create_blank_result_note_writes_no_note` — `result_note="  "` → `notes == []`, no `experiment_notes` row for the result.
  - `test_run_samples_include_result_scoped_notes` — seed observation + result_note + modification on one result and a `description` note on the experiment → that sample's `notes` has the three result-scoped notes in id order and no description.
  - `test_patch_result_note_updates_first_in_place` — two result_notes seeded; PATCH `result_note="new"` → the lower-id note's text is `"new"`, same id, other unchanged; one `ModificationsLog` row with `modified_table == "experiment_notes"`.
  - `test_patch_result_note_blank_deletes_and_audits` — PATCH `result_note=""` → note gone; audit `old_values == {"note_text": <old>}`.
  - `test_patch_result_note_leaves_observation` — only an observation (`created_by="master_bulk_upload"`) seeded; PATCH `result_note="x"` → observation untouched, new result_note created.
  - `test_patch_without_result_note_key_leaves_notes` — PATCH `final_ph=7.1` → notes unchanged, no notes audit row.
  - `test_patch_result_note_only_is_not_noop` — PATCH body `{"result_note": "x"}` returns 200 and the note exists.
  - `test_list_item_description_is_root_segment` — root `CF_900` description "root desc", child `CF_900-2` "child desc" → list item `description == "root desc"`.
  - `test_list_q_matches_description` — `q="tuscarora"` finds a run whose root description is "Tuscarora core".
- [ ] **Step 2:** `pytest tests/api/test_core_floods.py -v` → new tests FAIL.
- [ ] **Step 3:** Implement the interfaces above.
- [ ] **Step 4:** `pytest tests/api/test_core_floods.py tests/api/test_core_flood_view.py -v` → all PASS.
- [ ] **Step 5:** Update `API_REFERENCE.md`. Commit: `[#140] Add sample notes and perm flow to core flood API`.

---

### Task 3: API — run ICP endpoint

**Files:**
- Modify: `backend/api/schemas/core_floods.py`, `backend/services/core_flood_service.py`, `backend/api/routers/core_floods.py`
- Test: `tests/api/test_core_floods.py`
- Docs: `docs/api/API_REFERENCE.md`

**Interfaces:**
- Produces: `CoreFloodIcpRow(BaseModel)`: `result_id: int`, `experiment_id: str`, `is_variant: bool`, `cumulative_time_post_reaction_days: Optional[float]`, `sample_date: Optional[datetime]`, `elements: dict[str, float]` (keys lowercase symbols from `ICP_ELEMENTS` in `backend/api/schemas/results.py`, non-null values only, ppm).
- Produces: `get_run_icp(db: Session, base_id: str) -> list[CoreFloodIcpRow]` — raises `CoreFloodNotFound` when the base has no core flood segments; rows in view order; a sample without an `icp_results` row is omitted.
- Produces: `GET /api/core-floods/{base_id}/icp` → `list[CoreFloodIcpRow]`, auth like the other routes. Declare it **before** `GET /{base_id}`.

- [ ] **Step 1: Write the failing tests:**
  - `test_icp_rows_for_run` — two samples, ICP (`fe=12.4, ca=210, cu=None`) on one → one row, `elements == {"fe": 12.4, "ca": 210.0}`.
  - `test_icp_rows_include_variants_flagged` — ICP on a `CF_901-2_Bypass1` sample → row present with `is_variant is True`.
  - `test_icp_unknown_run_404`.
  - `test_icp_run_without_icp_returns_empty_list`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (one SQL join of `v_core_flood_samples` to `icp_results` on `result_id`, filtered by `run_base_id`; build `elements` from the `ICP_ELEMENTS` columns). **Step 4:** `pytest tests/api/test_core_floods.py -v` → PASS.
- [ ] **Step 5:** Docs; commit `[#140] Add core flood run ICP endpoint`.

---

### Task 4: Frontend API types and form field logic

**Files:**
- Modify: `frontend/src/api/coreFloods.ts`
- Modify: `frontend/src/pages/CoreFloods/fields.ts`
- Modify: `frontend/src/pages/CoreFloods/useCoreFloodWrites.ts`
- Test: `frontend/src/pages/CoreFloods/__tests__/fields.test.ts`

**Interfaces:**
- Consumes: Tasks 2-3 wire shapes.
- Produces (`coreFloods.ts`): `CoreFloodSampleNote`, `CoreFloodIcpRow` types mirroring the Pydantic ones; `CoreFloodSample.permeability_flow_rate_mL_min`, `CoreFloodSample.notes`; `CoreFloodRunListItem.description`; `CoreFloodSampleCreate.permeability_flow_rate_mL_min?` and `result_note?: string | null`; `coreFloodsApi.icp(baseId: string): Promise<CoreFloodIcpRow[]>`.
- Produces (`fields.ts`):
  - `SampleFieldKey` adds `'permeability_flow_rate_mL_min'`; `SAMPLE_FIELDS` adds it with label `'Permeability test flow rate'`, unit `mL/min`, `min: 0, minExclusive: true`, help `'Rate while pressures were read. Marks this sample as a permeability test.'`. Flow rate's help becomes `'Rate since the previous sample.'`.
  - `SAMPLE_GROUPS: Record<'gc' | 'solution' | 'coreflood', readonly SampleFieldKey[]>` in Design item 6 order (`coreflood`: flow, permeability, inlet, outlet, N₂).
  - `prefillFromPrevious` copies only `flow_rate_mL_min` and `nitrogen_flow_rate_mL_min`.
  - `withPressure(form: SampleForm, key: 'inlet_pressure_psi' | 'outlet_pressure_psi', value: string, opts: { permEdited: boolean }): SampleForm`.
  - `validatePermeability(form: SampleForm): Partial<Record<SampleFieldKey, string>>` — messages exactly: on `permeability_flow_rate_mL_min`: `'Enter the test flow rate used for these pressures'`; on `inlet_pressure_psi`: `'Enter inlet or outlet pressure for this permeability test'`.
  - `resultNoteOf(s: CoreFloodSample): CoreFloodSampleNote | undefined` (first `result_note`) and `noteSummary(s: CoreFloodSample): { text: string; hasModification: boolean }` (result_note + observation texts joined `' · '`).
  - `invalidateCoreFloodWrites` also invalidates `['core-flood-icp', baseId]`.

- [ ] **Step 1: Write the failing tests** in `fields.test.ts`:
  - `prefill no longer copies pressures` — prev has inlet 120 → `next.inlet_pressure_psi === ''`, `next.flow_rate_mL_min === '0.1'`.
  - `typing a pressure fills the test rate from a non-zero flow` — flow `'0.05'`, perm `''` → `withPressure(..., '1520', {permEdited:false}).permeability_flow_rate_mL_min === '0.05'`.
  - `pressure does not fill the test rate on a hold or after the user edited it` — flow `'0'` → stays `''`; `permEdited: true` → stays as typed.
  - `pressures without a test rate is an error` / `test rate without pressures is an error` / `both blank or both present is fine` — exact messages above.
  - `permeability rate must be > 0` — `validateForm` gives `'Must be > 0'` for `'0'`.
  - `noteSummary joins result and observation notes and flags modifications`.
- [ ] **Step 2:** `npx vitest run src/pages/CoreFloods/__tests__/fields.test.ts` → FAIL. **Step 3:** Implement. **Step 4:** Re-run → PASS (fix any existing prefill assertions that expected pressures to carry).
- [ ] **Step 5:** Commit `[#140] Add permeability and notes field logic`.

---

### Task 5: Sample form re-layout (hold, result note, permeability)

**Files:**
- Modify: `frontend/src/pages/CoreFloods/CoreFloodSampleModal.tsx`
- Test: `frontend/src/pages/CoreFloods/__tests__/CoreFloodSampleModal.test.tsx`

**Interfaces:**
- Consumes: Task 4 (`SAMPLE_GROUPS`, `withPressure`, `validatePermeability`, `resultNoteOf`).
- Produces: unchanged component props.

Layout per Design items 6-7. Each column is a bordered block with an uppercase heading `GC` / `Solution` / `Core flood` (use `frontend-builder` skill for tokens; `<section aria-label="GC">` etc.). Result note: a `<textarea aria-label="Result note">` styled like `Input`; existing other notes (`notes` minus the first `result_note`) render read-only below it with their type. Hold checkbox `aria-label="Hold since last sample"`. Submit runs `validatePermeability` alongside `validateForm`. Create body adds `result_note` when non-blank; patch body adds `result_note` (blank → `null`) only when the trimmed text differs from the initial.

- [ ] **Step 1: Write the failing tests:**
  - `renders GC, Solution and Core flood groups with their fields` — `within(screen.getByRole('region', {name: 'GC'})).getByLabelText(/H₂ \(ppm\)/)` etc. for each Design item 6 field.
  - `hold checkbox sets flow to 0 and disables it; unchecking restores` — prefilled flow `0.1` → check → flow input value `'0'` and disabled → uncheck → `'0.1'`.
  - `hold toggle round-trip leaves patch empty` — edit a sample with flow 0.1, check then uncheck, add pH → `updateSample` called with body lacking `flow_rate_mL_min`.
  - `blocks save when pressures have no test rate` — on a hold, type inlet `1520` → submit → error text shown, `createSample` not called.
  - `sends result_note on create` and `omits result_note when unchanged` / `sends null when cleared` on edit.
  - `lists other notes read-only` — sample with an observation note shows its text and no textbox for it.
  - Update existing tests that relied on pressure prefill or the flat field order.
- [ ] **Step 2:** `npx vitest run src/pages/CoreFloods/__tests__/CoreFloodSampleModal.test.tsx` → FAIL. **Step 3:** Implement. **Step 4:** → PASS.
- [ ] **Step 5:** Commit `[#140] Regroup core flood sample form`.

---

### Task 6: Samples table, run page layout, list page

**Files:**
- Create: `frontend/src/pages/CoreFloods/Collapsible.tsx`
- Modify: `frontend/src/pages/CoreFloods/SamplesTable.tsx`, `CoreFloodRunPage.tsx`, `CoreFloodListPage.tsx`
- Test: `__tests__/CoreFloodRunPage.test.tsx`, `__tests__/CoreFloodListPage.test.tsx`, create `__tests__/SamplesTable.test.tsx`

**Interfaces:**
- Consumes: Task 4 types, `noteSummary`, `coreFloodsApi.icp`.
- Produces:
  - `Collapsible({ title: string; summary?: ReactNode; defaultOpen?: boolean; open?: boolean; onOpenChange?: (o: boolean) => void; children })` — a `<button aria-expanded>` header; children unmounted when closed.
  - `SamplesTable` props become `{ samples; variant: boolean; onEdit; icpByResult: Map<number, Record<string, number>> }`. Rows render newest first (reverse of server order — do not re-sort by date). Expander button `aria-label="Show ICP for <date>"` only when `icpByResult.has(result_id)`; its click stops propagation; expanded row lists `Fe 12.4` style (`fmt`, symbol capitalised) in `ICP_ELEMENTS` order.
  - Run page runs `useQuery({ queryKey: ['core-flood-icp', baseId], queryFn: () => coreFloodsApi.icp(baseId) })`.
  - CleanupPanel's `onRename` / `onEditDescription` also open the Segments collapsible (controlled `open`).

- [ ] **Step 1: Write the failing tests:**
  - SamplesTable: `renders newest first`; `shows grouped headers GC, Solution, Core flood`; `shows HOLD on flow 0 and PERM when a test rate is set`; `result note cell joins notes and shows MOD`; `ICP expander only on rows with ICP and does not open edit` (click expander → `onEdit` not called, `Fe 12.4` visible).
  - Run page: `header shows run description, rig and ongoing segment`; `samples table comes before collapsed sections`; `run totals collapsed by default and show cumulative H₂ when opened`; `segments collapsed by default; rename from data checks opens it`; `side samples collapsed`. Remove/replace tests that asserted the four MetricCards at the top.
  - List page: `shows description column`; `shows Ongoing status for runs with an ongoing segment`; no `Segments`/`Warnings` headers.
- [ ] **Step 2:** `npx vitest run src/pages/CoreFloods` → FAIL. **Step 3:** Implement (load `frontend-builder` skill first for design tokens). **Step 4:** → PASS.
- [ ] **Step 5:** Commit `[#140] Rework core flood run and list pages`.

---

### Task 7: ICP chart

**Files:**
- Create: `frontend/src/pages/CoreFloods/IcpChart.tsx`, `frontend/src/pages/CoreFloods/icpSeries.ts`
- Modify: `CoreFloodRunPage.tsx` (Collapsible "ICP over time", `defaultOpen`, rendered only when ICP rows exist)
- Test: `__tests__/icpSeries.test.ts`, `__tests__/IcpChart.test.tsx`

**Interfaces:**
- Consumes: `CoreFloodIcpRow[]`, run `segments` and `samples`.
- Produces (`icpSeries.ts`, pure):
  - `elementsPresent(rows: CoreFloodIcpRow[]): string[]` — `ICP_ELEMENTS` order (copy the list into `frontend/src/pages/CoreFloods/icpElements.ts` as `ICP_ELEMENTS` with a comment naming the backend source).
  - `defaultSelection(present: string[]): string[]` — Design item 9 rule.
  - `chartPoints(rows, selected: string[], log: boolean): Array<{ day: number } & Record<string, number | null>>` — non-variant rows with a cumulative day, sorted by day; in log mode values `<= 0` become `null`.
  - `segmentStarts(samples: CoreFloodSample[]): Array<{ day: number; experimentId: string }>` — first non-variant sample's cumulative day per segment, skipping the first segment.
- `IcpChart({ rows, samples })` — chips are `<button aria-pressed>` per present element; log toggle `<button aria-pressed>` labelled `Log scale`; Recharts `LineChart` in `ResponsiveContainer` (pattern: `ExperimentDetail/GroupedResultsView.tsx`), `XAxis dataKey="day" type="number"` labelled "Cumulative day", `YAxis` labelled "ppm" with `scale={log ? 'log' : 'linear'}` and `domain={['auto','auto']}`, `connectNulls`, one `ReferenceLine` per segment start.

- [ ] **Step 1: Write the failing tests:**
  - `icpSeries`: `elementsPresent keeps ICP_ELEMENTS order`; `defaultSelection prefers ca si fe cu ni`; `defaultSelection falls back to first five present`; `excludes variant rows`; `drops non-positive values in log mode`; `segmentStarts skips the first segment`.
  - `IcpChart`: `renders a chip per present element with defaults pressed`; `toggling a chip changes aria-pressed`; `log scale toggle is pressable`.
- [ ] **Step 2:** `npx vitest run src/pages/CoreFloods` → FAIL. **Step 3:** Implement. **Step 4:** → PASS.
- [ ] **Step 5:** Commit `[#140] Add ICP over time chart to run page`.

---

### Task 8: Whole-branch verification

- [ ] **Step 1:** `pytest tests/models/ tests/api/test_core_floods.py tests/api/test_core_flood_view.py -v` → PASS. Then the full `pytest -q` once; the 3 known `pg_backup_restore` failures are pre-existing (memory note) — compare against `develop` if anything else fails.
- [ ] **Step 2:** `cd frontend && npx vitest run && npx tsc --noEmit && npm run lint` → all clean.
- [ ] **Step 3:** Browser check (Chrome DevTools MCP) on the dev app with the backend already running: list shows descriptions; open `CF-015` (has ICP) → samples newest first, notes visible, ICP expander, chart lines with segment markers, log toggle; add a hold sample with a test rate and pressures, then edit it and clear the result note. Roll back or delete any test sample afterwards. Screenshot each state for the PR.
- [ ] **Step 4:** Run `/complete-task` (docs sync, merge to `develop`, PR with `--base develop`).
