# Core Floods Run Page Implementation Plan (issue #134)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Core Floods" sidebar page: a run list and a run record where researchers add and edit samples across segments and fix the run's data-quality warnings.

**Architecture:** Frontend only, on top of the shipped `/api/core-floods` API (#133) and the existing experiments, notes and conditions endpoints. One field map (`fields.ts`) owns every UI-to-API translation (labels, units, psi to MPa, lab-local day, which fields changed), so the modal and the tables hold no conversion logic. Server-derived run values (interval days, cumulative volume, pore volumes, cumulative H₂, g/t/day, hold) are displayed as returned and never recomputed.

**Tech Stack:** React 18 + TypeScript strict, TanStack Query v5, React Router v6, Tailwind (tokens in `frontend/tailwind.config.*`), vitest + Testing Library.

**Spec:** `docs/issues/issue-core-flood-frontend.md` (parent `docs/issues/issue-core-flood-run-page.md`). API contract: `docs/api/API_REFERENCE.md` "Core floods" and `backend/api/schemas/core_floods.py`.

## Global Constraints

- Frontend only. If a backend change turns out to be needed, stop and ask the user.
- No new npm dependency. If one becomes unavoidable, ask first, then commit `package.json` and `package-lock.json` together.
- Design-system tokens only (`surface-*`, `ink-*`, `status-*`, `navy-*`, `red-*` Tailwind classes; `@/components/ui`). No hex values, no inline styles.
- Request bodies use API field names only. Both sample bodies use `extra="forbid"`, so never send an unknown key.
- PATCH never sends `time_post_reaction_days`. It never sends `null` for `flow_rate_mL_min` or `measurement_date`.
- Dates go on the wire as date-only `"YYYY-MM-DD"`.
- The day is counted in lab-local calendar days (`LAB_TZ = 'America/New_York'`, `frontend/src/utils/labDate.ts`), not UTC and not millisecond arithmetic. 2026-10-23 → 2026-11-03 is day 11.
- After every write, invalidate `['core-floods']`, `['core-flood', baseId]`, `['experiment', segmentId]`, `['experiment-results', segmentId]`, `['experiments']`, `['dashboard']`.
- Commits are `[#134] <imperative, <50 chars>`, with the body lines `- Tests added: yes/no` and `- Docs updated: yes/no`, then the Co-Authored-By trailer. Use `git commit -F <scratchpad file>`.
- `npm run lint` must not exceed the develop baseline of **5 errors**. `npm run test` must pass.
- Error mapping: a 404 means the run or sample was not found (or the result is not a primary timepoint). A 422 means validation failed. Show the server `detail` in the modal. `apiClient`'s interceptor already copies `detail` into `err.message`.

## Review Focus

1. **Start date with or without an offset.** `segment.date` may arrive as a naive `"2026-10-23T00:00:00"`, an aware `"2026-10-23T04:00:00Z"`, or a non-midnight `"2026-10-23T14:04:00"`. Each must prefill day 11 for a 2026-11-03 sample, and a same-day sample must give day 0. Pinned in Task 1.
2. **Phantom edits from psi/MPa rounding.** Opening an edit and saving without touching anything must send no request. Pinned in Task 1 (`buildPatchBody` returns `{}`) and Task 2 (no `updateSample` call).
3. **Clearing a required field in edit.** An emptied flow or sample date must show "Required" and send nothing. An emptied optional field must send `null`. Pinned in Tasks 1 and 2.
4. **Garbage numeric input.** "abc", "1,5" or a negative volume must produce a field error and no request. Server constraints mirrored: tube `> 0`; volumes, H₂ and gas pressure `>= 0`; flow `>= 0`. Pinned in Task 1.
5. **Legacy and partial rows.** NULL cumulative time, NULL `sampling_volume_mL` and NULL pore volumes must render "—", never `0` or `NaN`, and the server's row order must be kept. Pinned in Task 4.

---

### Task 1: API client, units, field map

**Files:**
- Create: `frontend/src/utils/units.ts`
- Modify: `frontend/src/pages/ExperimentDetail/AddResultsModal.tsx:8` (delete the local const, import it from `@/utils/units`)
- Modify: `frontend/src/utils/labDate.ts` (add two functions)
- Create: `frontend/src/api/coreFloods.ts`
- Create: `frontend/src/pages/CoreFloods/fields.ts`
- Test: `frontend/src/pages/CoreFloods/__tests__/fields.test.ts`

**Interfaces:**
- Produces, in `units.ts`: `export const PSI_TO_MPA = 0.00689476`.
- Produces, in `labDate.ts`:
  - `labDateOf(value: string): string`. Returns the lab-local `YYYY-MM-DD`. A value with no `Z` or `±hh:mm` offset is already lab wall clock, so return its first 10 characters. Otherwise format the instant in `LAB_TZ` (same `Intl.DateTimeFormat('en-CA', …)` call as `labTodayISO`).
  - `labCalendarDays(start: string, sampleYmd: string): number`. Computes `(Date.UTC(sample y,m,d) − Date.UTC(labDateOf(start) y,m,d)) / 86_400_000`. That is an exact integer, with no DST hour.
- Produces, in `coreFloods.ts` (types copied field for field from `backend/api/schemas/core_floods.py`, with datetimes typed `string` and Optionals typed `T | null`):
  - Types: `CoreFloodWarningCode`, `CoreFloodWarning`, `CoreFloodSegment`, `CoreFloodSample`, `CoreFloodRun`, `CoreFloodRunListItem`.
  - `CoreFloodSampleCreate`: `measurement_date: string`, `flow_rate_mL_min: number`, `time_post_reaction_days?: number`, plus the optional shared fields as `?: number | string | null`.
  - `CoreFloodSampleUpdate = Partial<Omit<CoreFloodSampleCreate, 'time_post_reaction_days'>>`.
  - `coreFloodsApi.list(params: { scope: 'active' | 'all'; q?: string }): Promise<CoreFloodRunListItem[]>` (GET `/core-floods`).
  - `coreFloodsApi.get(baseId: string): Promise<CoreFloodRun>` (GET `/core-floods/${encodeURIComponent(baseId)}`).
  - `coreFloodsApi.createSample(experimentId: string, body: CoreFloodSampleCreate): Promise<CoreFloodSample>` (POST `/core-floods/${enc}/samples`).
  - `coreFloodsApi.updateSample(resultId: number, body: CoreFloodSampleUpdate): Promise<CoreFloodSample>` (PATCH `/core-floods/samples/${resultId}`).
  - All four unwrap `.then((r) => r.data)`, the same as `experimentsApi`.
- Produces, in `fields.ts`:
  - `type SampleFieldKey`, the 14 API keys in spec-table order: `measurement_date, time_post_reaction_days, gc_run_date, sample_tube_number, flow_rate_mL_min, nitrogen_flow_rate_mL_min, inlet_pressure_psi, outlet_pressure_psi, sampling_volume_mL, h2_concentration, gas_sampling_volume_ml, gas_sampling_pressure_MPa, final_ph, final_conductivity_mS_cm`.
  - `interface SampleFieldDef { key: SampleFieldKey; label: string; unit?: string; kind: 'date' | 'number' | 'integer'; required?: boolean; min?: number; minExclusive?: boolean; help?: string; toWire(s: string): string | number; fromWire(v: string | number | null | undefined): string }`.
  - `SAMPLE_FIELDS: readonly SampleFieldDef[]` and `FIELD_BY_KEY: Record<SampleFieldKey, SampleFieldDef>`. Labels are copied verbatim from the spec table ("Sample date", "Day", "GC run date", "Tube #", "Flow rate", "N₂ flow", "Inlet pressure", "Outlet pressure", "Liquid sample volume", "H₂", "Gas volume", "Gas pressure", "pH", "Conductivity"), with the units in `unit`. Flow `help` = `"Rate since the previous sample. Enter 0 for a hold."`. Gas pressure has unit `psi`: `toWire` multiplies by `PSI_TO_MPA`, and `fromWire` divides and rounds to 2 decimals (`parseFloat(x.toFixed(2)).toString()`). Dates: `fromWire` = `labDateOf`, `toWire` = identity.
  - `type SampleForm = Record<SampleFieldKey, string>`. `emptyForm(): SampleForm`. `formFromSample(s: CoreFloodSample): SampleForm`, where `measurement_date` comes from `s.sample_date` and the day from `s.time_post_reaction_days`.
  - `prefillFromPrevious(form: SampleForm, prev: CoreFloodSample | undefined): SampleForm`. Copies flow, N₂, inlet and outlet from the previous sample.
  - `withSampleDate(form: SampleForm, date: string, opts: { segmentStart: string | null; gcEdited: boolean; dayEdited: boolean }): SampleForm`. Sets `measurement_date`. Unless `gcEdited`, it sets `gc_run_date = date`. Unless `dayEdited`, it sets the day: `String(labCalendarDays(start, date))` when there's a start and a valid date, otherwise `''`.
  - `validateForm(form: SampleForm): Partial<Record<SampleFieldKey, string>>`. Messages: `'Required'`, `'Must be a number'`, `'Must be a whole number'`, `'Must be ≥ 0'`, `'Must be > 0'`. Numbers must match `/^-?\d+(\.\d+)?$/` after trim, so `"1,5"` and `"abc"` fail.
  - `buildCreateBody(form: SampleForm): CoreFloodSampleCreate`. Omits blank optional fields.
  - `buildPatchBody(initial: SampleForm, form: SampleForm): CoreFloodSampleUpdate`. Only keys whose trimmed string changed. Never `time_post_reaction_days`. Blank becomes `null`.
  - `fmt(v: number | null | undefined, digits = 3): string`. Returns `'—'` for null, undefined or non-finite, otherwise `parseFloat(v.toFixed(digits)).toString()`.

- [ ] **Step 1: Write the failing tests** in `fields.test.ts`:
  - `'145 psi is about 1.0 MPa on the wire'`: `expect(FIELD_BY_KEY.gas_sampling_pressure_MPa.toWire('145')).toBeCloseTo(0.99974, 4)` and `buildCreateBody({...form, gas_sampling_pressure_MPa: '145'}).gas_sampling_pressure_MPa` is the same value.
  - `'GC date follows the sample date until edited'`: `withSampleDate(emptyForm(), '2026-11-03', {segmentStart: null, gcEdited: false, dayEdited: false}).gc_run_date === '2026-11-03'`. With `gcEdited: true` and an existing `gc_run_date: '2026-11-04'`, it stays `'2026-11-04'`.
  - `'Day is prefilled from the segment start in lab calendar days'`: for each start in `['2026-10-23T00:00:00', '2026-10-23T04:00:00Z', '2026-10-23T14:04:00']` with sample `'2026-11-03'`, the day is `'11'`. Start `'2026-11-03T14:04:00'` with the same date gives `'0'`. `dayEdited: true` keeps the existing value.
  - `'labDateOf reads an aware instant in lab time'`: `labDateOf('2026-11-04T03:00:00Z') === '2026-11-03'`.
  - `'an untouched edit builds an empty patch'`: for `formFromSample(sample)` with `gas_sampling_pressure_MPa: 0.99974`, `buildPatchBody(f, f)` is `{}`.
  - `'a pH-only edit patches only final_ph'`: `buildPatchBody(f, {...f, final_ph: '7.4'})` equals `{ final_ph: 7.4 }`.
  - `'clearing an optional field sends null'`: clearing `final_ph` gives `{ final_ph: null }`.
  - `'validation'`: blank flow or sample date → `'Required'`; `'1,5'` → `'Must be a number'`; tube `'0'` → `'Must be > 0'`; tube `'2.5'` → `'Must be a whole number'`; volume `'-1'` → `'Must be ≥ 0'`; flow `'0'` is valid.
  - `'fmt renders missing values as a dash'`: `fmt(null) === '—'`, `fmt(NaN) === '—'`, `fmt(0) === '0'`.

- [ ] **Step 2: Run to verify they fail.** `cd frontend && npx vitest run src/pages/CoreFloods/__tests__/fields.test.ts`. Expected: FAIL, module not found.

- [ ] **Step 3: Implement** `units.ts`, the `labDate.ts` additions, `coreFloods.ts` and `fields.ts` per the Interfaces above. Then update `AddResultsModal.tsx` to import `PSI_TO_MPA`.

- [ ] **Step 4: Run to verify.** The same command passes. Then `npx vitest run src/pages/ExperimentDetail` passes and `npx tsc --noEmit` is clean.

- [ ] **Step 5: Commit** `[#134] Add core flood client and field map`.

---

### Task 2: Sample modal (add and edit)

**Files:**
- Create: `frontend/src/pages/CoreFloods/useCoreFloodWrites.ts`
- Create: `frontend/src/pages/CoreFloods/CoreFloodSampleModal.tsx`
- Test: `frontend/src/pages/CoreFloods/__tests__/CoreFloodSampleModal.test.tsx`

**Interfaces:**
- Consumes: everything from Task 1.
- Produces:
  - `invalidateCoreFloodWrites(qc: QueryClient, baseId: string, segmentIds: string[]): Promise<void>`. Invalidates the six keys in Global Constraints, once per segment ID for the per-experiment keys.
  - `CoreFloodSampleModal(props: { open: boolean; onClose: () => void; baseId: string; segments: CoreFloodSegment[]; samples: CoreFloodSample[]; editing?: CoreFloodSample })`.

**Behavior:**
- **Add mode** (no `editing`): a "Segment" `Select` over all segments, labeled with their `experiment_id` and with variants suffixed " (side)". It defaults to the single ONGOING segment. With zero or several ONGOING segments it starts empty, is required, and shows the error "Choose a segment". The form starts as `prefillFromPrevious(emptyForm(), last non-variant sample in server order)`, with the sample date set to `labTodayISO()` through `withSampleDate`. Changing the segment recomputes the day unless the day has been edited. Submitting runs `validateForm`, then one `coreFloodsApi.createSample(segment.experiment_id, buildCreateBody(form))`.
- **Edit mode**: the title is "Edit sample — <experiment_id>". The segment is fixed text. The Day input is disabled (read-only) with the help text "Day can't be edited here". Submitting with an empty `buildPatchBody` closes the modal with no request. Otherwise it sends one `updateSample(editing.result_id, body)`.
- Each input is labeled `"<label> (<unit>)"` so `getByLabelText` can find it, and shows its field error beneath. On a 404 or 422, show `err.message` in an inline error block inside the modal; it does not close. On success: `invalidateCoreFloodWrites`, a success toast, close.

- [ ] **Step 1: Write the failing tests.** Mock `@/api/coreFloods`. Fixture: one ONGOING segment `CF_020-3` with `date: '2026-10-23T00:00:00'` and a previous sample with `flow_rate_mL_min: 0.5, inlet_pressure_psi: 1500`. Tests:
  - `'prefills flow from the previous sample and requires it'`: the flow input value is `'0.5'`. Clear it and submit: "Required" shows and `createSample` is not called.
  - `'submitting runs one createSample call'`: set the sample date to `2026-11-03` and submit. `createSample` is called once with `('CF_020-3', expect.objectContaining({ measurement_date: '2026-11-03', time_post_reaction_days: 11, flow_rate_mL_min: 0.5 }))`, and every key of the body is a member of the Task 1 `SampleFieldKey` list.
  - `'an edit that changes only pH sends {final_ph}'`: in edit mode, change pH to `7.4` and submit. `updateSample` is called with `(sample.result_id, { final_ph: 7.4 })` and the Day input is disabled.
  - `'an untouched edit sends nothing'`: submit without changes. `updateSample` is not called.
  - `'several ONGOING segments make the researcher choose'`: with two ONGOING segments, submitting shows "Choose a segment" and makes no call.
  - `'a 422 shows the server detail in the modal'`: `createSample` rejects with `Object.assign(new Error('sample dated before the start'), { response: { status: 422 } })`. That text appears and the modal stays open.

- [ ] **Step 2: Run to verify they fail.** `npx vitest run src/pages/CoreFloods/__tests__/CoreFloodSampleModal.test.tsx`. Expected: FAIL.

- [ ] **Step 3: Implement** `useCoreFloodWrites.ts` and `CoreFloodSampleModal.tsx`. Use `Modal size="lg"`, `Input` and `Select` from `@/components/ui`, and a two-column grid that collapses to one column below `sm`. Keep `gcEdited`/`dayEdited` as `useState` flags, set when the user types in those inputs. Form state is only reset when `open` flips to true, through a `key` on the modal body rather than an effect that clobbers input.

- [ ] **Step 4: Run to verify.** The same command passes.

- [ ] **Step 5: Commit** `[#134] Add core flood sample modal`.

---

### Task 3: Navigation and run list

**Files:**
- Modify: `frontend/src/layouts/AppLayout.tsx` (a nav item after Experiments: `{ path: '/core-floods', label: 'Core Floods', icon: <16×16 stroke svg, a cylinder or core> }`)
- Modify: `frontend/src/App.tsx` (routes `/core-floods` → `CoreFloodListPage` and `/core-floods/:baseId` → `CoreFloodRunPage`, after the `/experiments/:id` route)
- Create: `frontend/src/pages/CoreFloods/CoreFloodListPage.tsx`
- Create: `frontend/src/pages/CoreFloods/CoreFloodRunPage.tsx` (a placeholder export only, filled in by Task 4, so the route compiles)
- Create: `frontend/src/pages/CoreFloods/index.ts` (re-exports both pages)
- Test: `frontend/src/pages/CoreFloods/__tests__/CoreFloodListPage.test.tsx`

**Interfaces:**
- Consumes: `coreFloodsApi.list`, `fmt`, `labDateOf`.
- Produces: `CoreFloodListPage()` and `CoreFloodRunPage()` (no props, `baseId` from `useParams`).

**Behavior:** the scope is held in `useSearchParams` (`?scope=all`), with Active as the default. The search input is debounced 250 ms. The query key is `['core-floods', scope, q]`. Columns: Run (base ID, linking to `/core-floods/${encodeURIComponent(base_id)}`), Rig, Segments, Samples, Last sample (lab date), Cum. H₂ (g/t) (`fmt`), and Warnings (a `Badge variant="warning"` with `warning_count` when > 0, otherwise "—"). An empty state reads "No active core floods" or "No core floods match". The table wraps in `overflow-x-auto`.

- [ ] **Step 1: Write the failing tests:**
  - `'defaults to Active and switches to All'`: on first render `list` is called with exactly `{ scope: 'active' }` (`q` is omitted when the search is blank). Click "All", and the next call has `scope: 'all'`.
  - `'renders a warnings badge and links runs'`: an item with `warning_count: 2` shows "2", and the Run link `href` is `/core-floods/CF_027`.
  - In `src/layouts/__tests__/AppLayout.badge.test.tsx`, or a new `AppLayout.nav.test.tsx`: `'sidebar shows Core Floods'`.

- [ ] **Step 2: Run to verify they fail.** `npx vitest run src/pages/CoreFloods src/layouts`.

- [ ] **Step 3: Implement** the nav item, routes, list page and placeholder.

- [ ] **Step 4: Run to verify.** The same command passes, and the existing `AppLayout` tests still pass.

- [ ] **Step 5: Commit** `[#134] Add Core Floods nav and run list`.

---

### Task 4: Run page — header, segments, samples

**Files:**
- Modify: `frontend/src/pages/CoreFloods/CoreFloodRunPage.tsx`
- Create: `frontend/src/pages/CoreFloods/SamplesTable.tsx`
- Test: `frontend/src/pages/CoreFloods/__tests__/CoreFloodRunPage.test.tsx`

**Interfaces:**
- Consumes: `coreFloodsApi.get`, `CoreFloodSampleModal`, `fmt`, `labDateOf`.
- Produces: `SamplesTable(props: { samples: CoreFloodSample[]; variant: boolean; onEdit: (s: CoreFloodSample) => void })`. Task 5 adds the segment-row edits into the segments table this task renders, as `SegmentsTable(props: { baseId: string; segments: CoreFloodSegment[] })` in `SegmentsTable.tsx`. Create that file here showing read-only cells: ID (linking to `/experiments/:id`), `StatusBadge`, description text, and pore volume (`fmt`, with the unit mL).

**Behavior:**
- The query is `['core-flood', baseId]`. A 404 shows "No core flood run <baseId>" with a link back to `/core-floods`.
- **Header:** run ID; rig (the last segment with a `reactor_slot`); ONGOING segment(s), comma-joined, or "None"; cumulative H₂ g/t and pore volumes to date. Both come from the **last non-variant sample in server order**, shown with `fmt` and never computed.
- **Samples table** (non-variant rows, in server order): Sample date, Day (`cumulative_time_post_reaction_days`), Segment, Tube #, Flow (mL/min, with `Badge` "HOLD" when `flow_rate_mL_min === 0`), Liquid vol (mL), H₂ (ppm), H₂ (µmol), H₂ (g/t), Cum. H₂ (g/t), g/t/day, Pore volumes (`cumulative_pore_volumes`), pH, Cond. (mS/cm). Every number goes through `fmt`.
- **"Side samples (blanks, bypass)"** section (variant rows), shown only when there are any. Same columns minus Cum. H₂, g/t/day and Pore volumes.
- Clicking a row opens the modal in edit mode. "+ Add sample" (primary button in the samples card header) opens it in add mode.

- [ ] **Step 1: Write the failing tests.** Mock `coreFloodsApi`. The fixture run has two segments and one variant segment `CF_020-5_Bypass1`, with a variant sample whose derived columns are null, and one sample with `flow_rate_mL_min: 0`. A legacy sample has `cumulative_time_post_reaction_days: null` and `sampling_volume_mL: null`. Tests:
  - `'variants render in Side samples without cumulative values'`: within the "Side samples (blanks, bypass)" region, the variant's experiment ID is present and the column headers "Cum. H₂ (g/t)" and "Pore volumes" are absent.
  - `'a zero flow shows a HOLD badge'`.
  - `'legacy nulls render as dashes, in server order'`: the legacy row shows "—" in Day and Liquid vol, and the row order matches the fixture.
  - `'header shows the server cumulative values'`: the header shows the last non-variant sample's `cumulative_h2_grams_per_ton` exactly as `fmt` gives it.

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement.** Wrap the tables in `overflow-x-auto`.

- [ ] **Step 4: Run to verify they pass.**

- [ ] **Step 5: Commit** `[#134] Add core flood run page tables`.

---

### Task 5: Segment edits and cleanup panel

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/DescriptionEditor.tsx`. Add optional props `onSaved?: () => void` (called after the existing invalidations) and `initialEditing?: boolean` (seeds `editing` and `draft`). Behavior is unchanged when both are omitted. `DescriptionEdit.test.tsx` must still pass.
- Modify: `frontend/src/pages/CoreFloods/SegmentsTable.tsx`
- Create: `frontend/src/pages/CoreFloods/CleanupPanel.tsx`
- Modify: `frontend/src/pages/CoreFloods/CoreFloodRunPage.tsx` (render `CleanupPanel` above the segments)
- Test: extend `CoreFloodRunPage.test.tsx`

**Interfaces:**
- Consumes: `experimentsApi.patchStatus(id, status)`, `experimentsApi.patch(id, { experiment_id })` (returns `ExperimentDetail` with `base_experiment_id`), `experimentsApi.get(id)` (its `notes` hold the `note_type === 'description'` note), `conditionsApi.patch(conditionsId, { pore_volume_mL })`, `invalidateCoreFloodWrites`.
- Produces: `CleanupPanel(props: { baseId: string; run: CoreFloodRun; onEditSample: (s: CoreFloodSample) => void; onRename: (experimentId: string) => void; onEditDescription: (experimentId: string) => void })`. `SegmentsTable` takes `renaming` / `describing` (experiment IDs or null) and setters from the page, so the panel's actions can open them.

**Segment row behavior:**
- **Status:** a `Select` over `ExperimentStatus`, which calls `patchStatus`. On error (for example the 409 occupancy check), `toastError('Status not changed', err.message)` and the select shows the old value.
- **Description:** the text, or "Add description". The first click sets `describing`. That enables `useQuery(['experiment', id], experimentsApi.get)`, and once it loads, renders `<DescriptionEditor experimentId note={descriptionNote} initialEditing onSaved={() => invalidateCoreFloodWrites(...)} />`. There's no backend change: the note ID comes from the experiment detail.
- **Rename:** an inline input with Save and Cancel that calls `patch(id, { experiment_id })`. On success, invalidate. If `updated.base_experiment_id ?? updated.experiment_id` differs from `baseId` and this was the run's only segment, `navigate('/core-floods/' + newBase, { replace: true })`. If it differs and other segments remain, stay and show a toast reading "<new id> moved to run <newBase>" with the run link text. On error, show the toast with `err.message`.
- **Pore volume:** click to edit a number (must be > 0), which calls `conditionsApi.patch(conditions_id, { pore_volume_mL })`. It's disabled with the title "No conditions row" when `conditions_id` is null.

**Cleanup panel:** shown only when `run.warnings.length > 0`. It's a `Card` titled "Cleanup", with one line per warning, each line giving the affected IDs and its fix:
- `multiple_roots`: "Several segments have no parent: <ids>. Rename the extra roots into this run's sequence." Plus a "Rename" button per ID (`onRename`).
- `multiple_ongoing`: "More than one segment is ONGOING: <ids>." Plus a status `Select` per ID, the same control and mutation as the segments table (extract a `SegmentStatusSelect` component used by both).
- `missing_pore_volume`: "No pore volume on: <ids>." Plus a number input and a "Set pore volume for all segments" button, which calls `conditionsApi.patch` once per listed segment that has a `conditions_id`, then invalidates once. It reports in the toast any listed segment skipped for having no conditions row.
- `missing_description`: "No description on: <ids>." Plus a "Describe" button per ID (`onEditDescription`).
- `sample_missing_flow_rate`: "Samples with no flow rate on: <ids>." Plus an "Edit" button for each matching non-variant sample, labeled by its lab date (`onEditSample`).

- [ ] **Step 1: Write the failing tests** (mock `@/api/experiments` and `@/api/conditions` as well; wrap in `MemoryRouter initialEntries={['/core-floods/CF_027']}` with `<Routes>` for both run paths):
  - `'a multiple_ongoing warning shows the status action'`: with the warning for `['CF_027', 'CF_027-1']`, the Cleanup card has a status select for each. Choosing COMPLETED on `CF_027-1` calls `patchStatus('CF_027-1', 'COMPLETED')`.
  - `'set pore volume for all segments patches each missing segment'`: with the warning for two segments (`conditions_id` 11 and 12), enter `42` and click. `conditionsApi.patch` is called with `(11, { pore_volume_mL: 42 })` and `(12, { pore_volume_mL: 42 })`.
  - `'renaming the only segment moves the URL to the new run'`: run `CF_020_5` with the sole segment `CF_020_5_Brine`. `patch` resolves `{ experiment_id: 'CF_020-5_Brine', base_experiment_id: 'CF_020' }`. After saving the rename, the route shows `/core-floods/CF_020` (assert on a location probe), and `get` is next called with `'CF_020'`.
  - `'renaming one of several segments refetches the run in place'`: `get` is called again with the same base ID, and the refetched segments list shows the new ID.
  - `'a rejected status change shows the server detail'`: `patchStatus` rejects with `new Error('Reactor CF01 is occupied by CF_026')`, and the toast text appears.
- Run `npx vitest run src/pages/ExperimentDetail/__tests__/DescriptionEdit.test.tsx` as well, to protect the shared editor.

- [ ] **Step 2: Run to verify the new tests fail.**

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run** `npx vitest run src/pages/CoreFloods src/pages/ExperimentDetail` and confirm it passes.

- [ ] **Step 5: Commit** `[#134] Add segment edits and cleanup panel`.

---

### Task 6: Verification, browser check, docs

**Files:**
- Modify: `docs/issues/issue-core-flood-frontend.md` (tick the acceptance boxes; use `[~]` for any that can't pass, per memory)
- Modify: `docs/working/issue-log.md` (a new entry in the house format: files changed, why, decisions, verification, browser-verification results reported separately from vitest, anything written to the dev DB, follow-ups, tests added and docs updated)
- Modify: `docs/user_guide/`, adding a short Core Floods section only if a page-level guide for experiments exists there. Check first.

- [ ] **Step 1: Automated checks.** From `frontend/`: `npm run test` (all pass), `npm run lint` (≤ 5 errors, listing any new ones), `npm run type-check` (clean). Record the counts.
- [ ] **Step 2: Dev DB.** `alembic upgrade head` against the dev DB. Confirm with `SELECT to_regclass('v_core_flood_samples')` that the view exists. Check `max(created_at)` for currency (memory: dev DB currency). Never seed an ONGOING experiment with a `reactor_number`.
- [ ] **Step 3: Servers.** Start the backend and Vite through the `run` skill. Check that `netstat -ano | findstr :8000` shows exactly one listener; kill orphan `spawn_main` workers per memory.
- [ ] **Step 4: Chrome DevTools walk-through.** Run the user's seven steps: the list (sidebar, Active default, toggle, search, badges); CF_027 (header, segments, samples, HOLD, side samples, cleanup lines); "+ Add sample", checking one POST with API keys only, the gas pressure in MPa, a date-only `measurement_date` and the right day, plus the refetch; an edit to pH only, with the body exactly `{"final_ph": …}` and the Day read-only; a cleanup action that clears its warning; a rename that updates the segments and URL; then console, screenshots of the list and run pages saved to the scratchpad, and a `resize_page` to 390 px wide. Write only to clearly marked throwaway data. Sample writes on a real run should be reverted where possible, and every write recorded for the issue log.
- [ ] **Step 5: Docs.** Update the issue doc and the issue log. Confirm the project_context sync ran (memory: the hook is bypassed for script edits).
- [ ] **Step 6: Commit** `[#134] Document run page and log verification`. Then hand off to `/complete-task`, whose PR uses `--base develop` and includes the screenshots.
