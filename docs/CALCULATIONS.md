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
