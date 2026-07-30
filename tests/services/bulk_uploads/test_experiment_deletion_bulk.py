"""Bulk experiment deletion from an uploaded ID list (issue #109, Phase 1).

The per-experiment purge itself is `experiment_deletion.delete_experiment_cascade`
and is covered by tests/services/test_experiment_deletion.py. What is tested here
is the batch wrapper: column parsing, dedupe, missing-ID reporting, and the
requirement that one bad row must not stop the rest of the batch.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment, ModificationsLog

from .excel_helpers import make_excel


def _experiment(db_session, experiment_id: str, number: int) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
        researcher="Test Researcher",
    )
    db_session.add(exp)
    db_session.commit()
    return exp


def _ids_file(ids: list[str | None], header: str = "experiment_id") -> bytes:
    return make_excel([header], [[i] for i in ids])


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_reads_the_experiment_id_column():
    from backend.services.bulk_uploads.experiment_deletion_bulk import parse_experiment_ids

    ids, errors = parse_experiment_ids(_ids_file(["BDEL_001", "BDEL_002"]), "ids.xlsx")

    assert ids == ["BDEL_001", "BDEL_002"]
    assert errors == []


def test_parse_dedupes_and_drops_blank_rows():
    from backend.services.bulk_uploads.experiment_deletion_bulk import parse_experiment_ids

    ids, errors = parse_experiment_ids(
        _ids_file(["BDEL_001", None, " BDEL_001 ", "", "BDEL_002"]), "ids.xlsx"
    )

    assert ids == ["BDEL_001", "BDEL_002"]
    assert errors == []


def test_parse_accepts_a_differently_cased_header():
    from backend.services.bulk_uploads.experiment_deletion_bulk import parse_experiment_ids

    ids, errors = parse_experiment_ids(_ids_file(["BDEL_001"], header="Experiment ID"), "ids.xlsx")

    assert ids == ["BDEL_001"]
    assert errors == []


def test_parse_reads_a_csv_file():
    from backend.services.bulk_uploads.experiment_deletion_bulk import parse_experiment_ids

    ids, errors = parse_experiment_ids(b"experiment_id\nBDEL_001\nBDEL_002\n", "ids.csv")

    assert ids == ["BDEL_001", "BDEL_002"]
    assert errors == []


def test_parse_reports_a_missing_id_column():
    from backend.services.bulk_uploads.experiment_deletion_bulk import parse_experiment_ids

    ids, errors = parse_experiment_ids(make_excel(["status"], [["ONGOING"]]), "ids.xlsx")

    assert ids == []
    assert any("experiment_id" in e for e in errors)


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------

def test_delete_removes_exactly_the_listed_experiments(db_session):
    from backend.services.bulk_uploads.experiment_deletion_bulk import delete_experiments_from_file

    _experiment(db_session, "BDEL_DEL_001", 7301)
    _experiment(db_session, "BDEL_DEL_002", 7302)
    _experiment(db_session, "BDEL_KEEP_001", 7303)

    result = delete_experiments_from_file(
        db_session,
        _ids_file(["BDEL_DEL_001", "BDEL_DEL_002"]),
        "ids.xlsx",
        modified_by="mhearl@addisenergy.com",
    )

    assert result.deleted == ["BDEL_DEL_001", "BDEL_DEL_002"]
    assert result.missing == []
    assert result.failed == []

    surviving = db_session.execute(
        select(Experiment.experiment_id).where(
            Experiment.experiment_id.in_(["BDEL_DEL_001", "BDEL_DEL_002", "BDEL_KEEP_001"])
        )
    ).scalars().all()
    assert surviving == ["BDEL_KEEP_001"]


def test_delete_reports_unknown_ids_and_still_deletes_the_rest(db_session):
    from backend.services.bulk_uploads.experiment_deletion_bulk import delete_experiments_from_file

    _experiment(db_session, "BDEL_MIX_001", 7304)

    result = delete_experiments_from_file(
        db_session,
        _ids_file(["BDEL_TYPO_999", "BDEL_MIX_001"]),
        "ids.xlsx",
        modified_by="mhearl@addisenergy.com",
    )

    assert result.missing == ["BDEL_TYPO_999"]
    assert result.deleted == ["BDEL_MIX_001"]
    assert db_session.execute(
        select(Experiment).where(Experiment.experiment_id == "BDEL_MIX_001")
    ).scalar_one_or_none() is None


def test_delete_isolates_a_failing_row_from_the_rest_of_the_batch(db_session):
    """One experiment that cannot be deleted must not abort the batch — it lands
    in `failed` with its reason and the remaining rows still delete."""
    from backend.services.bulk_uploads import experiment_deletion_bulk

    _experiment(db_session, "BDEL_FAIL_001", 7305)
    _experiment(db_session, "BDEL_OK_001", 7306)

    real_cascade = experiment_deletion_bulk.delete_experiment_cascade

    def flaky(db, exp, modified_by):
        if exp.experiment_id == "BDEL_FAIL_001":
            raise RuntimeError("row is locked")
        return real_cascade(db, exp, modified_by)

    with patch.object(experiment_deletion_bulk, "delete_experiment_cascade", flaky):
        result = experiment_deletion_bulk.delete_experiments_from_file(
            db_session,
            _ids_file(["BDEL_FAIL_001", "BDEL_OK_001"]),
            "ids.xlsx",
            modified_by="mhearl@addisenergy.com",
        )

    assert result.deleted == ["BDEL_OK_001"]
    assert [f["experiment_id"] for f in result.failed] == ["BDEL_FAIL_001"]
    assert "row is locked" in result.failed[0]["error"]

    assert db_session.execute(
        select(Experiment).where(Experiment.experiment_id == "BDEL_FAIL_001")
    ).scalar_one_or_none() is not None
    assert db_session.execute(
        select(Experiment).where(Experiment.experiment_id == "BDEL_OK_001")
    ).scalar_one_or_none() is None


def test_delete_writes_one_audit_row_per_deleted_experiment(db_session):
    """delete_experiment_cascade owns the audit row; this asserts the batch path
    actually reaches it for every row rather than bypassing it."""
    from backend.services.bulk_uploads.experiment_deletion_bulk import delete_experiments_from_file

    _experiment(db_session, "BDEL_LOG_001", 7307)
    _experiment(db_session, "BDEL_LOG_002", 7308)

    delete_experiments_from_file(
        db_session,
        _ids_file(["BDEL_LOG_001", "BDEL_LOG_002"]),
        "ids.xlsx",
        modified_by="mhearl@addisenergy.com",
    )

    rows = db_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_id.in_(["BDEL_LOG_001", "BDEL_LOG_002"]),
            ModificationsLog.modification_type == "delete",
        )
    ).scalars().all()

    assert sorted(r.experiment_id for r in rows) == ["BDEL_LOG_001", "BDEL_LOG_002"]
    # experiment_fk must stay NULL or the CASCADE takes the audit row down too.
    assert all(r.experiment_fk is None for r in rows)
    assert all(r.modified_by == "mhearl@addisenergy.com" for r in rows)


def test_delete_returns_file_errors_and_deletes_nothing(db_session):
    from backend.services.bulk_uploads.experiment_deletion_bulk import delete_experiments_from_file

    _experiment(db_session, "BDEL_SAFE_001", 7309)
    before = db_session.execute(select(func.count()).select_from(Experiment)).scalar_one()

    result = delete_experiments_from_file(
        db_session,
        make_excel(["status"], [["ONGOING"]]),
        "ids.xlsx",
        modified_by="mhearl@addisenergy.com",
    )

    assert result.errors
    assert result.deleted == []
    assert db_session.execute(
        select(func.count()).select_from(Experiment)
    ).scalar_one() == before


@pytest.mark.parametrize("ids", [[], [None, ""]])
def test_delete_reports_an_empty_id_list_as_an_error(db_session, ids):
    from backend.services.bulk_uploads.experiment_deletion_bulk import delete_experiments_from_file

    result = delete_experiments_from_file(
        db_session, _ids_file(ids), "ids.xlsx", modified_by="mhearl@addisenergy.com"
    )

    assert result.errors
    assert result.deleted == []
