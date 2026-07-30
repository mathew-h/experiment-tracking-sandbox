"""Tests for NewExperimentsUploadService.bulk_upsert_from_excel overwrite behavior.

Regression coverage for issue #68: db.expire_all() (called after the experiments-sheet
loop) was discarding unflushed status/sample_id/researcher/date writes made in the
update-existing-experiment branch before they were ever persisted.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Experiment, ExperimentalConditions, SampleInfo
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
    sample_id: str | None = None,
    researcher: str | None = None,
) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=status,
        sample_id=sample_id,
        researcher=researcher,
    )
    db.add(exp)
    db.flush()
    return exp


def _seed_sample(db: Session, sample_id: str) -> SampleInfo:
    sample = SampleInfo(sample_id=sample_id)
    db.add(sample)
    db.flush()
    return sample


def _experiments_excel(rows: list[list]) -> bytes:
    return make_excel(_EXP_HEADERS, rows, sheet_name="experiments")


def test_overwrite_persists_status_sample_researcher_date(db_session: Session):
    """overwrite=True on an existing experiment must persist status/sample_id/researcher/date."""
    _seed_experiment(db_session, "HPHT_I68_001", 68001, status=ExperimentStatus.ONGOING)
    _seed_sample(db_session, "SAMPLE-I68-001")

    xlsx = _experiments_excel([
        ["HPHT_I68_001", None, "SAMPLE-I68-001", "JD", "2026-02-01", "QUEUED", None, True],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1
    assert created == 0

    exp = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_001").first()
    assert exp.status == ExperimentStatus.QUEUED, "status overwrite was silently discarded"
    assert exp.sample_id == "SAMPLE-I68-001", "sample_id overwrite was silently discarded"
    assert exp.researcher == "JD", "researcher overwrite was silently discarded"
    assert exp.date is not None and exp.date.date().isoformat() == "2026-02-01", (
        "date overwrite was silently discarded"
    )


def test_reactivation_via_overwrite_demotes_prior_reactor_occupant(db_session: Session):
    """Setting an existing experiment back to ONGOING in an occupied reactor (via overwrite)
    must trigger manage_reactor_occupancy and demote the current occupant."""
    occupant = _seed_experiment(db_session, "HPHT_I68_010", 68010, status=ExperimentStatus.ONGOING)
    occupant_conditions = ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=7,
        experiment_type="HPHT",
    )
    db_session.add(occupant_conditions)
    _seed_experiment(db_session, "HPHT_I68_011", 68011, status=ExperimentStatus.COMPLETED)
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["HPHT_I68_011", None, None, None, None, "ONGOING", None, True]],
        ),
        "conditions": (
            ["experiment_id", "reactor_number"],
            [["HPHT_I68_011", 7]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"

    reactivated = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_011").first()
    demoted = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_010").first()
    assert reactivated.status == ExperimentStatus.ONGOING
    assert demoted.status == ExperimentStatus.COMPLETED, (
        "reactor occupancy check saw the stale (pre-overwrite) status and never fired"
    )
    assert any("Auto-completed" in m for m in info), (
        f"expected an auto-completion info message, got: {info}"
    )


def test_rename_with_status_change_persists_both(db_session: Session):
    """old_experiment_id rename combined with a status change in the same row must
    persist both the rename and the status change."""
    _seed_experiment(db_session, "HPHT_I68_020", 68020, status=ExperimentStatus.ONGOING)

    xlsx = _experiments_excel([
        ["HPHT_I68_020_Renamed", "HPHT_I68_020", None, None, None, "QUEUED", None, True],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1

    renamed = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_020_Renamed").first()
    assert renamed is not None, "rename was not persisted"
    assert renamed.status == ExperimentStatus.QUEUED, "status change alongside rename was discarded"


def test_new_experiment_creation_path_unaffected(db_session: Session):
    """New-experiment creation (flushed immediately, before expire_all runs) must be unaffected."""
    xlsx = _experiments_excel([
        ["HPHT_I68_030", None, None, "AB", "2026-01-10", "ONGOING", "Created via test", False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert updated == 0

    exp = db_session.query(Experiment).filter_by(experiment_id="HPHT_I68_030").first()
    assert exp is not None
    assert exp.status == ExperimentStatus.ONGOING
    assert exp.researcher == "AB"


def test_duplicate_replicate_id_skips_with_clear_warning_not_crash(db_session: Session):
    """Creating a replicate ID that already exists (overwrite=False) must produce a
    clear warning and skip the row — never raise or silently overwrite."""
    _seed_experiment(db_session, "HPHT_I69_001a", 69001, status=ExperimentStatus.ONGOING)

    xlsx = _experiments_excel([
        ["HPHT_I69_001a", None, None, "MH", "2026-02-01", "ONGOING", None, False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == []
    assert created == 0
    assert updated == 0
    assert any("already exists" in w and "HPHT_I69_001a" in w for w in warnings), (
        f"expected a clear conflict warning naming the ID, got: {warnings}"
    )


def test_old_experiment_id_without_overwrite_conflicts_not_creates(db_session: Session):
    """issue #100: old_experiment_id provided with overwrite falsy must not silently
    fall through to standard matching and CREATE a duplicate — it must emit an
    explicit conflict naming both IDs and skip the row (2026-07-28 SERUM_Catalyst
    incident: 80 intended renames became 80 creates this way)."""
    _seed_experiment(db_session, "SERUM_I100_001", 100001, status=ExperimentStatus.ONGOING)

    xlsx = _experiments_excel([
        ["SERUM_I100_001_New", "SERUM_I100_001", None, None, None, None, None, False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == []
    assert created == 0, "row must not silently create a duplicate experiment"
    assert updated == 0

    ghost = db_session.query(Experiment).filter_by(experiment_id="SERUM_I100_001_New").first()
    assert ghost is None, "duplicate experiment was created instead of being blocked"

    original = db_session.query(Experiment).filter_by(experiment_id="SERUM_I100_001").first()
    assert original is not None, "original experiment must be untouched"

    assert any(
        "SERUM_I100_001" in w and "SERUM_I100_001_New" in w and "overwrite" in w.lower()
        for w in warnings
    ), f"expected an explicit conflict warning naming both IDs, got: {warnings}"


def test_creating_three_replicates_via_bulk_upload(db_session: Session):
    """Creating SERUM_001a/b/c in one upload yields three experiments sharing a base."""
    xlsx = _experiments_excel([
        ["HPHT_I69_010a", None, None, "MH", "2026-02-01", "ONGOING", "Replicate a", False],
        ["HPHT_I69_010b", None, None, "MH", "2026-02-01", "ONGOING", "Replicate b", False],
        ["HPHT_I69_010c", None, None, "MH", "2026-02-01", "ONGOING", "Replicate c", False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == []
    assert created == 3

    rep_a = db_session.query(Experiment).filter_by(experiment_id="HPHT_I69_010a").first()
    rep_b = db_session.query(Experiment).filter_by(experiment_id="HPHT_I69_010b").first()
    rep_c = db_session.query(Experiment).filter_by(experiment_id="HPHT_I69_010c").first()

    assert rep_a.base_experiment_id == "HPHT_I69_010"
    assert rep_b.base_experiment_id == "HPHT_I69_010"
    assert rep_c.base_experiment_id == "HPHT_I69_010"
    assert {rep_a.replicate_label, rep_b.replicate_label, rep_c.replicate_label} == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# Reactor occupancy gates on the new-experiments path (issue #97, Defect 3)
# ---------------------------------------------------------------------------

def test_serum_row_with_reactor_number_does_not_demote_hpht_occupant(db_session: Session):
    """Mirror of test_apply_no_demotion_for_serum_type_even_with_reactor_number
    (test_experiment_status.py:506) on the other write path, which had no
    equivalent. A Serum vial holds no vessel, so it cannot evict one.

    This is NOT a live bug reproduction: Task 4's derive-fallback inside
    `manage_reactor_occupancy` (experiment_status.py:401-410) already resolves
    the slot from `new_experiment.conditions.experiment_type` whenever the
    call site omits `reactor_slot`, and both call sites in new_experiments.py
    did that before this task. So a Serum row already derived `None` and
    returned `(0, [])` even under the old, un-gated call. This test now pins
    that behaviour against regression now that the call site passes
    `reactor_slot` explicitly (removing the dependency on the lazy
    `.conditions` load happening at just the right moment).
    """
    occupant = _seed_experiment(db_session, "HPHT_9731", 97301, status=ExperimentStatus.ONGOING)
    db_session.add(ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=3,
        experiment_type="HPHT",
    ))
    _seed_experiment(db_session, "SERUM_9741", 97302, status=ExperimentStatus.COMPLETED)
    db_session.flush()
    assert occupant.conditions.reactor_slot == "R03"

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_9741", None, None, None, None, "ONGOING", None, True]],
        ),
        "conditions": (
            ["experiment_id", "reactor_number", "experiment_type"],
            [["SERUM_9741", 3, "Serum"]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING, (
        "a Serum row with a stray reactor_number completed the HPHT in R03"
    )
    assert not any("Auto-completed" in m for m in info), (
        f"no auto-completion should be reported, got: {info}"
    )


def test_core_flood_row_does_not_demote_hpht_in_same_number(db_session: Session):
    """The cross-series collision on the new-experiments path. R01 and CF01 are
    different vessels.

    This is NOT a live bug reproduction either: Task 4's derive-fallback
    inside `manage_reactor_occupancy` already scopes occupancy to the
    canonical slot (`derive_reactor_slot(1, "Core Flood") == "CF01"`, not the
    bare integer 1), so a Core Flood row already missed the HPHT sitting in
    R01 before this task's edits. This test pins that behaviour against
    regression now that the call site passes `reactor_slot` explicitly rather
    than relying on the fallback deriving it from a possibly-unflushed
    `.conditions` relationship.
    """
    occupant = _seed_experiment(db_session, "HPHT_9732", 97303, status=ExperimentStatus.ONGOING)
    db_session.add(ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=1,
        experiment_type="HPHT",
    ))
    _seed_experiment(db_session, "CF_9742", 97304, status=ExperimentStatus.COMPLETED)
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["CF_9742", None, None, None, None, "ONGOING", None, True]],
        ),
        "conditions": (
            ["experiment_id", "reactor_number", "experiment_type"],
            [["CF_9742", 1, "Core Flood"]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING, (
        "loading Core Flood rig 1 completed the HPHT in R01"
    )


def test_hpht_row_still_demotes_the_occupant_of_the_same_slot(db_session: Session):
    """Guard against over-correcting. Two HPHTs in R14 is a real collision and the
    demotion must survive — this is the behaviour test_reactivation_via_overwrite_
    demotes_prior_reactor_occupant (line 79) covers via the same path.
    """
    occupant = _seed_experiment(db_session, "HPHT_9733", 97305, status=ExperimentStatus.ONGOING)
    db_session.add(ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=14,
        experiment_type="HPHT",
    ))
    _seed_experiment(db_session, "HPHT_9743", 97306, status=ExperimentStatus.COMPLETED)
    db_session.flush()

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["HPHT_9743", None, None, None, None, "ONGOING", None, True]],
        ),
        "conditions": (
            ["experiment_id", "reactor_number", "experiment_type"],
            [["HPHT_9743", 14, "HPHT"]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    # A fresh query, not db_session.refresh(occupant): manage_reactor_occupancy is
    # called with commit=False, so the demotion is an unflushed pending change.
    # Session.refresh() expires the instance's attributes BEFORE autoflushing,
    # discarding that pending write and reloading the stale (pre-demotion) row;
    # a fresh query autoflushes first, so it observes the demotion. Same reason
    # test_reactivation_via_overwrite_demotes_prior_reactor_occupant (line 79)
    # re-queries rather than calling refresh().
    occupant_after = db_session.query(Experiment).filter_by(experiment_id="HPHT_9733").first()
    assert occupant_after.status == ExperimentStatus.COMPLETED
    assert any("R14" in m for m in info), (
        f"the auto-completion message should name the slot, got: {info}"
    )


def test_zero_reactor_number_does_not_demote_anyone(db_session: Session):
    """reactor_number = 0 is not a slot, so it evicts nobody.

    NOTE: this passes both before and after the change — before, because `if
    conditions.reactor_number` is falsy for 0; after, because derive_reactor_slot
    returns None for 0. It is here because the fix replaces the falsy check with
    `is not None`, and without this guard that swap would silently start treating
    R00 as a real slot. The eight R00 rows in the 2026-07-28 prod audit are this case.
    """
    occupant = _seed_experiment(db_session, "HPHT_9734", 97307, status=ExperimentStatus.ONGOING)
    db_session.add(ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=0,
        experiment_type="HPHT",
    ))
    _seed_experiment(db_session, "HPHT_9744", 97308, status=ExperimentStatus.COMPLETED)
    db_session.flush()
    assert occupant.conditions.reactor_slot is None

    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["HPHT_9744", None, None, None, None, "ONGOING", None, True]],
        ),
        "conditions": (
            ["experiment_id", "reactor_number", "experiment_type"],
            [["HPHT_9744", 0, "HPHT"]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING


def test_auto_copied_conditions_from_parent_demotes_hpht_occupant(db_session: Session):
    """Task 4's review left an open concern: the auto-copy call site
    (new_experiments.py:905, "Auto-copy conditions for experiments with parents
    but no conditions sheet entry") routes through the same derive-fallback as
    the conditions-sheet path, but nothing asserted a demotion actually fires
    there. This closes that gap.

    HPHT_9735-2 is a sequential re-run of HPHT_9735 with NO row on the
    conditions sheet -- in fact no conditions sheet at all in this workbook, so
    the conditions-sheet block (new_experiments.py:780-841, gated on
    `if 'conditions' in normalized`) never runs. The only way HPHT_9735-2 gets
    a reactor_number/experiment_type is via find_parent_for_copy() resolving
    HPHT_9735 as its parent and the "Auto-copy conditions" loop
    (new_experiments.py:845-913) copying the parent's ExperimentalConditions
    fields onto a freshly created ExperimentalConditions row -- which is
    exactly the :903-913 branch under test. This IS the evidence it takes the
    inherited-conditions branch and not the conditions-sheet branch: there is
    no 'conditions' sheet in the xlsx at all, so the conditions-sheet branch
    has nothing to iterate and cannot be what sets reactor_number/type here.
    """
    parent = _seed_experiment(db_session, "HPHT_9735", 97309, status=ExperimentStatus.COMPLETED)
    db_session.add(ExperimentalConditions(
        experiment_id=parent.experiment_id,
        experiment_fk=parent.id,
        reactor_number=5,
        experiment_type="HPHT",
    ))
    occupant = _seed_experiment(db_session, "HPHT_9745", 97310, status=ExperimentStatus.ONGOING)
    db_session.add(ExperimentalConditions(
        experiment_id=occupant.experiment_id,
        experiment_fk=occupant.id,
        reactor_number=5,
        experiment_type="HPHT",
    ))
    db_session.flush()
    assert occupant.conditions.reactor_slot == "R05"

    # Single-sheet workbook: experiments only. No 'conditions' sheet at all, so
    # HPHT_9735-2 can only acquire a reactor_number/experiment_type via the
    # auto-copy-from-parent branch, never via the conditions-sheet branch.
    xlsx = _experiments_excel([
        ["HPHT_9735-2", None, None, None, None, "ONGOING", None, False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    child = db_session.query(Experiment).filter_by(experiment_id="HPHT_9735-2").first()
    assert child is not None, "sequential re-run was not created"
    assert child.conditions is not None, "auto-copy branch did not create a conditions row"
    assert child.conditions.reactor_number == 5, "conditions were not copied from parent"
    assert child.conditions.experiment_type == "HPHT"

    occupant_after = db_session.query(Experiment).filter_by(experiment_id="HPHT_9745").first()
    assert occupant_after.status == ExperimentStatus.COMPLETED, (
        "auto-copied conditions did not trigger reactor occupancy demotion"
    )
    assert any("R05" in m for m in info), (
        f"the auto-completion message should name the slot, got: {info}"
    )
