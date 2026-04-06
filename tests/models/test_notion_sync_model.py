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
        date=date(2026, 4, 1),
        notion_page_id="abc12345123412341234abc123456789",
    )
    mem_db.add(row)
    mem_db.commit()
    mem_db.refresh(row)

    assert row.id is not None
    assert row.reactor_label == "R05"
    assert row.carried_forward is False
    assert row.created_at is not None


def test_unique_constraint_reactor_date(mem_db) -> None:
    """Same reactor_label + date should raise on duplicate insert."""
    from sqlalchemy.exc import IntegrityError

    def _row():
        return ReactorChangeRequest(
            reactor_label="R01",
            requested_change="Test",
            notion_status="Pending",
            carried_forward=False,
            date=date(2026, 4, 1),
            notion_page_id="aaaabbbbccccddddaaaabbbbccccdddd",
        )

    mem_db.add(_row())
    mem_db.commit()
    mem_db.add(_row())
    with pytest.raises(IntegrityError):
        mem_db.commit()
