"""Plan-gate tests for POST /api/bulk-uploads/new-experiments (issue #100 items 4 and 5).

Item 4 — a plan containing conflicts rejects the WHOLE file. Before this, conflicting
rows were skipped and the remaining rows committed; that partial application is what
turned the 2026-07-28 SERUM_Catalyst mistake into a 149-row reconciliation.

Item 5 — the plan is fingerprinted. A dry-run response carries `plan_hash`; supplying
it on the real submit requires the freshly-computed plan to be identical, so a workbook
edited between preview and commit is refused.

Both are scoped to `new-experiments` — the only one of the 13 upload endpoints that
builds an UploadPlan (see the item-2 scoping note in `backend/api/schemas/bulk_upload.py`).
"""
from __future__ import annotations

import io

import openpyxl
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Experiment
from database.models.enums import ExperimentStatus
from tests.api.conftest import _test_engine
from backend.api.schemas.bulk_upload import (
    UploadPlan,
    PlanCreate,
    PlanConflict,
    PlanOverwrite,
    PlanFieldChange,
)

_ENDPOINT = "/api/bulk-uploads/new-experiments"

_ID_PREFIX = "HPHT_GATE_"


@pytest.fixture(autouse=True)
def purge_committed_rows():
    """Delete experiments this module committed for real, after every test.

    Several tests here deliberately exercise the COMMIT path, and a `session.commit()`
    on the conftest `db_session` consumes the fixture's outer transaction — so its
    teardown `transaction.rollback()` becomes a no-op (hence the "transaction already
    deassociated" SAWarning) and the rows genuinely land in `experiments_test`.

    Left alone they break any later test asserting an empty experiments table, e.g.
    `tests/api/test_experiments.py::test_list_experiments_empty` — a cross-file,
    order-dependent failure that is miserable to diagnose from the other end. Every
    ID in this module uses the `HPHT_GATE_` prefix so this stays surgical; child rows
    (conditions, notes, modifications) go with the parent via ON DELETE CASCADE,
    which `experiments_test` has because it is built with `Base.metadata.create_all`.
    """
    yield
    with _test_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM experiments WHERE experiment_id LIKE :prefix"),
            {"prefix": f"{_ID_PREFIX}%"},
        )


_EXP_HEADERS = [
    "experiment_id", "old_experiment_id", "sample_id", "researcher",
    "date", "status", "initial_note", "overwrite",
]


