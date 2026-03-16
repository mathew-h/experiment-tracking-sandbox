# database/models/enums.py
import enum

# === Experiment-Related Enums ===
class ExperimentStatus(enum.Enum):
    """Status of an experiment"""
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED" 
    CANCELLED = "CANCELLED"

class ExperimentType(enum.Enum):
    """Type of experimental setup"""
    SERUM = "Serum"
    AUTOCLAVE = "Autoclave"
    HPHT = "HPHT"
    CF = "Core Flood"
    OTHER = "Other"

class FeedstockType(enum.Enum):
    """Type of feedstock used in experiment"""
    NITROGEN = "Nitrogen"
    NITRATE = "Nitrate"
    BLANK = "Blank"

# === Component-Related Enums ===
class ComponentType(enum.Enum):
    """Type of experimental component"""
    CATALYST = "catalyst"
    PROMOTER = "promoter"
    SUPPORT = "support"
    ADDITIVE = "additive"
    INHIBITOR = "inhibitor"  # Future expansion

# === Analysis-Related Enums ===
class AnalysisType(enum.Enum):
    """Type of external analysis performed"""
    PXRF = "pXRF"
    XRD = "XRD"
    SEM = "SEM"
    ELEMENTAL = "Elemental"
    MAGNETIC_SUSCEPTIBILITY = "Magnetic Susceptibility"
    TITRATION = "Titration"  # New addition
    OTHER = "Other"

class AmmoniumQuantMethod(enum.Enum):
    """Method used for quantifying ammonium"""
    NMR = "NMR"
    COLORIMETRIC_ASSAY = "Colorimetric Assay"
    ION_CHROMATOGRAPHY = "Ion Chromatography"  # Future expansion

class TitrationType(enum.Enum):
    """Type of titration analysis"""
    ACID_BASE = "Acid-Base"
    COMPLEXOMETRIC = "Complexometric"
    REDOX = "Redox"
    PRECIPITATION = "Precipitation"

# # === File-Related Enums ===
# class FileType(enum.Enum):
#     """Type of uploaded file"""
#     IMAGE = "image"
#     DOCUMENT = "document"
#     DATA = "data"
#     SPECTRUM = "spectrum"
#     OTHER = "other"

# # === Quality/Status Enums ===
# class DataQuality(enum.Enum):
#     """Quality assessment of data"""
#     EXCELLENT = "excellent"
#     GOOD = "good"
#     FAIR = "fair"
#     POOR = "poor"
#     INVALID = "invalid"

# class ValidationStatus(enum.Enum):
#     """Validation status of data entry"""
#     PENDING = "pending"
#     VALIDATED = "validated"
#     REJECTED = "rejected"
#     NEEDS_REVIEW = "needs_review"

# === Rock/Sample Enums ===
# class RockClassification(enum.Enum):
#     """Basic rock classification types"""
#     IGNEOUS = "Igneous"
#     SEDIMENTARY = "Sedimentary"
#     METAMORPHIC = "Metamorphic"
#     UNKNOWN = "Unknown"

class CharacterizationStatus(enum.Enum):
    """Status of sample characterization"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"

# === Unit Enums (for future validation) ===
class ConcentrationUnit(enum.Enum):
    """Units for concentration measurements"""
    PPM = "ppm"
    MILLIMOLAR = "mM"
    MOLAR = "M"
    PERCENT = "%"
    WEIGHT_PERCENT = "wt%"

class PressureUnit(enum.Enum):
    """Units for pressure measurements"""
    PSI = "psi"
    BAR = "bar"
    ATM = "atm"
    PA = "Pa"
    KPA = "kPa"
    MPA = "MPa"

class AmountUnit(enum.Enum):
    """Units for mass and volume measurements"""
    GRAM = "g"
    MILLIGRAM = "mg"
    MICROGRAM = "μg"
    KILOGRAM = "kg"
    MICROLITER = "μL"
    MILLILITER = "mL"
    LITER = "L"
    MICROMOLE = "μmol"
    MILLIMOLE = "mmol"
    MOLE = "mol"
    # Added concentration-style units for additive entry convenience
    PPM = "ppm"
    MILLIMOLAR = "mM"
    MOLAR = "M"
    PERCENT = "%"
    WEIGHT_PERCENT = "wt%"
    PERCENT_OF_ROCK = "% of Rock"