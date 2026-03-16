# Import all models to make them available at package level
from .experiments import Experiment, ExperimentNotes, ModificationsLog
from .conditions import ExperimentalConditions
from .results import ExperimentalResults, ScalarResults, ICPResults, ResultFiles
from .samples import SampleInfo, SamplePhotos
from .analysis import AnalysisFiles, ExternalAnalysis, PXRFReading
from .xrd import XRDAnalysis, XRDPhase
from .chemicals import Compound, ChemicalAdditive
from .characterization import *  # Future characterization models
from .enums import (
    ExperimentStatus, ExperimentType, FeedstockType, ComponentType,
    AnalysisType, AmmoniumQuantMethod, TitrationType, CharacterizationStatus,
    ConcentrationUnit, PressureUnit, AmountUnit
)

# Ensure all models are available at package level
__all__ = [
    # Experiments
    'Experiment', 'ExperimentNotes', 'ModificationsLog',
    # Conditions
    'ExperimentalConditions',
    # Results
    'ExperimentalResults', 'ScalarResults', 'ICPResults', 'ResultFiles',
    # Samples
    'SampleInfo', 'SamplePhotos',
    # Analysis
    'AnalysisFiles', 'ExternalAnalysis', 'XRDAnalysis', 'PXRFReading', 'XRDPhase',
    'Analyte', 'ElementalAnalysis',
    # Chemicals
    'Compound', 'ChemicalAdditive',
    # Enums
    'ExperimentStatus', 'ExperimentType', 'FeedstockType', 'ComponentType',
    'AnalysisType', 'AmmoniumQuantMethod', 'TitrationType', 'CharacterizationStatus',
    'ConcentrationUnit', 'PressureUnit', 'AmountUnit',
]
