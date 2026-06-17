import pytest
from database.models import SampleInfo, PXRFReading


def test_create_pxrf_reading(test_db):
    """Test creating a new pXRF reading with current model structure."""
    sample = SampleInfo(
        sample_id="TEST-001",
        rock_classification="Test Rock",
        locality="Test Site"
    )

    test_db.add(sample)
    test_db.commit()

    reading = PXRFReading(
        reading_no="TEST-001",
        fe=45.67,
        si=12.34,
        al=5.67
    )

    test_db.add(reading)
    test_db.commit()

    saved_reading = test_db.query(PXRFReading).first()
    assert saved_reading is not None
    assert saved_reading.fe == 45.67
    assert saved_reading.si == 12.34
    assert saved_reading.al == 5.67
    assert saved_reading.ingested_at is not None
