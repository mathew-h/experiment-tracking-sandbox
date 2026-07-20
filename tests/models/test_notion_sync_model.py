"""Test ReactorChangeRequest model instantiation and constraints."""
from __future__ import annotations

import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from database.models.notion_sync import ReactorChangeRequest


@pytest.fixture
def mem_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Only create the table(s) under test — other models use JSONB which SQLite can't compile.
    ReactorChangeRequest.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()
    ReactorChangeRequest.__table__.drop(engine)


def test_reactor_change_request_create(mem_db) -> None:
    row = ReactorChangeRequest(
        reactor_label="R05",
        experiment_id=None,
        requested_change="Sample and clean",
        notion_status="Pending",
        carried_forward=False,
        sync_date=date(2026, 4, 1),
        notion_page_id="abc12345123412341234abc123456789",
    )
    mem_db.add(row)
    mem_db.commit()
    mem_db.refresh(row)

    assert row.id is not None
    assert row.reactor_label == "R05"
    assert row.carried_forward is False
    assert row.created_at is not None


def test_unique_constraint_reactor_experiment_date(mem_db) -> None:
    """Same reactor_label + experiment_id + date should raise on duplicate insert."""
    from sqlalchemy.exc import IntegrityError

    def _row():
        return ReactorChangeRequest(
            reactor_label="R01",
            experiment_id="EXP_001",
            requested_change="Test",
            notion_status="Pending",
            carried_forward=False,
            sync_date=date(2026, 4, 1),
            notion_page_id="aaaabbbbccccddddaaaabbbbccccdddd",
        )

    mem_db.add(_row())
    mem_db.commit()
    mem_db.add(_row())
    with pytest.raises(IntegrityError):
        mem_db.commit()


def test_same_reactor_date_different_experiment_does_not_collide(mem_db) -> None:
    """Widened constraint (issue #63): two experiments on the same reactor on the
    same calendar day must not silently overwrite each other's entry."""
    def _row(experiment_id, text):
        return ReactorChangeRequest(
            reactor_label="R02",
            experiment_id=experiment_id,
            requested_change=text,
            notion_status=None,
            carried_forward=False,
            sync_date=date(2026, 4, 1),
            notion_page_id=None,
        )

    mem_db.add(_row("EXP_OUTGOING", "Outgoing note"))
    mem_db.add(_row("EXP_INCOMING", "Incoming note"))
    mem_db.commit()

    rows = mem_db.query(ReactorChangeRequest).filter_by(reactor_label="R02").all()
    assert len(rows) == 2
