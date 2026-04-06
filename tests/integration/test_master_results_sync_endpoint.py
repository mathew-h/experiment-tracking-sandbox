"""Integration tests for Master Results Sync — Sampled Solution Volume (Issue #31)."""
from __future__ import annotations

import io

import openpyxl
import pytest
from sqlalchemy.orm import Session

from database import Base, Experiment, ExperimentalResults
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.master_bulk_upload import MasterBulkUploadService


def _seed_experiment(db: Session, experiment_id: str, exp_num: int) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    return exp


def _make_xlsx(headers: list[str], rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dashboard"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_HEADERS_WITH_VOL = [
    "Experiment ID", "Duration (Days)", "Description", "Sample Date",
    "NMR Run Date", "ICP Run Date", "GC Run Date",
    "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
    "Sample pH", "Sample Conductivity (mS/cm)",
    "Sampled Solution Volume (mL)",
    "Modification", "Overwrite",
]

_HEADERS_LEGACY = [
    "Experiment ID", "Duration (Days)", "Description", "Sample Date",
    "NMR Run Date", "ICP Run Date", "GC Run Date",
    "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
    "Sample pH", "Sample Conductivity (mS/cm)",
    "Modification", "Overwrite",
]


def test_sync_writes_sampled_solution_volume(db_session: Session):
    """Full service round-trip: column present → ScalarResults.sampling_volume_mL persisted."""
    _seed_experiment(db_session, "CF_INT001", 9001)

    xlsx = _make_xlsx(_HEADERS_WITH_VOL, [
        ["CF_INT001", 14.0, "Day 14", None, None, None, None,
         None, None, None, None, 7.1, None, 42.5, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "CF_INT001")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    assert result.scalar_data.sampling_volume_mL == pytest.approx(42.5)


def test_sync_without_sampled_solution_volume_column(db_session: Session):
    """Legacy file without the column → sync succeeds, sampling_volume_mL is None."""
    _seed_experiment(db_session, "CF_INT002", 9002)

    xlsx = _make_xlsx(_HEADERS_LEGACY, [
        ["CF_INT002", 14.0, "Day 14", None, None, None, None,
         None, None, None, None, 7.1, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "CF_INT002")
        .first()
    )
    assert result is not None
    assert result.scalar_data is not None
    assert result.scalar_data.sampling_volume_mL is None
