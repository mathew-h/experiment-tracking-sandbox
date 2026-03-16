from sqlalchemy import Column, Integer, String, DateTime, Float, JSON, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from ..database import Base

class Analyte(Base):
    __tablename__ = "analytes"

    id = Column(Integer, primary_key=True, index=True)  # analyte_id
    analyte_symbol = Column(String, unique=True, nullable=False, index=True)  # e.g., FeO, SiO2
    unit = Column(String, nullable=False)  # e.g., ppm, %
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    elemental_results = relationship("ElementalAnalysis", back_populates="analyte")


class ElementalAnalysis(Base):
    __tablename__ = "elemental_analysis"

    id = Column(Integer, primary_key=True, index=True)
    
    # Link to parent ExternalAnalysis (grouping container)
    external_analysis_id = Column(Integer, ForeignKey("external_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Optional direct link to SampleInfo (for backward compatibility or direct sample access)
    # Made nullable to support experiment-linked analyses
    sample_id = Column(String, ForeignKey("sample_info.sample_id", ondelete="CASCADE"), nullable=True, index=True)
    
    analyte_id = Column(Integer, ForeignKey("analytes.id", ondelete="CASCADE"), nullable=False, index=True)
    analyte_composition = Column(Float, nullable=True)  # numeric value in the unit defined by Analyte.unit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Uniqueness: one row per (external_analysis_id, analyte_id)
    __table_args__ = (
        UniqueConstraint('external_analysis_id', 'analyte_id', name='uq_elemental_analysis_ext_analyte'),
    )

    # Relationships
    analyte = relationship("Analyte", back_populates="elemental_results")
    external_analysis = relationship("ExternalAnalysis", backref="elemental_analysis") # Backref for easy access
