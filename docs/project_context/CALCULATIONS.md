# Calculations Reference

This document is the source of truth for all derived-field formulas in the experiment tracking system.

Formulas live in `backend/services/calculations/`. The Documentation Agent keeps this file
in sync with the implementation after every change.

---

## How the Calculation Engine Works

After any database write, M3 API endpoints call:

```python
from backend.services.calculations import registry
registry.recalculate(instance, session)
```

The registry dispatches to the correct formula function based on `type(instance)`.
Each formula module registers itself with `@registry.register(ModelClass)`.

To add a new formula:
1. Create or open the relevant `*_calcs.py` module in `backend/services/calculations/`
2. Decorate your function with `@registry.register(YourModel)`
3. Import the module in `backend/services/calculations/__init__.py`
4. Update this document

---

## Conditions Calculations (`conditions_calcs.py`)

### `water_to_rock_ratio`

```
water_to_rock_ratio = water_volume_mL / rock_mass_g
```

- Set to `None` if either input is missing or `rock_mass_g ≤ 0`
- Units: mL/g (dimensionless ratio)

---

## Additive Calculations (`additive_calcs.py`)

### Unit Conversion to Grams (`mass_in_grams`)

| Input Unit | Conversion |
|------------|------------|
| g | 1× |
| mg | ÷ 1,000 |
| µg | ÷ 1,000,000 |
| kg | × 1,000 |
| mL | × 1 (assumes density 1 g/mL) |
| µL | × 0.001 |
| L | × 1,000 |
| mM | `(amount / 1000) × volume_L × MW` |
| M | `amount × volume_L × MW` |
| ppm | `amount × volume_L / 1000` (ppm = mg/L) |
| % of Rock | `(amount / 100) × rock_mass_g` |
| %, wt% | `(amount / 100) × water_volume_mL` |
| wt% of fluid | `(amount / 100) × water_volume_mL` — assumes fluid density ≈ 1 g/mL for dilute aqueous solutions |

### Moles (`moles_added`)

```
moles_added = mass_in_grams / molecular_weight_g_mol
```

Requires `Compound.molecular_weight_g_mol` to be set. `None` if MW unavailable.

### Final Concentration (`final_concentration`, `concentration_units`)

For concentration-input units (mM, M, ppm, %, wt%): mirrors the input value.
For mass inputs with known volume: `(mass_g / volume_L) × 1,000,000` → ppm.

### Catalyst Fields (`elemental_metal_mass`, `catalyst_percentage`, `catalyst_ppm`)

Requires `Compound.elemental_fraction` to be set (pre-calculated fraction of elemental metal
to compound mass, e.g., `58.69 / 237.69` for Ni in NiCl₂·6H₂O).

```
elemental_metal_mass = mass_in_grams × elemental_fraction

catalyst_percentage  = (elemental_metal_mass / rock_mass_g) × 100

catalyst_ppm         = round((elemental_metal_mass / water_volume_mL) × 1,000,000 / 10) × 10
```

`catalyst_ppm` is rounded to the nearest 10 ppm.
All three fields are `None` if `elemental_fraction` is not set on the compound.

---

## Scalar Calculations (`scalar_calcs.py`)

### Ammonium Yield (`grams_per_ton_yield`)

```
net_concentration_mM = max(0, gross_ammonium_concentration_mM − background_ammonium_concentration_mM)

ammonia_mass_g = (net_concentration_mM / 1000) × (volume_mL / 1000) × 18.04
              = mol/L × L × g/mol   [MW of NH₄⁺ = 18.04 g/mol]

grams_per_ton_yield = 1,000,000 × (ammonia_mass_g / rock_mass_g)
```

- `volume_mL`: uses `sampling_volume_mL` if provided; otherwise falls back to `water_volume_mL` from conditions
- `background_ammonium_concentration_mM` defaults to `0.2 mM` if not set
- Net concentration is clamped to `≥ 0` (negative background subtraction → 0 yield, not negative)
- Set to `None` if `rock_mass_g` is missing or `≤ 0`

### Hydrogen Amount (PV = nRT, `h2_micromoles`, `h2_mass_ug`)

```
P_atm = gas_sampling_pressure_MPa × 9.86923      [MPa → atm]
V_L   = gas_sampling_volume_ml / 1000             [mL → L]

n_total_mol = (P_atm × V_L) / (R × T_K)          [R = 0.082057 L·atm/(mol·K), T = 293.15 K = 20°C]
h2_fraction = h2_concentration_ppm / 1,000,000   [ppm → mole fraction]
h2_mol      = n_total_mol × h2_fraction

h2_micromoles = h2_mol × 1,000,000               [µmol]
h2_mass_ug    = h2_mol × 2.01588 × 1,000,000     [µg; MW H₂ = 2.01588 g/mol]
```

