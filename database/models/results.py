from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Text, Index, Boolean, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from typing import Dict
from ..database import Base

class ExperimentalResults(Base):
    __tablename__ = "experimental_results"
    __table_args__ = (
        Index(
            "uq_primary_result_per_experiment_bucket",
            "experiment_fk",
            "time_post_reaction_bucket_days",
            unique=True,
            postgresql_where=text("is_primary_timepoint_result = true"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    experiment_fk = Column(Integer,
                           ForeignKey("experiments.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    time_post_reaction_days = Column(Float, nullable=True, index=True) # Time in days post-reaction start
    time_post_reaction_bucket_days = Column(Float, nullable=True, index=True) # Normalized bucket for tolerant matching
    cumulative_time_post_reaction_days = Column(Float, nullable=True, index=True) # Cumulative time across lineage chain (days)
    is_primary_timepoint_result = Column(Boolean, nullable=False, default=True, server_default=text("true"), index=True)
    description = Column(Text, nullable=False)

    # Brine modification tracking — operational metadata about what happened at this timepoint
    brine_modification_description = Column(Text, nullable=True)
    has_brine_modification = Column(Boolean, nullable=False, default=False, server_default=text("false"), index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    @validates('brine_modification_description')
    def sync_brine_flag(self, key, value):
        """Auto-sync has_brine_modification whenever brine_modification_description is set."""
        self.has_brine_modification = bool(value and str(value).strip())
        return value

    # Relationship
    experiment = relationship("Experiment", back_populates="results", foreign_keys=[experiment_fk])
    # Relationship to ResultFiles (one-to-many)
    files = relationship("ResultFiles", back_populates="result_entry", cascade="all, delete-orphan")

    # Relationships to specific data tables (one-to-one)
    scalar_data = relationship(
        "ScalarResults",
        back_populates="result_entry",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    icp_data = relationship(
        "ICPResults",
        back_populates="result_entry",
        uselist=False,
        cascade="all, delete-orphan"
    )

    # No unique constraints - allow multiple results per experiment/time combination

class ScalarResults(Base):
    __tablename__ = "scalar_results"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("experimental_results.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Scalar fields
    ferrous_iron_yield = Column(Float, nullable=True)  # in percentage
    gross_ammonium_concentration_mM = Column(Float, nullable=True)  # in mM
    background_ammonium_concentration_mM = Column(Float, nullable=True, default=0.2, server_default=text("0.2"))  # in mM
    ammonium_quant_method = Column(String, nullable=True) # e.g., 'NMR', 'Colorimetric Assay'
    grams_per_ton_yield = Column(Float, nullable=True)  # yield in g/ton
    final_ph = Column(Float, nullable=True)
    final_nitrate_concentration_mM = Column(Float, nullable=True)  # in mM
    final_dissolved_oxygen_mg_L = Column(Float, nullable=True) # in ppm
    co2_partial_pressure_MPa = Column(Float, nullable=True) # in psi
    final_conductivity_mS_cm = Column(Float, nullable=True) # in uS/cm
    final_alkalinity_mg_L = Column(Float, nullable=True) # in mg/L CaCO3
    sampling_volume_mL = Column(Float, nullable=True) # in mL
    measurement_date = Column(DateTime(timezone=True), nullable=True)
    nmr_run_date = Column(DateTime(timezone=True), nullable=True)
    icp_run_date = Column(DateTime(timezone=True), nullable=True)
    gc_run_date = Column(DateTime(timezone=True), nullable=True)
    xrd_run_date = Column(DateTime(timezone=True), nullable=True)

    # Hydrogen tracking inputs
    h2_concentration = Column(Float, nullable=True)  # ppm (vol/vol)
    h2_concentration_unit = Column(String, nullable=True)  # always 'ppm'
    gas_sampling_volume_ml = Column(Float, nullable=True)  # mL at sampling conditions
    gas_sampling_pressure_MPa = Column(Float, nullable=True)  # MPa at sampling conditions

    # Hydrogen derived outputs (stored as microunits per requirements)
    h2_micromoles = Column(Float, nullable=True)  # micromoles (μmol)
    h2_mass_ug = Column(Float, nullable=True)  # micrograms (μg)
    # Hydrogen yield normalized by rock mass (g/ton rock)
    h2_grams_per_ton_yield = Column(Float, nullable=True)

    # Ferrous iron yield derived from H2 and NH3 measurements
    ferrous_iron_yield_h2_pct = Column(Float, nullable=True)   # H2-derived Fe(II) yield (%)
    ferrous_iron_yield_nh3_pct = Column(Float, nullable=True)  # NH3-derived Fe(II) yield (%)

    background_experiment_id = Column(String, nullable=True)
    background_experiment_fk = Column(Integer, ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True)
    background_experiment = relationship("Experiment", back_populates="scalar_data", foreign_keys=[background_experiment_fk])
    # Relationship back to the main entry using result_id
    result_entry = relationship(
        "ExperimentalResults",
        back_populates="scalar_data",
    )

    @validates('h2_concentration', 'gas_sampling_volume_ml', 'gas_sampling_pressure_MPa')
    def validate_non_negative(self, key, value):
        if value is not None and value < 0:
            raise ValueError(f"{key} must be non-negative.")
        return value

    @validates('h2_concentration_unit')
    def validate_h2_unit(self, key, value):
        if value is None:
            return value
        if value != 'ppm':
            raise ValueError("h2_concentration_unit must be 'ppm'")
        return value

class ICPResults(Base):
    __tablename__ = "icp_results"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("experimental_results.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Fixed columns for common elements (all concentrations in ppm)
    fe = Column(Float, nullable=True)   # Iron
    si = Column(Float, nullable=True)   # Silicon
    ni = Column(Float, nullable=True)   # Nickel
    cu = Column(Float, nullable=True)   # Copper
    mo = Column(Float, nullable=True)   # Molybdenum
    ca = Column(Float, nullable=True)   # Calcium
    zn = Column(Float, nullable=True)   # Zinc
    mn = Column(Float, nullable=True)   # Manganese
    cr = Column(Float, nullable=True)   # Chromium
    co = Column(Float, nullable=True)   # Cobalt
    mg = Column(Float, nullable=True)   # Magnesium
    al = Column(Float, nullable=True)   # Aluminum
    sr = Column(Float, nullable=True)   # Strontium
    y = Column(Float, nullable=True)   # Yttrium
    nb = Column(Float, nullable=True)   # Niobium
    sb = Column(Float, nullable=True)   # Antimony
    cs = Column(Float, nullable=True)   # Cesium
    ba = Column(Float, nullable=True)   # Barium
    nd = Column(Float, nullable=True)   # Neodymium
    gd = Column(Float, nullable=True)   # Gadolinium
    pt = Column(Float, nullable=True)   # Platinum
    rh = Column(Float, nullable=True)   # Rhodium
    ir = Column(Float, nullable=True)   # Iridium
    pd = Column(Float, nullable=True)   # Palladium
    ru = Column(Float, nullable=True)   # Ruthenium
    os = Column(Float, nullable=True)   # Osmium
    tl = Column(Float, nullable=True)   # Thallium

    # JSON storage for all elements (including the fixed ones above for completeness)
    all_elements = Column(JSONB, nullable=True)  # e.g., {"fe": 125.0, "mg": 45.8, "ca": 12.3, "k": 8.9}
    
    # ICP-specific metadata
    dilution_factor = Column(Float, nullable=True)
    measurement_date = Column(DateTime(timezone=True), nullable=True)
    sample_date = Column(DateTime(timezone=True), nullable=True)
    instrument_used = Column(String, nullable=True)
    detection_limits = Column(JSONB, nullable=True)  # Store per-element detection limits
    raw_label = Column(String, nullable=True)  # Original sample label from ICP file
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship back to the main entry using result_id
    result_entry = relationship(
        "ExperimentalResults",
        back_populates="icp_data",
    )

    @validates('all_elements', 'detection_limits')
    def validate_json(self, key, value):
        if value is not None and not isinstance(value, dict):
            raise ValueError(f"{key} must be a valid JSON object.")
        return value

    def get_element_concentration(self, element_symbol: str) -> float:
        """
        Get concentration for any element, checking fixed columns first, then JSON.
        
        Args:
            element_symbol: Element symbol (e.g., 'Fe', 'Mg', 'Ca')
            
        Returns:
            Concentration in ppm, or 0 if not found
        """
        element_lower = element_symbol.lower()
        
        # Check fixed columns first (faster)
        if hasattr(self, element_lower):
            value = getattr(self, element_lower)
            if value is not None:
                return value
        
        # Check JSON storage
        if self.all_elements and isinstance(self.all_elements, dict):
            return self.all_elements.get(element_lower, 0)
        
        return 0

    def get_all_detected_elements(self) -> Dict[str, float]:
        """
        Get all detected elements with their concentrations.
        
        Returns:
            Dictionary of {element: concentration_ppm}
        """
        # Import at runtime to avoid circular dependency
        from frontend.config.variable_config import ICP_FIXED_ELEMENT_FIELDS
        
        elements = {}
        
        # Add fixed columns
        for element in ICP_FIXED_ELEMENT_FIELDS:
            value = getattr(self, element)
            if value is not None:
                elements[element] = value
        
        # Add JSON elements (may override fixed columns with same values)
        if self.all_elements and isinstance(self.all_elements, dict):
            elements.update(self.all_elements)
        
        return elements

class ResultFiles(Base):
    __tablename__ = "result_files"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("experimental_results.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String, nullable=False)
    file_name = Column(String)
    file_type = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to the specific result entry
    result_entry = relationship("ExperimentalResults", back_populates="files")
