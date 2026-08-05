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
from database.models.characterization import Analyte, ElementalAnalysis
from database.models.xrd import XRDPhase
from database.models.notion_sync import ReactorChangeRequest
from tests.pre_constraint_conditions import without_conditions_unique

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
    assert impact.conditions == 1
    assert impact.results == 1
    assert impact.scalar_results == 1
    assert impact.icp_results == 1
    assert impact.result_files == 1
    assert impact.notes == 1
    assert impact.additives == 1
    assert impact.external_analyses == 1
    assert impact.xrd_phases == 1
    assert impact.change_requests == 1
    assert impact.total == 10


def test_collect_impact_counts_the_conditions_row(db):
    """The commonest live shape: conditions and nothing else (44 experiments in
    the dev DB). The conditions row is hard-deleted by the ORM cascade, so it
    must be counted -- otherwise total == 0 and the dialog says "nothing else is
    affected" while a full setup record is destroyed."""
    from backend.services.experiment_deletion import collect_delete_impact

    exp = Experiment(experiment_id="DEL_COND_001", experiment_number=7112,
                     status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(experiment_fk=exp.id, experiment_id="DEL_COND_001",
                                  temperature_c=90.0, rock_mass_g=10.0))
    db.commit()
    db.refresh(exp)

    impact = collect_delete_impact(db, exp)
    assert impact.conditions == 1
    assert impact.total == 1  # counted, so the typed-ID gate engages


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


def test_snapshot_captures_experiment_conditions_and_additives(db):
    from backend.services.experiment_deletion import serialize_experiment_snapshot

    exp = _full_experiment(db, "DEL_SNAP_001", 7201)
    snap = serialize_experiment_snapshot(db, exp)

    assert snap["experiment"]["experiment_id"] == "DEL_SNAP_001"
    assert snap["experiment"]["experiment_number"] == 7201
    assert snap["experiment"]["researcher"] == "Test Researcher"
    assert snap["experiment"]["status"] == "ONGOING"
    assert snap["conditions"]["temperature_c"] == 80.0
    assert len(snap["additives"]) == 1
    assert snap["additives"][0]["compound_name"] == "Magnetite 7201"
    assert snap["additives"][0]["amount"] == 5.0
    assert snap["notes"] == ["a note"]


def test_snapshot_is_json_serializable(db):
    """old_values is a JSONB column -- datetimes and enums must already be
    primitives or the flush fails."""
    import json
    from datetime import datetime, timezone
    from backend.services.experiment_deletion import serialize_experiment_snapshot

    exp = _full_experiment(db, "DEL_JSON_001", 7202)
    exp.date = datetime(2026, 7, 20, tzinfo=timezone.utc)
    db.commit()

    json.dumps(serialize_experiment_snapshot(db, exp))  # must not raise


def test_delete_writes_a_log_row_that_survives_the_delete(db):
    from backend.services.experiment_deletion import delete_experiment_cascade

    exp = _full_experiment(db, "DEL_LOG_001", 7203)
    delete_experiment_cascade(db, exp, modified_by="tester@addisenergy.com")

    assert db.execute(
        select(Experiment).where(Experiment.experiment_id == "DEL_LOG_001")
    ).scalar_one_or_none() is None

    entry = db.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_id == "DEL_LOG_001",
            ModificationsLog.modification_type == "delete",
        )
    ).scalar_one()
    # experiment_fk MUST be NULL: that FK is ondelete="CASCADE", so a populated
    # value would have deleted this very row along with the experiment.
    assert entry.experiment_fk is None
    assert entry.modified_table == "experiments"
    assert entry.modified_by == "tester@addisenergy.com"
    assert entry.old_values["experiment"]["experiment_number"] == 7203
    assert entry.old_values["conditions"]["temperature_c"] == 80.0
    assert entry.new_values["impact"]["results"] == 1


