"""Tests for XRDAutoDetectService and format detection."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Experiment
from database.models import XRDPhase
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.xrd_upload import XRDAutoDetectService, _detect_format

from .excel_helpers import make_excel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_experiment(
    db: Session, experiment_id: str, exp_num: int
) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    return exp


# ---------------------------------------------------------------------------
# Format detection tests (no DB required)
# ---------------------------------------------------------------------------

def test_detect_experiment_timepoint_format(db_session: Session):
    """File with 'Experiment ID' + 'Time (days)' columns → 'experiment-timepoint'."""
    xlsx = make_excel(
        ["Experiment ID", "Time (days)", "Quartz", "Calcite"],
        [["HPHT_001", 7.0, 45.2, 20.1]],
    )
    fmt = _detect_format(xlsx)
    assert fmt == "experiment-timepoint"


def test_detect_aeris_format(db_session: Session):
    """File with Aeris-pattern Sample ID values → 'aeris'."""
    xlsx = make_excel(
        ["Sample ID", "Quartz", "Calcite"],
        [["20260218_HPHT070-d19_02", 55.0, 20.0]],
    )
    fmt = _detect_format(xlsx)
    assert fmt == "aeris"


def test_detect_actlabs_format(db_session: Session):
    """File with plain sample_id column and non-Aeris values → 'actlabs'."""
    xlsx = make_excel(
        ["sample_id", "Quartz", "Calcite"],
        [["S001", 45.0, 22.0]],
    )
    fmt = _detect_format(xlsx)
    assert fmt == "actlabs"


def test_unknown_format_returns_none(db_session: Session):
    """File with no recognizable columns returns None."""
    xlsx = make_excel(
        ["column_a", "column_b"],
        [["foo", "bar"]],
    )
    fmt = _detect_format(xlsx)
    assert fmt is None


def test_unknown_format_upload_returns_error(db_session: Session):
    """upload() with unrecognizable file returns an error string."""
    xlsx = make_excel(
        ["column_a", "column_b"],
        [["foo", "bar"]],
    )
    created, updated, skipped, errors = XRDAutoDetectService.upload(db_session, xlsx)
    assert created == 0
    assert any("Unable to detect" in e for e in errors)


# ---------------------------------------------------------------------------
# Experiment-timepoint round-trip (DB required)
# ---------------------------------------------------------------------------

def test_experiment_timepoint_creates_xrd_phases(db_session: Session):
    """Valid experiment+timepoint file creates XRDPhase rows for each mineral."""
    exp = _seed_experiment(db_session, "HPHT_XRD001", 8801)

    xlsx = make_excel(
        ["Experiment ID", "Time (days)", "Quartz", "Calcite"],
        [["HPHT_XRD001", 7.0, 45.2, 20.1]],
    )
    created, updated, skipped, errors = XRDAutoDetectService.upload(db_session, xlsx)

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 2  # two mineral columns
    assert updated == 0

    phases = (
        db_session.query(XRDPhase)
        .filter(XRDPhase.experiment_id == "HPHT_XRD001")
        .all()
    )
    assert len(phases) == 2
    mineral_names = {p.mineral_name for p in phases}
    assert mineral_names == {"Quartz", "Calcite"}


def test_experiment_timepoint_updates_existing_phase(db_session: Session):
    """Re-uploading the same experiment+time+mineral updates, not creates."""
    exp = _seed_experiment(db_session, "HPHT_XRD002", 8802)

    # First upload
    xlsx = make_excel(
        ["Experiment ID", "Time (days)", "Quartz"],
        [["HPHT_XRD002", 14.0, 50.0]],
    )
    XRDAutoDetectService.upload(db_session, xlsx)

    # Second upload with updated value
    xlsx2 = make_excel(
        ["Experiment ID", "Time (days)", "Quartz"],
        [["HPHT_XRD002", 14.0, 60.0]],
    )
    created, updated, skipped, errors = XRDAutoDetectService.upload(db_session, xlsx2)

    assert errors == []
    assert created == 0
    assert updated == 1

    phase = (
        db_session.query(XRDPhase)
        .filter(
            XRDPhase.experiment_id == "HPHT_XRD002",
            XRDPhase.mineral_name == "Quartz",
        )
        .first()
    )
    assert phase is not None
    assert phase.amount == pytest.approx(60.0)


def test_unknown_experiment_recorded_as_error(db_session: Session):
    """Row referencing a non-existent experiment is recorded as an error."""
    xlsx = make_excel(
        ["Experiment ID", "Time (days)", "Quartz"],
        [["NONEXISTENT_XRD", 7.0, 50.0]],
    )
    created, updated, skipped, errors = XRDAutoDetectService.upload(db_session, xlsx)

    assert created == 0
    assert any("NONEXISTENT_XRD" in e for e in errors)


def test_mineral_column_percentage_suffix_stripped(db_session: Session):
    """Column headers like 'Quartz (%)' have the trailing suffix removed."""
    exp = _seed_experiment(db_session, "HPHT_XRD003", 8803)

    xlsx = make_excel(
        ["Experiment ID", "Time (days)", "Quartz (%)", "Calcite [%]"],
        [["HPHT_XRD003", 3.0, 30.0, 25.0]],
    )
    created, updated, skipped, errors = XRDAutoDetectService.upload(db_session, xlsx)

    assert errors == []
    phases = (
        db_session.query(XRDPhase)
        .filter(XRDPhase.experiment_id == "HPHT_XRD003")
        .all()
    )
    mineral_names = {p.mineral_name for p in phases}
    assert "Quartz" in mineral_names
    assert "Calcite" in mineral_names


def test_generate_template_returns_bytes(db_session: Session):
    """generate_template_bytes() returns non-empty bytes for both modes."""
    for mode in ("sample", "experiment"):
        data = XRDAutoDetectService.generate_template_bytes(mode=mode)
        assert isinstance(data, bytes)
        assert len(data) > 0
