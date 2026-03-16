"""
Configuration file containing all experiment-related constants and defaults.
"""

import os # Add os import if not present
import datetime # Make sure datetime is imported if needed for date default

# Import enums from database models to ensure consistency
from database.models.enums import (
    ExperimentStatus, ExperimentType, FeedstockType, ComponentType,
    AnalysisType, AmmoniumQuantMethod, TitrationType, CharacterizationStatus,
    ConcentrationUnit, PressureUnit
)

# Path configuration
DATA_DIR = 'data'
PXRF_DATA_FILENAME = 'pXRF_data.xlsx'
PXRF_DATA_PATH = os.path.join(DATA_DIR, PXRF_DATA_FILENAME)

# Available experiment types - now sourced from enums
EXPERIMENT_TYPES = [e.value for e in ExperimentType]

# Available experiment statuses - now sourced from enums
EXPERIMENT_STATUSES = [e.value for e in ExperimentStatus]

# Available external analysis types - now sourced from enums
ANALYSIS_TYPES = [e.value for e in AnalysisType]

# Feedstock types - now sourced from enums
FEEDSTOCK_TYPES = [e.value for e in FeedstockType]

# Component types - from enums
COMPONENT_TYPES = [e.value for e in ComponentType]

# Ammonium quantification methods - from enums
AMMONIUM_QUANT_METHODS = [e.value for e in AmmoniumQuantMethod]

# Titration types - from enums
TITRATION_TYPES = [e.value for e in TitrationType]

# Characterization statuses - from enums
CHARACTERIZATION_STATUSES = [e.value for e in CharacterizationStatus]

# Concentration units - from enums
CONCENTRATION_UNITS = [e.value for e in ConcentrationUnit]

# Pressure units - from enums
PRESSURE_UNITS = [e.value for e in PressureUnit]

# For pXRF data ingestion
PXRF_ELEMENT_COLUMNS = ["Fe", "Mg", "Si", "Ni", "Cu", "Mo", "Co", "Al", "Ca", "K", "Au"]
PXRF_REQUIRED_COLUMNS = set(PXRF_ELEMENT_COLUMNS) | {'Reading No'}

# Backward-compatibility alias for tests expecting ELEMENT_COLUMNS
ELEMENT_COLUMNS = PXRF_ELEMENT_COLUMNS

# ICP fixed element columns (ordered for Power BI / fixed-column storage)
ICP_FIXED_ELEMENT_FIELDS = [
    'fe', 'si', 'ni', 'cu', 'mo', 'zn', 'mn', 'ca', 'cr', 'co', 'mg', 'al',
    'sr', 'y', 'nb', 'sb', 'cs', 'ba', 'nd', 'gd', 'pt', 'rh', 'ir',
    'pd', 'ru', 'os', 'tl'
]

# Configuration for rock sample form fields
ROCK_SAMPLE_CONFIG = {
    'sample_id': {
        'label': "Sample ID",
        'type': 'text',
        'required': True,
        'default': '',
        'help': "Enter a unique identifier for this rock sample (e.g., 20UM21)"
    },
    'description': {
        'label': "Sample Description (optional)",
        'type': 'text',
        'required': False,
        'default': '',
        'help': "Add any relevant details about the rock sample"
    },
    'state': {
        'label': "State/Province",
        'type': 'text',
        'required': True,
        'default': '',
        'help': "Enter the state or province where the sample was collected"
    },
    'country': {
        'label': "Country",
        'type': 'text',
        'required': True,
        'default': '',
        'help': "Enter the country where the sample was collected"
    },
    'locality': {
        'label': "Locality (optional)",
        'type': 'text',
        'required': False,
        'default': '',
        'help': "Enter the specific locality where the sample was collected"
    },
    'latitude': {
        'label': "Latitude",
        'type': 'number',
        'required': True,
        'default': 0.0,
        'min_value': -90.0,
        'max_value': 90.0,
        'step': 0.000001,
        'format': "%.6f",
        'help': "Enter the latitude coordinate of the collection site (0.0 for unknown/unspecified location)"
    },
    'longitude': {
        'label': "Longitude",
        'type': 'number',
        'required': True,
        'default': 0.0,
        'min_value': -180.0,
        'max_value': 180.0,
        'step': 0.000001,
        'format': "%.6f",
        'help': "Enter the longitude coordinate of the collection site (0.0 for unknown/unspecified location)"
    },
    'rock_classification': {
        'label': "Rock Classification (optional)",
        'type': 'text',
        'required': False,
        'default': '',
        'help': "Enter the rock type/classification"
    },
    'characterized': {
        'label': "Characterized",
        'type': 'checkbox',
        'default': False,
        'required': False,
        'help': "Check if this sample has been characterized"
    }
}

