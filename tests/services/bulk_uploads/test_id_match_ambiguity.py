"""The finders must never resolve an ambiguous ID to an arbitrary row.

Task 1 removed every collision present in the dev DB, but the guard is what
makes a future collision loud instead of silent. `GUARD_AMB_1` and
`GUARD_AMB_001` are two distinct legal experiment_id strings that share the
normalized key `guard_amb_1` under any zero-stripping scheme.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Experiment, SampleInfo
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads._id_match import (
    AmbiguousExperimentIdError,
    find_experiment_matches,
    find_sample_matches,
    fuzzy_find_experiment,
    fuzzy_find_sample,
    normalize_id,
)


@pytest.fixture()
def two_colliding_experiments(db_session: Session) -> Session:
    db_session.add_all([
        Experiment(experiment_id="GUARD_AMB_1", experiment_number=8804001,
                   status=ExperimentStatus.ONGOING),
        Experiment(experiment_id="GUARD_AMB_001", experiment_number=8804002,
                   status=ExperimentStatus.ONGOING),
    ])
    db_session.flush()
    return db_session


def test_the_fixture_really_collides():
    assert normalize_id("GUARD_AMB_1") == normalize_id("GUARD_AMB_001")


def test_exact_match_wins_over_ambiguity(two_colliding_experiments: Session):
    """A byte-exact ID is never ambiguous, even when its normalized key is."""
    exp = fuzzy_find_experiment(two_colliding_experiments, "GUARD_AMB_001")
    assert exp is not None
    assert exp.experiment_id == "GUARD_AMB_001"


def test_find_experiment_matches_returns_both(two_colliding_experiments: Session):
    matches = find_experiment_matches(two_colliding_experiments, "guard-amb-01")
    assert {m.experiment_id for m in matches} == {"GUARD_AMB_1", "GUARD_AMB_001"}


def test_fuzzy_find_experiment_refuses_to_guess(two_colliding_experiments: Session):
    """The whole point: no arbitrary .first() on an ambiguous key."""
    assert fuzzy_find_experiment(two_colliding_experiments, "guard-amb-01") is None


def test_unambiguous_lookup_still_resolves(db_session: Session):
    db_session.add(Experiment(
        experiment_id="GUARD_SOLO_007", experiment_number=8804003,
        status=ExperimentStatus.ONGOING,
    ))
    db_session.flush()
    exp = fuzzy_find_experiment(db_session, "guard-solo-7")
    assert exp is not None and exp.experiment_id == "GUARD_SOLO_007"


def test_missing_experiment_still_returns_none(db_session: Session):
    assert fuzzy_find_experiment(db_session, "GUARD_NOPE_999") is None


def test_ambiguous_error_carries_the_candidates():
    err = AmbiguousExperimentIdError("guard-amb-01", ["GUARD_AMB_001", "GUARD_AMB_1"])
    assert isinstance(err, ValueError)
    assert err.raw_id == "guard-amb-01"
    assert err.candidates == ["GUARD_AMB_001", "GUARD_AMB_1"]
    assert "GUARD_AMB_001" in str(err) and "GUARD_AMB_1" in str(err)


def test_sample_finder_also_refuses_to_guess(db_session: Session):
    db_session.add_all([
        SampleInfo(sample_id="GUARD_SMP_1"),
        SampleInfo(sample_id="GUARD_SMP_001"),
    ])
    db_session.flush()
    assert len(find_sample_matches(db_session, "guard-smp-01")) == 2
    assert fuzzy_find_sample(db_session, "guard-smp-01") is None
