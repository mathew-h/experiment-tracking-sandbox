"""Tests for ExperimentStatusService.

Per-row model:
- Each row sets its own `status` (ONGOING / COMPLETED / CANCELLED / QUEUED).
- `reactor_number` and `date` are optional; `date` is the experiment start date.
- Setting an HPHT or Core Flood row to ONGOING with a reactor_number schedules
  demotion of an older ONGOING occupant in the same reactor (see Task 2 tests).
- A missing `experiment_id` or `status` column hard-errors the whole upload.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Experiment
from database.models import ExperimentalConditions
from database.models.enums import ExperimentStatus
from backend.services.bulk_uploads.experiment_status import ExperimentStatusService

from .excel_helpers import make_excel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_experiment(
    db: Session,
    experiment_id: str,
    exp_num: int,
    status: ExperimentStatus = ExperimentStatus.ONGOING,
    experiment_type: str | None = None,
    reactor_number: int | None = None,
    date=None,
) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=status,
        date=date,
    )
    db.add(exp)
    db.flush()

    if experiment_type is not None or reactor_number is not None:
        cond = ExperimentalConditions(
            experiment_fk=exp.id,
            experiment_id=experiment_id,
            experiment_type=experiment_type,
            reactor_number=reactor_number,
        )
        db.add(cond)
        db.flush()

    return exp


# ---------------------------------------------------------------------------
# Column / row validation
# ---------------------------------------------------------------------------

def test_preview_missing_experiment_id_column_returns_error(db_session: Session):
    xlsx = make_excel(["status", "reactor_number"], [["ONGOING", 3]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "experiment_id" in preview.errors[0]
    assert preview.changes == []


def test_preview_missing_status_column_returns_error(db_session: Session):
    xlsx = make_excel(["experiment_id", "reactor_number"], [["HPHT_ST001", 3]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "status" in preview.errors[0]
    assert preview.changes == []


def test_preview_builds_planned_change_per_row(db_session: Session):
    """A valid row produces one PlannedChange with the parsed status/reactor/date."""
    _seed_experiment(db_session, "HPHT_ST001", 6601, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST001", "ongoing", 3, "2026-07-15"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert len(preview.changes) == 1
    change = preview.changes[0]
    assert change.experiment_id == "HPHT_ST001"
    assert change.new_status == "ONGOING"
    assert change.new_reactor_number == 3
    assert change.new_date is not None
    assert change.new_date.date().isoformat() == "2026-07-15"


def test_preview_records_missing_experiment_ids(db_session: Session):
    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["NONEXISTENT_ST", "ONGOING", 2]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert "NONEXISTENT_ST" in preview.missing_ids
    assert preview.changes == []
    assert preview.errors == []


def test_preview_invalid_status_produces_row_error(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST002", 6602, ExperimentStatus.ONGOING, "HPHT")
    xlsx = make_excel(
        ["experiment_id", "status"],
        [["HPHT_ST002", "IN_PROGRESS"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "Invalid status" in preview.errors[0]


def test_preview_invalid_reactor_number_produces_row_error(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST003", 6603, ExperimentStatus.ONGOING, "HPHT")
    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["HPHT_ST003", "ONGOING", "not-a-number"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "Invalid reactor_number" in preview.errors[0]


def test_preview_invalid_date_produces_row_error(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST004", 6604, ExperimentStatus.ONGOING, "HPHT")
    xlsx = make_excel(
        ["experiment_id", "status", "date"],
        [["HPHT_ST004", "ONGOING", "not-a-date"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert len(preview.errors) == 1
    assert "Invalid date" in preview.errors[0]


# ---------------------------------------------------------------------------
# Same-reactor-in-file conflict (Open Item #3: error, don't let apply order decide)
# ---------------------------------------------------------------------------

def test_preview_same_reactor_multiple_rows_errors(db_session: Session):
    _seed_experiment(db_session, "HPHT_ST005", 6605, ExperimentStatus.COMPLETED, "HPHT")
    _seed_experiment(db_session, "HPHT_ST006", 6606, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["HPHT_ST005", "ONGOING", 4], ["HPHT_ST006", "ONGOING", 4]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert len(preview.errors) == 1
    # issue #97: the conflict message now names the canonical slot (R04),
    # not the bare reactor number, so it distinguishes R04 from CF04.
    assert "Reactor R04" in preview.errors[0]
    assert "HPHT_ST005" in preview.errors[0]
    assert "HPHT_ST006" in preview.errors[0]
    assert preview.changes == []


def test_preview_serum_rows_same_reactor_do_not_conflict(db_session: Session):
    """The same-reactor conflict check only applies to HPHT/Core Flood rows."""
    _seed_experiment(db_session, "Serum_ST001", 6607, ExperimentStatus.COMPLETED, "Serum")
    _seed_experiment(db_session, "Serum_ST002", 6608, ExperimentStatus.COMPLETED, "Serum")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["Serum_ST001", "ONGOING", 4], ["Serum_ST002", "ONGOING", 4]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert len(preview.changes) == 2


# ---------------------------------------------------------------------------
# Reactor demotion planning (read-only — preview does not mutate the DB)
# ---------------------------------------------------------------------------

def test_preview_demotes_older_hpht_occupant_in_same_reactor(db_session: Session):
    from datetime import datetime

    _seed_experiment(
        db_session, "HPHT_ST010", 6610, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=5, date=datetime(2026, 1, 1),
    )
    _seed_experiment(db_session, "HPHT_ST011", 6611, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST011", "ONGOING", 5, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert len(preview.demotions) == 1
    assert preview.demotions[0].experiment_id == "HPHT_ST010"
    assert preview.demotions[0].triggering_experiment_id == "HPHT_ST011"
    assert any("HPHT_ST010" in w and "COMPLETED" in w for w in preview.warnings)


def test_preview_demotes_older_core_flood_occupant_in_same_reactor(db_session: Session):
    from datetime import datetime

    _seed_experiment(
        db_session, "CF_ST001", 6612, ExperimentStatus.ONGOING, "Core Flood",
        reactor_number=1, date=datetime(2026, 1, 1),
    )
    _seed_experiment(db_session, "CF_ST002", 6613, ExperimentStatus.COMPLETED, "Core Flood")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["CF_ST002", "ONGOING", 1, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    demoted_ids = [d.experiment_id for d in preview.demotions]
    assert "CF_ST001" in demoted_ids


def test_preview_warns_no_demote_when_occupant_newer(db_session: Session):
    from datetime import datetime

    _seed_experiment(
        db_session, "HPHT_ST012", 6614, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=6, date=datetime(2026, 6, 1),
    )
    _seed_experiment(db_session, "HPHT_ST013", 6615, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST013", "ONGOING", 6, "2026-01-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert preview.demotions == []
    assert any("HPHT_ST012" in w for w in preview.warnings)


def test_preview_warns_no_demote_when_occupant_equal_date(db_session: Session):
    """Open Item #4: same-day → warn, do not demote."""
    from datetime import datetime

    _seed_experiment(
        db_session, "HPHT_ST014", 6616, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=7, date=datetime(2026, 6, 1),
    )
    _seed_experiment(db_session, "HPHT_ST015", 6617, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST015", "ONGOING", 7, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.demotions == []
    assert any("HPHT_ST014" in w for w in preview.warnings)


def test_preview_warns_no_demote_when_incoming_date_missing(db_session: Session):
    """Open Item #1: missing incoming date → don't demote, warn."""
    from datetime import datetime

    _seed_experiment(
        db_session, "HPHT_ST016", 6618, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=8, date=datetime(2026, 1, 1),
    )
    _seed_experiment(db_session, "HPHT_ST017", 6619, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["HPHT_ST017", "ONGOING", 8]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.demotions == []
    assert any("HPHT_ST016" in w for w in preview.warnings)


def test_preview_warns_no_demote_when_occupant_date_missing(db_session: Session):
    """Open Item #1: missing occupant date → don't demote, warn."""
    _seed_experiment(
        db_session, "HPHT_ST018", 6620, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=9, date=None,
    )
    _seed_experiment(db_session, "HPHT_ST019", 6621, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST019", "ONGOING", 9, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.demotions == []
    assert any("HPHT_ST018" in w for w in preview.warnings)


def test_preview_serum_ongoing_with_reactor_no_demotion(db_session: Session):
    """Non-occupancy types never trigger demotion, even if ONGOING with a reactor_number."""
    from datetime import datetime

    _seed_experiment(
        db_session, "Serum_ST003", 6622, ExperimentStatus.ONGOING, "Serum",
        reactor_number=10, date=datetime(2026, 1, 1),
    )
    _seed_experiment(db_session, "Serum_ST004", 6623, ExperimentStatus.COMPLETED, "Serum")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["Serum_ST004", "ONGOING", 10, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.demotions == []
    assert preview.warnings == []


# ---------------------------------------------------------------------------
# manage_reactor_occupancy — start-date guard
# ---------------------------------------------------------------------------

def test_manage_reactor_occupancy_legacy_call_still_demotes_unconditionally(db_session: Session):
    """Regression: callers that don't pass newer_than (new_experiments.py, legacy create)
    keep demoting regardless of start dates."""
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_ST020", 6624, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=11, date=datetime(2026, 12, 31),  # newer than the incoming experiment
    )
    new_exp = _seed_experiment(
        db_session, "HPHT_ST021", 6625, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=11, date=datetime(2026, 1, 1),
    )

    marked, warnings = ExperimentStatusService.manage_reactor_occupancy(
        db_session, new_exp, 11, commit=False,
    )

    assert marked == 1
    db_session.flush()
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.COMPLETED
    assert any("COMPLETED" in w for w in warnings)


def test_manage_reactor_occupancy_guard_demotes_older_occupant(db_session: Session):
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_ST022", 6626, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=12, date=datetime(2026, 1, 1),
    )
    new_exp = _seed_experiment(
        db_session, "HPHT_ST023", 6627, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=12, date=datetime(2026, 6, 1),
    )

    marked, warnings = ExperimentStatusService.manage_reactor_occupancy(
        db_session, new_exp, 12, commit=False, newer_than=datetime(2026, 6, 1),
    )

    assert marked == 1
    db_session.flush()
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.COMPLETED


def test_manage_reactor_occupancy_guard_warns_on_newer_or_equal_occupant(db_session: Session):
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_ST024", 6628, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=13, date=datetime(2026, 6, 1),
    )
    new_exp = _seed_experiment(
        db_session, "HPHT_ST025", 6629, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=13, date=datetime(2026, 1, 1),
    )

    marked, warnings = ExperimentStatusService.manage_reactor_occupancy(
        db_session, new_exp, 13, commit=False, newer_than=datetime(2026, 1, 1),
    )

    assert marked == 0
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING
    assert any("HPHT_ST024" in w and "HPHT_ST025" in w for w in warnings)


def test_manage_reactor_occupancy_guard_warns_when_newer_than_is_none(db_session: Session):
    occupant = _seed_experiment(
        db_session, "HPHT_ST026", 6630, ExperimentStatus.ONGOING, "HPHT", reactor_number=14,
    )
    new_exp = _seed_experiment(
        db_session, "HPHT_ST027", 6631, ExperimentStatus.ONGOING, "HPHT", reactor_number=14,
    )

    marked, warnings = ExperimentStatusService.manage_reactor_occupancy(
        db_session, new_exp, 14, commit=False, newer_than=None,
    )

    assert marked == 0
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status,exp_num",
    [("ONGOING", 6700), ("COMPLETED", 6701), ("CANCELLED", 6702), ("QUEUED", 6703)],
)
def test_apply_sets_each_status_value(db_session: Session, status: str, exp_num: int):
    exp = _seed_experiment(db_session, f"HPHT_ST_{status}", exp_num, ExperimentStatus.ONGOING, "HPHT")

    xlsx = make_excel(["experiment_id", "status"], [[exp.experiment_id, status]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert preview.errors == []

    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.errors == []
    assert result.status_changes_applied == 1
    db_session.refresh(exp)
    assert exp.status == ExperimentStatus(status)


def test_apply_writes_date_when_provided(db_session: Session):
    exp = _seed_experiment(db_session, "HPHT_ST030", 6640, ExperimentStatus.ONGOING, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "date"],
        [["HPHT_ST030", "ONGOING", "2026-03-15"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.date_updates == 1
    db_session.refresh(exp)
    assert exp.date.date().isoformat() == "2026-03-15"


def test_apply_leaves_date_untouched_when_absent(db_session: Session):
    from datetime import datetime

    exp = _seed_experiment(
        db_session, "HPHT_ST031", 6641, ExperimentStatus.ONGOING, "HPHT", date=datetime(2026, 1, 1),
    )

    xlsx = make_excel(["experiment_id", "status"], [["HPHT_ST031", "COMPLETED"]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.date_updates == 0
    db_session.refresh(exp)
    assert exp.date.date().isoformat() == "2026-01-01"


def test_apply_updates_reactor_number_when_provided(db_session: Session):
    exp = _seed_experiment(
        db_session, "HPHT_ST032", 6642, ExperimentStatus.ONGOING, "HPHT", reactor_number=1,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number"],
        [["HPHT_ST032", "ONGOING", 9]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.reactor_updates == 1
    db_session.refresh(exp)
    assert exp.conditions.reactor_number == 9


def test_apply_triggers_demotion_for_ongoing_hpht_with_older_occupant(db_session: Session):
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_ST033", 6643, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=15, date=datetime(2026, 1, 1),
    )
    new_exp = _seed_experiment(db_session, "HPHT_ST034", 6644, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST034", "ONGOING", 15, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 1
    db_session.refresh(occupant)
    db_session.refresh(new_exp)
    assert occupant.status == ExperimentStatus.COMPLETED
    assert new_exp.status == ExperimentStatus.ONGOING


def test_apply_no_demotion_for_serum_type_even_with_reactor_number(db_session: Session):
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "Serum_ST005", 6645, ExperimentStatus.ONGOING, "Serum",
        reactor_number=16, date=datetime(2026, 1, 1),
    )
    new_exp = _seed_experiment(db_session, "Serum_ST006", 6646, ExperimentStatus.COMPLETED, "Serum")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["Serum_ST006", "ONGOING", 16, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 0
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING


def test_apply_does_not_touch_unlisted_ongoing_experiment(db_session: Session):
    """The retired 'complete every unlisted ongoing HPHT' behavior must not fire."""
    unlisted = _seed_experiment(db_session, "HPHT_ST035", 6647, ExperimentStatus.ONGOING, "HPHT")
    listed = _seed_experiment(db_session, "HPHT_ST036", 6648, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(["experiment_id", "status"], [["HPHT_ST036", "ONGOING"]])
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    ExperimentStatusService.apply_status_changes(db_session, preview)

    db_session.refresh(unlisted)
    assert unlisted.status == ExperimentStatus.ONGOING


def test_full_round_trip_file_to_db_state(db_session: Session):
    """Full round-trip: file → preview → apply → DB state correct, including a demotion."""
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_ST037", 6649, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=5, date=datetime(2026, 1, 1),
    )
    new_exp = _seed_experiment(db_session, "HPHT_ST038", 6650, ExperimentStatus.COMPLETED, "HPHT")

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_ST038", "ONGOING", 5, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert preview.errors == []

    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.errors == []
    assert result.status_changes_applied == 1
    assert result.demotions_applied == 1
    db_session.refresh(new_exp)
    db_session.refresh(occupant)
    assert new_exp.status == ExperimentStatus.ONGOING
    assert new_exp.date.date().isoformat() == "2026-06-01"
    assert occupant.status == ExperimentStatus.COMPLETED


# ---------------------------------------------------------------------------
# Cross-series slot identity (issue #97)
# ---------------------------------------------------------------------------

def test_core_flood_going_ongoing_does_not_demote_hpht_in_same_number(db_session: Session):
    """THE headline regression test. R01 and CF01 are different vessels.

    Before #97 the occupant query keyed on the bare integer, so loading Core
    Flood rig 1 found the HPHT in R01, passed the date guard, and silently set a
    running experiment to COMPLETED.
    """
    from datetime import datetime

    hpht = _seed_experiment(
        db_session, "HPHT_SLOT_209", 97201, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=1, date=datetime(2026, 5, 1),
    )
    cf = _seed_experiment(
        db_session, "CF_SLOT_301", 97202, ExperimentStatus.COMPLETED, "Core Flood",
        reactor_number=1,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["CF_SLOT_301", "ONGOING", 1, "2026-07-20"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert preview.demotions == []
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 0
    db_session.refresh(hpht)
    db_session.refresh(cf)
    assert hpht.status == ExperimentStatus.ONGOING
    assert cf.status == ExperimentStatus.ONGOING


def test_hpht_going_ongoing_does_not_demote_core_flood_in_same_number(db_session: Session):
    """The same collision in the other direction."""
    from datetime import datetime

    cf = _seed_experiment(
        db_session, "CF_SLOT_302", 97203, ExperimentStatus.ONGOING, "Core Flood",
        reactor_number=2, date=datetime(2026, 5, 1),
    )
    hpht = _seed_experiment(
        db_session, "HPHT_SLOT_210", 97204, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=2,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_SLOT_210", "ONGOING", 2, "2026-07-20"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 0
    db_session.refresh(cf)
    assert cf.status == ExperimentStatus.ONGOING


def test_same_number_different_series_in_one_file_is_not_a_conflict(db_session: Session):
    """An HPHT into R01 and a Core Flood into CF01 in the same workbook is legal.

    Before #97 `reactor_targets` was keyed on the integer, so this produced a
    spurious "Reactor 1 is targeted by multiple rows" error — and conflict_errors
    short-circuits the whole preview, so one false positive blocked the file.
    """
    hpht = _seed_experiment(
        db_session, "HPHT_SLOT_211", 97205, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=1,
    )
    cf = _seed_experiment(
        db_session, "CF_SLOT_303", 97206, ExperimentStatus.COMPLETED, "Core Flood",
        reactor_number=1,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [
            ["HPHT_SLOT_211", "ONGOING", 1, "2026-07-20"],
            ["CF_SLOT_303", "ONGOING", 1, "2026-07-20"],
        ],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert preview.errors == []
    assert len(preview.changes) == 2


def test_same_slot_twice_in_one_file_is_still_a_conflict(db_session: Session):
    """The real conflict must survive, and the message must name the slot."""
    _seed_experiment(
        db_session, "HPHT_SLOT_212", 97207, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=7,
    )
    _seed_experiment(
        db_session, "HPHT_SLOT_213", 97208, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=7,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [
            ["HPHT_SLOT_212", "ONGOING", 7, "2026-07-20"],
            ["HPHT_SLOT_213", "ONGOING", 7, "2026-07-20"],
        ],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)

    assert len(preview.errors) == 1
    assert "R07" in preview.errors[0]
    assert "HPHT_SLOT_212" in preview.errors[0]
    assert "HPHT_SLOT_213" in preview.errors[0]


def test_demotion_within_the_same_slot_still_works(db_session: Session):
    """Guard against over-correcting: two HPHTs in R11 must still demote."""
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_SLOT_214", 97209, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=11, date=datetime(2026, 1, 1),
    )
    incoming = _seed_experiment(
        db_session, "HPHT_SLOT_215", 97210, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=11,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_SLOT_215", "ONGOING", 11, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    assert [d.reactor_slot for d in preview.demotions] == ["R11"]
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 1
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.COMPLETED
    assert any("R11" in w for w in result.warnings)


def test_zero_reactor_number_never_demotes_anyone(db_session: Session):
    """reactor_number = 0 is not a slot. The 8 R00 SERUM_JW vials in the
    2026-07-28 prod audit exist because zero slipped through."""
    from datetime import datetime

    occupant = _seed_experiment(
        db_session, "HPHT_SLOT_216", 97211, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=0, date=datetime(2026, 1, 1),
    )
    incoming = _seed_experiment(
        db_session, "HPHT_SLOT_217", 97212, ExperimentStatus.COMPLETED, "HPHT",
        reactor_number=0,
    )

    xlsx = make_excel(
        ["experiment_id", "status", "reactor_number", "date"],
        [["HPHT_SLOT_217", "ONGOING", 0, "2026-06-01"]],
    )
    preview = ExperimentStatusService.preview_status_changes_from_excel(db_session, xlsx)
    result = ExperimentStatusService.apply_status_changes(db_session, preview)

    assert result.demotions_applied == 0
    db_session.refresh(occupant)
    assert occupant.status == ExperimentStatus.ONGOING


def test_manage_reactor_occupancy_derives_slot_when_not_passed(db_session: Session):
    """The legacy Streamlit caller (legacy/streamlit_frontend/new_experiment.py:398)
    passes no reactor_slot. It must still be scoped by series."""
    from datetime import datetime

    hpht = _seed_experiment(
        db_session, "HPHT_SLOT_218", 97213, ExperimentStatus.ONGOING, "HPHT",
        reactor_number=5, date=datetime(2026, 1, 1),
    )
    cf = _seed_experiment(
        db_session, "CF_SLOT_304", 97214, ExperimentStatus.ONGOING, "Core Flood",
        reactor_number=5,
    )

    marked, warnings = ExperimentStatusService.manage_reactor_occupancy(
        db_session, cf, 5, commit=False
    )

    assert marked == 0
    db_session.refresh(hpht)
    assert hpht.status == ExperimentStatus.ONGOING
