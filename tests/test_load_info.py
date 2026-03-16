import pytest
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime

# --- Adjust path to import from project root ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from database import Base, SampleInfo, ExternalAnalysis, PXRFReading
# Some older tests referenced ELEMENT_COLUMNS; new config uses PXRF_ELEMENT_COLUMNS
try:
    from frontend.config.variable_config import ELEMENT_COLUMNS  # legacy name
except Exception:
    from frontend.config.variable_config import PXRF_ELEMENT_COLUMNS as ELEMENT_COLUMNS
# Import the function to test
from frontend.components.load_info import get_external_analyses

# --- Test Fixtures ---

@pytest.fixture(scope='function')
def test_db_session():
    """Creates an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)

def test_get_external_analyses_with_pxrf(test_db: Session):
    """Test retrieving external analyses with pXRF data."""
    # Create test data
    sample_id = "TEST-001"
    
    # Create SampleInfo first
    sample_info = SampleInfo(
        sample_id=sample_id,
        rock_classification="Test Rock",
        state="Test State",
        country="Test Country"
    )
    test_db.add(sample_info)
    test_db.commit()
    
    # Create a pXRF analysis with two readings
    pxrf_analysis = ExternalAnalysis(
        sample_id=sample_id,
        sample_info_id=sample_info.id,
        analysis_type="pXRF",
        analysis_date=datetime.now(),
        laboratory="Test Lab",
        analyst="Test Analyst",
        pxrf_reading_no="1,2",
        description="Test pXRF Analysis"
    )
    test_db.add(pxrf_analysis)
    
    # Create two pXRF readings with valid columns
    reading1 = PXRFReading(
        reading_no="1",
        fe=10000,
        mg=500,
        ni=300,
        cu=200,
        si=100,
        co=50,
        mo=25,
        al=1000
    )
    reading2 = PXRFReading(
        reading_no="2",
        fe=12000,
        mg=600,
        ni=400,
        cu=250,
        si=150,
        co=75,
        mo=30,
        al=1200
    )
    test_db.add_all([reading1, reading2])
    test_db.commit()

    # Get analyses
    analyses = get_external_analyses(sample_id, test_db)
    
    # Assertions
    assert len(analyses) == 1
    analysis = analyses[0]
    assert analysis['analysis_type'] == "pXRF"
    assert analysis['pxrf_reading_no'] == "1,2"
    
    # Check pXRF readings
    assert len(analysis['pxrf_readings']) == 2
    readings = sorted(analysis['pxrf_readings'], key=lambda x: x['reading_no'])
    
    # Check first reading
    assert readings[0]['reading_no'] == "1"
    assert readings[0]['fe'] == 10000
    assert readings[0]['mg'] == 500
    assert readings[0]['ni'] == 300
    assert readings[0]['cu'] == 200
    assert readings[0]['si'] == 100
    assert readings[0]['co'] == 50
    assert readings[0]['mo'] == 25
    assert readings[0]['al'] == 1000
    
    # Check second reading
    assert readings[1]['reading_no'] == "2"
    assert readings[1]['fe'] == 12000
    assert readings[1]['mg'] == 600
    assert readings[1]['ni'] == 400
    assert readings[1]['cu'] == 250
    assert readings[1]['si'] == 150
    assert readings[1]['co'] == 75
    assert readings[1]['mo'] == 30
    assert readings[1]['al'] == 1200

def test_get_external_analyses_no_pxrf(test_db: Session):
    """Test retrieving non-pXRF analyses."""
    # Create test data
    sample_id = "TEST-002"
    
    # Create SampleInfo first
    sample_info = SampleInfo(
        sample_id=sample_id,
        rock_classification="Test Rock",
        state="Test State",
        country="Test Country"
    )
    test_db.add(sample_info)
    test_db.commit()
    
    # Create a non-pXRF analysis
    analysis = ExternalAnalysis(
        sample_id=sample_id,
        sample_info_id=sample_info.id,
        analysis_type="XRD",
        analysis_date=datetime.now(),
        laboratory="Test Lab",
        analyst="Test Analyst",
        description="Test XRD Analysis"
    )
    test_db.add(analysis)
    test_db.commit()

    # Get analyses
    analyses = get_external_analyses(sample_id, test_db)
    
    # Assertions
    assert len(analyses) == 1
    assert analyses[0]['analysis_type'] == "XRD"
    assert analyses[0]['pxrf_readings'] == []

def test_get_external_analyses_pxrf_no_readings_linked(test_db: Session):
    """Test retrieving pXRF analysis with no readings linked."""
    # Create test data
    sample_id = "TEST-003"
    
    # Create SampleInfo first
    sample_info = SampleInfo(
        sample_id=sample_id,
        rock_classification="Test Rock",
        state="Test State",
        country="Test Country"
    )
    test_db.add(sample_info)
    test_db.commit()
    
    # Create a pXRF analysis with no readings linked
    analysis = ExternalAnalysis(
        sample_id=sample_id,
        sample_info_id=sample_info.id,
        analysis_type="pXRF",
        analysis_date=datetime.now(),
        laboratory="Test Lab",
        analyst="Test Analyst",
        description="Test pXRF Analysis"
    )
    test_db.add(analysis)
    test_db.commit()

    # Get analyses
    analyses = get_external_analyses(sample_id, test_db)
    
    # Assertions
    assert len(analyses) == 1
    assert analyses[0]['analysis_type'] == "pXRF"
    assert analyses[0]['pxrf_readings'] == []

def test_get_external_analyses_pxrf_readings_not_in_db(test_db: Session):
    """Test retrieving pXRF analysis with non-existent reading numbers."""
    # Create test data
    sample_id = "TEST-004"
    
    # Create SampleInfo first
    sample_info = SampleInfo(
        sample_id=sample_id,
        rock_classification="Test Rock",
        state="Test State",
        country="Test Country"
    )
    test_db.add(sample_info)
    test_db.commit()
    
    # Create a pXRF analysis with non-existent reading numbers
    analysis = ExternalAnalysis(
        sample_id=sample_id,
        sample_info_id=sample_info.id,
        analysis_type="pXRF",
        analysis_date=datetime.now(),
        laboratory="Test Lab",
        analyst="Test Analyst",
        pxrf_reading_no="999,1000",
        description="Test pXRF Analysis"
    )
    test_db.add(analysis)
    test_db.commit()

    # Get analyses
    analyses = get_external_analyses(sample_id, test_db)
    
    # Assertions
    assert len(analyses) == 1
    assert analyses[0]['analysis_type'] == "pXRF"
    assert analyses[0]['pxrf_reading_no'] == "999,1000"
    assert analyses[0]['pxrf_readings'] == [] 