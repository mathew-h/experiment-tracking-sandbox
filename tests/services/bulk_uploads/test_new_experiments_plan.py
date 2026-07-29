"""Tests for NewExperimentsUploadService.bulk_upsert_from_excel_ex's structured
UploadPlan (issue #100 item 2: creates/renames/overwrites/skips/conflicts).

bulk_upsert_from_excel_ex must behave identically to bulk_upsert_from_excel (same
6 leading return values) and additionally return a plan. bulk_upsert_from_excel's
own existing 6-tuple return is exercised elsewhere (test_new_experiments.py,
test_new_experiments_rename_lineage.py, test_new_experiments_additives.py,
tests/test_experiment_rename.py) and is unaffected by this file.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Experiment, ExperimentalConditions
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService

from .excel_helpers import make_excel, make_excel_multisheet

_EXP_HEADERS = [
    "experiment_id", "old_experiment_id", "sample_id", "researcher",
    "date", "status", "initial_note", "overwrite",
]


def _seed_experiment(
    db: Session,
    experiment_id: str,
    exp_num: int,
    status: ExperimentStatus = ExperimentStatus.ONGOING,
) -> Experiment:
    exp = Experiment(experiment_id=experiment_id, experiment_number=exp_num, status=status)
    db.add(exp)
    db.flush()
    return exp


def _experiments_excel(rows: list[list]) -> bytes:
    return make_excel(_EXP_HEADERS, rows, sheet_name="experiments")


def test_create_row_appears_in_plan_creates(db_session: Session):
    xlsx = _experiments_excel([
        ["HPHT_9001", None, None, "MH", "2026-02-01", "ONGOING", None, False],
    ])
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert errors == []
    assert created == 1
    assert plan.counts == {"creates": 1, "renames": 0, "overwrites": 0, "skips": 0, "conflicts": 0}
    assert len(plan.creates) == 1
    assert plan.creates[0].experiment_id == "HPHT_9001"
    assert plan.creates[0].parent_id is None
    assert plan.creates[0].copied_from is None
    assert plan.creates[0].row == 2


def test_sequential_create_records_parent_id_and_copied_from(db_session: Session):
    _seed_experiment(db_session, "HPHT_9010", 10001)

    xlsx = _experiments_excel([
        ["HPHT_9010-2", None, None, "MH", None, "ONGOING", None, False],
    ])
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert errors == []
    assert created == 1
    assert len(plan.creates) == 1
    assert plan.creates[0].experiment_id == "HPHT_9010-2"
    assert plan.creates[0].parent_id == "HPHT_9010"
    assert plan.creates[0].copied_from == "HPHT_9010"


def test_rename_row_appears_in_plan_renames_not_overwrites(db_session: Session):
    _seed_experiment(db_session, "HPHT_9020", 10002)

    xlsx = _experiments_excel([
        ["HPHT_9020_Renamed", "HPHT_9020", None, None, None, None, None, True],
    ])
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert errors == []
    assert updated == 1
    assert plan.counts["renames"] == 1
    assert plan.counts["overwrites"] == 0
    assert plan.renames[0].from_id == "HPHT_9020"
    assert plan.renames[0].to_id == "HPHT_9020_Renamed"


def test_overwrite_records_experiments_sheet_field_diff(db_session: Session):
    _seed_experiment(db_session, "HPHT_9030", 10003, status=ExperimentStatus.ONGOING)

    xlsx = _experiments_excel([
        ["HPHT_9030", None, None, None, None, "COMPLETED", None, True],
    ])
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert errors == []
    assert updated == 1
    assert plan.counts["overwrites"] == 1
    assert plan.counts["renames"] == 0
    overwrite = plan.overwrites[0]
    assert overwrite.experiment_id == "HPHT_9030"
    changed = {fc.field: (fc.old, fc.new) for fc in overwrite.fields_changed}
    assert changed["status"] == ("ONGOING", "COMPLETED")


def test_overwrite_records_conditions_sheet_field_diff(db_session: Session):
    """The issue's own example: an overwrite silently changing initial_ph 4 -> 9
    must be visible in fields_changed."""
    exp = _seed_experiment(db_session, "HPHT_9040", 10004)
    db_session.add(ExperimentalConditions(
        experiment_id=exp.experiment_id, experiment_fk=exp.id, initial_ph=4.0,
    ))
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["HPHT_9040", None, None, None, None, None, None, True]],
        ),
        "conditions": (
            ["experiment_id", "initial_ph"],
            [["HPHT_9040", 9.0]],
        ),
    })
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert errors == []
    assert plan.counts["overwrites"] == 1
    overwrite = plan.overwrites[0]
    assert overwrite.experiment_id == "HPHT_9040"
    changed = {fc.field: (fc.old, fc.new) for fc in overwrite.fields_changed}
    assert changed["initial_ph"] == (4.0, 9.0)


def test_conditions_only_overwrite_with_no_experiments_row_change(db_session: Session):
    """A conditions-sheet-only field change (no experiments-sheet diff on the same
    row) must still surface as one PlanOverwrite, keyed by experiment_id."""
    exp = _seed_experiment(db_session, "HPHT_9041", 10041)
    db_session.add(ExperimentalConditions(
        experiment_id=exp.experiment_id, experiment_fk=exp.id, rock_mass_g=5.0,
    ))
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["HPHT_9041", None, None, None, None, None, None, True]],
        ),
        "conditions": (
            ["experiment_id", "rock_mass_g"],
            [["HPHT_9041", 8.0]],
        ),
    })
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert errors == []
    assert len(plan.overwrites) == 1
    changed = {fc.field: (fc.old, fc.new) for fc in plan.overwrites[0].fields_changed}
    assert changed["rock_mass_g"] == (5.0, 8.0)


def test_brand_new_conditions_row_is_not_diffed_as_overwrite(db_session: Session):
    """A conditions row created for the first time (no prior value) must not be
    reported as a field change — there's nothing to have silently overwritten."""
    _seed_experiment(db_session, "HPHT_9042", 10042)

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["HPHT_9042", None, None, None, None, None, None, True]],
        ),
        "conditions": (
            ["experiment_id", "rock_mass_g"],
            [["HPHT_9042", 8.0]],
        ),
    })
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert errors == []
    assert plan.counts["overwrites"] == 0


