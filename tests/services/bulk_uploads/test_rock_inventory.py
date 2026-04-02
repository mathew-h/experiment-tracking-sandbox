"""Tests for RockInventoryService."""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

# rock_inventory.py imports utils.storage and utils.pxrf which don't exist as importable modules.
# Stub them before the import so the module loads correctly.
if "utils" not in sys.modules:
    _utils = ModuleType("utils")
    sys.modules["utils"] = _utils
if "utils.storage" not in sys.modules:
    _utils_storage = ModuleType("utils.storage")
    _utils_storage.save_file = MagicMock(return_value="/fake/path/file.jpg")
    sys.modules["utils.storage"] = _utils_storage
if "utils.pxrf" not in sys.modules:
    _utils_pxrf = ModuleType("utils.pxrf")
    _utils_pxrf.split_normalized_pxrf_readings = MagicMock(return_value=[])
    sys.modules["utils.pxrf"] = _utils_pxrf

from database import SampleInfo
from backend.services.bulk_uploads.rock_inventory import RockInventoryService

from .excel_helpers import make_excel


def test_creates_new_sample(db_session: Session):
    """Valid row creates a SampleInfo record."""
    xlsx = make_excel(
        ["sample_id", "rock_classification", "state", "country", "locality"],
        [["S_ROCK001", "Basalt", "BC", "Canada", "Vancouver Island"]],
    )
    created, updated, _images, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert updated == 0

    # Service normalizes sample_id: uppercase + remove underscores/spaces
    normalized_id = "SROCK001"
    sample = (
        db_session.query(SampleInfo)
        .filter(SampleInfo.sample_id == normalized_id)
        .first()
    )
    assert sample is not None
    assert sample.rock_classification == "Basalt"
    assert sample.country == "Canada"


def test_updates_existing_sample_with_overwrite(db_session: Session):
    """Row with overwrite=TRUE updates an existing sample."""
    existing = SampleInfo(sample_id="S_ROCK002", rock_classification="Gabbro")
    db_session.add(existing)
    db_session.flush()

    xlsx = make_excel(
        ["sample_id", "rock_classification", "overwrite"],
        [["S_ROCK002", "Dunite", "TRUE"]],
    )
    created, updated, _images, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )

    assert errors == []
    assert created == 0
    assert updated == 1

    db_session.flush()
    db_session.refresh(existing)
    assert existing.rock_classification == "Dunite"


def test_missing_sample_id_column_returns_error(db_session: Session):
    """File without a 'sample_id' column returns an error immediately."""
    xlsx = make_excel(
        ["rock_classification", "country"],
        [["Basalt", "Canada"]],
    )
    created, updated, _images, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )

    assert created == 0
    assert any("sample_id" in e.lower() for e in errors)


def test_blank_sample_id_rows_skipped(db_session: Session):
    """Rows with a whitespace-only sample_id are skipped."""
    xlsx = make_excel(
        ["sample_id", "rock_classification"],
        [["   ", "Peridotite"]],  # spaces-only → .strip() → "" → skipped
    )
    created, updated, _images, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )

    assert created == 0
    assert skipped == 1


def test_characterized_flag_parsed_correctly(db_session: Session):
    """'TRUE' in the characterized column is stored as True."""
    xlsx = make_excel(
        ["sample_id", "characterized"],
        [["S_ROCK003", "TRUE"]],
    )
    created, updated, _images, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )

    assert errors == []
    # Service normalizes: "S_ROCK003" → "SROCK003"
    sample = (
        db_session.query(SampleInfo)
        .filter(SampleInfo.sample_id == "SROCK003")
        .first()
    )
    assert sample is not None
    assert sample.characterized is True


def test_invalid_file_bytes_returns_error(db_session: Session):
    """Non-Excel bytes return a file-read error."""
    created, updated, _images, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, b"not excel", [])
    )
    assert created == 0
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# magnetic_susceptibility tests (Issue #28)
# ---------------------------------------------------------------------------

def test_mag_susc_creates_external_analysis(db_session: Session):
    """magnetic_susceptibility column creates ExternalAnalysis of type 'Magnetic Susceptibility'."""
    from database.models.analysis import ExternalAnalysis

    xlsx = make_excel(
        ["sample_id", "magnetic_susceptibility"],
        [["S_MAG001", 2.5]],
    )
    created, updated, _images, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )

    assert errors == [], errors
    assert created == 1
    db_session.flush()

    # Service normalizes "S_MAG001" → "SMAG001"
    ea = (
        db_session.query(ExternalAnalysis)
        .filter(
            ExternalAnalysis.sample_id == "SMAG001",
            ExternalAnalysis.analysis_type == "Magnetic Susceptibility",
        )
        .first()
    )
    assert ea is not None
    assert ea.magnetic_susceptibility == "2.5"


