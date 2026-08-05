"""PATCH /api/experiments/{id} must sync every denormalized experiment_id copy."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from database import (
    Experiment,
    ExperimentNotes,
    ExperimentalConditions,
    ExternalAnalysis,
    ModificationsLog,
    XRDPhase,
)
from database.models.enums import ExperimentStatus
from tests.api.conftest import _test_engine

_ID_PREFIX = "RENAME_API_"


@pytest.fixture(autouse=True)
def purge_committed_rows():
    """Delete anything this module may have committed for real, after every test.

    Follows the convention established by `test_bulk_uploads_plan_gate.py`
    (see its fixture for the full rationale). This module seeds with
    `db_session.commit()` and then calls an endpoint that commits again, so it
    is exactly the shape at risk: if the conftest fixture's outer transaction
    is ever consumed, its teardown `transaction.rollback()` becomes a no-op,
    the rows genuinely land in `experiments_test`, and every later test
    asserting an empty experiments table fails — notably
    `tests/api/test_experiments.py::test_list_experiments_empty`, a cross-file
    order-dependent failure that is miserable to diagnose from the other end.

    Measured on SQLAlchemy 2.0.39 (2026-08-05): a plain `session.commit()` on a
    session joined to an externally-begun transaction does NOT commit that
    outer transaction, so no leak reproduces from this module today. What does
    deassociate it is an error path — a flush that raises leaves the
    "transaction already deassociated from connection" SAWarning and a
    genuinely committed state. This purge is therefore cheap insurance rather
    than a fix for an observed failure: it keeps the module safe under
    reordering, under a future test here that trips an IntegrityError, and
    under a SQLAlchemy upgrade that changes the join-transaction semantics.

    Every ID in this module uses the `RENAME_API_` prefix so this stays
    surgical; child rows go with the parent via ON DELETE CASCADE, which
    `experiments_test` has because it is built with `Base.metadata.create_all`.
    """
    yield
    with _test_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM experiments WHERE experiment_id LIKE :prefix"),
            {"prefix": f"{_ID_PREFIX}%"},
        )


def test_patch_rename_syncs_all_denormalized_ids(client, db_session):
    exp = Experiment(
        experiment_id="RENAME_API_001",
        experiment_number=8802001,
        status=ExperimentStatus.ONGOING,
    )
    db_session.add(exp)
    db_session.flush()
    db_session.add_all([
        ExperimentalConditions(
            experiment_id="RENAME_API_001", experiment_fk=exp.id, temperature_c=200.0
        ),
        ExperimentNotes(
            experiment_id="RENAME_API_001", experiment_fk=exp.id, note_text="n"
        ),
        ModificationsLog(
            experiment_id="RENAME_API_001", experiment_fk=exp.id,
            modified_by="t", modification_type="create", modified_table="experiments",
        ),
        ExternalAnalysis(
            experiment_id="RENAME_API_001", experiment_fk=exp.id, analysis_type="XRD"
        ),
        XRDPhase(
            experiment_id="RENAME_API_001", experiment_fk=exp.id,
            mineral_name="Olivine", amount=4.0, time_post_reaction_days=1.0,
        ),
    ])
    db_session.commit()
    exp_pk = exp.id

    resp = client.patch(
        "/api/experiments/RENAME_API_001",
        json={"experiment_id": "RENAME_API_001a-t1"},
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    for model in (ExperimentalConditions, ExperimentNotes, ExternalAnalysis, XRDPhase):
        for row in db_session.query(model).filter(model.experiment_fk == exp_pk).all():
            assert row.experiment_id == "RENAME_API_001a-t1", (
                f"{model.__name__} not synced: {row.experiment_id!r}"
            )
    # Every modifications_log row for this experiment now names the new id,
    # including the pre-existing one and the row the rename itself wrote.
    mods = db_session.query(ModificationsLog).filter(
        ModificationsLog.experiment_fk == exp_pk
    ).all()
    assert mods
    assert {m.experiment_id for m in mods} == {"RENAME_API_001a-t1"}