def test_empty_experiment_id_row_appears_in_plan_skips(db_session: Session):
    xlsx = _experiments_excel([
        [" ", None, None, None, None, None, None, False],
    ])
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert plan.counts["skips"] == 1
    assert plan.skips[0].reason == "empty experiment_id"


def test_already_exists_without_overwrite_appears_in_plan_conflicts(db_session: Session):
    _seed_experiment(db_session, "HPHT_9050", 10005)

    xlsx = _experiments_excel([
        ["HPHT_9050", None, None, None, None, None, None, False],
    ])
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert plan.counts["conflicts"] == 1
    assert plan.conflicts[0].kind == "already_exists"


def test_rename_without_overwrite_appears_in_plan_conflicts(db_session: Session):
    """issue #100 item 3's guard also shows up in the item 2 plan."""
    _seed_experiment(db_session, "HPHT_9060", 10006)

    xlsx = _experiments_excel([
        ["HPHT_9060_New", "HPHT_9060", None, None, None, None, None, False],
    ])
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert plan.counts["conflicts"] == 1
    assert plan.conflicts[0].kind == "rename_without_overwrite"


def test_overwrite_nonexistent_appears_in_plan_conflicts(db_session: Session):
    xlsx = _experiments_excel([
        ["HPHT_9070_GHOST", None, None, None, None, None, None, True],
    ])
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert plan.counts["conflicts"] == 1
    assert plan.conflicts[0].kind == "overwrite_nonexistent"


def test_multi_row_upload_counts_match_category_lengths(db_session: Session):
    _seed_experiment(db_session, "HPHT_9080", 10007)
    _seed_experiment(db_session, "HPHT_9081", 10008)

    xlsx = _experiments_excel([
        ["HPHT_9082", None, None, "MH", None, "ONGOING", None, False],       # create
        ["HPHT_9080_Renamed", "HPHT_9080", None, None, None, None, None, True],  # rename
        ["HPHT_9081", None, None, None, None, "COMPLETED", None, True],      # overwrite
        [" ", None, None, None, None, None, None, False],                        # skip
        ["HPHT_9090_GHOST", None, None, None, None, None, None, True],       # conflict
    ])
    created, updated, skipped, errors, warnings, info, plan = (
        NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx)
    )

    assert errors == []
    counts = plan.counts
    assert counts["creates"] == len(plan.creates) == 1
    assert counts["renames"] == len(plan.renames) == 1
    assert counts["overwrites"] == len(plan.overwrites) == 1
    assert counts["skips"] == len(plan.skips) == 1
    assert counts["conflicts"] == len(plan.conflicts) == 1


def test_bulk_upsert_from_excel_and_ex_agree_on_leading_six_values(db_session: Session):
    """bulk_upsert_from_excel and bulk_upsert_from_excel_ex must produce identical
    created/updated/skipped/errors/warnings/info for the same input (issue #100
    item 2's additive-not-breaking constraint)."""
    xlsx = _experiments_excel([
        ["HPHT_9100", None, None, "MH", None, "ONGOING", None, False],
    ])
    plain = NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)

    xlsx2 = _experiments_excel([
        ["HPHT_9101", None, None, "MH", None, "ONGOING", None, False],
    ])
    ex_result = NewExperimentsUploadService.bulk_upsert_from_excel_ex(db_session, xlsx2)

    assert len(plain) == 6
    assert len(ex_result) == 7
    assert plain[:3] == (1, 0, 0)
    assert ex_result[:3] == (1, 0, 0)