def test_delete_removes_xrd_phases_freeing_the_unique_slot(db):
    from backend.services.experiment_deletion import delete_experiment_cascade

    exp = _full_experiment(db, "DEL_XRD_FREE", 7204)
    delete_experiment_cascade(db, exp, modified_by="tester@addisenergy.com")

    assert db.execute(
        select(func.count()).select_from(XRDPhase)
        .where(XRDPhase.experiment_id == "DEL_XRD_FREE")
    ).scalar_one() == 0

    # The freed (experiment_id, time, mineral) slot is reusable.
    db.add(XRDPhase(experiment_fk=None, experiment_id="DEL_XRD_FREE",
                    time_post_reaction_days=7, mineral_name="Magnetite", amount=13.0))
    db.commit()  # must not raise on uq_xrd_phase_experiment_time_mineral


def test_delete_decouples_background_string_and_fk(db):
    from backend.services.experiment_deletion import delete_experiment_cascade

    target = Experiment(experiment_id="DEL_BG2_TARGET", experiment_number=7205,
                        status=ExperimentStatus.ONGOING)
    other = Experiment(experiment_id="DEL_BG2_USER", experiment_number=7206,
                       status=ExperimentStatus.ONGOING)
    db.add_all([target, other])
    db.flush()
    result = ExperimentalResults(experiment_fk=other.id, time_post_reaction_days=0.0,
                                 is_primary_timepoint_result=True, description="t0")
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, background_experiment_id="DEL_BG2_TARGET",
                         background_experiment_fk=target.id,
                         background_ammonium_concentration_mM=0.2))
    db.commit()
    db.refresh(target)

    impact = delete_experiment_cascade(db, target, modified_by="tester@addisenergy.com")
    assert impact.background_for == ["DEL_BG2_USER"]

    scalar = db.execute(
        select(ScalarResults).where(ScalarResults.result_id == result.id)
    ).scalar_one()
    assert scalar.background_experiment_id is None
    assert scalar.background_experiment_fk is None
    # Provenance only -- the background NUMBER is untouched, so no derived
    # field changed and no recalculate() was needed.
    assert scalar.background_ammonium_concentration_mM == 0.2


def test_delete_purges_change_requests(db):
    """Product decision (2026-07-29): change requests are PURGED with the
    experiment, not unlinked. This also makes `change_requests` -- already summed
    into `total`, which is documented as rows destroyed -- truthful."""
    from backend.services.experiment_deletion import delete_experiment_cascade

    exp = _full_experiment(db, "DEL_CR_001", 7207)
    delete_experiment_cascade(db, exp, modified_by="tester@addisenergy.com")

    assert db.execute(
        select(func.count()).select_from(ReactorChangeRequest)
        .where(ReactorChangeRequest.reactor_label == "R01")
    ).scalar_one() == 0


def test_delete_purges_elemental_analysis_children(db):
    """F1 regression guard.

    ElementalAnalysis.external_analysis_id is nullable=False, but the
    relationship is a bare backref with no cascade and no passive_deletes, so
    when Experiment.external_analyses cascade-deletes the parent the ORM first
    emits `UPDATE elemental_analysis SET external_analysis_id=NULL` -- a
    NotNullViolation, HTTP 500, and the delete never completes. Without the
    service-side purge this test raises instead of failing an assert.
    """
    from backend.services.experiment_deletion import delete_experiment_cascade

    exp = _full_experiment(db, "DEL_ELEM_001", 7211)
    ext = db.execute(
        select(ExternalAnalysis).where(ExternalAnalysis.experiment_fk == exp.id)
    ).scalar_one()
    analyte = Analyte(analyte_symbol="FeO_7211", unit="%")
    db.add(analyte)
    db.flush()
    db.add(ElementalAnalysis(external_analysis_id=ext.id, analyte_id=analyte.id,
                             analyte_composition=8.5))
    db.commit()
    ext_id = ext.id

    delete_experiment_cascade(db, exp, modified_by="tester@addisenergy.com")

    assert db.execute(
        select(func.count()).select_from(ElementalAnalysis)
        .where(ElementalAnalysis.external_analysis_id == ext_id)
    ).scalar_one() == 0, "elemental_analysis rows left behind"
    assert db.execute(
        select(func.count()).select_from(ExternalAnalysis)
        .where(ExternalAnalysis.id == ext_id)
    ).scalar_one() == 0


