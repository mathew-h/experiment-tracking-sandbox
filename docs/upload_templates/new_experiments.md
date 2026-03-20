# New Experiments Upload Template

**Source:** [backend/services/bulk_uploads/new_experiments.py](../../backend/services/bulk_uploads/new_experiments.py)

## Overview
Creates or updates Experiments, Experimental Conditions, and Chemical Additives using a structured, multi-sheet Excel workbook.

## Excel Format
Requires a multi-sheet workbook with specific (case-insensitive) sheet names.

### Sheets Structure

| Sheet | Required | Columns |
|-------|----------|---------|
| `experiments` | Yes | experiment_id*, old_experiment_id (optional, for renames), sample_id, date, status, initial_note, overwrite, researcher |
| `conditions` | No | experiment_id*, columns matching ExperimentalConditions (e.g., particle_size, rock_mass_g, water_volume_mL, reactor_number) |
| `additives` | No | experiment_id*, compound*, amount*, unit*, order, method |

## Experiment ID Format
Supports structured naming conventions:
- **3-part:** `ExperimentType_ResearcherInitials_Index` (e.g., `Serum_MH_101`)
- **2-part:** `ExperimentType_Index` (e.g., `HPHT_001`)
- **Suffixes:** Appending `-NUMBER` designates a sequential experiment, while `_TEXT` designates a treatment variant.

## Parsing Logic

### General Rules
- **Headers:** Asterisks (`*`) and parenthetical hints are stripped, and names are normalized to lowercase.
- **Overwrite:** Interprets values like `true`, `1`, `yes`, `y` as `True`.
- **Status:** Maps to the `ExperimentStatus` enum using a case-insensitive match on name or value.
- **Date:** Handles Excel serial dates, ISO strings, or blank values.

### Advanced Behaviors
- **Auto-copy:** Sequential and treatment variant experiments automatically inherit conditions from their parent experiment. However, chemical additives are never auto-copied and must be explicitly defined.
- **Renaming:** Utilizing the `old_experiment_id` column alongside `overwrite=True` locates the experiment by its old ID and renames it to the newly provided `experiment_id`.

## Data Model Specifications

### Conditions Sheet
Columns map directly to `ExperimentalConditions` model attributes. Certain legacy/deprecated columns (e.g., catalyst, buffer_system, surfactant_type) are blacklisted. The `experiment_type` is auto-populated based on the parsed `experiment_id`.

### Additives Sheet
The `unit` column must strictly match `AmountUnit` enum values (e.g., `g`, `mg`, `mM`, `ppm`). Missing compounds are automatically created in the database. When `overwrite=True`, existing additives for the experiment are entirely replaced by the newly provided set.

## Output
Returns `(created_experiments, updated_experiments, skipped_rows, errors, warnings, info_messages)`.
