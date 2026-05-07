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
        reactor_label="R05", sync_date=date.today()
    ).one()
    assert row.requested_change == "Check pressure gauge"


def test_upsert_overwrites_existing_for_same_reactor_day(client, db_session):
    exp = _make_experiment(db_session, "CR_TEST_002", 9002)
    for text in ("First entry", "Updated entry"):
        resp = client.post(
            f"/api/experiments/{exp.experiment_id}/change-requests",
            json={"reactor_label": "R06", "requested_change": text},
        )
        assert resp.status_code == 200

    rows = db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R06", sync_date=date.today()
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


def test_get_recent_returns_today_and_previous(client, db_session):
    today = date.today()
    yesterday = today - timedelta(days=1)

    db_session.add(ReactorChangeRequest(
        reactor_label="R10", experiment_id=None,
        requested_change="Today's note", sync_date=today,
        notion_page_id=None, notion_status=None, carried_forward=False,
    ))
    db_session.add(ReactorChangeRequest(
        reactor_label="R10", experiment_id=None,
        requested_change="Yesterday's note", sync_date=yesterday,
        notion_page_id=None, notion_status=None, carried_forward=False,
    ))
    db_session.commit()

    resp = client.get("/api/change-requests/reactor/R10/recent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["today"]["requested_change"] == "Today's note"
    assert data["previous"]["requested_change"] == "Yesterday's note"


def test_get_recent_returns_nulls_when_no_records(client, db_session):
    resp = client.get("/api/change-requests/reactor/R99/recent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["today"] is None
    assert data["previous"] is None


def test_get_recent_no_today_still_returns_previous(client, db_session):
    two_days_ago = date.today() - timedelta(days=2)
    db_session.add(ReactorChangeRequest(
        reactor_label="R11", experiment_id=None,
        requested_change="Old note", sync_date=two_days_ago,
        notion_page_id=None, notion_status=None, carried_forward=False,
    ))
    db_session.commit()

    resp = client.get("/api/change-requests/reactor/R11/recent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["today"] is None
    assert data["previous"]["requested_change"] == "Old note"
