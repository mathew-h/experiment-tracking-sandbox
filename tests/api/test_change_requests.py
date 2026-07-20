from __future__ import annotations

from datetime import date, timedelta

from database.models.experiments import Experiment
from database.models.enums import ExperimentStatus
from database.models.notion_sync import ReactorChangeRequest


def _make_experiment(db, exp_id="CR_TEST_001", number=9001):
    exp = Experiment(
        experiment_id=exp_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def test_upsert_creates_new_record(client, db_session):
    exp = _make_experiment(db_session)
    resp = client.post(
        f"/api/experiments/{exp.experiment_id}/change-requests",
        json={"reactor_label": "R05", "requested_change": "Check pressure gauge"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reactor_label"] == "R05"
    assert data["requested_change"] == "Check pressure gauge"
    assert data["sync_date"] == str(date.today())
    assert data["notion_status"] is None

    row = db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R05", experiment_id=exp.experiment_id, sync_date=date.today()
    ).one()
    assert row.requested_change == "Check pressure gauge"


def test_upsert_overwrites_existing_for_same_reactor_experiment_day(client, db_session):
    exp = _make_experiment(db_session, "CR_TEST_002", 9002)
    for text in ("First entry", "Updated entry"):
        resp = client.post(
            f"/api/experiments/{exp.experiment_id}/change-requests",
            json={"reactor_label": "R06", "requested_change": text},
        )
        assert resp.status_code == 200

    rows = db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R06", experiment_id=exp.experiment_id, sync_date=date.today()
    ).all()
    assert len(rows) == 1
    assert rows[0].requested_change == "Updated entry"


def test_upsert_blank_text_returns_422(client, db_session):
    exp = _make_experiment(db_session, "CR_TEST_003", 9003)
    resp = client.post(
        f"/api/experiments/{exp.experiment_id}/change-requests",
        json={"reactor_label": "R07", "requested_change": "   "},
    )
    assert resp.status_code == 422

    count = db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R07", sync_date=date.today()
    ).count()
    assert count == 0


def test_upsert_missing_experiment_returns_404(client, db_session):
    resp = client.post(
        "/api/experiments/DOES_NOT_EXIST/change-requests",
        json={"reactor_label": "R08", "requested_change": "Test"},
    )
    assert resp.status_code == 404


def test_upsert_accepts_explicit_sync_date(client, db_session):
    exp = _make_experiment(db_session, "CR_TEST_004", 9004)
    yesterday = date.today() - timedelta(days=1)
    resp = client.post(
        f"/api/experiments/{exp.experiment_id}/change-requests",
        json={
            "reactor_label": "R09",
            "requested_change": "Backfilled note",
            "sync_date": str(yesterday),
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sync_date"] == str(yesterday)

    row = db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R09", experiment_id=exp.experiment_id, sync_date=yesterday
    ).one()
    assert row.requested_change == "Backfilled note"


def test_upsert_same_reactor_same_day_different_experiments_do_not_collide(client, db_session):
    outgoing = _make_experiment(db_session, "CR_TEST_005A", 9005)
    incoming = _make_experiment(db_session, "CR_TEST_005B", 9006)
    today = date.today()

    resp1 = client.post(
        f"/api/experiments/{outgoing.experiment_id}/change-requests",
        json={"reactor_label": "R10", "requested_change": "Outgoing note", "sync_date": str(today)},
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        f"/api/experiments/{incoming.experiment_id}/change-requests",
        json={"reactor_label": "R10", "requested_change": "Incoming note", "sync_date": str(today)},
    )
    assert resp2.status_code == 200

    rows = db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R10", sync_date=today
    ).all()
    assert len(rows) == 2
    by_exp = {r.experiment_id: r.requested_change for r in rows}
    assert by_exp[outgoing.experiment_id] == "Outgoing note"
    assert by_exp[incoming.experiment_id] == "Incoming note"


def test_recent_scoped_to_experiment_not_reactor(client, db_session):
    """A freshly started experiment on a reactor with older, different-experiment
    history must never surface that other experiment's entry (issue #63)."""
    outgoing = _make_experiment(db_session, "CR_TEST_006A", 9007)
    incoming = _make_experiment(db_session, "CR_TEST_006B", 9008)
    yesterday = date.today() - timedelta(days=1)

    db_session.add(ReactorChangeRequest(
        reactor_label="R11", experiment_id=outgoing.experiment_id,
        requested_change="Outgoing experiment's note", sync_date=yesterday,
        notion_page_id=None, notion_status=None, carried_forward=False,
    ))
    db_session.commit()

    resp = client.get(f"/api/experiments/{incoming.experiment_id}/change-requests/recent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected"] is None
    assert data["previous"] is None


def test_recent_returns_selected_and_previous_for_date(client, db_session):
    exp = _make_experiment(db_session, "CR_TEST_007", 9009)
    today = date.today()
    yesterday = today - timedelta(days=1)

    db_session.add(ReactorChangeRequest(
        reactor_label="R12", experiment_id=exp.experiment_id,
        requested_change="Today's note", sync_date=today,
        notion_page_id=None, notion_status=None, carried_forward=False,
    ))
    db_session.add(ReactorChangeRequest(
        reactor_label="R12", experiment_id=exp.experiment_id,
        requested_change="Yesterday's note", sync_date=yesterday,
        notion_page_id=None, notion_status=None, carried_forward=False,
    ))
    db_session.commit()

    resp = client.get(f"/api/experiments/{exp.experiment_id}/change-requests/recent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected"]["requested_change"] == "Today's note"
    assert data["previous"]["requested_change"] == "Yesterday's note"


def test_recent_accepts_date_query_param(client, db_session):
    exp = _make_experiment(db_session, "CR_TEST_008", 9010)
    two_days_ago = date.today() - timedelta(days=2)
    three_days_ago = date.today() - timedelta(days=3)

    db_session.add(ReactorChangeRequest(
        reactor_label="R13", experiment_id=exp.experiment_id,
        requested_change="Two days ago note", sync_date=two_days_ago,
        notion_page_id=None, notion_status=None, carried_forward=False,
    ))
    db_session.add(ReactorChangeRequest(
        reactor_label="R13", experiment_id=exp.experiment_id,
        requested_change="Three days ago note", sync_date=three_days_ago,
        notion_page_id=None, notion_status=None, carried_forward=False,
    ))
    db_session.commit()

    resp = client.get(
        f"/api/experiments/{exp.experiment_id}/change-requests/recent",
        params={"date": str(two_days_ago)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected"]["requested_change"] == "Two days ago note"
    assert data["previous"]["requested_change"] == "Three days ago note"


def test_recent_returns_nulls_when_no_records(client, db_session):
    exp = _make_experiment(db_session, "CR_TEST_009", 9011)
    resp = client.get(f"/api/experiments/{exp.experiment_id}/change-requests/recent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected"] is None
    assert data["previous"] is None


def test_recent_missing_experiment_returns_404(client, db_session):
    resp = client.get("/api/experiments/DOES_NOT_EXIST/change-requests/recent")
    assert resp.status_code == 404