def test_mag_susc_aliases_recognized(db_session: Session):
    """All four alias column names for mag susc are accepted."""
    from database.models.analysis import ExternalAnalysis

    aliases = ["magnetic_susceptibility", "magnetic susceptibility", "mag_susc", "mag susc"]
    for alias in aliases:
        safe_alias = alias.replace(" ", "X").replace("_", "Y").upper()
        xlsx = make_excel(
            ["sample_id", alias],
            [[f"S_{safe_alias}", 3.7]],
        )
        created, updated, _images, skipped, errors, warnings = (
            RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
        )
        assert errors == [], f"Alias '{alias}' produced errors: {errors}"
        db_session.flush()
        expected_sid = f"S{safe_alias}"
        ea = (
            db_session.query(ExternalAnalysis)
            .filter(
                ExternalAnalysis.sample_id == expected_sid,
                ExternalAnalysis.analysis_type == "Magnetic Susceptibility",
            )
            .first()
        )
        assert ea is not None, f"No EA created for alias '{alias}'"


def test_mag_susc_blank_skipped(db_session: Session):
    """Blank magnetic_susceptibility cell does not create an ExternalAnalysis."""
    from database.models.analysis import ExternalAnalysis

    xlsx = make_excel(
        ["sample_id", "magnetic_susceptibility"],
        [["S_BLANK001", ""]],
    )
    RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    db_session.flush()

    ea = (
        db_session.query(ExternalAnalysis)
        .filter(
            ExternalAnalysis.sample_id == "SBLANK001",
            ExternalAnalysis.analysis_type == "Magnetic Susceptibility",
        )
        .first()
    )
    assert ea is None


def test_mag_susc_string_value_stored(db_session: Session):
    """Any non-blank string value (including ranges) is stored as-is without error."""
    from database.models.analysis import ExternalAnalysis

    xlsx = make_excel(
        ["sample_id", "magnetic_susceptibility"],
        [["S_STR001", "1.2-1.5"]],
    )
    created, updated, _images, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )
    assert errors == [], errors
    db_session.flush()

    ea = (
        db_session.query(ExternalAnalysis)
        .filter(
            ExternalAnalysis.sample_id == "SSTR001",
            ExternalAnalysis.analysis_type == "Magnetic Susceptibility",
        )
        .first()
    )
    assert ea is not None
    assert ea.magnetic_susceptibility == "1.2-1.5"


def test_mag_susc_skip_without_overwrite(db_session: Session):
    """Re-upload with a different value and no overwrite flag leaves the existing EA unchanged."""
    from database.models.analysis import ExternalAnalysis
    from database.models.samples import SampleInfo

    sample = SampleInfo(sample_id="SOVER001")
    db_session.add(sample)
    db_session.flush()
    ea = ExternalAnalysis(
        sample_id="SOVER001",
        analysis_type="Magnetic Susceptibility",
        magnetic_susceptibility="1.0",  # string
    )
    db_session.add(ea)
    db_session.flush()

    xlsx = make_excel(
        ["sample_id", "magnetic_susceptibility"],
        [["SOVER001", 99.9]],
    )
    RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    db_session.flush()
    db_session.refresh(ea)

    assert ea.magnetic_susceptibility == "1.0"  # unchanged


def test_mag_susc_update_with_overwrite(db_session: Session):
    """Re-upload with overwrite=TRUE updates the existing EA's magnetic_susceptibility value."""
    from database.models.analysis import ExternalAnalysis
    from database.models.samples import SampleInfo

    sample = SampleInfo(sample_id="SOVER002")
    db_session.add(sample)
    db_session.flush()
    ea = ExternalAnalysis(
        sample_id="SOVER002",
        analysis_type="Magnetic Susceptibility",
        magnetic_susceptibility="1.0",  # string
    )
    db_session.add(ea)
    db_session.flush()

    xlsx = make_excel(
        ["sample_id", "magnetic_susceptibility", "overwrite"],
        [["SOVER002", 99.9, "TRUE"]],
    )
    RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    db_session.flush()
    db_session.refresh(ea)

    assert ea.magnetic_susceptibility == "99.9"  # updated, no pytest.approx
