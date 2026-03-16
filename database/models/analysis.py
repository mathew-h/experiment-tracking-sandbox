from sqlalchemy import Column, Integer, String, DateTime, Float, JSON, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from typing import Dict
from ..database import Base

class AnalysisFiles(Base):
    __tablename__ = "analysis_files"

    id = Column(Integer, primary_key=True, index=True)
    external_analysis_id = Column(Integer, ForeignKey("external_analyses.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String, nullable=False)
    file_name = Column(String)
    file_type = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    external_analysis = relationship("ExternalAnalysis", back_populates="analysis_files")

class ExternalAnalysis(Base):
    __tablename__ = "external_analyses"

    id = Column(Integer, primary_key=True, index=True)
    # Add ondelete="CASCADE"
    sample_id = Column(String, ForeignKey("sample_info.sample_id", ondelete="CASCADE"), nullable=True, index=True)
    experiment_fk = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=True, index=True)
    experiment_id = Column(String, nullable=True, index=True)  # Human-readable experiment ID
    
    analysis_type = Column(String)  # General type/category (e.g., 'Elemental Scan', 'Mineralogy')
    analysis_date = Column(DateTime(timezone=True))
    laboratory = Column(String, nullable=True)
    analyst = Column(String, nullable=True)
    # Store comma-separated pXRF reading numbers (e.g., "2,3,4" for multiple readings)
    # No FK constraint to allow multiple readings per sample
    pxrf_reading_no = Column(String, nullable=True, index=True)
    description = Column(Text)
    analysis_metadata = Column(JSON)  # For storing additional analysis-specific data
    # Add magnetic susceptibility field
    magnetic_susceptibility = Column(String, nullable=True)  # Store as string to maintain flexibility
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    # Updated sample_info relationship
    sample_info = relationship(
        "SampleInfo",
        back_populates="external_analyses",
        foreign_keys=[sample_id] # Join on sample_id
    )
    
    experiment = relationship(
        "Experiment",
        back_populates="external_analyses",
        foreign_keys=[experiment_fk]
    )
    
    analysis_files = relationship("AnalysisFiles", back_populates="external_analysis", cascade="all, delete-orphan")
    # Add one-to-one relationships for specific analysis types
    xrd_analysis = relationship("XRDAnalysis", back_populates="external_analysis", uselist=False, cascade="all, delete-orphan")




class PXRFReading(Base):
    __tablename__ = "pxrf_readings"

    # Using Reading No as the primary key - ensure it's treated as string consistently
    reading_no = Column(String, primary_key=True, index=True)

    # Elemental data columns - nullable allows for missing data in source
    fe = Column(Float, name="Fe", nullable=True)
    mg = Column(Float, name="Mg", nullable=True)
    ni = Column(Float, name="Ni", nullable=True)
    cu = Column(Float, name="Cu", nullable=True)
    si = Column(Float, name="Si", nullable=True)
    co = Column(Float, name="Co", nullable=True)
    mo = Column(Float, name="Mo", nullable=True)
    al = Column(Float, name="Al", nullable=True)
    ca = Column(Float, name="Ca", nullable=True)
    k = Column(Float, name="K", nullable=True)
    au = Column(Float, name="Au", nullable=True)
    zn = Column(Float, name="Zn", nullable=True)
    # Add other elements as needed, matching REQUIRED_COLUMNS in ingestion script

    # Timestamps for tracking ingestion
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<PXRFReading(reading_no='{self.reading_no}')>"
