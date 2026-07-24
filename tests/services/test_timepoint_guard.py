"""Issue #81: ID-encoded timepoint is canonical for result times.

apply_id_timepoint unit table + the create_scalar_result_ex service guard
(the choke point for scalar, master, and long-format bulk paths).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.services.result_merge_utils import apply_id_timepoint
from backend.services.scalar_results_service import ScalarResultsService


class TestApplyIdTimepoint:
    def test_no_id_timepoint_passthrough(self):
        assert apply_id_timepoint(None, 3.0) == 3.0
        assert apply_id_timepoint(None, None) is None

    def test_blank_time_filled_from_id(self):
        assert apply_id_timepoint(7.0, None) == 7.0

    def test_matching_time_accepted(self):
        assert apply_id_timepoint(7.0, 7.0) == 7.0
        assert apply_id_timepoint(7.0, 7.00005) == 7.00005  # inside 0.0001 tolerance

    def test_conflicting_time_rejected(self):
        with pytest.raises(ValueError) as exc:
            apply_id_timepoint(7.0, 3.0)
        assert "-t7" in str(exc.value)
        assert "canonical" in str(exc.value)

    def test_decimal_day_conflict(self):
        with pytest.raises(ValueError):
            apply_id_timepoint(0.5, 1.0)


class TestServiceGuard:
    """create_scalar_result_ex fills/validates against Experiment.id_timepoint_days."""

    def _seed_vial(self, db, exp_id="SERUM_060a-t7", number=6000):
        from database.models import Experiment
        exp = Experiment(experiment_id=exp_id, experiment_number=number)
        db.add(exp)
        db.flush()
        return exp

    def test_blank_time_filled_from_id_column(self, db_session):
        self._seed_vial(db_session)
        upsert = ScalarResultsService.create_scalar_result_ex(
            db_session, "SERUM_060a-t7",
            {"description": "day 7 vial", "gross_ammonium_concentration_mM": 2.0},
        )
        assert upsert.experimental_result.time_post_reaction_days == 7.0
        assert upsert.experimental_result.time_post_reaction_bucket_days == 7.0

    def test_matching_time_accepted(self, db_session):
        self._seed_vial(db_session, "SERUM_061a-t7", 6100)
        upsert = ScalarResultsService.create_scalar_result_ex(
            db_session, "SERUM_061a-t7",
            {"time_post_reaction": 7.0, "description": "ok"},
        )
        assert upsert.experimental_result.time_post_reaction_days == 7.0

    def test_conflicting_time_rejected(self, db_session):
        self._seed_vial(db_session, "SERUM_062a-t7", 6200)
        with pytest.raises(ValueError, match="canonical"):
            ScalarResultsService.create_scalar_result_ex(
                db_session, "SERUM_062a-t7",
                {"time_post_reaction": 3.0, "description": "wrong day"},
            )

    def test_untimed_experiment_unaffected(self, db_session):
        self._seed_vial(db_session, "SERUM_063a", 6300)
        upsert = ScalarResultsService.create_scalar_result_ex(
            db_session, "SERUM_063a",
            {"time_post_reaction": 3.0, "description": "free timepoint"},
        )
        assert upsert.experimental_result.time_post_reaction_days == 3.0
