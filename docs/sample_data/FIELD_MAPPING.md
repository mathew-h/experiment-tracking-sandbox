# Field Mapping Reference

Maps upload template column headers to their database model fields.
For full upload instructions see `docs/user_guide/BULK_UPLOADS.md`.

---

## New Experiments (`/api/bulk-uploads/new-experiments`)

| Template Column | Model | Field |
|----------------|-------|-------|
| experiment_id | Experiment | experiment_id |
| experiment_type | Experiment | experiment_type (HPHT / Serum / Autoclave / Core Flood / Other) |
| status | Experiment | status (ONGOING / COMPLETED / CANCELLED) |
| researcher | Experiment | researcher |
| date | Experiment | date |
| sample_id | Experiment | sample_id (FK → SampleInfo) |
| temperature_c | ExperimentalConditions | temperature_c |
| initial_ph | ExperimentalConditions | initial_ph |
| rock_mass_g | ExperimentalConditions | rock_mass_g |
| water_volume_mL | ExperimentalConditions | water_volume_mL |
| reactor_number | ExperimentalConditions | reactor_number |
| stir_speed_rpm | ExperimentalConditions | stir_speed_rpm |
| particle_size | ExperimentalConditions | particle_size |
| feedstock | ExperimentalConditions | feedstock |
| experiment_type (conditions) | ExperimentalConditions | experiment_type |
| co2_partial_pressure_MPa | ExperimentalConditions | co2_partial_pressure_MPa |

---

## Solution Chemistry (`/api/bulk-uploads/scalar-results`)

Template header → internal field (header map after asterisk stripping):

| Template Column | Model | Field |
|----------------|-------|-------|
| Date | ScalarResults | measurement_date |
| Experiment ID | ExperimentalResults | experiment_id (FK → Experiment) |
| Time (days) | ExperimentalResults | time_post_reaction_days |
| Description | ExperimentalResults | description |
| Gross Ammonium (mM) | ScalarResults | gross_ammonium_concentration_mM |
| Sampling Vol (mL) | ScalarResults | sampling_volume_mL |
| Bkg Ammonium (mM) | ScalarResults | background_ammonium_concentration_mM |
| Bkg Exp ID | ScalarResults | background_experiment_id |
| H2 Conc (ppm) | ScalarResults | h2_concentration |
| Gas Sample Vol (mL) | ScalarResults | gas_sampling_volume_ml |
| Gas Pressure (MPa) | ScalarResults | gas_sampling_pressure_MPa |
| Final pH | ScalarResults | final_ph |
| Fe2+ Yield (%) | ScalarResults | ferrous_iron_yield |
| Final Nitrate (mM) | ScalarResults | final_nitrate_concentration_mM |
| Final DO (mg/L) | ScalarResults | final_dissolved_oxygen_mg_L |
| CO2 Pressure (MPa) | ScalarResults | co2_partial_pressure_MPa |
| Conductivity (mS/cm) | ScalarResults | final_conductivity_mS_cm |
| Alkalinity (mg/L) | ScalarResults | final_alkalinity_mg_L |
| Overwrite | (parser flag) | Overwrite existing row at same timepoint |

**Derived fields** (calculated after write, not in template):
`h2_micromoles`, `h2_mass_ug`, `h2_grams_per_ton_yield`, `grams_per_ton_yield`

---

## Master Results Tracker (`/api/bulk-uploads/master-results`)

Sheet: `Dashboard`

| Tracker Column | Model | Field |
|----------------|-------|-------|
| Experiment ID | ExperimentalResults | experiment_id |
| Duration (Days) | ExperimentalResults | time_post_reaction_days |
| Description | ExperimentalResults | description |
| Sample Date | ExperimentalResults | (timepoint label) |
| NH4 (mM) | ScalarResults | gross_ammonium_concentration_mM |
| H2 (ppm) | ScalarResults | h2_concentration |
| Gas Volume (mL) | ScalarResults | gas_sampling_volume_ml |
| Gas Pressure (psi) | ScalarResults | gas_sampling_pressure_MPa (converted from psi) |
| Sample pH | ScalarResults | final_ph |
| Sample Conductivity (mS/cm) | ScalarResults | final_conductivity_mS_cm |
| Overwrite | (parser flag) | Overwrite existing row |

---

## Rock Inventory (`/api/bulk-uploads/rock-inventory`)

| Template Column | Model | Field |
|----------------|-------|-------|
| sample_id | SampleInfo | sample_id (normalised to uppercase, spaces/underscores removed) |
| rock_classification | SampleInfo | rock_classification |
| state | SampleInfo | state |
| country | SampleInfo | country |
| locality | SampleInfo | locality |
| latitude | SampleInfo | latitude |
| longitude | SampleInfo | longitude |
| description | SampleInfo | description |
| characterized | SampleInfo | characterized (TRUE/FALSE) |
| pxrf_reading_no | PXRFReading | reading_no (links to existing pXRF record) |
| overwrite | (parser flag) | Overwrite all optional fields |

---

## Chemical Inventory (`/api/bulk-uploads/chemical-inventory`)

| Template Column | Model | Field |
|----------------|-------|-------|
| name | Compound | name (case-insensitive unique key) |
| formula | Compound | formula |
| cas_number | Compound | cas_number |
| molecular_weight | Compound | molecular_weight_g_mol |
| density | Compound | density_g_cm3 |
| melting_point | Compound | melting_point_c |
| boiling_point | Compound | boiling_point_c |
| solubility | Compound | solubility |
| hazard_class | Compound | hazard_class |
| supplier | Compound | supplier |
| catalog_number | Compound | catalog_number |
| notes | Compound | notes |

---

## Sample Chemical Composition (`/api/bulk-uploads/elemental-composition`)

Wide-format: `sample_id` column + one column per analyte symbol.

| Template Column | Model | Field |
|----------------|-------|-------|
| sample_id | ElementalAnalysis | sample_id (FK → SampleInfo) |
| \<analyte symbol\> | ElementalAnalysis | analyte_composition (linked to Analyte by symbol) |

Analyte symbols must match existing `Analyte.analyte_symbol` rows, or pass `?default_unit=wt%`
to auto-create unknown analytes.

---

## Timepoint Modifications (`/api/bulk-uploads/timepoint-modifications`)

| Template Column | Model | Field |
|----------------|-------|-------|
| experiment_id | ExperimentalResults | experiment_id |
| time_point | ExperimentalResults | time_post_reaction_days (matched within ±0.0001) |
| modification_description | ExperimentalResults | brine_modification_description |

---

## XRD Mineralogy (`/api/bulk-uploads/xrd-mineralogy`)

Two auto-detected formats:

**ActLabs wide-format:**

| Template Column | Model | Field |
|----------------|-------|-------|
| sample_id | XRDPhase | (links to SampleInfo or ExternalAnalysis) |
| \<Mineral Name\> | XRDPhase | mineral_name / amount (%) |

**Aeris time-series format:** raw `.xlsx` from Aeris diffractometer.
Sample ID column matches `^\d{8}_.+?-d\d+_\d+$` and maps to experiment + time_post_reaction_days.
