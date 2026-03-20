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
