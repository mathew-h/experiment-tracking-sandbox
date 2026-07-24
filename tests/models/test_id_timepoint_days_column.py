"""Issue #81: Experiment.id_timepoint_days column contract."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sqlalchemy import Float
from database.models import Experiment


class TestIdTimepointDaysColumn:
    def test_column_exists_nullable_float(self):
        col = Experiment.__table__.columns['id_timepoint_days']
        assert isinstance(col.type, Float)
        assert col.nullable is True
        assert col.index is True

    def test_default_is_null(self):
        exp = Experiment(experiment_id="SERUM_900", experiment_number=90001)
        assert exp.id_timepoint_days is None
