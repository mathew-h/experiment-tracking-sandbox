"""Regression tests for issue #86.

Two independent defects on the New-Experiments bulk-upload rename path:

  A. The rename branch recomputed lineage from an UNFLUSHED experiment_id, so the
     group-parent SELECT still saw the row's OLD id. When the old id and the new
     replicate stem normalize to the same string (e.g. ``X_cation_001`` ->
     ``X_Cation_001a-t5`` both normalize to ``xcation001``), the query matched the
     row against itself and set it as its own parent -> ``CircularDependencyError``
     at flush.  Fixed by A1 (flush the rename before the lineage lookup) and A2
     (defensive self-parent guard in ``update_experiment_lineage``).

  B. The per-row handler appended a warning and continued without rolling back, so
     one row's failed flush left the session in a pending-rollback state and every
     later row raised ``PendingRollbackError`` — burying the real error and failing
     the whole file.  Fixed by wrapping each row in a ``begin_nested`` savepoint.

These tests use a production-faithful session with ``autoflush=False`` (matching
``database.database.SessionLocal``).  The shared ``db_session`` conftest fixture
uses ``autoflush=True``, which would flush the pending rename before the lineage
SELECT and therefore MASK defect A entirely (see the issue's "out of scope" note
on ``autoflush``).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database import Experiment
from database.models.enums import ExperimentStatus
from database.lineage_utils import update_experiment_lineage
from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService

from .excel_helpers import make_excel

# Same test DB as conftest, but autoflush OFF to mirror production SessionLocal.
_TEST_DB_URL = "postgresql://experiments_user:password@localhost:5432/experiments_test"
_engine = create_engine(_TEST_DB_URL, pool_pre_ping=True)
_SessionAutoflushOff = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

_EXP_HEADERS = [
    "experiment_id",
    "old_experiment_id",
    "sample_id",
    "researcher",
    "date",
    "status",
    "initial_note",
    "overwrite",
]


@pytest.fixture()
def pg_session(create_test_tables) -> Session:
    """Per-test autoflush=False session, wrapped in a transaction that rolls back."""
    connection = _engine.connect()
    transaction = connection.begin()
    session = _SessionAutoflushOff(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _experiments_excel(rows: list[list]) -> bytes:
    return make_excel(_EXP_HEADERS, rows, sheet_name="experiments")


# --------------------------------------------------------------------------- #
# Defect A — self-parent on a normalize collision                             #
# --------------------------------------------------------------------------- #


def test_update_lineage_drops_self_parent_on_normalize_collision(pg_session: Session):
    """A2 unit test: when the only row matching the group-parent stem IS the
    experiment itself (because its rename hasn't been flushed), the self-parent
    must be dropped rather than assigned."""
    exp = Experiment(
        experiment_id="X_cation_001",
        experiment_number=8601001,
        status=ExperimentStatus.ONGOING,
    )
    pg_session.add(exp)
    pg_session.flush()  # persisted with the OLD id

    # Rename in memory only (NOT flushed): the group-parent SELECT for the new
    # stem "X_Cation_001" (norm "xcation001") still matches the persisted OLD id
    # "X_cation_001" (norm "xcation001") -> resolves to this same object.
    exp.experiment_id = "X_Cation_001a-t5"

    update_experiment_lineage(pg_session, exp)

    assert exp.parent is None, "experiment was set as its own parent"
    assert exp.parent_experiment_fk is None
    # Must not raise CircularDependencyError:
    pg_session.flush()
    assert exp.parent_experiment_fk is None
    assert exp.replicate_label == "a"
    assert exp.base_experiment_id == "X_Cation_001"


def test_rename_into_replicate_stem_no_circular_dependency(pg_session: Session):
    """A (direct, via upload): renaming X_cation_001 -> X_Cation_001a-t5 (old id
    normalizes to the new replicate stem) must succeed with correct lineage and
    no CircularDependencyError / PendingRollbackError."""
    seed = Experiment(
        experiment_id="X_cation_001",
        experiment_number=8601010,
        status=ExperimentStatus.ONGOING,
    )
    pg_session.add(seed)
    pg_session.flush()

    xlsx = _experiments_excel(
        [
            ["X_Cation_001a-t5", "X_cation_001", None, None, None, None, None, True],
        ]
    )
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(pg_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert not any(
        "CircularDependency" in w or "PendingRollback" in w for w in warnings
    ), f"Unexpected crash warnings: {warnings}"
    assert updated == 1

    renamed = (
        pg_session.query(Experiment).filter_by(experiment_id="X_Cation_001a-t5").first()
    )
    assert renamed is not None, "rename was not persisted"
    assert renamed.base_experiment_id == "X_Cation_001"
    assert renamed.replicate_label == "a"
    assert renamed.id_timepoint_days == 5.0
    assert renamed.parent_experiment_fk != renamed.id, "experiment is its own parent"


def test_rename_sibling_group_gets_abc_labels(pg_session: Session):
    """A (sibling group): the 3-row triplet from the issue renames a flat sequence
    into a lettered replicate group; each row must get a/b/c and a shared base."""
    for i, n in enumerate((1, 2, 3), start=0):
        pg_session.add(
            Experiment(
                experiment_id=f"X_cation_00{n}",
                experiment_number=8601020 + i,
                status=ExperimentStatus.ONGOING,
            )
        )
    pg_session.flush()

    xlsx = _experiments_excel(
        [
            ["X_Cation_001a-t5", "X_cation_001", None, None, None, None, None, True],
            ["X_Cation_001b-t5", "X_cation_002", None, None, None, None, None, True],
            ["X_Cation_001c-t5", "X_cation_003", None, None, None, None, None, True],
        ]
    )
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(pg_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert not any(
        "PendingRollback" in w for w in warnings
    ), f"cascade failure: {warnings}"
    assert updated == 3

    labels = {}
    bases = set()
    for letter in ("a", "b", "c"):
        exp = (
            pg_session.query(Experiment)
            .filter_by(experiment_id=f"X_Cation_001{letter}-t5")
            .first()
        )
        assert exp is not None, f"replicate {letter} not persisted"
        labels[letter] = exp.replicate_label
        bases.add(exp.base_experiment_id)

    assert labels == {"a": "a", "b": "b", "c": "c"}
    assert bases == {"X_Cation_001"}, f"replicates do not share a base: {bases}"


# --------------------------------------------------------------------------- #
# Defect B — one bad row must not poison the rest of the batch                #
# --------------------------------------------------------------------------- #


def test_one_bad_row_does_not_poison_batch(pg_session: Session):
    """B: a row that fails its flush (here: a non-existent sample_id FK) must roll
    back only its own savepoint; later valid rows still commit and there is no
    cascading PendingRollbackError."""
    xlsx = _experiments_excel(
        [
            # data row 1 (idx 0 -> "Row 2"): FK violation on flush
            [
                "HPHT_B01_001",
                None,
                "GHOST_SAMPLE_XYZ",
                "MH",
                None,
                "ONGOING",
                None,
                False,
            ],
            # data row 2 (idx 1 -> "Row 3"): valid
            ["HPHT_B01_002", None, None, "MH", None, "ONGOING", None, False],
        ]
    )
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(pg_session, xlsx)
    )

    good = pg_session.query(Experiment).filter_by(experiment_id="HPHT_B01_002").first()
    assert good is not None, "valid row was discarded by an unrelated row's failure"

    bad = pg_session.query(Experiment).filter_by(experiment_id="HPHT_B01_001").first()
    assert bad is None, "the failing row should not have persisted"

    assert created == 1

    row_warnings = [w for w in warnings if "Row 2:" in w]
    assert (
        len(row_warnings) == 1
    ), f"expected exactly one warning for the bad row, got: {warnings}"
    assert not any(
        "PendingRollbackError" in w for w in warnings
    ), f"cascading PendingRollbackError should never appear: {warnings}"


def test_batch_failure_reports_real_exception_not_pending_rollback(pg_session: Session):
    """B (regression): the reported warning must name the failing row and the real
    exception type, not the downstream PendingRollbackError symptom."""
    xlsx = _experiments_excel(
        [
            [
                "HPHT_B02_001",
                None,
                "GHOST_SAMPLE_ABC",
                "MH",
                None,
                "ONGOING",
                None,
                False,
            ],
            ["HPHT_B02_002", None, None, "MH", None, "ONGOING", None, False],
        ]
    )
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(pg_session, xlsx)
    )

    bad_row_warnings = [w for w in warnings if "Row 2:" in w]
    assert (
        len(bad_row_warnings) == 1
    ), f"expected one warning for the bad row, got: {warnings}"
    assert (
        "IntegrityError" in bad_row_warnings[0]
    ), f"expected the real exception type, got: {bad_row_warnings}"
    # The downstream symptom must not appear ANYWHERE: without per-row isolation the
    # next row's query raises PendingRollbackError and that becomes the reported error.
    assert not any(
        "PendingRollbackError" in w for w in warnings
    ), f"the misleading cascade symptom leaked into the report: {warnings}"