# Configuration for external analysis form fields
EXTERNAL_ANALYSIS_CONFIG = {
    'analysis_type': {
        'label': "Analysis Type",
        'type': 'select',
        'options': ANALYSIS_TYPES,
        'default': ANALYSIS_TYPES[0] if ANALYSIS_TYPES else None, # Default to first option or None
        'required': True,
        'help': "Select the type of analysis performed"
    },
    'pxrf_reading_no': {
        'label': "pXRF Reading No(s)",
        'type': 'text',
        'default': '',
        'required': False, # Required conditionally in the UI, not always
        'help': "Enter the pXRF reading number(s). Can be integers separated by commas (e.g., 1, 2, 5)."
    },
    'magnetic_susceptibility': {
        'label': "Mag. Susc (1x10^-3)",
        'type': 'text',
        'default': '',
        'required': False,
        'help': "Enter the magnetic susceptibility value or range (e.g., 0.5-1). Units: 1x10^-3. Leave blank if not measured."
    },
    'description': {
        'label': "Description",
        'type': 'text_area',
        'default': '',
        'required': False,
        'height': 100,
        'help': "Add a description of the analysis"
    }
}

# Configuration for experiment form fields
FIELD_CONFIG = {
    # --- Required Fields ---
    'experiment_type': {
        'label': "Experiment Type",
        'default': ExperimentType.SERUM.value,
        'type': 'select',
        'options': EXPERIMENT_TYPES, # Reference the list above
        'required': True,
        'help': "Select the type of experiment setup."
    },
    'reactor_number': {
        'label': "Reactor Number",
        'type': 'number',
        'default': None,
        'min_value': 0,
        'step': 1,
        'format': "%d",
        'required': False,
        'help': "Enter the reactor number (optional integer)."
    },
    'initial_ph': {
        'label': "Initial pH",
        'default': 7.0,
        'type': 'number',
        'min_value': 0.0,
        'max_value': 14.0,
        'step': 0.1,
        'format': "%.1f",
        'required': True,
        'help': "Specify the starting pH of the solution."
    },
    'rock_mass_g': {
        'label': "Rock Mass (g)",
        'default': 0.0,
        'type': 'number',
        'min_value': 0.0,
        'step': 0.001,
        'format': "%.3f",
        'required': True,
        'help': "Enter the mass of the rock sample in grams."
    },
    'water_volume_mL': {
        'label': "Water Volume (mL)",
        'default': 0.0,
        'type': 'number',
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': True,
        'help': "Enter the volume of water used in milliliters."
    },
    'temperature_c': {
        'label': "Temperature (°C)",
        'default': 25.0,
        'type': 'number',
        'min_value': -273.15, # Absolute zero
        'step': 1.0,
        'format': "%.1f",
        'required': True,
        'help': "Specify the experiment temperature in Celsius."
    },

    # --- Optional Fields ---
    'particle_size': {
        'label': "Particle Size (μm)",
        'default': '',
        'type': 'text',
        'required': False,
        'help': "Enter particle size (e.g., '75', '<75', '>100', '75-150'). Accepts numeric values or text with comparators."
    },
    'water_to_rock_ratio': {
        'label': "Water to Rock Ratio",
        'default': 0.0,  # Simple default value instead of lambda
        'type': 'number',
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.2f",
        'required': False,
        'help': "This is automatically calculated based on rock mass and water volume.",
        'readonly': True # Make this field read-only
    },
    'feedstock': {
        'label': "Feedstock Type",
        'type': 'select',
        'options': FEEDSTOCK_TYPES,
        'default': FeedstockType.BLANK.value,
        'required': True,
        'help': "Feedstock type. Valid values: Nitrogen, Nitrate, or Blank."
    },
    'initial_nitrate_concentration': {
        'label': "Initial Nitrate Concentration (mM)",
        'default': 0.0,
        'type': 'number',
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Enter the initial nitrate concentration in millimolar (mM). Should be 50 for 'Nitrate' feedstock and 0 for 'Nitrogen' or 'Blank'."
    },
    'initial_dissolved_oxygen': {  # Renamed from 'dissolved_oxygen'
        'label': "Initial Dissolved Oxygen (ppm)",
        'default': 0.0,
        'type': 'number',
        'min_value': 0.0,
        'max_value': 100.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Enter the initial dissolved oxygen concentration in parts per million (ppm)."
    },
    'stir_speed_rpm': {
        'label': "Stir Speed (RPM)",
        'type': 'number',
        'default': None,
        'min_value': 0.0,
        'step': 1.0,
        'format': "%.0f",
        'required': False,
        'help': "Stir speed in rotations per minute (RPM)."
    },
    'initial_conductivity_mS_cm': {
        'label': "Initial Conductivity (mS/cm)",
        'type': 'number',
        'default': None,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Initial conductivity measurement (millisiemens per centimeter)."
    },
    # 'initial_alkalinity': {
    #     'label': "Initial Alkalinity (mg/L CaCO₃)",
    #     'type': 'number',
    #     'default': None,
    #     'min_value': 0.0,
    #     'step': 0.1,
    #     'format': "%.1f",
    #     'required': False,
    #     'help': "Initial alkalinity measurement (mg/L as CaCO₃)."
    # },
    'room_temp_pressure_psi': {  
        'label': "Pressure at Room Temperature (psi)",
        'default': 14.6959, # Standard atmospheric pressure
        'type': 'number',
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.2f",
        'required': False,
        'help': "Specify the room temperature pressure in pounds per square inch (psi)."
    },
    'rxn_temp_pressure_psi': {
        'label': "Pressure at Reaction Temperature (psi)",
        'type': 'number',
        'default': None,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.2f",
        'required': False,
        'help': "Reaction temperature pressure (psi)."
    },
    'confining_pressure': {
        'label': "Confining Pressure (psi)",
        'default': 0.0,
        'type': 'number',
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.2f",
        'required': False,
        'help': "Specify the confining pressure in psi (for core flood/HPHT)."
    },
    'pore_pressure': {
        'label': "Pore Pressure (psi)",
        'default': 0.0,
        'type': 'number',
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.2f",
        'required': False,
        'help': "Specify the pore pressure in psi (for core flood/HPHT)."
    },
    'core_height_cm': {
        'label': "Core Height (cm)",
        'type': 'number',
        'default': None,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.2f",
        'required': False,
        'help': "Core height (in centimeters)."
    },
    'core_width_cm': {
        'label': "Core Width (cm)",
        'type': 'number',
        'default': None,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.2f",
        'required': False,
        'help': "Core width (in centimeters)."
    },
    'core_volume_cm3': {
        'label': "Core Volume (cm³)",
        'type': 'number',
        'default': None,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.2f",
        'required': False,
        'help': "Core volume (in cubic centimeters)."
    },
    'flow_rate': {
        'label': "Flow Rate (mL/min)",
        'default': 0.0,
        'type': 'number',
        'min_value': 0.0,
        'step': 0.001,
        'format': "%.3f",
        'required': False,
        'help': "Specify the flow rate in mL/min (for flow-through experiments)."
    },
    'co2_partial_pressure_MPa': {
        'label': "CO2 Partial Pressure (MPa)",
        'default': 0.0,
        'type': 'number',
        'min_value': 0.0,
        'step': 0.001,
        'format': "%.3f",
        'required': False,
        'help': "Specify the partial pressure of CO2 in MPa (for relevant experiments)."
    },
}

