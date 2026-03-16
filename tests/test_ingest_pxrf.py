import pytest
import pandas as pd
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# --- Adjust path to import from project root ---
# This assumes your 'tests' directory is at the project root.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from database import Base, PXRFReading
# Import the function to test *after* potentially patching its dependencies
# We will patch PXRF_DATA_PATH and SessionLocal/engine inside tests or fixtures

# --- Test Fixtures ---

@pytest.fixture(scope='function')
def test_db_session():
    """Creates an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)  # Create tables
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session # Provide the session to the test
    finally:
        session.close()
        Base.metadata.drop_all(engine) # Clean up tables

@pytest.fixture(scope='function')
def mock_excel_file(tmp_path):
    """Creates a temporary Excel file for testing ingestion."""
    def _create_file(data: dict, filename="test_pxrf_data.xlsx"):
        file_path = tmp_path / filename
        df = pd.DataFrame(data)
        df.to_excel(file_path, index=False)
        return str(file_path) # Return the path as a string
    return _create_file

# --- Test Cases ---

def test_ingest_new_data(test_db_session: Session, mock_excel_file, monkeypatch):
    """Test ingesting data into an empty database."""
    # Arrange: Prepare Excel data and patch dependencies
    excel_data = {
        'Reading No': ['1', '2', '3'],
        'Fe': [10.1, 12.5, 15.0],
        'Mg': [5.5, 6.0, '' ], # Test empty string -> 0
        'Ni': [1.0, '<LOD', 1.5], # Test <LOD -> 0
        'Cu': [0.5, None, 0.8], # Test None -> 0
        'Si': [20.0, 'N/A', 25.0], # Test N/A -> 0
        'Co': [0.1, 0.2, 'n.d.'], # Test n.d. -> 0
        'Mo': [0.01, 0.02, 0.03],
        'Al': [8.0, 9.0, 10.0]
    }
    test_file_path = mock_excel_file(excel_data)

    # Dynamically import here after setup, or patch before import
    from database.ingest_pxrf import ingest_pxrf_data, SessionLocal as IngestSessionLocal

    # Patch the session maker used by the script and the file path
    monkeypatch.setattr("database.ingest_pxrf.PXRF_DATA_PATH", test_file_path)
    monkeypatch.setattr("database.ingest_pxrf.SessionLocal", lambda: test_db_session)

    # Act: Run the ingestion function
    ingest_pxrf_data(file_path=test_file_path, update_existing=False)

    # Assert: Check database content
    readings = test_db_session.query(PXRFReading).order_by(PXRFReading.reading_no).all()
    assert len(readings) == 3

    # --- Check Reading 1 (standard data) ---
    r1 = readings[0]
    assert r1.reading_no == '1'
    assert isinstance(r1.reading_no, str)
    assert r1.fe == pytest.approx(10.1)
    assert r1.mg == pytest.approx(5.5)
    assert r1.ni == pytest.approx(1.0)
    assert r1.cu == pytest.approx(0.5)
    assert r1.si == pytest.approx(20.0)
    assert r1.co == pytest.approx(0.1)
    assert r1.mo == pytest.approx(0.01)
    assert r1.al == pytest.approx(8.0)
    # Check data types
    assert isinstance(r1.fe, float)
    assert isinstance(r1.mg, float)
    assert isinstance(r1.ni, float)
    assert isinstance(r1.cu, float)
    assert isinstance(r1.si, float)
    assert isinstance(r1.co, float)
    assert isinstance(r1.mo, float)
    assert isinstance(r1.al, float)

    # --- Check Reading 2 (cleaned data) ---
    r2 = readings[1]
    assert r2.reading_no == '2'
    assert isinstance(r2.reading_no, str)
    assert r2.fe == pytest.approx(12.5)
    assert r2.mg == pytest.approx(6.0)
    assert r2.ni == pytest.approx(0.0)    # '<LOD' became 0
    assert r2.cu == pytest.approx(0.0)    # None became 0
    assert r2.si == pytest.approx(0.0)    # 'N/A' became 0
    assert r2.co == pytest.approx(0.2)
    assert r2.mo == pytest.approx(0.02)
    assert r2.al == pytest.approx(9.0)
    # Check data types
    assert isinstance(r2.ni, float)
    assert isinstance(r2.cu, float)
    assert isinstance(r2.si, float)

    # --- Check Reading 3 (cleaned data) ---
    r3 = readings[2]
    assert r3.reading_no == '3'
    assert isinstance(r3.reading_no, str)
    assert r3.fe == pytest.approx(15.0)
    assert r3.mg == pytest.approx(0.0)    # '' became 0
    assert r3.ni == pytest.approx(1.5)
    assert r3.cu == pytest.approx(0.8)
    assert r3.si == pytest.approx(25.0)
    assert r3.co == pytest.approx(0.0)    # 'n.d.' became 0
    assert r3.mo == pytest.approx(0.03)
    assert r3.al == pytest.approx(10.0)
    # Check data types
    assert isinstance(r3.mg, float)
    assert isinstance(r3.co, float)

def test_skip_existing_data(test_db_session: Session, mock_excel_file, monkeypatch, capsys):
    """Test skipping existing records when update_existing=False."""
    # Arrange: Pre-populate DB and prepare Excel
    initial_reading = PXRFReading(reading_no='10', fe=1.0, mg=1.0, ni=1.0, cu=1.0, si=1.0, co=1.0, mo=1.0, al=1.0)
    test_db_session.add(initial_reading)
    test_db_session.commit()

    excel_data = {
        'Reading No': ['10', '11'], # 10 exists, 11 is new
        'Fe': [99.9, 2.0], # Try to change 10's Fe
        'Mg': [99.9, 2.0],
        'Ni': [99.9, 2.0],
        'Cu': [99.9, 2.0],
        'Si': [99.9, 2.0],
        'Co': [99.9, 2.0],
        'Mo': [99.9, 2.0],
        'Al': [99.9, 2.0]
    }
    test_file_path = mock_excel_file(excel_data)

    from database.ingest_pxrf import ingest_pxrf_data
    monkeypatch.setattr("database.ingest_pxrf.PXRF_DATA_PATH", test_file_path)
    monkeypatch.setattr("database.ingest_pxrf.SessionLocal", lambda: test_db_session)

    # Act
    ingest_pxrf_data(file_path=test_file_path, update_existing=False) # Important flag

    # Assert
    captured = capsys.readouterr() # Capture print output for summary check
    assert "New readings inserted: 1" in captured.out
    assert "Existing readings skipped: 1" in captured.out
    assert "Existing readings updated: 0" in captured.out

    readings = test_db_session.query(PXRFReading).order_by(PXRFReading.reading_no).all()
    assert len(readings) == 2 # Initial 10 + new 11

    # Check that reading 10 was NOT updated
    reading10 = test_db_session.query(PXRFReading).filter(PXRFReading.reading_no == '10').first()
    assert reading10.fe == pytest.approx(1.0) # Should still be the initial value
    assert reading10.mg == pytest.approx(1.0)

    # Check that reading 11 was inserted
    reading11 = test_db_session.query(PXRFReading).filter(PXRFReading.reading_no == '11').first()
    assert reading11 is not None
    assert reading11.fe == pytest.approx(2.0)

# def test_update_existing_data(test_db_session: Session, mock_excel_file, monkeypatch, capsys):
#     """Test updating existing records when update_existing=True."""
#     # Arrange: Pre-populate DB and prepare Excel with CHANGES
#     initial_reading = PXRFReading(reading_no='20', fe=1.0, mg=1.0, ni=1.0, cu=1.0, si=1.0, co=1.0, mo=1.0, al=1.0)
#     no_change_reading = PXRFReading(reading_no='21', fe=5.0, mg=5.0, ni=5.0, cu=5.0, si=5.0, co=5.0, mo=5.0, al=5.0)
#     test_db_session.add_all([initial_reading, no_change_reading])
#     test_db_session.commit()
#
#     excel_data = {
#         'Reading No': ['20', '21', '22'], # 20 changed, 21 same, 22 new
#         'Fe': [99.9, 5.0, 6.0], # Change 20's Fe, keep 21's, add 22's
#         'Mg': [99.9, 5.0, 6.0], # Change 20's Mg, keep 21's, add 22's
#         'Ni': [1.0, 5.0, 6.0], # Keep 20's Ni, keep 21's, add 22's
#         'Cu': [99.9, 5.0, 6.0], # Change 20's Cu, keep 21's, add 22's
#         'Si': [99.9, 5.0, 6.0],
#         'Co': [99.9, 5.0, 6.0],
#         'Mo': [99.9, 5.0, 6.0],
#         'Al': [99.9, 5.0, 6.0]
#     }
#     test_file_path = mock_excel_file(excel_data)
#
#     from database.ingest_pxrf import ingest_pxrf_data
#     monkeypatch.setattr("database.ingest_pxrf.PXRF_DATA_PATH", test_file_path)
#     monkeypatch.setattr("database.ingest_pxrf.SessionLocal", lambda: test_db_session)
#
#     # Act
#     ingest_pxrf_data(file_path=test_file_path, update_existing=True) # Important flag
#
#     # Assert
#     captured = capsys.readouterr()
#     assert "New readings inserted: 1" in captured.out
#     assert "Existing readings updated: 1" in captured.out # Only 20 should be updated
#     assert "Existing readings skipped: 1" in captured.out # 21 should be skipped (no changes)
#
#     readings = test_db_session.query(PXRFReading).order_by(PXRFReading.reading_no).all()
#     assert len(readings) == 3 # 20, 21, 22
#
#     # Check that reading 20 WAS updated (Fe, Mg, Cu changed, Ni didn't)
#     reading20 = test_db_session.query(PXRFReading).filter(PXRFReading.reading_no == '20').first()
#     assert reading20.fe == pytest.approx(99.9) # New value
#     assert reading20.mg == pytest.approx(99.9) # New value
#     assert reading20.ni == pytest.approx(1.0) # Old value (no change in excel for this col)
#     assert reading20.cu == pytest.approx(99.9) # New value
#
#     # Check that reading 21 was NOT physically updated (skipped)
#     reading21 = test_db_session.query(PXRFReading).filter(PXRFReading.reading_no == '21').first()
#     assert reading21.fe == pytest.approx(5.0)
#     # Optionally, check updated_at timestamp didn't change significantly if needed
#
#     # Check that reading 22 was inserted
#     reading22 = test_db_session.query(PXRFReading).filter(PXRFReading.reading_no == '22').first()
#     assert reading22 is not None
#     assert reading22.fe == pytest.approx(6.0)

def test_invalid_reading_no(test_db_session: Session, mock_excel_file, monkeypatch, capsys):
    """Test skipping rows with invalid or missing reading numbers."""
    excel_data = {
        'Reading No': ['1', None, '', '4'], # Include None and empty string
        'Fe': [10.0, 20.0, 30.0, 40.0],
        'Mg': [1.0, 2.0, 3.0, 4.0],
        # ... add other required columns
        'Ni': [1,1,1,1], 'Cu': [1,1,1,1], 'Si': [1,1,1,1],
        'Co': [1,1,1,1], 'Mo': [1,1,1,1], 'Al': [1,1,1,1],
    }
    test_file_path = mock_excel_file(excel_data)

    from database.ingest_pxrf import ingest_pxrf_data
    monkeypatch.setattr("database.ingest_pxrf.PXRF_DATA_PATH", test_file_path)
    monkeypatch.setattr("database.ingest_pxrf.SessionLocal", lambda: test_db_session)

    # Act
    ingest_pxrf_data(file_path=test_file_path, update_existing=False)

    # Assert
    captured = capsys.readouterr()
    assert "Total rows processed from file: 2" in captured.out # Only rows 1 and 4 are valid
    assert "New readings inserted: 2" in captured.out

    readings = test_db_session.query(PXRFReading).order_by(PXRFReading.reading_no).all()
    assert len(readings) == 2
    assert readings[0].reading_no == '1'
    assert readings[1].reading_no == '4'

def test_missing_required_column(test_db_session: Session, mock_excel_file, monkeypatch, capsys):
    """Test ingestion fails if a required column is missing."""
    excel_data = {
        'Reading No': ['1', '2'],
        'Fe': [10.1, 12.5],
        # Missing Mg column
        'Ni': [1.0, 1.2],
        'Cu': [0.5, 0.6],
        'Si': [20.0, 22.0],
        'Co': [0.1, 0.2],
        'Mo': [0.01, 0.02],
        'Al': [8.0, 9.0]
    }
    test_file_path = mock_excel_file(excel_data)

    from database.ingest_pxrf import ingest_pxrf_data
    monkeypatch.setattr("database.ingest_pxrf.PXRF_DATA_PATH", test_file_path)
    monkeypatch.setattr("database.ingest_pxrf.SessionLocal", lambda: test_db_session)

    # Act
    ingest_pxrf_data(file_path=test_file_path, update_existing=False)

    # Assert
    captured = capsys.readouterr()
    assert "Error: Missing required columns" in captured.out
    assert "'mg'" in captured.out # Check specific missing column name if needed

    readings = test_db_session.query(PXRFReading).count()
    assert readings == 0 # Should not insert anything


def test_file_not_found(test_db_session: Session, monkeypatch, capsys):
    """Test handling when the Excel file does not exist."""
    non_existent_path = "/path/to/non_existent_pxrf_data.xlsx"

    from database.ingest_pxrf import ingest_pxrf_data
    # No need to patch session if file read fails first
    monkeypatch.setattr("database.ingest_pxrf.PXRF_DATA_PATH", non_existent_path)

    # Act
    ingest_pxrf_data(file_path=non_existent_path, update_existing=False)

    # Assert
    captured = capsys.readouterr()
    assert f"Error: pXRF data file not found at {non_existent_path}" in captured.out

    readings = test_db_session.query(PXRFReading).count()
    assert readings == 0
