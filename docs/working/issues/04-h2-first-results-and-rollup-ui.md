# H2-first results and rollup views: remove ammonium metrics from the frontend

**Labels:** `frontend`
**Depends on:** `Expose H2 concentration (ppm) through the results API and the rollup view` (issue 03)
**Blocks:** nothing

## Problem

The team's current focus is hydrogen. Both results surfaces still lead with ammonium, which means the H2 numbers people actually read are buried mid-table behind three NH4 columns.

This is a display change only. All ammonium fields stay in the schema, in the calculation engine, in the SQL views, and in the Power BI datasets. Nothing is deleted from the backend.

## Change

### 1. Per-result table, `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`

Columns become, left to right:

| ★ | Time (d) | Sample Date | H2 (ppm) | H2 (µmol) | H2 (g/t) | Fe²⁺ H2 (%) | pH | Cond. (mS/cm) | ICP / XRD / MOD | chevron |

Removed: `Gross NH₄ (mM)`, `NH₄ (g/t)`, `Fe²⁺ NH₃ (%)`.
Added: `H2 (ppm)` from the new `r.h2_concentration` field (issue 03), positioned first in the H2 block since it is the measured value and the rest are derived from it.

The `GRID` constant on line 24 is a hardcoded 13-track `grid-cols-[...]` template. It must be rewritten to match the new column count (11 tracks) or the header and body rows will desynchronize. Both the header row and the data row use the same constant, so they stay aligned automatically once it is correct.

### 2. Remove the Background NH4 control

Delete the entire background-ammonium affordance from the results action bar:

- the `Background NH₄: {value} mM` button and the inline number input
- `bgInput`, `bgValue` state and `storedBgValue` derivation
- the `bgMutation` `useMutation` block and its `queryClient.invalidateQueries` calls
- the now-unused `DEFAULT_BACKGROUND_NH4` constant

Leave `experimentsApi.setBackgroundAmmonium` in `frontend/src/api/experiments.ts` and the backend endpoint in place. Only the UI entry point goes away.

**Known consequence, accepted:** after this change there is no UI path to set background ammonium. It remains settable through bulk upload and the API. Revisit if the team returns to NH3 work.

### 3. Expanded drawer, `ExpandedRow` in the same file

Remove `Gross NH₄` and `Net NH₄ Yield` from the scalar field list. Keep `Final pH`, `Conductivity`, `H₂ (ppm)`, `H₂ (µmol)`, `H₂ Yield`, `DO`, `Fe(II)`.

Flag and drawer behavior is otherwise unchanged: ICP, XRD, and MOD continue to render as badges on the collapsed row and their detail continues to appear when the row is expanded. XRD remains badge-only (no phase detail in the drawer) as it is today.

### 4. Rollup, `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx`

`METRICS` array becomes, in this order:

| key | label | mean | sd | individual |
|---|---|---|---|---|
| `h2_ppm` | `H₂ (ppm)` | `mean_h2_ppm` | `sd_h2_ppm` | `r.h2_concentration` |
| `h2_umol` | `H₂ (µmol)` | `mean_h2_micromoles` | `sd_h2_micromoles` | `r.h2_micromoles` |
| `h2_gpt` | `H₂ (g/t)` | `mean_h2_grams_per_ton` | `sd_h2_grams_per_ton` | `r.h2_grams_per_ton_yield` |
| `fe_h2` | `Fe²⁺ → H₂ (%)` | `mean_fe_yield_h2_pct` | `sd_fe_yield_h2_pct` | `r.ferrous_iron_yield_h2_pct` |
| `ph` | `pH` | `mean_final_ph` | `null` | `r.final_ph` |

Removed entries: `gross_nh4`, `net_nh4`, `nh4_gpt`, `fe_nh3`.

Change the default `metricKey` from `'h2_umol'` to `'h2_ppm'`.

Rollup table columns become: `Time (d)`, `n`, `H₂ (ppm)`, `H₂ (µmol)`, `H₂ (g/t)`, `Fe²⁺ → H₂ (%)`, `pH`. Each mean cell keeps the existing `mean ± sd` rendering and the existing `—` fallback when the mean is null. Use 1 decimal place for ppm, consistent with µmol and g/t.

The individual-replicate overlay, outlier styling, drill-in links, and error bars are unchanged.

## Files

- `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`
- `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx`

## Acceptance criteria

- [ ] Per-result table shows no NH4 column and no Fe²⁺ → NH₃ column
- [ ] Per-result table header and data rows are aligned (grid track count matches column count)
- [ ] H2 (ppm) appears in the per-result table and reads from the single existing `/results` request, not a per-row `getScalar` call
- [ ] The Background NH₄ button is gone from the action bar
- [ ] Expanded drawer shows no NH4 values
- [ ] ICP, XRD, and MOD badges still render on collapsed rows, and ICP and MOD detail still render when expanded
- [ ] Rollup metric dropdown lists exactly five options and defaults to H₂ (ppm)
- [ ] Rollup table shows no NH4 column
- [ ] Selecting H₂ (ppm) plots mean ± sd with the individual replicate overlay
- [ ] `v_results_scalar_rollup` still computes every ammonium aggregate (verify by querying the view directly, unchanged)

## Tests

- [ ] `frontend/src/pages/ExperimentDetail/__tests__/ResultsTab.columns.test.tsx`: update expected headers, assert no `NH₄` text renders, assert `H₂ (ppm)` renders with a value
- [ ] `ResultsTab.columns.test.tsx`: assert the Background NH₄ button is absent
- [ ] `frontend/src/pages/ExperimentDetail/__tests__/GroupedResultsView.test.tsx`: update the metric option list, assert default selection is H₂ (ppm), assert no NH4 headers in the rollup table
- [ ] `GroupedResultsView.test.tsx`: assert `mean_h2_ppm` renders as `mean ± sd` and that a null mean renders `—`

## Docs

- [ ] `docs/user_guide/`: note that the results and rollup views are H2-focused and that ammonium data remains in the database and Power BI datasets

## Out of scope

**Data entry paths keep their ammonium fields.** `AddResultsModal.tsx` and `BulkUploads.tsx` both reference NH4 and are deliberately untouched. Removing NH4 from the entry form would make the field unrecordable, which is not the intent. If you want entry simplified too, that is a separate issue.

Also out of scope:

- Any backend, schema, view, or calculation change beyond what issue 03 delivers
- Adding XRD phase detail to the expanded drawer
- Changing outlier handling, replicate grouping, or timepoint bucketing
