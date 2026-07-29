from __future__ import annotations
from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker, Session

from database import Base  # noqa: F401 — side-effect: registers all models
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.enums import AmountUnit, ExperimentStatus
from database.models.conditions import ExperimentalConditions
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.results import ExperimentalResults, ScalarResults, ICPResults, ResultFiles
from database.models.analysis import ExternalAnalysis
from database.models.xrd import XRDPhase
from database.models.notion_sync import ReactorChangeRequest

TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="module", autouse=True)
def _tables():
    Base.metadata.create_all(bind=_engine)
    yield


@pytest.fixture()
def db(_tables) -> Session:
    connection = _engine.connect()
    transaction = connection.begin()
    session = _SessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _full_experiment(db: Session, experiment_id="DEL_FULL_001", number=7101) -> Experiment:
    """An experiment with one of every dependent record type."""
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
        researcher="Test Researcher",
    )
    db.add(exp)
    db.flush()

    cond = ExperimentalConditions(experiment_fk=exp.id, experiment_id=experiment_id, temperature_c=80.0)
    db.add(cond)
    db.flush()

    compound = Compound(name=f"Magnetite {number}", molecular_weight_g_mol=231.5)
    db.add(compound)
    db.flush()
    # ChemicalAdditive.experiment_id is the CONDITIONS row id (Integer FK), and
    # `unit` is Column(Enum(AmountUnit)) -- a bare "g" string will not bind.
    db.add(ChemicalAdditive(experiment_id=cond.id, compound_id=compound.id,
                            amount=5.0, unit=AmountUnit.GRAM))

    result = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=7.0,
        time_post_reaction_bucket_days=7.0,
        is_primary_timepoint_result=True,
        description="t7 sample",
    )
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, final_ph=7.4))
    db.add(ICPResults(result_id=result.id, fe=980.0))
    db.add(ResultFiles(result_id=result.id, file_path="/tmp/x.csv", file_name="x.csv"))

    db.add(ExperimentNotes(experiment_id=experiment_id, experiment_fk=exp.id, note_text="a note"))
    db.add(ExternalAnalysis(experiment_fk=exp.id, experiment_id=experiment_id, analysis_type="XRD"))
    db.add(XRDPhase(experiment_fk=exp.id, experiment_id=experiment_id,
                    time_post_reaction_days=7, mineral_name="Magnetite", amount=12.0))
    db.add(ReactorChangeRequest(reactor_label="R01", experiment_id=experiment_id,
                                requested_change="swap", sync_date=date(2026, 7, 28)))
    db.commit()
    db.refresh(exp)
    return exp


def test_collect_impact_counts_every_dependent_record(db):
    from backend.services.experiment_deletion import collect_delete_impact

    exp = _full_experiment(db)
    impact = collect_delete_impact(db, exp)

    assert impact.experiment_id == "DEL_FULL_001"
    assert impact.results == 1
    assert impact.scalar_results == 1
    assert impact.icp_results == 1
    assert impact.result_files == 1
    assert impact.notes == 1
    assert impact.additives == 1
    assert impact.external_analyses == 1
    assert impact.xrd_phases == 1
    assert impact.change_requests == 1
    assert impact.total == 9


def test_collect_impact_is_zero_for_a_bare_experiment(db):
    from backend.services.experiment_deletion import collect_delete_impact

    exp = Experiment(experiment_id="DEL_BARE_001", experiment_number=7102,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.commit()
    db.refresh(exp)

    impact = collect_delete_impact(db, exp)
    assert impact.total == 0
    assert impact.background_for == []
    assert impact.replicate_children == []


def test_collect_impact_reports_background_dependents_by_string(db):
    """background_experiment_fk is unpopulated in practice (0/1056 rows) — the
    STRING column is the real reference and has no FK protecting it."""
    from backend.services.experiment_deletion import collect_delete_impact

    target = Experiment(experiment_id="DEL_BG_TARGET", experiment_number=7103,
                        status=ExperimentStatus.ONGOING)
    other = Experiment(experiment_id="DEL_BG_USER", experiment_number=7104,
                       status=ExperimentStatus.ONGOING)
    db.add_all([target, other])
    db.flush()

    result = ExperimentalResults(experiment_fk=other.id, time_post_reaction_days=0.0,
                                 is_primary_timepoint_result=True, description="t0")
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, background_experiment_id="DEL_BG_TARGET"))
    db.commit()
    db.refresh(target)

    impact = collect_delete_impact(db, target)
    assert impact.background_for == ["DEL_BG_USER"]
    assert impact.total == 0  # decoupled, not destroyed


def test_collect_impact_reports_replicate_children(db):
    from backend.services.experiment_deletion import collect_delete_impact

    parent = Experiment(experiment_id="DEL_PARENT_001", experiment_number=7105,
                        status=ExperimentStatus.ONGOING)
    db.add(parent)
    db.flush()
    db.add(Experiment(experiment_id="DEL_PARENT_001a", experiment_number=7106,
                      status=ExperimentStatus.ONGOING, base_experiment_id="DEL_PARENT_001",
                      replicate_label="a", parent_experiment_fk=parent.id))
    db.commit()
    db.refresh(parent)

    impact = collect_delete_impact(db, parent)
    assert impact.replicate_children == ["DEL_PARENT_001a"]


def test_collect_impact_counts_xrd_phases_matched_by_string_only(db):
    """A phase row whose experiment_fk was already nulled by a previous delete
    still names the experiment by string and still blocks the unique constraint."""
    from backend.services.experiment_deletion import collect_delete_impact

    exp = Experiment(experiment_id="DEL_XRD_001", experiment_number=7107,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    db.add(XRDPhase(experiment_fk=exp.id, experiment_id="DEL_XRD_001",
                    time_post_reaction_days=0, mineral_name="Olivine", amount=5.0))
    db.add(XRDPhase(experiment_fk=None, experiment_id="DEL_XRD_001",
                    time_post_reaction_days=7, mineral_name="Olivine", amount=6.0))
    db.commit()
    db.refresh(exp)

    assert collect_delete_impact(db, exp).xrd_phases == 2
