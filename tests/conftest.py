import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from azure.storage.blob import BlobServiceClient, BlobClient
import datetime

from database import Base, PXRFReading, Experiment, ExperimentalConditions, ExperimentalResults, ScalarResults, ICPResults

@pytest.fixture
def test_db() -> Session:
    """Create a test database session for use in tests."""
    # Create an in-memory SQLite database for testing
    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool
    )
    
    # Create all tables in the test database
    Base.metadata.create_all(engine)
    
    # Create a session factory
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create a new session for the test
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        # Clean up after the test
        db.close()
        Base.metadata.drop_all(engine)

@pytest.fixture
def pxrf_reading(test_db):
    """Create a sample pXRF reading entry."""
    reading = PXRFReading(
        reading_no="TEST001",
        fe=10.5,
        mg=2.3,
        ni=0.5,
        cu=0.3,
        si=45.2,
        co=0.1,
        mo=0.02,
        al=8.4
    )
    test_db.add(reading)
    test_db.commit()
    return reading 

@pytest.fixture
def test_experiment(test_db: Session) -> Experiment:
    """Create a sample Experiment with basic conditions."""
    conditions = ExperimentalConditions(
        experiment_id="YIELD_TEST_001",
        rock_mass_g=100.0,  # grams
        water_volume_mL=500.0, # mL
        temperature_c=25.0,
        room_temp_pressure_psi=14.7, # Using a valid pressure field (psi)
        stir_speed_rpm=300          # Corrected field name (RPM)
    )
    experiment = Experiment(
        experiment_id="YIELD_TEST_001",
        date=datetime.date.today(),
    )
    # Link conditions to experiment correctly
    experiment.conditions = conditions
    # Set required fields for Experiment that were missing
    experiment.experiment_number = 1 # Assign a dummy number for test
    experiment.status = 'PLANNED' # Assign default status

    test_db.add(experiment) # Add experiment first to get ID
    test_db.flush() # Flush to get the experiment.id

    # Set the foreign key and string ID on conditions *after* experiment has ID
    conditions.experiment_fk = experiment.id
    conditions.experiment_id = experiment.experiment_id

    test_db.commit()
    test_db.refresh(experiment)
    test_db.refresh(conditions)
    return experiment

@pytest.fixture
def test_experimental_result(test_db: Session, test_experiment: Experiment) -> ExperimentalResults:
    """Create a base ExperimentalResults entry linked to the test experiment."""
    result_entry = ExperimentalResults(
        experiment_fk=test_experiment.id,
        time_post_reaction_days=1.0,
        description="Test result entry"
    )
    test_db.add(result_entry)
    test_db.commit()
    test_db.refresh(result_entry)
    return result_entry

@pytest.fixture
def test_scalar_result(test_db: Session, test_experimental_result: ExperimentalResults) -> ScalarResults:
    """Create a ScalarResults entry linked to the test ExperimentalResults."""
    scalar_data = ScalarResults(
        result_id=test_experimental_result.id,
        final_ph=7.0,  # Add some dummy data
        gross_ammonium_concentration_mM=10.5,
        ammonium_quant_method='NMR'
    )
    # Manually link back (SQLAlchemy doesn't always do this automatically before commit)
    test_experimental_result.scalar_data = scalar_data
    test_db.add(scalar_data)
    test_db.commit()
    test_db.refresh(scalar_data)
    test_db.refresh(test_experimental_result) # Refresh parent too
    return scalar_data 