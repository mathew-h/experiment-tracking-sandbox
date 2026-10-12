from .database import Base, engine, SessionLocal, get_db, init_db
from .models import (
    # Experiments
    Experiment, ExperimentNotes, ModificationsLog,
    # Conditions
    ExperimentalConditions,
    # Results
    ExperimentalResults, ScalarResults, ICPResults, ResultFiles,
    # Samples
    SampleInfo, SamplePhotos,
    # Analysis
    AnalysisFiles, ExternalAnalysis, XRDAnalysis, XRDPhase, PXRFReading, Analyte, ElementalAnalysis,
    # Enums
    ExperimentStatus, ExperimentType, FeedstockType, ComponentType,
    AnalysisType, AmmoniumQuantMethod, TitrationType, CharacterizationStatus,
    ConcentrationUnit, PressureUnit, AmountUnit
)
# Import chemicals after other models to avoid circular imports
from .models import Compound, ChemicalAdditive

# Configure all mappers after all models are imported
# This resolves string references in relationships
from sqlalchemy.orm import configure_mappers
try:
    configure_mappers()
except Exception as e:
    # If mapper configuration fails, log but don't crash
    import logging
    logging.warning(f"Mapper configuration warning: {e}")

__all__ = [
    # Database utilities
    'Base',
    'engine',
    'SessionLocal',
    'get_db',
    'init_db',
    # Experiments
    'Experiment', 'ExperimentNotes', 'ModificationsLog',
    # Conditions
    'ExperimentalConditions',
    # Results
    'ExperimentalResults', 'ScalarResults', 'ICPResults', 'ResultFiles',
    # Samples
    'SampleInfo', 'SamplePhotos',
    # Analysis
    'AnalysisFiles', 'ExternalAnalysis', 'XRDAnalysis', 'XRDPhase', 'PXRFReading', 'Analyte', 'ElementalAnalysis',
    # Chemicals
    'Compound', 'ChemicalAdditive',
    # Enums
    'ExperimentStatus', 'ExperimentType', 'FeedstockType', 'ComponentType',
    'AnalysisType', 'AmmoniumQuantMethod', 'TitrationType', 'CharacterizationStatus',
    'ConcentrationUnit', 'PressureUnit', 'AmountUnit'
] 