# Configuration for experiment scalar results (formerly RESULTS_CONFIG)
SCALAR_RESULTS_CONFIG = {
    'gross_ammonium_concentration_mM': {
        'label': "Gross Ammonium Concentration (mM)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.001,
        'format': "%.3f",
        'required': False,
        'help': "Enter the gross ammonium concentration in the solution in millimolar (mM)."
    },

    'background_ammonium_concentration_mM': {
        'label': "Background Ammonium Concentration (mM)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.001,
        'format': "%.3f",
        'required': False,
        'help': "Enter the background ammonium concentration in the solution in millimolar (mM)."
    },
    'final_ph': {
        'label': "Final pH",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'max_value': 14.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Enter the final pH of the solution (if measured)."
    },
    'sampling_volume_mL': {
        'label': "Sampling Volume (mL)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Sampling volume in milliliters."
    },
    'grams_per_ton_yield': {
        'label': "Yield (g NH3/ton rock)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.01,
        'format': "%.2f",
        'required': False,
        'help': "Enter the yield in grams per ton (if measured)."
    },
    'ferrous_iron_yield': {  
        'label': "Ferrous Iron Yield (%)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'max_value': 100.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Enter the ferrous iron yield as a percentage (if measured)."
    },
    'co2_partial_pressure_MPa': {
        'label': "CO2 Partial Pressure (MPa)",
        'default': 0.0,
        'type': 'number',
        'min_value': 0.0,
        'step': 0.001,
        'format': "%.3f",
        'required': False,
        'help': "Specify the partial pressure of CO2 in MPa (for relevant experiments)."
    },
    # --- Hydrogen tracking fields ---
    'h2_concentration': {
        'label': "H₂ Concentration (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.01,
        'format': "%.2f",
        'required': False,
        'help': "Measured hydrogen concentration in the gas (ppm)."
    },
    'gas_sampling_volume_ml': {
        'label': "Gas Sampling Volume (mL)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Volume of gas sampled for the measurement (mL)."
    },
    'gas_sampling_pressure_MPa': {
        'label': "Gas Sampling Pressure (MPa)",
        'type': 'number',
        'default': 0.1013,
        'min_value': 0.0,
        'step': 0.0001,
        'format': "%.4f",
        'required': False,
        'help': "Pressure of the gas sample during measurement (MPa). Required for H₂ calculation."
    },
    'h2_micromoles': {
        'label': "H₂ Amount (μmol)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.001,
        'format': "%.3f",
        'required': False,
        'readonly': True,
        'help': "Calculated micromoles of H₂ in the sampled gas."
    },
    'h2_mass_ug': {
        'label': "H₂ Mass (μg)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.001,
        'format': "%.3f",
        'required': False,
        'readonly': True,
        'help': "Calculated micrograms of H₂ in the sampled gas."
    },
    'h2_grams_per_ton_yield': {
        'label': "H₂ Yield (g/ton rock)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.001,
        'format': "%.3f",
        'required': False,
        'readonly': True,
        'help': "Calculated hydrogen yield normalized to rock mass (g per metric ton)."
    },
    'background_experiment_id': {
        'label': "Background Experiment ID",
        'type': 'text',
        'default': '',
        'required': False,
        'help': "ID of the background experiment."
    },
    'final_nitrate_concentration_mM': {
        'label': "Final Nitrate Concentration (mM)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Enter the final nitrate concentration in mM (if measured)."
    },
    'final_dissolved_oxygen_mg_L': {
        'label': "Final Dissolved Oxygen (mg/L)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Final dissolved oxygen concentration (mg/L)."
    },
    'final_conductivity_mS_cm': {
        'label': "Final Conductivity (mS/cm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Final conductivity measurement (millisiemens per centimeter)."
    },
    'final_alkalinity_mg_L': {
        'label': "Final Alkalinity (mg/L CaCO₃)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Final alkalinity measurement (mg/L as CaCO₃)."
    },
    'time_post_reaction': {
        'label': "Time Post-Reaction (days)",
        'type': 'number',
        'required': True,
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'help': "Enter the time elapsed in days since the reaction started when these results were measured."
    }
}

