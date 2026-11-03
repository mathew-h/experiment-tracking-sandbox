"""resolve_primary_timepoint: shared time/bucket/demotion logic (issue #133).

Extracted from POST /api/results (issues #81, #83).
"""
import pytest

from backend.services.result_merge_utils import (
    normalize_timepoint,
    resolve_primary_timepoint,
)
from database.models import Experiment
from database.models.results import ExperimentalResults


def _exp(db, exp_id="SERUM_RPT_001", number=7100):
    exp = Experiment(experiment_id=exp_id, experiment_number=number)
    db.add(exp)
    db.flush()
    return exp


def _seed_primary(db, exp, day):
    row = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=day,
        time_post_reaction_bucket_days=normalize_timepoint(day),
        is_primary_timepoint_result=True,
    )
    db.add(row)
    db.flush()
    return row


def test_returns_time_and_bucket(db_session):
    exp = _exp(db_session)
    assert resolve_primary_timepoint(db_session, exp, 7.0) == (7.0, normalize_timepoint(7.0))


def test_id_token_fills_blank_time(db_session):
    exp = _exp(db_session, "SERUM_RPT_001a-t7", 7101)
    assert resolve_primary_timepoint(db_session, exp, None) == (7.0, 7.0)


def test_conflicting_token_raises(db_session):
    exp = _exp(db_session, "SERUM_RPT_001a-t7", 7101)
    with pytest.raises(ValueError):
        resolve_primary_timepoint(db_session, exp, 3.0)


def test_demotes_existing_primary_in_bucket(db_session):
    exp = _exp(db_session)
    seeded = _seed_primary(db_session, exp, 5.0)
    resolve_primary_timepoint(db_session, exp, 5.0)
    db_session.expire(seeded)
    assert seeded.is_primary_timepoint_result is False


def test_non_primary_does_not_demote(db_session):
    exp = _exp(db_session)
    seeded = _seed_primary(db_session, exp, 5.0)
    resolve_primary_timepoint(db_session, exp, 5.0, is_primary=False)
    db_session.expire(seeded)
    assert seeded.is_primary_timepoint_result is True
