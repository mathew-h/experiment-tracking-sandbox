"""
Metric group definitions for quick-upload templates.

Each group defines a focused subset of ScalarResults fields that can be uploaded
independently via a minimal Excel template.  All groups share the same backend
upsert pipeline (ScalarResultsService.create_scalar_result with _overwrite=False),
so uploading one group never touches fields belonging to another.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Metric group registry
# ---------------------------------------------------------------------------

METRIC_GROUPS: Dict[str, Dict[str, Any]] = {
    "hydrogen": {
        "label": "Hydrogen (H2)",
        "required_fields": {"experiment_id", "time_post_reaction", "h2_concentration"},
        "optional_fields": {
            "gas_sampling_volume_ml",
            "gas_sampling_pressure_MPa",
            "measurement_date",
            "description",
        },
        "template_headers": OrderedDict([
            ("experiment_id", "Experiment ID*"),
            ("time_post_reaction", "Time (days)*"),
            ("h2_concentration", "H2 Conc (ppm)*"),
            ("gas_sampling_volume_ml", "Gas Sample Vol (mL)"),
            ("gas_sampling_pressure_MPa", "Gas Pressure (MPa)"),
            ("measurement_date", "Date"),
            ("description", "Description"),
        ]),
        "defaults": {"h2_concentration_unit": "ppm"},
        "validations": {
            "h2_concentration": {"min": 0, "type": "numeric"},
            "gas_sampling_volume_ml": {"min": 0, "type": "numeric"},
            "gas_sampling_pressure_MPa": {"min": 0, "type": "numeric"},
        },
    },
    "ph_conductivity": {
        "label": "pH / Conductivity",
        "required_fields": {"experiment_id", "time_post_reaction"},
        "optional_fields": {
            "final_ph",
            "final_conductivity_mS_cm",
            "final_dissolved_oxygen_mg_L",
            "measurement_date",
            "description",
        },
        "template_headers": OrderedDict([
            ("experiment_id", "Experiment ID*"),
            ("time_post_reaction", "Time (days)*"),
            ("final_ph", "Final pH"),
            ("final_conductivity_mS_cm", "Conductivity (mS/cm)"),
            ("final_dissolved_oxygen_mg_L", "Final DO (mg/L)"),
            ("measurement_date", "Date"),
            ("description", "Description"),
        ]),
        "defaults": {},
        "validations": {
            "final_ph": {"min": 0, "max": 14, "type": "numeric"},
            "final_conductivity_mS_cm": {"min": 0, "type": "numeric"},
            "final_dissolved_oxygen_mg_L": {"min": 0, "type": "numeric"},
        },
    },
    "ammonium": {
        "label": "Ammonium (NH4+)",
        "required_fields": {"experiment_id", "time_post_reaction"},
        "optional_fields": {
            "gross_ammonium_concentration_mM",
            "background_ammonium_concentration_mM",
            "background_experiment_id",
            "sampling_volume_mL",
            "measurement_date",
            "description",
        },
        "template_headers": OrderedDict([
            ("experiment_id", "Experiment ID*"),
            ("time_post_reaction", "Time (days)*"),
            ("gross_ammonium_concentration_mM", "Gross Ammonium (mM)"),
            ("background_ammonium_concentration_mM", "Bkg Ammonium (mM)"),
            ("background_experiment_id", "Bkg Exp ID"),
            ("sampling_volume_mL", "Sampling Vol (mL)"),
            ("measurement_date", "Date"),
            ("description", "Description"),
        ]),
        "defaults": {},
        "validations": {
            "gross_ammonium_concentration_mM": {"min": 0, "type": "numeric"},
            "background_ammonium_concentration_mM": {"min": 0, "type": "numeric"},
            "sampling_volume_mL": {"min": 0, "type": "numeric"},
        },
    },
}


# ---------------------------------------------------------------------------
# Long-format metric registry  (Phase 3)
# Maps human-readable metric names to (db_field, default_unit) pairs.
# ---------------------------------------------------------------------------

METRIC_REGISTRY: Dict[str, Dict[str, Any]] = {
    "h2_concentration": {
        "db_field": "h2_concentration",
        "label": "H2 Concentration",
        "default_unit": "ppm",
        "allowed_units": ["ppm"],
        "type": "numeric",
        "min": 0,
    },
    "final_ph": {
        "db_field": "final_ph",
        "label": "Final pH",
        "default_unit": "",
        "allowed_units": [""],
        "type": "numeric",
        "min": 0,
        "max": 14,
    },
    "final_conductivity_mS_cm": {
        "db_field": "final_conductivity_mS_cm",
        "label": "Conductivity",
        "default_unit": "mS/cm",
        "allowed_units": ["mS/cm"],
        "type": "numeric",
        "min": 0,
    },
    "final_dissolved_oxygen_mg_L": {
        "db_field": "final_dissolved_oxygen_mg_L",
        "label": "Dissolved Oxygen",
        "default_unit": "mg/L",
        "allowed_units": ["mg/L"],
        "type": "numeric",
        "min": 0,
    },
    "gross_ammonium_concentration_mM": {
        "db_field": "gross_ammonium_concentration_mM",
        "label": "Gross Ammonium",
        "default_unit": "mM",
        "allowed_units": ["mM"],
        "type": "numeric",
        "min": 0,
    },
    "background_ammonium_concentration_mM": {
        "db_field": "background_ammonium_concentration_mM",
        "label": "Background Ammonium",
        "default_unit": "mM",
        "allowed_units": ["mM"],
        "type": "numeric",
        "min": 0,
    },
    "ferrous_iron_yield": {
        "db_field": "ferrous_iron_yield",
        "label": "Fe2+ Yield",
        "default_unit": "%",
        "allowed_units": ["%"],
        "type": "numeric",
        "min": 0,
    },
    "sampling_volume_mL": {
        "db_field": "sampling_volume_mL",
        "label": "Sampling Volume",
        "default_unit": "mL",
        "allowed_units": ["mL"],
        "type": "numeric",
        "min": 0,
    },
}