def test_delete_leaves_no_orphan_rows_anywhere(db):
    """The headline acceptance criterion, checked table by table."""
    from backend.services.experiment_deletion import delete_experiment_cascade

    exp = _full_experiment(db, "DEL_ORPHAN_001", 7208)
    exp_pk = exp.id
    delete_experiment_cascade(db, exp, modified_by="tester@addisenergy.com")

    for model, clause in [
        (ExperimentalConditions, ExperimentalConditions.experiment_fk == exp_pk),
        (ExperimentNotes, ExperimentNotes.experiment_fk == exp_pk),
        (ExternalAnalysis, ExternalAnalysis.experiment_fk == exp_pk),
        (ExperimentalResults, ExperimentalResults.experiment_fk == exp_pk),
        (XRDPhase, XRDPhase.experiment_id == "DEL_ORPHAN_001"),
        (XRDPhase, XRDPhase.experiment_fk == exp_pk),
    ]:
        assert db.execute(
            select(func.count()).select_from(model).where(clause)
        ).scalar_one() == 0, f"orphan rows left in {model.__tablename__}"


def test_delete_nulls_replicate_children_parent_fk_but_keeps_the_group_string(db):
    from backend.services.experiment_deletion import delete_experiment_cascade

    parent = Experiment(experiment_id="DEL_GP_001", experiment_number=7209,
                        status=ExperimentStatus.ONGOING)
    db.add(parent)
    db.flush()
    db.add(Experiment(experiment_id="DEL_GP_001a", experiment_number=7210,
                      status=ExperimentStatus.ONGOING, base_experiment_id="DEL_GP_001",
                      replicate_label="a", parent_experiment_fk=parent.id))
    db.commit()
    db.refresh(parent)

    impact = delete_experiment_cascade(db, parent, modified_by="tester@addisenergy.com")
    assert impact.replicate_children == ["DEL_GP_001a"]

    child = db.execute(
        select(Experiment).where(Experiment.experiment_id == "DEL_GP_001a")
    ).scalar_one()
    assert child.parent_experiment_fk is None
    # base_experiment_id survives, so /experiments/groups/DEL_GP_001 still
    # resolves the group by string (MODELS.md, issue #87).
    assert child.base_experiment_id == "DEL_GP_001"
    assert child.replicate_label == "a"


def test_delete_succeeds_with_two_conditions_rows(db):
    """Regression (issue #109): serialize_experiment_snapshot used
    scalar_one_or_none on conditions, so a duplicate row raised
    MultipleResultsFound inside delete_experiment_cascade -- which is why the
    bulk-delete tool reported the row as failed and could not remove it."""
    from backend.services.experiment_deletion import delete_experiment_cascade

    # Pre-dates uq_conditions_experiment_fk (issue #109) — see helper docstring.
    with without_conditions_unique(db):
        exp = Experiment(experiment_id="DUPCOND_001", experiment_number=63001,
                         status=ExperimentStatus.ONGOING)
        db.add(exp)
        db.flush()
        db.add(ExperimentalConditions(experiment_fk=exp.id, experiment_id="DUPCOND_001",
                                      temperature_c=90.0))
        db.add(ExperimentalConditions(experiment_fk=exp.id, experiment_id="DUPCOND_OLD",
                                      temperature_c=90.0))
        db.commit()

        impact = delete_experiment_cascade(db, exp, modified_by="tester")

        assert impact.conditions == 2
        assert db.execute(
            select(Experiment).where(Experiment.experiment_id == "DUPCOND_001")
        ).scalar_one_or_none() is None
        assert db.execute(
            select(func.count()).select_from(ExperimentalConditions)
            .where(ExperimentalConditions.experiment_fk == exp.id)
        ).scalar_one() == 0