def _experiments_xlsx(rows: list[list]) -> io.BytesIO:
    """Build an in-memory New Experiments workbook with just an `experiments` sheet."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "experiments"
    ws.append(_EXP_HEADERS)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _post(client, rows: list[list], **data):
    """POST a freshly-built workbook. The buffer is consumed per request, so each
    call rebuilds it — reusing one BytesIO across posts silently uploads 0 bytes."""
    return client.post(
        _ENDPOINT,
        files={"file": ("test.xlsx", _experiments_xlsx(rows), "application/vnd.ms-excel")},
        data=data,
    )


def _seed(db: Session, experiment_id: str, exp_num: int) -> Experiment:
    """Seed a pre-existing experiment the upload will act on.

    Harness limitation worth knowing when reading the assertions below: the conftest
    `db_session` is bound to a connection with an outer transaction already open
    (SQLAlchemy's `conditional_savepoint` join mode), so the router's `db.rollback()`
    discards everything this test did — the seed included, and committing the seed
    first does not change that. So "the original experiment survived the rejection"
    is not observable here; the tests assert `commit` was never called instead.

    What IS observable and discriminating is the absence of a would-be-created row:
    `test_clean_file_with_no_conflicts_still_commits` proves that when the router does
    commit, the row is visible through this same session. So a missing row after a
    rejected upload really does mean the commit did not happen.
    """
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()
    return exp


# ---------------------------------------------------------------------------
# Item 4 — conflicts reject the whole file
# ---------------------------------------------------------------------------

def test_conflict_rejects_the_whole_file_including_its_good_rows(client, db_session):
    """The core of item 4: one bad row must take the good rows down with it.

    This is the incident shape — a rename workbook whose `overwrite` column is blank.
    Pre-item-4, `HPHT_GATE_7002` would have been created and committed while row 3
    was merely skipped.
    """
    _seed(db_session, "HPHT_GATE_7001", 70001)

    resp = _post(client, [
        ["HPHT_GATE_7002", None, None, "MH", None, "ONGOING", None, False],           # good create
        ["HPHT_GATE_7001_New", "HPHT_GATE_7001", None, None, None, None, None, False],  # conflict
    ])

    assert resp.status_code == 200
    body = resp.json()

    assert body["errors"], f"conflicts must surface as errors: {body}"
    assert body["created"] == 0, f"rejected file must report nothing created: {body}"
    assert body["updated"] == 0
    assert body["skipped"] == 0

    # The good row is NOT in the database — this is the whole point of item 4.
    # Pre-fix this row was committed while row 3 was merely skipped.
    assert db_session.query(Experiment).filter_by(experiment_id="HPHT_GATE_7002").first() is None
    # The rename did not happen either.
    assert db_session.query(Experiment).filter_by(experiment_id="HPHT_GATE_7001_New").first() is None
    # "the original HPHT_GATE_7001 survived" is asserted via commit-never-called in
    # test_conflict_rejection_rolls_back_and_does_not_commit — see _seed's docstring
    # for why it cannot be observed through this session after a rollback.


def test_rejected_file_still_returns_the_full_plan(client, db_session):
    """Rejection must not blank the plan — the researcher needs to see what the file
    WOULD have done in order to fix it. counts stay as parsed, not zeroed."""
    _seed(db_session, "HPHT_GATE_7010", 70010)

    resp = _post(client, [
        ["HPHT_GATE_7011", None, None, "MH", None, "ONGOING", None, False],            # create
        ["HPHT_GATE_7010_New", "HPHT_GATE_7010", None, None, None, None, None, False],   # conflict
    ])

    plan = resp.json()["plan"]
    assert plan is not None
    assert plan["counts"]["conflicts"] == 1
    assert plan["counts"]["creates"] == 1, "the would-be create must still be visible"
    assert plan["creates"][0]["experiment_id"] == "HPHT_GATE_7011"


def test_blank_overwrite_rename_conflict_names_both_ids(client, db_session):
    """Acceptance criterion 2: the error names the old AND the new ID, and says
    what the row would have done instead."""
    _seed(db_session, "HPHT_GATE_7020", 70020)

    resp = _post(client, [
        ["HPHT_GATE_7020_New", "HPHT_GATE_7020", None, None, None, None, None, False],
    ])

    body = resp.json()
    joined = " ".join(body["errors"])
    assert "HPHT_GATE_7020" in joined
    assert "HPHT_GATE_7020_New" in joined
    assert "overwrite" in joined.lower()
    assert body["plan"]["conflicts"][0]["kind"] == "rename_without_overwrite"


def test_chain_rename_conflict_blocks_at_preview(client, db_session):
    """Acceptance criterion 3: renaming A -> B while B already exists as a separate
    experiment reports CHAIN RENAME CONFLICT with the suggested row ordering, and
    blocks the commit rather than skipping the row."""
    _seed(db_session, "HPHT_GATE_7030", 70030)
    _seed(db_session, "HPHT_GATE_7031", 70031)

    resp = _post(client, [
        ["HPHT_GATE_7031", "HPHT_GATE_7030", None, None, None, None, None, True],
    ], dry_run="true")

    body = resp.json()
    conflicts = body["plan"]["conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["kind"] == "chain_rename_conflict"
    assert "FIRST" in conflicts[0]["detail"], "must suggest the row ordering fix"
    assert body["errors"], "a chain rename conflict must block the commit"


def test_conflict_rejection_rolls_back_and_does_not_commit(client, db_session):
    """Belt-and-braces on the transaction itself, not just the observable rows."""
    from unittest.mock import patch

    _seed(db_session, "HPHT_GATE_7040", 70040)

    with patch.object(db_session, "commit") as mock_commit, \
            patch.object(db_session, "rollback") as mock_rollback:
        _post(client, [
            ["HPHT_GATE_7040_New", "HPHT_GATE_7040", None, None, None, None, None, False],
        ])

    mock_commit.assert_not_called()
    assert mock_rollback.called


def test_clean_file_with_no_conflicts_still_commits(client, db_session):
    """Regression guard: item 4 must not make every upload a no-op."""
    resp = _post(client, [
        ["HPHT_GATE_7050", None, None, "MH", None, "ONGOING", None, False],
    ])

    body = resp.json()
    assert body["errors"] == []
    assert body["created"] == 1
    assert db_session.query(Experiment).filter_by(experiment_id="HPHT_GATE_7050").first() is not None


def test_skips_alone_do_not_reject_the_file(client, db_session):
    """A skip is not a conflict. A blank experiment_id row is a skip, and must not
    prevent the rest of the workbook from committing."""
    resp = _post(client, [
        ["HPHT_GATE_7060", None, None, "MH", None, "ONGOING", None, False],
        [" ", None, None, None, None, None, None, False],  # skip, not a conflict
    ])

    body = resp.json()
    assert body["plan"]["counts"]["skips"] == 1
    assert body["plan"]["counts"]["conflicts"] == 0
    assert body["errors"] == []
    assert db_session.query(Experiment).filter_by(experiment_id="HPHT_GATE_7060").first() is not None


# ---------------------------------------------------------------------------
# Item 5 — plan fingerprint, unit level
# ---------------------------------------------------------------------------

def test_fingerprint_is_stable_for_equal_plans():
    a = UploadPlan(creates=[PlanCreate(row=2, experiment_id="X_1")])
    b = UploadPlan(creates=[PlanCreate(row=2, experiment_id="X_1")])
    assert a.fingerprint() == b.fingerprint()


def test_fingerprint_changes_when_a_row_changes():
    a = UploadPlan(creates=[PlanCreate(row=2, experiment_id="X_1")])
    b = UploadPlan(creates=[PlanCreate(row=3, experiment_id="X_1")])
    assert a.fingerprint() != b.fingerprint()


def test_fingerprint_changes_when_an_id_changes():
    a = UploadPlan(creates=[PlanCreate(row=2, experiment_id="X_1")])
    b = UploadPlan(creates=[PlanCreate(row=2, experiment_id="X_2")])
    assert a.fingerprint() != b.fingerprint()


def test_fingerprint_covers_conflicts():
    a = UploadPlan(creates=[PlanCreate(row=2, experiment_id="X_1")])
    b = UploadPlan(
        creates=[PlanCreate(row=2, experiment_id="X_1")],
        conflicts=[PlanConflict(row=3, kind="already_exists", detail="d")],
    )
    assert a.fingerprint() != b.fingerprint()


def test_fingerprint_covers_field_change_values():
    """The highest-value case: an overwrite silently changing initial_ph 4 -> 9 must
    move the hash, so a preview of the 4->9 plan cannot authorize a 4->7 commit."""
    a = UploadPlan(overwrites=[PlanOverwrite(
        row=2, experiment_id="X_1",
        fields_changed=[PlanFieldChange(field="initial_ph", old=4, new=9)],
    )])
    b = UploadPlan(overwrites=[PlanOverwrite(
        row=2, experiment_id="X_1",
        fields_changed=[PlanFieldChange(field="initial_ph", old=4, new=7)],
    )])
    assert a.fingerprint() != b.fingerprint()


def test_fingerprint_ignores_counts_which_are_derived():
    """counts is a function of the lists, so an out-of-band counts value must not
    change the fingerprint (it would make the hash non-reproducible)."""
    a = UploadPlan(creates=[PlanCreate(row=2, experiment_id="X_1")], counts={})
    b = UploadPlan(creates=[PlanCreate(row=2, experiment_id="X_1")], counts={"creates": 1})
    assert a.fingerprint() == b.fingerprint()


def test_fingerprint_handles_non_json_native_field_values():
    """fields_changed carries whatever the ORM held — dates, enums, Decimals. The
    fingerprint must not raise on them."""
    import datetime
    from decimal import Decimal

    plan = UploadPlan(overwrites=[PlanOverwrite(
        row=2, experiment_id="X_1",
        fields_changed=[
            PlanFieldChange(field="date", old=datetime.date(2026, 1, 1), new=None),
            PlanFieldChange(field="rock_mass_g", old=Decimal("1.5"), new=Decimal("2.5")),
            PlanFieldChange(field="status", old=ExperimentStatus.ONGOING, new=ExperimentStatus.COMPLETED),
        ],
    )])
    assert isinstance(plan.fingerprint(), str)
    assert len(plan.fingerprint()) == 64  # sha256 hex


# ---------------------------------------------------------------------------
# Item 5 — plan fingerprint over the wire
# ---------------------------------------------------------------------------

def test_dry_run_response_carries_a_plan_hash(client, db_session):
    resp = _post(client, [
        ["HPHT_GATE_7100", None, None, "MH", None, "ONGOING", None, False],
    ], dry_run="true")

    body = resp.json()
    assert body["dry_run"] is True
    assert body["plan_hash"], f"dry run must return a plan hash: {body}"
    assert len(body["plan_hash"]) == 64


def test_previewed_hash_authorizes_the_matching_commit(client, db_session):
    """The happy path of the preview -> commit handshake."""
    rows = [["HPHT_GATE_7110", None, None, "MH", None, "ONGOING", None, False]]

    preview = _post(client, rows, dry_run="true").json()
    assert db_session.query(Experiment).filter_by(experiment_id="HPHT_GATE_7110").first() is None

    commit = _post(client, rows, plan_hash=preview["plan_hash"]).json()

    assert commit["errors"] == []
    assert commit["created"] == 1
    assert db_session.query(Experiment).filter_by(experiment_id="HPHT_GATE_7110").first() is not None


def test_editing_the_file_between_preview_and_commit_fails_the_hash_check(client, db_session):
    """Acceptance criterion 5. Preview one workbook, submit a different one with the
    previewed hash — must be refused with nothing persisted."""
    previewed_rows = [["HPHT_GATE_7120", None, None, "MH", None, "ONGOING", None, False]]
    edited_rows = [["HPHT_GATE_7121", None, None, "MH", None, "ONGOING", None, False]]

    preview = _post(client, previewed_rows, dry_run="true").json()
    resp = _post(client, edited_rows, plan_hash=preview["plan_hash"])

    body = resp.json()
    assert body["errors"], f"a stale plan hash must be rejected: {body}"
    assert body["created"] == 0
    assert db_session.query(Experiment).filter_by(experiment_id="HPHT_GATE_7121").first() is None
    assert db_session.query(Experiment).filter_by(experiment_id="HPHT_GATE_7120").first() is None


def test_stale_hash_error_tells_the_user_to_re_preview(client, db_session):
    preview = _post(client, [
        ["HPHT_GATE_7130", None, None, "MH", None, "ONGOING", None, False],
    ], dry_run="true").json()

    resp = _post(client, [
        ["HPHT_GATE_7131", None, None, "MH", None, "ONGOING", None, False],
    ], plan_hash=preview["plan_hash"])

    joined = " ".join(resp.json()["errors"]).lower()
    assert "changed" in joined or "stale" in joined
    assert "preview" in joined


def test_a_concurrent_db_change_invalidates_the_previewed_hash(client, db_session):
    """Because fields_changed reads current DB values, the fingerprint covers DB state
    as well as file bytes — so another researcher's edit between preview and commit
    also invalidates the plan. Here the target experiment appears after the preview,
    turning a would-be create into an already_exists conflict."""
    rows = [["HPHT_GATE_7140", None, None, "MH", None, "ONGOING", None, False]]

    preview = _post(client, rows, dry_run="true").json()

    _seed(db_session, "HPHT_GATE_7140", 70140)  # someone else got there first

    body = _post(client, rows, plan_hash=preview["plan_hash"]).json()
    assert body["errors"]
    assert body["created"] == 0


def test_omitting_the_hash_still_commits(client, db_session):
    """Backward compatibility: plan_hash is verified when supplied, not required.
    Every pre-existing caller posts without it and must keep working."""
    resp = _post(client, [
        ["HPHT_GATE_7150", None, None, "MH", None, "ONGOING", None, False],
    ])

    body = resp.json()
    assert body["errors"] == []
    assert body["created"] == 1
    assert db_session.query(Experiment).filter_by(experiment_id="HPHT_GATE_7150").first() is not None


def test_hash_mismatch_rolls_back_and_does_not_commit(client, db_session):
    from unittest.mock import patch

    with patch.object(db_session, "commit") as mock_commit, \
            patch.object(db_session, "rollback") as mock_rollback:
        _post(client, [
            ["HPHT_GATE_7160", None, None, "MH", None, "ONGOING", None, False],
        ], plan_hash="0" * 64)

    mock_commit.assert_not_called()
    assert mock_rollback.called


def test_real_submit_also_returns_a_plan_hash(client, db_session):
    """Not just dry runs — the committed response carries the hash of what it applied,
    so the frontend can confirm the handshake completed on the plan it showed."""
    resp = _post(client, [
        ["HPHT_GATE_7170", None, None, "MH", None, "ONGOING", None, False],
    ])

    body = resp.json()
    assert body["created"] == 1
    assert body["plan_hash"]
    assert len(body["plan_hash"]) == 64


def test_hash_is_reproducible_across_two_dry_runs_of_the_same_file(client, db_session):
    """If two previews of one unchanged workbook disagreed, the handshake could never
    succeed. Guards against any nondeterminism leaking into the plan."""
    rows = [
        ["HPHT_GATE_7180", None, None, "MH", None, "ONGOING", None, False],
        ["HPHT_GATE_7181", None, None, "MH", None, "ONGOING", None, False],
    ]

    first = _post(client, rows, dry_run="true").json()["plan_hash"]
    second = _post(client, rows, dry_run="true").json()["plan_hash"]

    assert first == second


def test_endpoints_without_a_plan_return_a_null_hash(client, db_session):
    """Scoping check (matches item 2): the other 12 endpoints build no plan, so they
    must report plan_hash: null rather than a hash of an empty plan."""
    import sys
    from unittest.mock import MagicMock, patch

    mock_svc = MagicMock()
    mock_svc.ingest_from_bytes.return_value = (1, 0, 0, [], [])
    fake_mod = MagicMock()
    fake_mod.XRDUploadService = mock_svc

    with patch.dict(sys.modules, {"backend.services.bulk_uploads.xrd_upload": fake_mod}):
        resp = client.post(
            "/api/bulk-uploads/xrd-mineralogy",
            files={"file": ("test.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )

    body = resp.json()
    assert body["plan"] is None
    assert body["plan_hash"] is None
