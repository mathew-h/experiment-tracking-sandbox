# Grouped experiment view: hide empty conditions and round numeric values

**Labels:** `frontend`, `bug`
**Depends on:** nothing
**Blocks:** nothing

## Problem

The shared conditions panel on the replicate group page (`/experiments/groups/{baseId}`) renders every condition field returned by the API, including the ones that are null. On a Serum group that means roughly a dozen rows of `Field Name: —` for parameters that only apply to core floods and HPHT runs: CO2 partial pressure, core height, core width, core volume, confining pressure, pore pressure, flow rate, reactor number, room temp pressure, rxn temp pressure, initial alkalinity, feedstock. They crowd out the four or five values that actually describe the run.

This is a divergence from the established pattern, not a missing feature. `ConditionsTab`'s `Row` component (`frontend/src/pages/ExperimentDetail/ConditionsTab.tsx:36`) already does the right thing:

```tsx
function Row({ label, value, unit }) {
  if (value == null || value === '') return null
  ...
}
```

The group page was written with its own `formatValue` helper that returns `'—'` for empty values instead of suppressing the row.

Second, unrelated defect on the same panel: floats render via `String(value)` with no rounding, so `total_ferrous_iron_g` displays as `0.40888731418072486`.

## Change

In `frontend/src/pages/ReplicateGroup/index.tsx`:

1. Skip shared-condition entries whose value is `null`, `undefined`, or `''`, matching `Row` semantics exactly. Do not hardcode a field blocklist. Fields stay visible when populated, so a core flood group still shows confining pressure and pore pressure.
2. Round numeric values to 3 decimal places and trim trailing zeros, so:
   - `0.40888731418072486` renders as `0.409`
   - `90` stays `90`, not `90.000`
   - `8` stays `8`
   - Integers and strings are untouched
3. Leave the divergent-fields loop alone. Those render `varies — see members table` and are meaningful by definition.
4. Leave the `Additives:` footer row alone. `—` there is informative (no additives recorded) rather than noise.

Consider extracting the numeric formatter to `frontend/src/utils/` if a shared formatting module already exists, since `ConditionsTab`'s `Row` has the same `String(value)` rounding gap and will hit it the moment `total_ferrous_iron_g` is added there.

## Files

- `frontend/src/pages/ReplicateGroup/index.tsx` (`formatValue`, and the shared conditions `.map` around line 149)
- possibly `frontend/src/utils/` for a shared number formatter

## Acceptance criteria

- [ ] On a Serum group with no core/pressure data, the conditions panel shows only populated fields
- [ ] On a core flood group, confining pressure and pore pressure still render
- [ ] `Total Ferrous Iron G` renders as `0.409`
- [ ] `Temperature C: 90` and `Initial Ph: 8` render without trailing zeros
- [ ] Divergent fields still render with the `varies` note even though their shared value is absent
- [ ] Boolean and string conditions (e.g. `Experiment Type: Serum`) unchanged

## Tests

`frontend/src/pages/ReplicateGroup/__tests__/ReplicateGroupPage.test.tsx`:

- [ ] A group whose `shared_conditions` contains null fields does not render those labels
- [ ] `total_ferrous_iron_g: 0.40888731418072486` renders as `0.409`
- [ ] An integer-valued condition renders without a decimal point
- [ ] A divergent field still renders its label and the `varies` text

## Out of scope

- The individual experiment Conditions tab, which already suppresses empty rows correctly
- Changing what the API returns in `shared_conditions`. This is display-layer only.
- Reordering or grouping the condition fields
