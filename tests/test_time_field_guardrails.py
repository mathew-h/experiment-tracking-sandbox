"""Tests for time field guardrails and re-upload null-time recovery."""

import datetime
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from database import (
    Experiment, ExperimentalConditions, ExperimentalResults,
    ScalarResults, ICPResults,
)
from backend.services.result_merge_utils import (
    create_experimental_result_row,
    normalize_timepoint,
)
from backend.services.scalar_results_service import ScalarResultsService
from backend.services.icp_service import ICPService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_experiment(db: Session, experiment_id: str = "TEST_001") -> Experiment:
    """Insert a minimal Experiment and return it."""
    conditions = ExperimentalConditions(
        experiment_id=experiment_id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    experiment = Experiment(
        experiment_id=experiment_id,
        date=datetime.date.today(),
        experiment_number=1,
        status="ONGOING",
    )
    experiment.conditions = conditions
    db.add(experiment)
    db.flush()
    conditions.experiment_fk = experiment.id
    conditions.experiment_id = experiment_id
    db.commit()
    db.refresh(experiment)
    return experiment


# ---------------------------------------------------------------------------
# Test 1: save_results rejects None time and returns False
# ---------------------------------------------------------------------------

def test_save_results_rejects_none_time():
    """save_results() should return False when time_post_reaction is None."""
    with patch("frontend.components.experimental_results.st") as mock_st:
        from frontend.components.experimental_results import save_results

        result = save_results(
            experiment_id=1,
            time_post_reaction=None,
            result_description="Test",
            scalar_data={},
        )
        assert result is False
        mock_st.error.assert_called_once()
        assert "required" in mock_st.error.call_args[0][0].lower()


# ---------------------------------------------------------------------------
# Test 2: create_experimental_result_row raises ValueError for None time
# ---------------------------------------------------------------------------

def test_create_result_row_rejects_none_time(test_db: Session):
    """create_experimental_result_row() must raise ValueError when time is None."""
    experiment = _make_experiment(test_db)
    with pytest.raises(ValueError, match="time_post_reaction is required"):
        create_experimental_result_row(
            db=test_db,
            experiment=experiment,
            time_post_reaction=None,
            description="should fail",
        )


# ---------------------------------------------------------------------------
# Test 3: ScalarResultsService.create_scalar_result_ex raises on missing time
# ---------------------------------------------------------------------------

def test_scalar_service_rejects_none_time(test_db: Session):
    """Scalar service must raise ValueError when time_post_reaction is missing."""
    _make_experiment(test_db, "SCALAR_TIME_TEST")
    with pytest.raises(ValueError, match="time_post_reaction"):
        ScalarResultsService.create_scalar_result_ex(
            db=test_db,
            experiment_id="SCALAR_TIME_TEST",
            result_data={"description": "no time provided"},
        )


# ---------------------------------------------------------------------------
# Test 4: After inserting scalar result, parent has non-NULL time fields
# ---------------------------------------------------------------------------

def test_scalar_result_has_time_fields(test_db: Session):
    """Inserting a scalar result must populate all time fields on the parent."""
    _make_experiment(test_db, "TIME_FIELDS_TEST")
    upsert = ScalarResultsService.create_scalar_result_ex(
        db=test_db,
        experiment_id="TIME_FIELDS_TEST",
        result_data={
            "time_post_reaction": 5.0,
            "description": "Day 5 results",
            "final_ph": 7.2,
        },
    )
    parent = upsert.experimental_result
    assert parent.time_post_reaction_days == 5.0
    assert parent.time_post_reaction_bucket_days is not None
    assert parent.time_post_reaction_bucket_days == normalize_timepoint(5.0)
    assert parent.cumulative_time_post_reaction_days is not None


# ---------------------------------------------------------------------------
# Test 5: Re-upload fills NULL-time row in-place (no duplicate created)
# ---------------------------------------------------------------------------

def test_reupload_fills_null_time_row(test_db: Session):
    """Re-uploading data for a NULL-time row must update it in-place."""
    experiment = _make_experiment(test_db, "REUPLOAD_TEST")

    # Simulate a legacy NULL-time row with scalar data
    null_time_row = ExperimentalResults(
        experiment_fk=experiment.id,
        time_post_reaction_days=None,
        time_post_reaction_bucket_days=None,
        description="Day 5 results",
    )
    test_db.add(null_time_row)
    test_db.flush()

    scalar = ScalarResults(
        result_id=null_time_row.id,
        final_ph=6.8,
    )
    test_db.add(scalar)
    test_db.commit()
    test_db.refresh(null_time_row)

    rows_before = (
        test_db.query(ExperimentalResults)
        .filter(ExperimentalResults.experiment_fk == experiment.id)
        .count()
    )

    # Re-upload with time provided and matching description
    upsert = ScalarResultsService.create_scalar_result_ex(
        db=test_db,
        experiment_id="REUPLOAD_TEST",
        result_data={
            "time_post_reaction": 5.0,
            "description": "Day 5 results",
            "final_ph": 7.0,
        },
    )

    rows_after = (
        test_db.query(ExperimentalResults)
        .filter(ExperimentalResults.experiment_fk == experiment.id)
        .count()
    )

    assert rows_after == rows_before, "Re-upload should not create a duplicate row"
    assert upsert.experimental_result.id == null_time_row.id
    assert upsert.experimental_result.time_post_reaction_days == 5.0
    assert upsert.experimental_result.time_post_reaction_bucket_days == normalize_timepoint(5.0)


# ---------------------------------------------------------------------------
# Test 6: ICP service rejects None time
# ---------------------------------------------------------------------------

def test_icp_service_rejects_none_time(test_db: Session):
    """ICP service must raise ValueError when time_post_reaction is None."""
    _make_experiment(test_db, "ICP_TIME_TEST")
    with pytest.raises(ValueError, match="time_post_reaction is required"):
        ICPService.create_icp_result(
            db=test_db,
            experiment_id="ICP_TIME_TEST",
            result_data={"description": "no time"},
        )