# Configuration for ICP results
ICP_RESULTS_CONFIG = {
    'fe': {
        'label': "Iron (Fe) (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Iron concentration in parts per million (ppm)."
    },
    'si': {
        'label': "Silicon (Si) (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Silicon concentration in parts per million (ppm)."
    },
    'ni': {
        'label': "Nickel (Ni) (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Nickel concentration in parts per million (ppm)."
    },
    'cu': {
        'label': "Copper (Cu) (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Copper concentration in parts per million (ppm)."
    },
    'mo': {
        'label': "Molybdenum (Mo) (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Molybdenum concentration in parts per million (ppm)."
    },
    'zn': {
        'label': "Zinc (Zn) (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Zinc concentration in parts per million (ppm)."
    },
    'mn': {
        'label': "Manganese (Mn) (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Manganese concentration in parts per million (ppm)."
    },
    'cr': {
        'label': "Chromium (Cr) (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Chromium concentration in parts per million (ppm)."
    },
    'co': {
        'label': "Cobalt (Co) (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Cobalt concentration in parts per million (ppm)."
    },
    'mg': {
        'label': "Magnesium (Mg) (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Magnesium concentration in parts per million (ppm)."
    },
    'al': {
        'label': "Aluminum (Al) (ppm)",
        'type': 'number',
        'default': 0.0,
        'min_value': 0.0,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Aluminum concentration in parts per million (ppm)."
    },
    'dilution_factor': {
        'label': "Dilution Factor",
        'type': 'number',
        'default': 1.0,
        'min_value': 0.1,
        'step': 0.1,
        'format': "%.1f",
        'required': False,
        'help': "Dilution factor applied to the sample for ICP analysis."
    },
    'instrument_used': {
        'label': "Instrument Used",
        'type': 'text',
        'default': '',
        'required': False,
        'help': "Name of the ICP instrument used for analysis."
    },
    'raw_label': {
        'label': "Raw Sample Label",
        'type': 'text',
        'default': '',
        'required': False,
        'help': "Original sample label from the ICP analysis file."
    }
}

