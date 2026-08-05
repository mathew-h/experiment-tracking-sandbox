"""An ambiguous experiment ID must raise, never fall through to auto-create."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Experiment
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads._id_match import AmbiguousExperimentIdError
from backend.services.scalar_results_service import ScalarResultsService


@pytest.fixture()
def two_colliding_experiments(db_session: Session) -> Session:
    db_session.add_all([
        Experiment(experiment_id="AMBSCAL_1", experiment_number=8805001,
                   status=ExperimentStatus.ONGOING),
        Experiment(experiment_id="AMBSCAL_001", experiment_number=8805002,
                   status=ExperimentStatus.ONGOING),
    ])
    db_session.flush()
    return db_session


def test_find_experiment_raises_on_ambiguity(two_colliding_experiments: Session):
    with pytest.raises(AmbiguousExperimentIdError) as excinfo:
        ScalarResultsService._find_experiment(two_colliding_experiments, "ambscal-01")
    assert set(excinfo.value.candidates) == {"AMBSCAL_1", "AMBSCAL_001"}


def test_ambiguity_does_not_auto_create_an_experiment(two_colliding_experiments: Session):
    """The real hazard: None would send create_scalar_result_ex into
    auto_create_treatment_experiment and fabricate a row."""
    before = two_colliding_experiments.query(Experiment).count()
    with pytest.raises(ValueError):
        ScalarResultsService.create_scalar_result_ex(
            two_colliding_experiments,
            "ambscal-01",
            {"description": "amb", "gross_ammonium_concentration_mM": 1.0,
             "time_post_reaction": 7.0},
        )
    assert two_colliding_experiments.query(Experiment).count() == before, (
        "an experiment was auto-created for an ambiguous ID"
    )


def test_unambiguous_lookup_unaffected(db_session: Session):
    db_session.add(Experiment(
        experiment_id="AMBSCAL_SOLO_009", experiment_number=8805003,
        status=ExperimentStatus.ONGOING,
    ))
    db_session.flush()
    exp = ScalarResultsService._find_experiment(db_session, "ambscal-solo-9")
    assert exp is not None and exp.experiment_id == "AMBSCAL_SOLO_009"


def test_read_path_returns_empty_instead_of_raising(two_colliding_experiments: Session):
    """get_scalar_results_for_experiment is a read helper behind a GET; an
    ambiguous ID there must not become a 500."""
    assert ScalarResultsService.get_scalar_results_for_experiment(
        two_colliding_experiments, "ambscal-01"
    ) == []
