# Core Floods sidebar page: run list and run record with sample entry and cleanup

**Type:** feat
**Area:** `frontend/src/pages/CoreFloods/`
**Priority:** high
**Related:** issue-core-flood-run-page.md (parent), depends on issue-core-flood-api.md

---

## Problem

No page shows a core flood run end to end. Samples are entered through the generic Add Results modal, which has no flow, tube or gas-volume fields tuned to core flood work, one segment at a time.

## Impact

Researchers fall back to the tracker workbook, cleanup across segments happens one experiment page at a time, and holds can't be recorded.

## Fix

**Navigation.**

- Add a "Core Floods" item after Experiments in `frontend/src/layouts/AppLayout.tsx` (nav items start at line 14).
- Add routes `/core-floods` and `/core-floods/:baseId` in `frontend/src/App.tsx` beside line 37.

**API client.** `frontend/src/api/coreFloods.ts` provides types and `coreFloodsApi.list / get / createSample / updateSample`.

**Field aliases.** `frontend/src/pages/CoreFloods/fields.ts` is one map from UI field to API field, label, unit and converter. Forms and tables read from it.

| UI label | API field | Behavior |
|---|---|---|
| Sample date | `measurement_date` | required |
| Day | `time_post_reaction_days` | prefilled from sample date minus segment start; editable |
| GC run date | `gc_run_date` | follows sample date until edited |
| Tube # | `sample_tube_number` | integer |
| Flow rate (mL/min) | `flow_rate_mL_min` | required; prefilled from previous sample; help text "Rate since the previous sample. Enter 0 for a hold." |
| N₂ flow (mL/min), Inlet pressure (psi), Outlet pressure (psi) | `nitrogen_flow_rate_mL_min`, `inlet_pressure_psi`, `outlet_pressure_psi` | optional; prefilled from previous sample |
| Liquid sample volume (mL) | `sampling_volume_mL` | |
| H₂ (ppm), Gas volume (mL) | `h2_concentration`, `gas_sampling_volume_ml` | |
| Gas pressure (psi) | `gas_sampling_pressure_MPa` | psi in the UI, MPa on the wire |
| pH, Conductivity (mS/cm) | `final_ph`, `final_conductivity_mS_cm` | |

Move `PSI_TO_MPA` from `frontend/src/pages/ExperimentDetail/AddResultsModal.tsx:8` into `frontend/src/utils/units.ts` and import it from both places. When editing, send only the fields whose input string changed, so psi/MPa rounding can't create phantom edits.

**List page** (`CoreFloodListPage.tsx`):

- An Active / All toggle and an ID search.
- Columns: Run, Rig, Segments, Samples, Last sample, Cum. H₂ (g/t), and a Warnings badge.

**Run page** (`CoreFloodRunPage.tsx`):

- **Header.** Run ID, rig, the ONGOING segment, cumulative H₂ g/t, and pore volumes to date.
- **Segments.** One row per segment:
  - experiment ID, linking to `/experiments/:id`
  - status, editable through `experimentsApi.patchStatus`
  - inline description, reusing `DescriptionEditor` (`frontend/src/pages/ExperimentDetail/DescriptionEditor.tsx:17`)
  - a rename action through `experimentsApi.patch` with `experiment_id`; after a rename, refetch the run, since lineage may change
  - pore volume
- **Samples table.** In order: sample date, cumulative day, segment, Tube #, flow (with a HOLD badge at 0), liquid volume, H₂ ppm, H₂ µmol, H₂ g/t, cumulative H₂ g/t, g/t/day, pore volumes, pH, conductivity. Variant rows go in a separate "Side samples (blanks, bypass)" section with no cumulative columns. Clicking a row edits it.
- **"+ Add sample".** Targets the single ONGOING segment. With zero or several, the researcher picks one.
- **Cleanup panel.** One line per API warning, each with its fix. `missing_pore_volume` gets "Set pore volume for all segments", which calls `conditionsApi.patch` on each segment missing it.

**Cache invalidation.** After every write, invalidate `['core-floods']`, `['core-flood', baseId]`, `['experiment', segmentId]`, `['experiment-results', segmentId]`, `['experiments']` and `['dashboard']`.

Use design-system tokens only, with no hex values.

## Acceptance criteria

- [ ] The sidebar shows "Core Floods". The list defaults to Active and switches to All
- [ ] `__tests__/fields.test.ts`: 145 psi becomes about 1.0 MPa on the wire. The GC date follows the sample date until edited. Day is prefilled from the segment start
- [ ] `__tests__/CoreFloodSampleModal.test.tsx` checks that:
  - flow is required and prefilled from the previous sample
  - an edit that changes only pH sends `{final_ph}`
  - submitting runs one `createSample` call
- [ ] `__tests__/CoreFloodRunPage.test.tsx`: variants render in Side samples, without cumulative values. A `multiple_ongoing` warning shows the status action
- [ ] After a rename on the run page, the segments list and URL reflect the new lineage
- [ ] `cd frontend && npm run test` passes, and `npm run lint` errors don't exceed the current baseline

## Notes

Experiment Detail's Results tab is unchanged. A Core Flood experiment's header can link to its run page as a small follow-up.
