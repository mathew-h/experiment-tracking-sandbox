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
- `background_ammonium_concentration_mM` defaults to `0.3 mM` if not set
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
- All three inputs required and > 0; otherwise both outputs are `None`

### Hydrogen Yield (`h2_grams_per_ton_yield`)

```
h2_mass_g = h2_mass_ug / 1,000,000

h2_grams_per_ton_yield = 1,000,000 × (h2_mass_g / rock_mass_g)
```

Set to `None` if `rock_mass_g` is missing or H2 inputs are insufficient.

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

**Trigger:** Fires via `registry.recalculate()` on `POST /conditions` and `PATCH /conditions`.

**Extensibility:** `get_analyte_wt_pct(sample_id, db, analyte_symbol='FeO')` accepts any
`analyte_symbol` — future oxides (MgO, SiO2, Al2O3) reuse the same traversal.