# Configuration for experiment notes
EXPERIMENT_NOTES_CONFIG = {
    'note_text': {
        'label': "Note",
        'type': 'text_area',
        'default': '',
        'required': True,
        'height': 150,
        'help': "Enter your note about this experiment."
    }
}

# Configuration for XRD analysis
XRD_ANALYSIS_CONFIG = {
    'mineral_phases': {
        'label': "Mineral Phases (%)",
        'type': 'json_input',
        'default': {},
        'required': False,
        'help': "Enter mineral phases and their percentages (e.g., {'quartz': 45.2, 'feldspar': 23.8})."
    },
    'peak_positions': {
        'label': "Peak Positions (2θ)",
        'type': 'json_input',
        'default': {},
        'required': False,
        'help': "Enter peak positions in 2θ degrees (e.g., {'2-theta': [20.8, 26.6]})."
    },
    'intensities': {
        'label': "Peak Intensities",
        'type': 'json_input',
        'default': {},
        'required': False,
        'help': "Enter peak intensities (e.g., {'counts': [1500, 8000]})."
    },
    'd_spacings': {
        'label': "d-spacings (Å)",
        'type': 'json_input',
        'default': {},
        'required': False,
        'help': "Enter d-spacings in Angstroms (e.g., {'angstrom': [4.26, 3.34]})."
    },
    'analysis_parameters': {
        'label': "Analysis Parameters",
        'type': 'json_input',
        'default': {},
        'required': False,
        'help': "Enter analysis parameters (e.g., {'xray_source': 'CuKa', 'scan_range': '5-90'})."
    }
}

# Configuration for elemental analysis
ELEMENTAL_ANALYSIS_CONFIG = {
    'major_elements': {
        'label': "Major Elements (%)",
        'type': 'json_input',
        'default': {},
        'required': False,
        'help': "Enter major elements and their percentages (e.g., {'SiO2': 65.5, 'Al2O3': 15.2})."
    },
    'minor_elements': {
        'label': "Minor Elements (%)",
        'type': 'json_input',
        'default': {},
        'required': False,
        'help': "Enter minor elements and their percentages (e.g., {'TiO2': 0.8, 'Fe2O3': 4.5})."
    },
    'trace_elements': {
        'label': "Trace Elements (ppm)",
        'type': 'json_input',
        'default': {},
        'required': False,
        'help': "Enter trace elements and their concentrations in ppm (e.g., {'Sr': 400, 'Ba': 850})."
    },
    'detection_method': {
        'label': "Detection Method",
        'type': 'text',
        'default': '',
        'required': False,
        'help': "Method used for elemental detection (e.g., 'XRF', 'ICP-MS')."
    },
    'detection_limits': {
        'label': "Detection Limits (ppm)",
        'type': 'json_input',
        'default': {},
        'required': False,
        'help': "Enter detection limits for elements in ppm (e.g., {'Sr': 0.5, 'Ba': 1})."
    },
    'analytical_conditions': {
        'label': "Analytical Conditions",
        'type': 'json_input',
        'default': {},
        'required': False,
        'help': "Enter analytical conditions (e.g., {'instrument': 'Thermo Fisher iCAP Q', 'digestion_method': 'HF-HNO3'})."
    }
}

# Mapping for Bulk Upload Template Headers (English -> DB Variable)
# Used in frontend/components/bulk_uploads.py (template generation)
# and backend/services/bulk_uploads/scalar_results.py (parsing)
SCALAR_RESULTS_TEMPLATE_HEADERS = {
    "measurement_date": "Date",
    "experiment_id": "Experiment ID",
    "time_post_reaction": "Time (days)",
    "description": "Description",
    "gross_ammonium_concentration_mM": "Gross Ammonium (mM)",
    "sampling_volume_mL": "Sampling Vol (mL)",
    "background_ammonium_concentration_mM": "Bkg Ammonium (mM)",
    "background_experiment_id": "Bkg Exp ID",
    "h2_concentration": "H2 Conc (ppm)",
    "gas_sampling_volume_ml": "Gas Sample Vol (mL)",
    "gas_sampling_pressure_MPa": "Gas Pressure (MPa)",
    "final_ph": "Final pH",
    "ferrous_iron_yield": "Fe2+ Yield (%)",
    "final_dissolved_oxygen_mg_L": "Final DO (mg/L)",
    "final_conductivity_mS_cm": "Conductivity (mS/cm)",
    "overwrite": "Overwrite"
}
