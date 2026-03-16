import pytest
from database import PXRFReading
from sqlalchemy.exc import IntegrityError

def test_pxrf_reading_fixture(test_db, pxrf_reading):
    """Test that the pXRF reading fixture creates a valid entry."""
    # Check that the reading was created
    assert pxrf_reading.reading_no == "TEST001"
    
    # Verify all element values
    assert pxrf_reading.fe == pytest.approx(10.5)
    assert pxrf_reading.mg == pytest.approx(2.3)
    assert pxrf_reading.ni == pytest.approx(0.5)
    assert pxrf_reading.cu == pytest.approx(0.3)
    assert pxrf_reading.si == pytest.approx(45.2)
    assert pxrf_reading.co == pytest.approx(0.1)
    assert pxrf_reading.mo == pytest.approx(0.02)
    assert pxrf_reading.al == pytest.approx(8.4)

def test_pxrf_reading_query(test_db, pxrf_reading):
    """Test querying pXRF readings from the database."""
    # Query the reading by reading_no
    queried_reading = test_db.query(PXRFReading).filter_by(reading_no="TEST001").first()
    
    # Verify it matches the fixture
    assert queried_reading is not None
    assert queried_reading.reading_no == pxrf_reading.reading_no
    assert queried_reading.fe == pxrf_reading.fe
    assert queried_reading.mg == pxrf_reading.mg

def test_pxrf_reading_unique_constraint(test_db, pxrf_reading):
    """Test that reading_no must be unique."""
    # Try to create another reading with the same reading_no
    duplicate_reading = PXRFReading(
        reading_no="TEST001",  # Same as fixture
        fe=99.9,  # Different values
        mg=99.9,
        ni=99.9,
        cu=99.9,
        si=99.9,
        co=99.9,
        mo=99.9,
        al=99.9
    )
    
    # Adding duplicate should raise IntegrityError
    with pytest.raises(IntegrityError):
        test_db.add(duplicate_reading)
        test_db.commit()

def test_pxrf_reading_update(test_db, pxrf_reading):
    """Test updating pXRF reading values."""
    # Update some values
    pxrf_reading.fe = 20.0
    pxrf_reading.mg = 3.0
    test_db.commit()
    
    # Query again to verify changes persisted
    updated_reading = test_db.query(PXRFReading).filter_by(reading_no="TEST001").first()
    assert updated_reading.fe == pytest.approx(20.0)
    assert updated_reading.mg == pytest.approx(3.0)
    # Other values should remain unchanged
    assert updated_reading.ni == pytest.approx(0.5)

def test_pxrf_reading_delete(test_db, pxrf_reading):
    """Test deleting a pXRF reading."""
    # Delete the reading
    test_db.delete(pxrf_reading)
    test_db.commit()
    
    # Verify it's gone
    deleted_reading = test_db.query(PXRFReading).filter_by(reading_no="TEST001").first()
    assert deleted_reading is None

def test_pxrf_reading_null_elements(test_db):
    """Test that element values can be null."""
    # Create reading with only some elements
    partial_reading = PXRFReading(
        reading_no="PARTIAL001",
        fe=10.5,  # Only specify some elements
        mg=2.3
    )
    test_db.add(partial_reading)
    test_db.commit()
    
    # Query and verify
    queried_reading = test_db.query(PXRFReading).filter_by(reading_no="PARTIAL001").first()
    assert queried_reading is not None
    assert queried_reading.fe == pytest.approx(10.5)
    assert queried_reading.mg == pytest.approx(2.3)
    assert queried_reading.ni is None  # Unspecified elements should be None
    assert queried_reading.cu is None
    assert queried_reading.si is None

def test_pxrf_reading_number_handling(test_db):
    """Test that reading numbers are handled correctly regardless of string/integer format."""
    # Create readings with different number formats
    readings = [
        PXRFReading(reading_no="3", fe=10.0),      # String number
        PXRFReading(reading_no="03", fe=11.0),     # Zero-padded string
        PXRFReading(reading_no="TEST3", fe=12.0),  # String with prefix
    ]
    
    for reading in readings:
        test_db.add(reading)
    test_db.commit()
    
    # Test different query formats
    # Query with string number
    result1 = test_db.query(PXRFReading).filter(PXRFReading.reading_no == "3").first()
    assert result1 is not None, "Failed to find reading with exact string match '3'"
    assert result1.fe == 10.0
    
    # Query with integer converted to string
    result2 = test_db.query(PXRFReading).filter(PXRFReading.reading_no == str(3)).first()
    assert result2 is not None, "Failed to find reading when querying with str(3)"
    assert result2.fe == 10.0
    
    # Query with zero-padded string
    result3 = test_db.query(PXRFReading).filter(PXRFReading.reading_no == "03").first()
    assert result3 is not None
    assert result3.fe == 11.0
    
    # Test list-based query (similar to website's query)
    reading_numbers = ["3"]
    list_results = test_db.query(PXRFReading).filter(
        PXRFReading.reading_no.in_(reading_numbers)
    ).all()
    assert len(list_results) == 1, f"Expected 1 result for reading_numbers {reading_numbers}, got {len(list_results)}"
    assert list_results[0].fe == 10.0 