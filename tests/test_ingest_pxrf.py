import pytest
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, PXRFReading
from backend.services.bulk_uploads.pxrf_data import PXRFUploadService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED = ["Reading No", "Fe", "Mg", "Ni", "Cu", "Si", "Co", "Mo", "Al", "Ca", "K", "Au"]


def _csv_bytes(data: dict) -> bytes:
    """Serialize dict-of-lists to in-memory CSV bytes."""
    return pd.DataFrame(data).to_csv(index=False).encode()


def _row(**overrides) -> dict:
    """One-row data dict with all required columns zeroed, reading_no='1'."""
    base = {col: [0.0] for col in _REQUIRED}
    base["Reading No"] = ["1"]
    for k, v in overrides.items():
        base[k] = [v]
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    engine = create_engine("postgresql://experiments_user:password@localhost:5432/experiments_test", pool_pre_ping=True)
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    s = Sess()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# Basic insert
# ---------------------------------------------------------------------------

def test_ingest_new_reading(db):
    data = _row(Fe=10.0, Ca=1.5, Au=0.005)
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data)
    )
    assert errors == []
    assert inserted == 1
    r = db.query(PXRFReading).filter_by(reading_no="1").first()
    assert r is not None
    assert r.fe == pytest.approx(10.0)
    assert r.ca == pytest.approx(1.5)
    assert r.au == pytest.approx(0.005)


def test_null_equivalents_become_zero(db):
    data = {
        "Reading No": ["5"],
        "Fe": ["<LOD"], "Mg": ["ND"], "Ni": ["N/A"],
        "Cu": [""], "Si": ["LOD"], "Co": ["n.d."],
        "Mo": ["n/a"], "Al": [None], "Ca": [0.0], "K": [0.0], "Au": [0.0],
    }
    PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    r = db.query(PXRFReading).filter_by(reading_no="5").first()
    assert r.fe == pytest.approx(0.0)
    assert r.ni == pytest.approx(0.0)
    assert r.co == pytest.approx(0.0)


def test_reading_no_float_normalized(db):
    """Excel stores ints as floats; '1.0' should become reading_no='1'."""
    data = _row(Fe=5.0)
    data["Reading No"] = ["1.0"]
    PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    assert db.query(PXRFReading).filter_by(reading_no="1").first() is not None


def test_empty_reading_no_rows_dropped(db):
    data = {col: [0.0, 0.0, 0.0, 0.0] for col in _REQUIRED}
    data["Reading No"] = ["1", "", None, "4"]
    data["Fe"] = [10.0, 20.0, 30.0, 40.0]
    inserted, *_ = PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    assert inserted == 2
    assert db.query(PXRFReading).filter_by(reading_no="1").first() is not None
    assert db.query(PXRFReading).filter_by(reading_no="4").first() is not None


# ---------------------------------------------------------------------------
# Skip / update logic
# ---------------------------------------------------------------------------

def _seed_reading(db, reading_no: str = "10", fe: float = 1.0) -> PXRFReading:
    r = PXRFReading(reading_no=reading_no, fe=fe, mg=0.0, ni=0.0, cu=0.0,
                    si=0.0, co=0.0, mo=0.0, al=0.0, ca=0.0, k=0.0, au=0.0)
    db.add(r)
    db.commit()
    return r


def test_skip_existing_when_update_false(db):
    _seed_reading(db, "10", fe=1.0)
    data = {col: [0.0, 0.0] for col in _REQUIRED}
    data["Reading No"] = ["10", "11"]
    data["Fe"] = [99.0, 5.0]
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data), update_existing=False
    )
    assert inserted == 1
    assert skipped == 1
    assert db.query(PXRFReading).filter_by(reading_no="10").first().fe == pytest.approx(1.0)


def test_update_existing_when_flag_true(db):
    _seed_reading(db, "20", fe=1.0)
    data = _row(Fe=99.9)
    data["Reading No"] = ["20"]
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data), update_existing=True
    )
    assert updated == 1
    assert inserted == 0
    assert db.query(PXRFReading).filter_by(reading_no="20").first().fe == pytest.approx(99.9)


def test_missing_required_column_returns_error(db):
    data = {"Reading No": ["1"], "Fe": [10.0]}  # missing Mg, Ni, Cu, Si, Co, Mo, Al, Ca, K, Au
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data)
    )
    assert inserted == 0
    assert any("Missing required columns" in e for e in errors)


# ---------------------------------------------------------------------------
# Bug 1: % → ppm normalization
# ---------------------------------------------------------------------------

def test_percent_rows_converted_to_ppm(db):
    """Niton exports in weight-% for some scan modes; parser must × 10,000."""
    data = {
        "Reading No": ["20", "21"],
        "Units": ["%", "ppm"],
        "Fe": [30.0, 300_000.0],
        "Mg": [0.0, 0.0], "Ni": [0.0, 0.0], "Cu": [0.0, 0.0],
        "Si": [0.0, 0.0], "Co": [0.0, 0.0], "Mo": [0.0, 0.0],
        "Al": [0.0, 0.0], "Ca": [0.0, 0.0], "K": [0.0, 0.0], "Au": [0.0, 0.0],
    }
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data)
    )
    assert inserted == 2
    assert errors == []
    assert len(warnings) == 1
    assert "converted" in warnings[0].lower()
    r20 = db.query(PXRFReading).filter_by(reading_no="20").first()
    assert r20.fe == pytest.approx(300_000.0)   # 30.0 × 10,000
    r21 = db.query(PXRFReading).filter_by(reading_no="21").first()
    assert r21.fe == pytest.approx(300_000.0)   # already ppm, unchanged


def test_no_warning_when_all_ppm(db):
    data = _row(Fe=5000.0)
    data["Units"] = ["ppm"]
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data)
    )
    assert warnings == []


def test_no_warning_when_no_units_column(db):
    """Older exports omit the Units column entirely; no warning expected."""
    data = _row(Fe=5000.0)
    # No "Units" key in data
    inserted, updated, skipped, errors, warnings = PXRFUploadService.ingest_from_bytes(
        db, _csv_bytes(data)
    )
    assert warnings == []


# ---------------------------------------------------------------------------
# Bug 2: Zn optional import
# ---------------------------------------------------------------------------

def test_zn_imported_when_column_present(db):
    data = _row(Fe=10.0)
    data["Zn"] = [42.5]
    PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    r = db.query(PXRFReading).filter_by(reading_no="1").first()
    assert r.zn == pytest.approx(42.5)


def test_zn_lod_becomes_zero(db):
    data = _row(Fe=10.0)
    data["Zn"] = ["<LOD"]
    PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    r = db.query(PXRFReading).filter_by(reading_no="1").first()
    assert r.zn == pytest.approx(0.0)


def test_zn_not_required_upload_succeeds_without_it(db):
    """Upload without Zn column must succeed; zn field stays None."""
    data = _row(Fe=10.0)
    assert "Zn" not in data
    inserted, *_ = PXRFUploadService.ingest_from_bytes(db, _csv_bytes(data))
    assert inserted == 1
    r = db.query(PXRFReading).filter_by(reading_no="1").first()
    assert r.zn is None
