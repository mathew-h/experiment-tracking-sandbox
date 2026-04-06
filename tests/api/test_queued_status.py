"""Tests for QUEUED ExperimentStatus (issue #33)."""
from __future__ import annotations

from database.models.enums import ExperimentStatus


def test_experiment_status_queued_enum_value():
    """ExperimentStatus('QUEUED') must not raise."""
    status = ExperimentStatus("QUEUED")
    assert status == ExperimentStatus.QUEUED
    assert status.value == "QUEUED"