- Temperature fixed at 20°C (293.15 K)
- `h2_concentration` always stored in ppm (vol/vol)
- Gas volume and pressure must both be present and > 0; concentration must be present and non-negative. A concentration of exactly `0` is valid and yields `0` outputs — it is a real "no H₂ detected" reading, not a missing one.

**Where the inputs come from on a Master Results upload (issue #111):** all
three inputs are read from a single GC block. Full Loop (`FL H2 (ppm)`,
`FL Gas Volume (mL)`, `FL Gas Pressure (psi)`) takes precedence; direct
injection (`DI H2 (ppm)`, `DI gas volume (mL)`, `DI gas pressure (psi)`) is
used only when the Full Loop concentration cell is blank. The blocks are never
mixed — pairing a Full Loop concentration with a DI sampling volume would
compute micromoles for an injection that never happened. A concentration of `0`
is a real measurement and is stored as such. Volume and pressure are read **only
when a concentration resolved** (issue #114): a row with no `H2 (ppm)` in either
block stores none of the three, because the sheet's gas columns carry the
previous run's values and were never computable without a concentration anyway.

**Replicate spread is not calculated here.** Mean and standard deviation across
replicate vials come from `v_results_scalar_rollup` (`mean_h2_ppm`,
`sd_h2_ppm`, `stddev_samp`, n-1, outlier vials excluded), served by
`GET /api/experiments/groups/{base_id}/rollup`. The Dashboard sheet no longer
carries avg/SD columns — each vial supplies one reading and the view aggregates.

### Hydrogen Yield (`h2_grams_per_ton_yield`)

```
h2_mass_g = h2_mass_ug / 1,000,000

h2_grams_per_ton_yield = 1,000,000 × (h2_mass_g / rock_mass_g)
```

Set to `None` if `rock_mass_g` is missing or H2 inputs are insufficient.

### Ferrous Iron Yield — H₂ Derived (`ferrous_iron_yield_h2_pct`)

Stoichiometry: 3 mol Fe²⁺ per 1 mol H₂

```
Fe²⁺_consumed_g = (h2_micromoles × 3 / 1,000,000) × 55.845
yield_h2_pct    = (Fe²⁺_consumed_g / total_ferrous_iron_g) × 100
```

- Reads `h2_micromoles` (already computed from H₂ gas inputs — see above)
- Reads `total_ferrous_iron` from `ExperimentalConditions` via `result_entry → experiment → conditions`
- Set to `None` if `h2_micromoles` is `None` or `total_ferrous_iron` is `None` or ≤ 0

**Verification:** 1,000 µmol H₂ with 1.0 g `total_ferrous_iron` → (0.003 mol × 55.845) / 1.0 × 100 = **16.75%**

### Ferrous Iron Yield — NH₃ Derived (`ferrous_iron_yield_nh3_pct`)

Stoichiometry: 9 mol Fe²⁺ per 2 mol NH₃ (ratio = 4.5)

```
net_ammonium_mM  = max(0, gross_ammonium_concentration_mM − background_ammonium_concentration_mM)
                   [background defaults to 0.2 mM if not provided]
total_NH3_mol    = (net_ammonium_mM / 1000) × (solution_volume_mL / 1000)
Fe²⁺_consumed_g  = total_NH3_mol × 4.5 × 55.845
yield_nh3_pct    = (Fe²⁺_consumed_g / total_ferrous_iron_g) × 100
```

- `solution_volume_mL`: prefers `sampling_volume_mL`; falls back to `water_volume_mL` from conditions
  (identical fallback chain as `grams_per_ton_yield`)
- Set to `None` if `gross_ammonium_concentration_mM` is `None`; or if `solution_volume_mL` or `total_ferrous_iron` is `None` or ≤ 0
- Net concentration clamped to ≥ 0

**Verification:** 10 mM gross (0.2 mM background), 100 mL, 1.0 g `total_ferrous_iron` →
0.00098 mol × 4.5 × 55.845 / 1.0 × 100 = **24.61%**

> Note: legacy `ferrous_iron_yield` column (manual-entry, deprecated) remains in the schema for
> backward data compatibility but is excluded from new calculations and UI forms.

---

## Core flood run values (`v_core_flood_samples`)

A core flood run is one `base_experiment_id` split across sequential segment experiments (`CF_020`, `CF_020-2`, ...). Values that depend on more than one sample are computed in the SQL view `v_core_flood_samples` (`database/event_listeners.py`), one row per primary timepoint of a Core Flood experiment. **These are view columns, not calculation-engine fields:** nothing is registered in the calculation registry, nothing is stored, and per-sample H2 (`h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`) is still computed by `recalculate_scalar` as above. The app and Power BI read the same view, so they cannot disagree.

**Window.** Per `run_base_id` (= `base_experiment_id`) and `is_variant`, ordered by `cumulative_time_post_reaction_days` then `result_id`, from the first sample to the current row.

| Column | Definition |
|---|---|
| `interval_days` | `cumulative_time − COALESCE(LAG(cumulative_time), 0)` |
| `cumulative_liquid_volume_mL` | `SUM(COALESCE(sampling_volume_mL, 0))` over the window |
| `cumulative_pore_volumes` | `cumulative_liquid_volume_mL / NULLIF(pore_volume_mL, 0)` |
| `cumulative_h2_grams_per_ton` | `SUM(COALESCE(h2_grams_per_ton_yield, 0))` over the window |
| `h2_grams_per_ton_per_day` | `h2_grams_per_ton_yield / NULLIF(interval_days, 0)` |
| `is_hold_interval` | `flow_rate_mL_min = 0` |

**Flow rule.** `flow_rate_mL_min` is the rate over the interval *ending* at that sample; `0` means a hold. Flow only ever changes at a sample, so a hold or a flow change needs no new experiment.

**Volume basis.** Volume is the measured liquid sample volume (`sampling_volume_mL`), not flow × time. Pore volumes = cumulative liquid volume / `pore_volume_mL`, the researcher-entered `experimental_conditions.pore_volume_mL` of that segment's own conditions row. A NULL liquid volume adds 0 to the running total; a NULL or 0 pore volume gives NULL pore volumes.

**H2 basis.** Each sample's H2 is only what was collected since the previous sample (confirmed by Mat, 2026-11-03). That is why per-sample H2 g/t can be summed into `cumulative_h2_grams_per_ton`, and why dividing a sample's H2 g/t by its interval days gives a rate (`h2_grams_per_ton_per_day`, compared against the 0.5 g/t/day target). If a sample's H2 were cumulative instead, both columns would be wrong.

**Variants (`is_variant`).** A `_Text` child of a segment (`CF_020-5_Bypass1`, `CF_023-3_Accumulator`) is a blank or bypass. `is_variant` is true when the experiment has a parent and its ID starts with `<parent experiment_id>_`. Variant rows keep their raw values (flow, tube, volume, H2, pH) but every derived column above is NULL, and they sit in their own window partition, so they never shift the segments' sums. Sequential segments (`-N`) are never variants.

**Edge cases.**
- Zero interval (two samples on one cumulative day, e.g. a segment boundary): `NULLIF` makes `h2_grams_per_ton_per_day` NULL, not an error.
- `CF_020_5_Brine` (underscore typo) parses to base `CF_020_5`, so it forms its own one-row run rather than a variant; renaming it on the run page fixes this.
- An orphaned variant (parent link cleared) is no longer a variant and counts as a segment.
- Assumes one `experimental_conditions` row per experiment (`uq_conditions_experiment_fk`).
- "Core Flood" is matched the way `database/reactor_slot.py::_SERIES_BY_TYPE` reads it: case- and whitespace-insensitive, and `CF` / `coreflood` count too (CF-014 is stored as `CF`).
- Two-root runs: CF_026 and CF_027 each have a bare root and a `-1` root holding their own samples. Both share one `base_experiment_id`, so the view merges them and interleaves their samples by cumulative time; an interval or rate can then be measured against the other root's sample. Cleanup is tracked in the parent issue (#131).
- Undated legacy rows: 54 of 180 Core Flood primary rows (CF-02 to CF-12, 2026-10-26 backup) have NULL cumulative time. They sort last in their run, their `interval_days` and `h2_grams_per_ton_per_day` are NULL, and the cumulative columns keep accumulating in `result_id` order, so the per-row progression is insertion order, not time. The run total on the last row is still right.

**Permeability (not computed).** Inlet/outlet pressures are recorded only when permeability is intentionally tested, at the sample's flow rate or at a separate test rate (issue #140). The presence of `permeability_flow_rate_mL_min` is what marks a sample as a permeability test and is the sole trigger for any future permeability (Darcy) computation; a sample without it is never treated as one, whatever its pressures. `flow_rate_mL_min` keeps its meaning: the rate over the interval ending at the sample, 0 meaning a hold. Nothing computes permeability yet. Pore pressure is `experimental_conditions.pore_pressure`, not a result column.

---

## Utility Functions

### `format_additives(conditions)` — `additive_calcs.py`

Returns a newline-separated display string of all chemical additives.

```
"5 g Mg(OH)₂\n1 g Magnetite"
```

Replaces the former `ExperimentalConditions.formatted_additives` hybrid_property.
The SQL view `v_experiment_additives_summary` handles the Power BI reporting case.

---

## Characterization-Derived Fields (`elemental_composition_service.py`, `conditions_calcs.py`)

These fields are computed from pre-experiment rock characterization data stored in
`ExternalAnalysis → ElementalAnalysis → Analyte`. The lookup traverses the `sample_id`
path only (not `experiment_fk`) to isolate pre-reaction characterization.

### `total_ferrous_iron_g` (on `ExperimentalConditions`)

**Analyte source:** `Analyte.analyte_symbol = 'FeO'`, `Analyte.unit = '%'`
**Stored in:** `ElementalAnalysis.analyte_composition` (numeric wt%)

**Lookup path:**
```
Experiment.sample_id
  → ExternalAnalysis (sample_id path, analysis_type in ('Elemental', 'Bulk Elemental Composition'))
    → ElementalAnalysis
      → Analyte (analyte_symbol = 'FeO', unit = '%')
        → ElementalAnalysis.analyte_composition  [FeO wt%]
```

**Multiple analyses resolution:** When multiple `ExternalAnalysis` records exist for the
same sample with FeO data, the most recent by `analysis_date` is used.

**Chemistry:**
```
Fe atomic mass  = 55.845 g/mol
O atomic mass   = 15.999 g/mol
FeO molar mass  = 71.844 g/mol

FE_IN_FEO_FRACTION = 55.845 / 71.844 ≈ 0.77731  (named constant in service)

fe_mass_fraction     = (feo_wt_pct / 100) × FE_IN_FEO_FRACTION
total_ferrous_iron_g = fe_mass_fraction × rock_mass_g
```

**Set to `None` when any of these are true:**
- `rock_mass_g` is missing or `≤ 0`
- No `ExternalAnalysis` with `analysis_type` in `'Elemental'` or `'Bulk Elemental Composition'` is linked to the sample via `sample_id`
- No `ElementalAnalysis` row exists for `Analyte.analyte_symbol = 'FeO'`
- `analyte_composition` is NULL

**Trigger:** Fires via `registry.recalculate()`. This field is **stored, not computed on
read**, so a conditions row is only correct if `recalculate()` ran after its last
mutation — and `calculate_ferrous_iron_yield_h2` returns NULL whenever this is NULL,
taking `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` down with it. Every
path that recalculates:

- `POST /api/conditions`, `PATCH /api/conditions/{id}` — `backend/api/routers/conditions.py:103`, `:125`
- `PATCH /api/experiments/{id}` — `backend/api/routers/experiments.py:1329`
- Replicate creation — `database/lineage_utils.py:603`
- Any elemental upload, via `recalculate_conditions_for_samples()` (`backend/services/elemental_composition_service.py:34`) — this is what covers experiments created *before* their rock's FeO data arrived
- The New Experiments bulk upload, as of 2026-08-10 — records every conditions row it touches and recalculates them in one pass before returning

**Known gap — the recalculation is not surfaced in the UI.** The bulk uploader appends
the recalculated-row count to the parser's `info_messages`, but
`backend/api/routers/bulk_uploads.py:180` destructures that value as `_info` and
discards it; nothing in `backend/api` or `frontend/src` reads it. So a researcher sees
no indication that derived fields were recomputed. Failures still surface — they go into
`warnings`, which the bulk-upload panel renders. Wiring `info_messages` through would
need a new response field and frontend rendering; it was deliberately left out of the
2026-08-10 fix.

Before 2026-08-10 the bulk uploader recalculated only `ChemicalAdditive`, so
bulk-created experiments landed with `total_ferrous_iron_g` **and**
`water_to_rock_ratio` NULL and therefore no Fe²⁺ yield percentages on any of their
scalar results — 845 of 1125 production conditions rows and 157 scalar rows. A NULL
`water_to_rock_ratio` on a row with positive rock mass and water volume is the
diagnostic for "recalculate never ran here". See
`docs/issues/issue-bulk-upload-never-recalculates-conditions.md`.

**Extensibility:** `get_analyte_wt_pct(sample_id, db, analyte_symbol='FeO')` accepts any
`analyte_symbol` — future oxides (MgO, SiO2, Al2O3) reuse the same traversal.
