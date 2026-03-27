# Locked Components — Do Not Modify Without Explicit User Instruction

These components represent working, production-tested logic. Treat them as read-only unless the user specifically authorizes changes.

## Database Schema (`database/models/`)

The SQLAlchemy models are the authoritative definition of all data structures. They encode years of real lab data. See `MODELS.md` for complete reference.

**Models are storage-only in the new architecture. All business logic and derived field calculations are moved to `backend/services/calculations/`. Do not add `@property` methods or hybrid properties to models for calculated fields.**

Locked models — preserve field names, types, relationships, and constraints exactly:

| Model | File | Notes |
|---|---|---|
| `Experiment` | `experiments.py` | Central entity — all FKs reference this |
| `ExperimentalConditions` | `conditions.py` | One-to-one with Experiment; `water_to_rock_ratio` is a stored derived field |
| `ExperimentalResults` | `results.py` | Timepoint parent record |
| `ScalarResults` | `results.py` | Solution chemistry; yield fields are stored derived fields |
| `ICPResults` | `results.py` | ICP-OES elemental data; JSON fields are intentional |
| `SampleInfo` | `samples.py` | Geological sample metadata |
| `Compound` | `chemicals.py` | Chemical reagent inventory |
| `ChemicalAdditive` | `chemicals.py` | Join table; calculated fields are stored derived fields |
| `ExternalAnalysis` | `analysis.py` | External lab report container |
| `XRDAnalysis` / `XRDPhase` | `xrd.py` | Mineral phase data |
| `PXRFReading` | `analysis.py` | Portable XRF data |
| `Analyte` / `ElementalAnalysis` | `characterization.py` | Elemental composition |
| All enums | `enums.py` | Changing these breaks existing data |

**JSON fields in `ICPResults` (`all_elements`, `detection_limits`) and `XRDAnalysis` (`mineral_phases`) are intentional design decisions.** In PostgreSQL these become `JSONB` columns — do not flatten them without explicit user instruction.

## Derived Fields — Stored, Not Computed on Read

All calculated/derived fields are **written to the database** at create/update time by the calculation engine. They are NOT computed on read via SQLAlchemy properties. This ensures Power BI and any direct SQL consumers see correct values without needing application logic.

Derived fields by table:
- `ExperimentalConditions`: `water_to_rock_ratio`
- `ScalarResults`: `h2_micromoles`, `grams_per_ton_yield`, `h2_grams_per_ton_yield`
- `ChemicalAdditive`: `mass_in_grams`, `moles_added`, `final_concentration`, `elemental_metal_mass`, `catalyst_percentage`, `catalyst_ppm`

## Firebase Authentication

Working in production. Do not modify auth logic. When building the React frontend, integrate using the existing Firebase project credentials stored in environment variables. The FastAPI backend validates Firebase ID tokens on every protected request.

## Bulk Upload Python Parsers (`backend/services/bulk_uploads/`)

These parsers handle real instrument output formats with edge cases accumulated from actual lab use. Do not rewrite parsing logic when rebuilding the UI layer. The task is to wrap these in FastAPI endpoints, not replace them.

| Parser | Handles |
|---|---|
| `new_experiments.py` | Multi-sheet Excel, experiment lineage parsing |
| `scalar_results.py` | Solution chemistry Excel, partial updates |
| `icp_service.py` | Raw ICP-OES CSV, delimiter detection, dilution correction |
| `actlabs_titration_data.py` | External titration lab reports |
| `actlabs_xrd_report.py` | External XRD lab reports |
| `xrd_upload.py` | Generic XRD file upload handler |
| `aeris_xrd.py` | Time-series Aeris instrument XRD data |
| `pxrf_data.py` | Portable XRF Excel uploads |
| `rock_inventory.py` | Geological sample bulk upsert |
| `chemical_inventory.py` | Chemical compound database updates |
| `experiment_status.py` | Batch status and reactor assignment updates |
| `experiment_additives.py` | Chemical additive bulk updates |
| `quick_upload.py` | Metric-specific mini-templates |
| `long_format.py` | Long-format LIMS-compatible data |
| `metric_groups.py` | Grouped metric upload templates |
| `timepoint_modifications.py` | Timepoint-level record modifications |
| `master_bulk_upload.py` | Dispatcher routing uploads to the correct parser |

## Alembic Migration History

Never delete, rewrite, or squash existing migration files. All new migrations must be additive. Migration files form a chain — breaking it corrupts production upgrade paths.
