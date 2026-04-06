# Notion Reactor Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily bidirectional sync service between the app DB and the Notion "Reactor Dashboard" database, importing Change Request entries and exporting current experiment assignments.

**Architecture:** A `backend/services/notion_sync/` package isolates all Notion SDK calls in a thin client wrapper, with separate import and export modules called by a sync orchestrator. APScheduler (already installed) runs the daily job in the FastAPI lifespan; a `POST /api/admin/notion-sync/trigger` endpoint enables on-demand runs.

**Tech Stack:** Python, FastAPI lifespan, APScheduler 3.11 (AsyncIOScheduler + CronTrigger), notion-client ≥ 2.2.1, SQLAlchemy 2.x (PostgreSQL upsert via `pg_insert`), pytest, structlog.

---

## File Structure

**Create:**
- `database/models/notion_sync.py` — `ReactorChangeRequest` ORM model
- `backend/services/notion_sync/__init__.py` — package marker
- `backend/services/notion_sync/client.py` — Notion SDK wrapper (all SDK calls live here)
- `backend/services/notion_sync/import_.py` — import step (read from Notion → upsert DB → clear Notion)
- `backend/services/notion_sync/export.py` — export step (ONGOING experiments → Notion)
- `backend/services/notion_sync/sync.py` — orchestrator + `make_scheduler()`
- `backend/api/routers/notion_sync.py` — `POST /api/admin/notion-sync/trigger`
- `docs/notion_sync/NOTION_SYNC.md` — field mapping reference
- `tests/services/test_notion_sync_import.py` — import unit tests
- `tests/services/test_notion_sync_export.py` — export unit tests
- `tests/api/test_notion_sync.py` — integration + API tests

**Modify:**
- `requirements.txt` — add `notion-client>=2.2.1`
- `database/models/__init__.py` — import `ReactorChangeRequest`
- `database/__init__.py` — import `ReactorChangeRequest`
- `backend/config/settings.py` — add four Notion fields
- `.env.example` — add Notion env vars
- `backend/api/main.py` — register router + scheduler in lifespan

---

## Task 1: Add notion-client dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add notion-client to requirements.txt**

Append to `requirements.txt`:
```
notion-client>=2.2.1
```

- [ ] **Step 2: Install the package**

```bash
.venv/Scripts/pip install notion-client>=2.2.1
```
Expected: Successfully installed notion-client-...

- [ ] **Step 3: Verify import works**

```bash
.venv/Scripts/python -c "from notion_client import Client; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "[#32] add notion-client dependency"
```

---

## Task 2: Add Notion settings to Settings class + .env.example

**Files:**
- Modify: `backend/config/settings.py:47-76`
- Modify: `.env.example`

- [ ] **Step 1: Add four Notion fields to Settings**

In `backend/config/settings.py`, add after the `cors_origins` field (before the `cors_origins_list` property):

```python
    # Notion sync — reactor dashboard
    notion_token: str = ""
    notion_database_id: str = ""
    notion_data_source_id: str = ""
    notion_sync_hour: int = 6  # Hour of day (24h) in America/New_York to run daily sync
```

- [ ] **Step 2: Add Notion vars to .env.example**

Append to `.env.example`:
```
# Notion Sync — Reactor Dashboard
# Token from Notion integration settings (secret_...)
NOTION_TOKEN=
# Reactor Dashboard database ID (32-char UUID without dashes)
NOTION_DATABASE_ID=53ec4778508541efa31eaf0e4accac35
# Data source ID for the Reactor Dashboard
NOTION_DATA_SOURCE_ID=d8d499ab-d6ef-44ce-9f67-d650dfaf5319
# Hour (0-23, America/New_York) to run the daily sync
NOTION_SYNC_HOUR=6
```

- [ ] **Step 3: Verify Settings loads new fields**

```bash
.venv/Scripts/python -c "
from backend.config.settings import Settings
s = Settings()
print(s.notion_token, s.notion_database_id, s.notion_sync_hour)
"
```
Expected: `  53ec4778508541efa31eaf0e4accac35 6`
(notion_token empty since not set in env)

- [ ] **Step 4: Commit**

```bash
git add backend/config/settings.py .env.example
git commit -m "[#32] add Notion env vars to Settings and .env.example"
```

---

## Task 3: ReactorChangeRequest model

**Files:**
- Create: `database/models/notion_sync.py`
- Modify: `database/models/__init__.py`
- Modify: `database/__init__.py`

- [ ] **Step 1: Write the failing model test**

Create `tests/models/test_notion_sync_model.py`:

```python
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
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()
    Base.metadata.drop_all(engine)


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/Scripts/pytest tests/models/test_notion_sync_model.py -v
```
Expected: FAIL — `ImportError: cannot import name 'ReactorChangeRequest'`

- [ ] **Step 3: Create the model**

Create `database/models/notion_sync.py`:

```python
"""ReactorChangeRequest — daily Notion reactor change request import."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func

from ..database import Base


class ReactorChangeRequest(Base):
    """One row per reactor per sync date; upserted on re-run."""

    __tablename__ = "reactor_change_requests"

    id: int = Column(Integer, primary_key=True)
    reactor_label: str = Column(String(10), nullable=False)
    # Nullable FK — not resolved during import; populated by future logic if needed.
    experiment_id: str | None = Column(
        String,
        ForeignKey("experiments.experiment_id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_change: str = Column(String, nullable=False)
    notion_status: str = Column(String(50), nullable=False)
    carried_forward: bool = Column(Boolean, nullable=False, default=False)
    date: date = Column(Date, nullable=False)
    # 32-char UUID (hyphens stripped) for Notion page traceability.
    notion_page_id: str = Column(String(32), nullable=False)
    created_at: datetime = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("reactor_label", "date", name="uq_change_request_reactor_date"),
    )
```

- [ ] **Step 4: Register model in database/models/__init__.py**

Add import at the top of the existing imports block:

```python
from .notion_sync import ReactorChangeRequest
```

Add to `__all__`:
```python
    'ReactorChangeRequest',
```

- [ ] **Step 5: Register model in database/__init__.py**

Add `ReactorChangeRequest` to the existing import from `.models`:

```python
from .models import (
    ...
    ReactorChangeRequest,
)
```

And add to `__all__`:
```python
    'ReactorChangeRequest',
```

- [ ] **Step 6: Run test to verify it passes**

```bash
.venv/Scripts/pytest tests/models/test_notion_sync_model.py -v
```
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add database/models/notion_sync.py database/models/__init__.py database/__init__.py tests/models/test_notion_sync_model.py
git commit -m "[#32] add ReactorChangeRequest model"
```

---

## Task 4: Alembic migration

**Files:**
- Create: `alembic/versions/<hash>_add_reactor_change_requests.py` (autogenerated)

- [ ] **Step 1: Generate migration**

```bash
.venv/Scripts/alembic revision --autogenerate -m "add_reactor_change_requests"
```
Expected: `Generating alembic/versions/<hash>_add_reactor_change_requests.py`

- [ ] **Step 2: Inspect and verify the generated migration**

Open the generated file and verify:
- `op.create_table('reactor_change_requests', ...)` is present
- All columns match the model definition
- The `UniqueConstraint` on `(reactor_label, date)` is included with name `uq_change_request_reactor_date`
- `downgrade()` has `op.drop_table('reactor_change_requests')`

If the ForeignKey to `experiments.experiment_id` was NOT generated (Alembic sometimes skips FK to non-PK columns), add it manually to `upgrade()`:

```python
sa.ForeignKeyConstraint(['experiment_id'], ['experiments.experiment_id'],
                         ondelete='SET NULL'),
```

- [ ] **Step 3: Apply migration**

```bash
.venv/Scripts/alembic upgrade head
```
Expected: `Running upgrade ... -> <revision>`

- [ ] **Step 4: Test downgrade and re-upgrade**

```bash
.venv/Scripts/alembic downgrade -1 && .venv/Scripts/alembic upgrade head
```
Expected: Both commands complete without error.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "[#32] migration: add reactor_change_requests table"
```

---

## Task 5: Notion client wrapper

**Files:**
- Create: `backend/services/notion_sync/__init__.py`
- Create: `backend/services/notion_sync/client.py`

The `client.py` module is the ONLY place in the codebase that imports from `notion_client`. All other modules call this wrapper. This makes mocking in tests trivial.

- [ ] **Step 1: Write failing client tests**

Create `tests/services/test_notion_sync_client.py`:

```python
"""Unit tests for Notion client wrapper."""
from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from backend.services.notion_sync.client import (
    NotionSyncClient,
    extract_reactor_label,
    extract_change_request,
    extract_change_status,
    PROP_REACTOR_LABEL,
)


def _page(reactor_label: str, change_request: str, status: str) -> dict:
    return {
        "id": "abc12345-1234-1234-1234-abc123456789",
        "properties": {
            "Name": {"title": [{"plain_text": reactor_label}]},
            "Change Request": {
                "rich_text": [{"plain_text": change_request}] if change_request else []
            },
            "Change Request Status": {"select": {"name": status} if status else None},
        },
    }


def test_extract_reactor_label() -> None:
    page = _page("R05", "Do something", "Pending")
    assert extract_reactor_label(page) == "R05"


def test_extract_change_request_nonempty() -> None:
    page = _page("R01", "Sample reactor", "Pending")
    assert extract_change_request(page) == "Sample reactor"


def test_extract_change_request_empty() -> None:
    page = _page("R02", "", "Pending")
    assert extract_change_request(page) == ""


def test_extract_change_status_set() -> None:
    page = _page("R03", "x", "In Progress")
    assert extract_change_status(page) == "In Progress"


def test_extract_change_status_none_select() -> None:
    page = _page("R03", "x", "")
    page["properties"]["Change Request Status"]["select"] = None
    assert extract_change_status(page) == "Pending"


def test_client_query_all_rows() -> None:
    mock_notion = MagicMock()
    mock_notion.databases.query.return_value = {"results": [{"id": "abc"}]}

    with patch("backend.services.notion_sync.client.Client", return_value=mock_notion):
        client = NotionSyncClient(token="secret_test", database_id="dbid123")
        rows = client.query_all_rows()

    mock_notion.databases.query.assert_called_once_with(database_id="dbid123")
    assert rows == [{"id": "abc"}]


def test_client_clear_change_request() -> None:
    mock_notion = MagicMock()
    with patch("backend.services.notion_sync.client.Client", return_value=mock_notion):
        client = NotionSyncClient(token="secret_test", database_id="dbid")
        client.clear_change_request("page-id-123")

    mock_notion.pages.update.assert_called_once_with(
        page_id="page-id-123",
        properties={
            "Change Request": {"rich_text": []},
            "Change Request Status": {"select": {"name": "Pending"}},
        },
    )


def test_client_write_experiment_info() -> None:
    mock_notion = MagicMock()
    with patch("backend.services.notion_sync.client.Client", return_value=mock_notion):
        client = NotionSyncClient(token="secret_test", database_id="dbid")
        client.write_experiment_info(
            page_id="page-id-456",
            experiment_id="SERUM_001",
            description="Rock dissolution test",
            date_started="2026-03-15",
        )

    mock_notion.pages.update.assert_called_once_with(
        page_id="page-id-456",
        properties={
            "Experiment ID": {"rich_text": [{"text": {"content": "SERUM_001"}}]},
            "Experiment Description": {"rich_text": [{"text": {"content": "Rock dissolution test"}}]},
            "Date Started": {"date": {"start": "2026-03-15"}},
        },
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_client.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.notion_sync'`

- [ ] **Step 3: Create the package and client module**

Create `backend/services/notion_sync/__init__.py` (empty):

```python
```

Create `backend/services/notion_sync/client.py`:

```python
"""Notion SDK wrapper — all notion_client SDK calls are isolated here.

Property name constants define the exact Notion column names for the
Reactor Dashboard database. Update these constants if the Notion schema changes.
"""
from __future__ import annotations

import structlog
from notion_client import Client

log = structlog.get_logger(__name__)

# Notion property names for the Reactor Dashboard database
PROP_REACTOR_LABEL = "Name"                # Title property — reactor label e.g. "R05"
PROP_CHANGE_REQUEST = "Change Request"     # rich_text
PROP_CHANGE_STATUS = "Change Request Status"  # select: Pending | In Progress | Carried Forward | Completed
PROP_EXPERIMENT_ID = "Experiment ID"       # rich_text (written by export)
PROP_EXPERIMENT_DESC = "Experiment Description"  # rich_text (written by export)
PROP_DATE_STARTED = "Date Started"         # date (written by export)

STATUS_PENDING = "Pending"
STATUS_IN_PROGRESS = "In Progress"
STATUS_CARRIED_FORWARD = "Carried Forward"
STATUS_COMPLETED = "Completed"


class NotionSyncClient:
    """Thin wrapper around notion-client SDK for reactor dashboard operations."""

    def __init__(self, token: str, database_id: str) -> None:
        self._client = Client(auth=token)
        self._database_id = database_id

    def query_all_rows(self) -> list[dict]:
        """Fetch all pages from the reactor dashboard database in a single API call."""
        response = self._client.databases.query(database_id=self._database_id)
        return response["results"]

    def update_page(self, page_id: str, properties: dict) -> None:
        """Update named properties on a Notion page."""
        self._client.pages.update(page_id=page_id, properties=properties)

    def clear_change_request(self, page_id: str) -> None:
        """Clear the Change Request text and reset status to Pending."""
        self.update_page(page_id, {
            PROP_CHANGE_REQUEST: {"rich_text": []},
            PROP_CHANGE_STATUS: {"select": {"name": STATUS_PENDING}},
        })

    def write_experiment_info(
        self,
        page_id: str,
        experiment_id: str,
        description: str,
        date_started: str,
    ) -> None:
        """Write experiment details to a Notion reactor row.

        Args:
            page_id: Notion page ID (with or without hyphens).
            experiment_id: User-defined experiment identifier e.g. "SERUM_MH_101".
            description: Experiment description text (first note).
            date_started: ISO date string e.g. "2026-03-15".
        """
        self.update_page(page_id, {
            PROP_EXPERIMENT_ID: {"rich_text": [{"text": {"content": experiment_id}}]},
            PROP_EXPERIMENT_DESC: {"rich_text": [{"text": {"content": description}}]},
            PROP_DATE_STARTED: {"date": {"start": date_started}},
        })

    def set_status_pending(self, page_id: str) -> None:
        """Set Change Request Status to Pending."""
        self.update_page(page_id, {
            PROP_CHANGE_STATUS: {"select": {"name": STATUS_PENDING}},
        })


def extract_reactor_label(page: dict) -> str:
    """Extract reactor label from the Notion page title property."""
    title_items = page["properties"][PROP_REACTOR_LABEL]["title"]
    return "".join(t["plain_text"] for t in title_items).strip()


def extract_change_request(page: dict) -> str:
    """Extract Change Request rich_text as a plain string."""
    items = page["properties"][PROP_CHANGE_REQUEST]["rich_text"]
    return "".join(t["plain_text"] for t in items).strip()


def extract_change_status(page: dict) -> str:
    """Extract Change Request Status select value; returns 'Pending' if unset."""
    select = page["properties"][PROP_CHANGE_STATUS]["select"]
    return select["name"] if select else STATUS_PENDING
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_client.py -v
```
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/notion_sync/ tests/services/test_notion_sync_client.py
git commit -m "[#32] add Notion client wrapper with unit tests"
```

---

## Task 6: Import service (TDD)

**Files:**
- Create: `backend/services/notion_sync/import_.py`
- Create: `tests/services/test_notion_sync_import.py`

- [ ] **Step 1: Write all import tests**

Create `tests/services/test_notion_sync_import.py`:

```python
"""Unit tests for the Notion import step.

Uses the PostgreSQL test DB (db_session fixture from tests/services/conftest.py).
All Notion API calls are mocked via MagicMock — no real Notion calls are made.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from backend.services.notion_sync.import_ import run_import
from database.models.notion_sync import ReactorChangeRequest

SYNC_DATE = date(2026, 4, 1)
_PAGE_ID = "abc12345-1234-1234-1234-abc123456789"
_PAGE_ID_STRIPPED = "abc1234512341234123412341234abc123456789".replace("-", "")  # will strip in model


def _page(
    page_id: str,
    reactor_label: str,
    change_request: str,
    status: str = "Pending",
) -> dict:
    """Build a minimal mock Notion page matching the extract_* function expectations."""
    return {
        "id": page_id,
        "properties": {
            "Name": {"title": [{"plain_text": reactor_label}]},
            "Change Request": {
                "rich_text": [{"plain_text": change_request}] if change_request.strip() else []
            },
            "Change Request Status": {"select": {"name": status}},
        },
    }


def _empty_page(page_id: str, reactor_label: str) -> dict:
    return {
        "id": page_id,
        "properties": {
            "Name": {"title": [{"plain_text": reactor_label}]},
            "Change Request": {"rich_text": []},
            "Change Request Status": {"select": {"name": "Pending"}},
        },
    }


def test_import_skips_empty_rows(db_session: Session) -> None:
    """Rows with blank Change Request produce zero DB writes and zero Notion calls."""
    client = MagicMock()
    pages = [_empty_page(_PAGE_ID, "R01")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.skipped == 1
    assert result.imported == 0
    client.clear_change_request.assert_not_called()
    assert db_session.query(ReactorChangeRequest).count() == 0


def test_import_skips_whitespace_only_change_request(db_session: Session) -> None:
    """Change Request with only whitespace is treated as empty."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R02", "   ", "Pending")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.skipped == 1
    assert result.imported == 0


def test_import_preserves_in_progress(db_session: Session) -> None:
    """In Progress row is written to DB; Notion clear is NOT called."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R05", "Run test today", "In Progress")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.imported == 1
    assert result.carried_forward == 0
    client.clear_change_request.assert_not_called()

    row = db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R05", sync_date=SYNC_DATE
    ).one()
    assert row.carried_forward is False
    assert row.notion_status == "In Progress"


def test_import_preserves_carried_forward(db_session: Session) -> None:
    """Carried Forward row is written with carried_forward=True; Notion clear NOT called."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R07", "Continue reaction", "Carried Forward")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.imported == 1
    assert result.carried_forward == 1
    client.clear_change_request.assert_not_called()

    row = db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R07", sync_date=SYNC_DATE
    ).one()
    assert row.carried_forward is True
    assert row.notion_status == "Carried Forward"


def test_import_clears_completed_after_write(db_session: Session) -> None:
    """Completed row: DB upsert first, THEN Notion clear."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R03", "Sample and clean", "Completed")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.imported == 1
    assert _PAGE_ID in result.cleared_page_ids
    client.clear_change_request.assert_called_once_with(_PAGE_ID)
    assert db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R03", sync_date=SYNC_DATE
    ).count() == 1


def test_import_clears_pending_with_content(db_session: Session) -> None:
    """Pending row with non-empty content is imported and cleared."""
    client = MagicMock()
    page_id = "deadbeef-dead-beef-dead-beefdeadbeef"
    pages = [_page(page_id, "R02", "Check pH and repressurize", "Pending")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    assert result.imported == 1
    assert page_id in result.cleared_page_ids
    client.clear_change_request.assert_called_once_with(page_id)


def test_import_db_committed_before_notion_clear(db_session: Session) -> None:
    """If Notion clear raises, the DB row must already be committed."""
    client = MagicMock()
    client.clear_change_request.side_effect = Exception("Network timeout")
    pages = [_page(_PAGE_ID, "R08", "Take a sample", "Completed")]

    result = run_import(client, db_session, pages, SYNC_DATE)

    # DB row persists despite Notion error
    assert db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R08", sync_date=SYNC_DATE
    ).count() == 1
    # Error was captured, not raised
    assert len(result.errors) == 1


def test_import_upsert_idempotent(db_session: Session) -> None:
    """Two runs with same reactor_label + sync_date produce exactly one DB row."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R01", "Sample reactor", "Pending")]

    run_import(client, db_session, pages, SYNC_DATE)
    result = run_import(client, db_session, pages, SYNC_DATE)

    assert db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R01", sync_date=SYNC_DATE
    ).count() == 1
    assert result.imported == 1


def test_carried_forward_accumulates_across_dates(db_session: Session) -> None:
    """Same Carried Forward row on two different sync dates produces two DB rows."""
    client = MagicMock()
    pages = [_page(_PAGE_ID, "R04", "Ongoing reaction", "Carried Forward")]
    date1 = date(2026, 4, 1)
    date2 = date(2026, 4, 2)

    run_import(client, db_session, pages, date1)
    run_import(client, db_session, pages, date2)

    assert db_session.query(ReactorChangeRequest).filter_by(
        reactor_label="R04"
    ).count() == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_import.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.notion_sync.import_'`

- [ ] **Step 3: Implement import_.py**

Create `backend/services/notion_sync/import_.py`:

```python
"""Import step — read Change Requests from Notion, upsert to DB, then clear Notion.

The Notion clear is deliberately called AFTER db.commit() so that a DB failure
never causes Notion data to be lost without a DB record.
"""
from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from database.models.notion_sync import ReactorChangeRequest
from .client import (
    NotionSyncClient,
    extract_change_request,
    extract_change_status,
    extract_reactor_label,
    STATUS_IN_PROGRESS,
    STATUS_CARRIED_FORWARD,
)

log = structlog.get_logger(__name__)


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    carried_forward: int = 0
    errors: list[str] = field(default_factory=list)
    cleared_page_ids: set[str] = field(default_factory=set)


def run_import(
    client: NotionSyncClient,
    db: Session,
    pages: list[dict],
    sync_date: date,
) -> ImportResult:
    """Import change requests from Notion pages into the DB for sync_date.

    For each page:
    - Empty Change Request → skip
    - In Progress / Carried Forward → upsert DB, do NOT clear Notion
    - Completed / Pending with content → upsert DB, THEN clear Notion after commit

    Returns ImportResult with counts and the set of page IDs that were cleared.
    """
    result = ImportResult()
    pages_to_clear: list[str] = []  # collected before commit; cleared after

    for page in pages:
        page_id_raw: str = page["id"]
        reactor_label: str = extract_reactor_label(page)
        change_request: str = extract_change_request(page)
        status: str = extract_change_status(page)

        if not change_request:
            result.skipped += 1
            continue

        carried_forward = status == STATUS_CARRIED_FORWARD
        should_clear = status not in (STATUS_IN_PROGRESS, STATUS_CARRIED_FORWARD)

        try:
            stmt = (
                pg_insert(ReactorChangeRequest)
                .values(
                    reactor_label=reactor_label,
                    experiment_id=None,
                    requested_change=change_request,
                    notion_status=status,
                    carried_forward=carried_forward,
                    sync_date=sync_date,
                    notion_page_id=page_id_raw.replace("-", ""),
                )
                .on_conflict_do_update(
                    index_elements=["reactor_label", "sync_date"],
                    set_=dict(
                        requested_change=change_request,
                        notion_status=status,
                        carried_forward=carried_forward,
                        notion_page_id=page_id_raw.replace("-", ""),
                    ),
                )
            )
            db.execute(stmt)
        except Exception as exc:
            result.errors.append(f"{reactor_label}: DB error — {exc}")
            log.error("notion_import_db_error", reactor=reactor_label, error=str(exc))
            continue

        if carried_forward:
            result.carried_forward += 1
        result.imported += 1

        if should_clear:
            pages_to_clear.append(page_id_raw)

    # Commit ALL upserts BEFORE touching Notion — protects against partial failures.
    try:
        db.commit()
    except Exception as exc:
        result.errors.append(f"DB commit failed: {exc}")
        log.error("notion_import_commit_error", error=str(exc))
        return result

    # Now clear Notion rows safely; DB is already committed.
    for page_id_raw in pages_to_clear:
        try:
            client.clear_change_request(page_id_raw)
            result.cleared_page_ids.add(page_id_raw)
        except Exception as exc:
            result.errors.append(f"Notion clear failed for {page_id_raw}: {exc}")
            log.warning("notion_clear_failed", page_id=page_id_raw, error=str(exc))

    log.info(
        "notion_import_done",
        imported=result.imported,
        skipped=result.skipped,
        carried_forward=result.carried_forward,
        errors=result.errors,
    )
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_import.py -v
```
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/notion_sync/import_.py tests/services/test_notion_sync_import.py
git commit -m "[#32] add import service with unit tests"
```

---

## Task 7: Export service (TDD)

**Files:**
- Create: `backend/services/notion_sync/export.py`
- Create: `tests/services/test_notion_sync_export.py`

- [ ] **Step 1: Write all export tests**

Create `tests/services/test_notion_sync_export.py`:

```python
"""Unit tests for the Notion export step.

Uses the PostgreSQL test DB (db_session fixture) and mocked NotionSyncClient.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from backend.services.notion_sync.export import run_export
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment, ExperimentNotes


def _notion_page(page_id: str, reactor_label: str, status: str = "Pending") -> dict:
    return {
        "id": page_id,
        "properties": {
            "Name": {"title": [{"plain_text": reactor_label}]},
            "Change Request": {"rich_text": []},
            "Change Request Status": {"select": {"name": status}},
        },
    }


def _seed_experiment(
    db: Session,
    experiment_id: str,
    experiment_number: int,
    reactor_number: int,
    experiment_type: str = "Serum",
    start_date: datetime | None = None,
    description: str = "",
    status: ExperimentStatus = ExperimentStatus.ONGOING,
) -> Experiment:
    """Seed an experiment with conditions into the test DB."""
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=experiment_number,
        status=status,
        date=start_date or datetime(2026, 1, 1),
    )
    db.add(exp)
    db.flush()
    if description:
        note = ExperimentNotes(
            experiment_fk=exp.id,
            experiment_id=experiment_id,
            note_text=description,
        )
        db.add(note)
    cond = ExperimentalConditions(
        experiment_fk=exp.id,
        experiment_id=experiment_id,
        reactor_number=reactor_number,
        experiment_type=experiment_type,
    )
    db.add(cond)
    db.flush()
    return exp


def test_export_skips_idle_slots(db_session: Session) -> None:
    """write_experiment_info is only called for occupied (ONGOING) reactor slots."""
    client = MagicMock()
    pages = [
        _notion_page("aaa", "R01"),
        _notion_page("bbb", "R02"),  # no experiment in R02
    ]
    _seed_experiment(db_session, "SERUM_001", 1001, reactor_number=1)

    result = run_export(client, db_session, pages, cleared_page_ids=set())

    assert result.exported == 1
    client.write_experiment_info.assert_called_once()
    assert client.write_experiment_info.call_args[1]["page_id"] == "aaa"


def test_export_writes_correct_properties(db_session: Session) -> None:
    """write_experiment_info is called with correct experiment_id, description, date_started."""
    client = MagicMock()
    pages = [_notion_page("ccc", "R03")]
    _seed_experiment(
        db_session, "HPHT_001", 1002,
        reactor_number=3, experiment_type="HPHT",
        start_date=datetime(2026, 3, 15),
        description="Rock dissolution test",
    )

    run_export(client, db_session, pages, cleared_page_ids=set())

    client.write_experiment_info.assert_called_once_with(
        page_id="ccc",
        experiment_id="HPHT_001",
        description="Rock dissolution test",
        date_started="2026-03-15",
    )


def test_export_sets_pending_after_clear(db_session: Session) -> None:
    """set_status_pending is called for a page that was cleared in this cycle."""
    client = MagicMock()
    pages = [_notion_page("ddd", "R05")]
    _seed_experiment(db_session, "SERUM_002", 1003, reactor_number=5)

    run_export(client, db_session, pages, cleared_page_ids={"ddd"})

    client.set_status_pending.assert_called_once_with("ddd")


def test_export_preserves_in_progress_status(db_session: Session) -> None:
    """set_status_pending is NOT called for a page that was not cleared (In Progress)."""
    client = MagicMock()
    pages = [_notion_page("eee", "R06", status="In Progress")]
    _seed_experiment(db_session, "SERUM_003", 1004, reactor_number=6)

    run_export(client, db_session, pages, cleared_page_ids=set())

    client.set_status_pending.assert_not_called()


def test_export_preserves_carried_forward_status(db_session: Session) -> None:
    """set_status_pending is NOT called for a Carried Forward page that was not cleared."""
    client = MagicMock()
    pages = [_notion_page("fff", "R07", status="Carried Forward")]
    _seed_experiment(db_session, "SERUM_004", 1005, reactor_number=7)

    run_export(client, db_session, pages, cleared_page_ids=set())

    client.set_status_pending.assert_not_called()


def test_export_cf_slots_mapped_correctly(db_session: Session) -> None:
    """Core Flood experiments map to CF01/CF02 Notion labels."""
    client = MagicMock()
    pages = [_notion_page("ggg", "CF01")]
    _seed_experiment(
        db_session, "CF_001", 1006,
        reactor_number=1, experiment_type="Core Flood",
    )

    result = run_export(client, db_session, pages, cleared_page_ids=set())

    assert result.exported == 1
    assert client.write_experiment_info.call_args[1]["page_id"] == "ggg"


def test_export_skips_completed_experiments(db_session: Session) -> None:
    """COMPLETED experiments are not exported (only ONGOING)."""
    client = MagicMock()
    pages = [_notion_page("hhh", "R08")]
    _seed_experiment(
        db_session, "SERUM_005", 1007,
        reactor_number=8, status=ExperimentStatus.COMPLETED,
    )

    result = run_export(client, db_session, pages, cleared_page_ids=set())

    assert result.exported == 0
    client.write_experiment_info.assert_not_called()


def test_export_no_description_writes_empty_string(db_session: Session) -> None:
    """Experiment with no notes exports description as empty string (not None)."""
    client = MagicMock()
    pages = [_notion_page("iii", "R09")]
    _seed_experiment(db_session, "SERUM_006", 1008, reactor_number=9, description="")

    run_export(client, db_session, pages, cleared_page_ids=set())

    call_kwargs = client.write_experiment_info.call_args[1]
    assert call_kwargs["description"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_export.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.notion_sync.export'`

- [ ] **Step 3: Implement export.py**

Create `backend/services/notion_sync/export.py`:

```python
"""Export step — write occupied reactor slot data to Notion.

Only writes for ONGOING experiments with a reactor_number assigned.
Idle slots are skipped entirely (no Notion calls).
"""
from __future__ import annotations

import structlog
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment
from .client import (
    NotionSyncClient,
    extract_change_status,
    extract_reactor_label,
)

log = structlog.get_logger(__name__)


@dataclass
class ExportResult:
    exported: int = 0
    errors: list[str] = field(default_factory=list)


def _reactor_label_for(reactor_number: int, experiment_type: str | None) -> str:
    """Map DB reactor_number + experiment_type to Notion label e.g. 'R05' or 'CF01'."""
    is_cf = (experiment_type == "Core Flood") if experiment_type else False
    return f"CF{reactor_number:02d}" if is_cf else f"R{reactor_number:02d}"


def run_export(
    client: NotionSyncClient,
    db: Session,
    pages: list[dict],
    cleared_page_ids: set[str],
) -> ExportResult:
    """Write experiment info to Notion for every occupied ONGOING reactor slot.

    Args:
        client: Notion client wrapper.
        db: SQLAlchemy session (read-only in this step).
        pages: All 18 Notion reactor pages (already fetched by orchestrator).
        cleared_page_ids: Page IDs whose Change Request was cleared in the import step.
            Only these pages get their status reset to Pending.
    """
    result = ExportResult()

    # Build lookup: reactor_label → page_id (with dashes, for Notion API calls)
    notion_rows: dict[str, str] = {
        extract_reactor_label(page): page["id"] for page in pages
    }

    # Query occupied slots: ONGOING experiments with a reactor assigned
    rows = (
        db.query(
            Experiment.experiment_id,
            Experiment.description,
            Experiment.date,
            ExperimentalConditions.reactor_number,
            ExperimentalConditions.experiment_type,
        )
        .join(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .filter(
            Experiment.status == ExperimentStatus.ONGOING,
            ExperimentalConditions.reactor_number.isnot(None),
        )
        .all()
    )

    for row in rows:
        label = _reactor_label_for(row.reactor_number, row.experiment_type)
        page_id = notion_rows.get(label)
        if page_id is None:
            log.warning("notion_export_no_page_for_reactor", reactor=label)
            continue

        date_started = row.date.strftime("%Y-%m-%d") if row.date else ""

        try:
            client.write_experiment_info(
                page_id=page_id,
                experiment_id=row.experiment_id,
                description=row.description or "",
                date_started=date_started,
            )
            # Re-confirm Pending status only for rows cleared in this cycle
            if page_id in cleared_page_ids:
                client.set_status_pending(page_id)
            result.exported += 1
        except Exception as exc:
            result.errors.append(f"{label}: export error — {exc}")
            log.error("notion_export_error", reactor=label, error=str(exc))

    log.info("notion_export_done", exported=result.exported, errors=result.errors)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_export.py -v
```
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/notion_sync/export.py tests/services/test_notion_sync_export.py
git commit -m "[#32] add export service with unit tests"
```

---

## Task 8: Sync orchestrator + integration tests

**Files:**
- Create: `backend/services/notion_sync/sync.py`
- Create: `tests/services/test_notion_sync_integration.py`

- [ ] **Step 1: Write integration tests**

Create `tests/services/test_notion_sync_integration.py`:

```python
"""Integration tests for the full Notion sync cycle.

Uses the PostgreSQL test DB and a fully mocked NotionSyncClient.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from backend.services.notion_sync.sync import run_sync
from backend.services.notion_sync.client import NotionSyncClient
from database.models.conditions import ExperimentalConditions
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment
from database.models.notion_sync import ReactorChangeRequest


def _notion_page(page_id: str, reactor_label: str, change_request: str = "", status: str = "Pending") -> dict:
    return {
        "id": page_id,
        "properties": {
            "Name": {"title": [{"plain_text": reactor_label}]},
            "Change Request": {
                "rich_text": [{"plain_text": change_request}] if change_request.strip() else []
            },
            "Change Request Status": {"select": {"name": status}},
        },
    }


def _seed(db: Session, experiment_id: str, number: int, reactor: int, etype: str = "Serum") -> None:
    exp = Experiment(
        experiment_id=experiment_id, experiment_number=number,
        status=ExperimentStatus.ONGOING, date=datetime(2026, 1, 1),
    )
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=experiment_id,
        reactor_number=reactor, experiment_type=etype,
    ))
    db.flush()


def test_full_sync_cycle(db_session: Session) -> None:
    """Full sync: 2 ONGOING experiments, 1 non-empty Change Request → 1 import + 2 exports."""
    client = MagicMock(spec=NotionSyncClient)
    client.query_all_rows.return_value = [
        _notion_page("page-r01-0000-0000-0000-000000000000", "R01", "Sample today", "Pending"),
        _notion_page("page-r03-0000-0000-0000-000000000000", "R03", "", "Pending"),
    ]

    _seed(db_session, "SERUM_A", 2001, reactor=1)
    _seed(db_session, "SERUM_B", 2002, reactor=3)

    result = run_sync(client, db_session)

    # Import: R01 has content, R03 is empty → 1 imported, 1 skipped
    assert result.imported == 1
    # Export: 2 ONGOING experiments → 2 Notion writes
    assert result.exported == 2
    assert result.errors == []

    # DB should have one ReactorChangeRequest row for R01
    assert db_session.query(ReactorChangeRequest).count() == 1
    # Notion write calls: one per occupied slot
    assert client.write_experiment_info.call_count == 2
    # R01 had its Change Request cleared → status was reset to Pending in export
    client.set_status_pending.assert_called_once_with(
        "page-r01-0000-0000-0000-000000000000"
    )


def test_sync_survives_notion_outage(db_session: Session) -> None:
    """If Notion API raises on query_all_rows, sync logs error and returns without crashing."""
    import httpx
    client = MagicMock(spec=NotionSyncClient)
    client.query_all_rows.side_effect = httpx.ConnectError("connection refused")

    result = run_sync(client, db_session)

    assert len(result.errors) == 1
    assert "connection refused" in result.errors[0]
    assert result.imported == 0
    assert result.exported == 0


def test_sync_result_to_dict(db_session: Session) -> None:
    """SyncResult.to_dict() returns the summary payload for the API response."""
    client = MagicMock(spec=NotionSyncClient)
    client.query_all_rows.return_value = []

    result = run_sync(client, db_session)

    d = result.to_dict()
    assert set(d.keys()) == {"imported", "exported", "carried_forward", "errors"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_integration.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.notion_sync.sync'`

- [ ] **Step 3: Implement sync.py**

Create `backend/services/notion_sync/sync.py`:

```python
"""Sync orchestrator — runs full import + export cycle.

Also provides make_scheduler() to configure APScheduler for the daily job.
"""
from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from .client import NotionSyncClient
from .import_ import run_import
from .export import run_export

log = structlog.get_logger(__name__)


@dataclass
class SyncResult:
    imported: int = 0
    exported: int = 0
    carried_forward: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "imported": self.imported,
            "exported": self.exported,
            "carried_forward": self.carried_forward,
            "errors": self.errors,
        }


def run_sync(client: NotionSyncClient, db) -> SyncResult:
    """Run one full sync cycle: import then export.

    The DB session is shared across both steps. Import commits after upserts.
    Export performs read-only queries.
    """
    try:
        pages = client.query_all_rows()
    except Exception as exc:
        log.error("notion_sync_query_failed", error=str(exc))
        return SyncResult(errors=[f"Notion API error: {exc}"])

    import_result = run_import(client, db, pages, date.today())
    export_result = run_export(client, db, pages, import_result.cleared_page_ids)

    result = SyncResult(
        imported=import_result.imported,
        exported=export_result.exported,
        carried_forward=import_result.carried_forward,
        errors=import_result.errors + export_result.errors,
    )
    log.info(
        "notion_sync_complete",
        imported=result.imported,
        exported=result.exported,
        carried_forward=result.carried_forward,
        errors=result.errors,
    )
    return result


def make_scheduler(notion_sync_hour: int) -> AsyncIOScheduler:
    """Build an AsyncIOScheduler with the daily notion sync job.

    The scheduler is returned un-started; call scheduler.start() in the
    FastAPI lifespan and scheduler.shutdown() on teardown.
    """
    tz = pytz.timezone("America/New_York")
    scheduler = AsyncIOScheduler()

    def _job() -> None:
        """APScheduler entry point — creates its own DB session."""
        from database.database import SessionLocal
        from backend.config.settings import get_settings

        settings = get_settings()
        notion_client = NotionSyncClient(
            token=settings.notion_token,
            database_id=settings.notion_database_id,
        )
        db = SessionLocal()
        try:
            run_sync(notion_client, db)
        except Exception as exc:
            log.error("notion_sync_job_unhandled_error", error=str(exc))
        finally:
            db.close()

    scheduler.add_job(
        _job,
        CronTrigger(hour=notion_sync_hour, timezone=tz),
        id="notion_sync",
        replace_existing=True,
    )
    return scheduler
```

- [ ] **Step 4: Run integration tests**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_integration.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 5: Run all notion sync service tests together**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_client.py tests/services/test_notion_sync_import.py tests/services/test_notion_sync_export.py tests/services/test_notion_sync_integration.py -v
```
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add backend/services/notion_sync/sync.py tests/services/test_notion_sync_integration.py
git commit -m "[#32] add sync orchestrator with integration tests"
```

---

## Task 9: Register scheduler in FastAPI lifespan

**Files:**
- Modify: `backend/api/main.py:22-26`

- [ ] **Step 1: Update lifespan to start/stop scheduler**

Replace the existing `lifespan` function in `backend/api/main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from database.database import reset_postgres_sequences
    reset_postgres_sequences()

    # Start the Notion sync scheduler if a token is configured
    _scheduler = None
    _settings = get_settings()
    if _settings.notion_token:
        from backend.services.notion_sync.sync import make_scheduler
        _scheduler = make_scheduler(_settings.notion_sync_hour)
        _scheduler.start()
        log.info(
            "notion_sync_scheduler_started",
            hour=_settings.notion_sync_hour,
            timezone="America/New_York",
        )

    yield

    if _scheduler is not None:
        _scheduler.shutdown()
        log.info("notion_sync_scheduler_stopped")
```

Also add `log = structlog.get_logger(__name__)` near the top of `main.py` (after the existing imports), and add `import structlog` if not already present.

- [ ] **Step 2: Verify the app starts without errors when NOTION_TOKEN is unset**

```bash
.venv/Scripts/python -c "from backend.api.main import app; print('app loaded ok')"
```
Expected: `app loaded ok` (no scheduler starts since NOTION_TOKEN is empty)

- [ ] **Step 3: Commit**

```bash
git add backend/api/main.py
git commit -m "[#32] register Notion sync scheduler in FastAPI lifespan"
```

---

## Task 10: Admin trigger endpoint + API tests

**Files:**
- Create: `backend/api/routers/notion_sync.py`
- Create: `tests/api/test_notion_sync.py`
- Modify: `backend/api/main.py` (add router import + include_router)

- [ ] **Step 1: Write API tests**

Create `tests/api/test_notion_sync.py`:

```python
"""API tests for POST /api/admin/notion-sync/trigger."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser


@pytest.fixture()
def unauth_client(db_session):
    def override_get_db():
        yield db_session

    async def no_auth():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_firebase_token] = no_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_trigger_requires_auth(unauth_client) -> None:
    """POST /api/admin/notion-sync/trigger without token returns 401."""
    resp = unauth_client.post("/api/admin/notion-sync/trigger")
    assert resp.status_code == 401


def test_trigger_notion_token_not_configured(client: TestClient) -> None:
    """Returns 503 when NOTION_TOKEN is not set."""
    from backend.config.settings import get_settings, Settings
    from unittest.mock import patch

    no_token_settings = Settings(notion_token="", notion_database_id="")

    with patch("backend.api.routers.notion_sync.get_settings", return_value=no_token_settings):
        resp = client.post("/api/admin/notion-sync/trigger")

    assert resp.status_code == 503
    assert "NOTION_TOKEN" in resp.json()["detail"]


def test_trigger_success(client: TestClient) -> None:
    """With valid auth and mocked sync, returns 200 with summary payload."""
    from backend.config.settings import Settings
    from backend.services.notion_sync.sync import SyncResult
    from unittest.mock import patch

    configured_settings = Settings(
        notion_token="secret_test_token",
        notion_database_id="testdbid",
    )
    mock_result = SyncResult(imported=2, exported=3, carried_forward=1, errors=[])

    with (
        patch("backend.api.routers.notion_sync.get_settings", return_value=configured_settings),
        patch("backend.api.routers.notion_sync.run_sync", return_value=mock_result),
    ):
        resp = client.post("/api/admin/notion-sync/trigger")

    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 2
    assert body["exported"] == 3
    assert body["carried_forward"] == 1
    assert body["errors"] == []


def test_trigger_returns_errors_in_payload(client: TestClient) -> None:
    """Sync errors are returned in the payload (not as HTTP 500) so the client can inspect them."""
    from backend.config.settings import Settings
    from backend.services.notion_sync.sync import SyncResult

    configured_settings = Settings(
        notion_token="secret_test_token",
        notion_database_id="testdbid",
    )
    mock_result = SyncResult(imported=0, exported=0, errors=["R01: DB error — timeout"])

    with (
        patch("backend.api.routers.notion_sync.get_settings", return_value=configured_settings),
        patch("backend.api.routers.notion_sync.run_sync", return_value=mock_result),
    ):
        resp = client.post("/api/admin/notion-sync/trigger")

    assert resp.status_code == 200
    assert resp.json()["errors"] == ["R01: DB error — timeout"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/pytest tests/api/test_notion_sync.py -v
```
Expected: FAIL — `404` on the trigger endpoint (router not registered yet)

- [ ] **Step 3: Create the router**

Create `backend/api/routers/notion_sync.py`:

```python
"""Admin endpoints for on-demand Notion sync."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import FirebaseUser, verify_firebase_token
from backend.config.settings import get_settings
from backend.services.notion_sync.client import NotionSyncClient
from backend.services.notion_sync.sync import run_sync

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/admin/notion-sync", tags=["admin"])


@router.post("/trigger")
def trigger_notion_sync(
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> dict:
    """Run a full Notion sync cycle on demand.

    Returns a summary dict with imported, exported, carried_forward, and errors counts.
    Sync errors are returned in the payload rather than raising HTTP 500 so callers
    can inspect partial results.
    """
    settings = get_settings()
    if not settings.notion_token:
        raise HTTPException(status_code=503, detail="NOTION_TOKEN not configured")

    notion_client = NotionSyncClient(
        token=settings.notion_token,
        database_id=settings.notion_database_id,
    )
    result = run_sync(notion_client, db)
    log.info(
        "notion_sync_triggered",
        user=current_user.email,
        **result.to_dict(),
    )
    return result.to_dict()
```

- [ ] **Step 4: Register the router in main.py**

In `backend/api/main.py`, add to the router imports:

```python
from backend.api.routers import (
    experiments, conditions, results, samples,
    chemicals, analysis, dashboard, admin, bulk_uploads, auth, additives, notion_sync,
)
```

And add after the other `include_router` calls:

```python
app.include_router(notion_sync.router)
```

- [ ] **Step 5: Run API tests**

```bash
.venv/Scripts/pytest tests/api/test_notion_sync.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 6: Run all notion sync tests together**

```bash
.venv/Scripts/pytest tests/services/test_notion_sync_client.py tests/services/test_notion_sync_import.py tests/services/test_notion_sync_export.py tests/services/test_notion_sync_integration.py tests/api/test_notion_sync.py -v
```
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/notion_sync.py backend/api/main.py tests/api/test_notion_sync.py
git commit -m "[#32] add notion-sync trigger endpoint with API tests"
```

---

## Task 11: NOTION_SYNC.md documentation

**Files:**
- Create: `docs/notion_sync/NOTION_SYNC.md`

- [ ] **Step 1: Create the documentation file**

Create `docs/notion_sync/NOTION_SYNC.md`:

```markdown
# Notion Sync — Reactor Dashboard

This document is the source of truth for the Notion sync integration.
Read it before editing any file in `backend/services/notion_sync/`.

---

## Notion Database

| Field | Value |
|-------|-------|
| Database Name | Reactor Dashboard |
| Database URL | https://www.notion.so/53ec4778508541efa31eaf0e4accac35 |
| Database ID | `53ec4778508541efa31eaf0e4accac35` |
| Data Source ID | `d8d499ab-d6ef-44ce-9f67-d650dfaf5319` |
| Rows | 18 (R01–R16, CF01, CF02) |

The "Daily Standup" gallery view is what team members use to enter change requests.

---

## Notion Property Map

All property names are defined as constants in `backend/services/notion_sync/client.py`.
**If the Notion schema changes, update client.py constants AND this table.**

| Constant | Notion Property Name | Type | Direction |
|----------|---------------------|------|-----------|
| `PROP_REACTOR_LABEL` | `Name` | Title | Read (import + export lookup) |
| `PROP_CHANGE_REQUEST` | `Change Request` | rich_text | Read (import), Clear (import) |
| `PROP_CHANGE_STATUS` | `Change Request Status` | select | Read (import), Write (import clear, export) |
| `PROP_EXPERIMENT_ID` | `Experiment ID` | rich_text | Write (export) |
| `PROP_EXPERIMENT_DESC` | `Experiment Description` | rich_text | Write (export) |
| `PROP_DATE_STARTED` | `Date Started` | date | Write (export) |

### Change Request Status values

| Value | Meaning |
|-------|---------|
| `Pending` | Default state; ready for a new request |
| `In Progress` | Team member is actively working on this reactor |
| `Carried Forward` | Request was not completed; carries to next day |
| `Completed` | Request was completed; import will clear and reset to Pending |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NOTION_TOKEN` | Notion integration token (`secret_...`) |
| `NOTION_DATABASE_ID` | 32-char database ID (no hyphens) |
| `NOTION_DATA_SOURCE_ID` | Data source ID (for reference) |
| `NOTION_SYNC_HOUR` | Hour (0–23, America/New_York) for daily job; default `6` |

The scheduler only starts when `NOTION_TOKEN` is non-empty.

---

## Sync Sequence

The sync runs daily at `NOTION_SYNC_HOUR` (America/New_York) via APScheduler,
and can be triggered on demand via `POST /api/admin/notion-sync/trigger`.

### Step 1 — Import

1. Query all 18 Notion rows in one SDK call.
2. For each row:
   - **Empty Change Request** → skip (no DB write, no Notion call)
   - **In Progress** → upsert to DB with `carried_forward=False`; do NOT clear Notion
   - **Carried Forward** → upsert to DB with `carried_forward=True`; do NOT clear Notion
   - **Completed** or **Pending with content** → upsert to DB; then clear Change Request + set status to Pending
3. The Notion clear is called **only after** the DB `commit()`. A Notion failure after commit is logged and counted in `errors` but does not undo the DB row.
4. `Carried Forward` rows accumulate: same reactor on different sync dates = different DB rows (the unique constraint is on `(reactor_label, date)`).

### Step 2 — Export

1. Query all ONGOING experiments with a `reactor_number` assigned.
2. For each occupied slot, write `Experiment ID`, `Experiment Description`, and `Date Started` to the corresponding Notion page.
3. If the Notion page was cleared in Step 1, also reset `Change Request Status` to Pending.
4. If status is `In Progress` or `Carried Forward` and the page was NOT cleared, the status column is not touched.
5. Idle reactor slots (no ONGOING experiment) are skipped entirely — no Notion writes.

### Step 3 — Log

```
structlog.info("notion_sync_complete",
    imported=N, exported=N, carried_forward=N, errors=[...])
```

---

## Reactor Label Mapping

DB `reactor_number` (integer) maps to Notion reactor label as follows:

| DB `experiment_type` | Label formula | Examples |
|---------------------|--------------|---------|
| `"Core Flood"` | `CF{reactor_number:02d}` | CF01, CF02 |
| anything else | `R{reactor_number:02d}` | R01 … R16 |

The same formula is used in `backend/api/routers/dashboard.py` (`REACTOR_SPECS`).

---

## DB Model

`ReactorChangeRequest` in `database/models/notion_sync.py`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto |
| `reactor_label` | String(10) | "R05", "CF01" |
| `experiment_id` | String, nullable FK | Ref to `experiments.experiment_id`; NULL on import |
| `requested_change` | String | Change Request text at import time |
| `notion_status` | String(50) | Status value at import time |
| `carried_forward` | Boolean | True if Carried Forward at import |
| `date` | Date | Sync cycle date |
| `notion_page_id` | String(32) | Notion page UUID, hyphens stripped |
| `created_at` | DateTime | Auto |

Unique constraint: `(reactor_label, date)` — re-running sync on the same day upserts rather than duplicates.

---

## API Endpoint

`POST /api/admin/notion-sync/trigger`

Requires Firebase auth (Bearer token). Runs a full sync cycle and returns:

```json
{
  "imported": 3,
  "exported": 12,
  "carried_forward": 1,
  "errors": []
}
```

Sync errors (Notion outage, individual row failures) are returned in `errors` at HTTP 200.
The endpoint only returns HTTP 500 if the sync itself raises an unhandled exception.
HTTP 503 is returned when `NOTION_TOKEN` is not configured.
```

- [ ] **Step 2: Verify the file was created**

```bash
cat docs/notion_sync/NOTION_SYNC.md | head -10
```
Expected: `# Notion Sync — Reactor Dashboard`

- [ ] **Step 3: Commit**

```bash
git add docs/notion_sync/NOTION_SYNC.md
git commit -m "[#32] add NOTION_SYNC.md documentation"
```

---

## Final Verification

- [ ] **Run the full notion sync test suite**

```bash
.venv/Scripts/pytest tests/models/test_notion_sync_model.py tests/services/test_notion_sync_client.py tests/services/test_notion_sync_import.py tests/services/test_notion_sync_export.py tests/services/test_notion_sync_integration.py tests/api/test_notion_sync.py -v
```
Expected: All tests pass.

- [ ] **Run the full backend test suite to check for regressions**

```bash
.venv/Scripts/pytest tests/api/ tests/services/ tests/models/ -v --tb=short 2>&1 | tail -20
```
Expected: No new failures.

- [ ] **Verify app loads cleanly**

```bash
.venv/Scripts/python -c "from backend.api.main import app; print('ok')"
```
Expected: `ok`

---

## Self-Review

**Spec coverage check:**

| Acceptance Criterion | Task |
|---------------------|------|
| `reactor_change_requests` table with upgrade + downgrade | Task 3–4 |
| Unique constraint `(reactor_label, date)` + upsert | Task 3, import_ |
| Export only for ONGOING slots; idle skipped | Task 7 |
| Export sets Pending only for cleared rows | Task 7 |
| Import skips empty/whitespace Change Request | Task 6 |
| Import preserves In Progress / Carried Forward in Notion | Task 6 |
| Carried Forward accumulates across dates | Task 6 |
| Notion clear only after DB commit | Task 6 |
| APScheduler in FastAPI lifespan | Task 9 |
| `POST /api/admin/notion-sync/trigger` with Firebase auth | Task 10 |
| Sync result logged to structlog INFO | Task 8 (run_sync), Task 10 (router) |
| Notion API outage: logs error, no crash | Task 8 integration test |
| Env vars in `.env.example` | Task 2 |
| `notion-client` in `requirements.txt` after approval | Task 1 |
| `docs/notion_sync/NOTION_SYNC.md` committed | Task 11 |

**Placeholder scan:** No TBD, TODO, or "similar to Task N" patterns. All code steps show complete implementations.

**Type consistency:**
- `ImportResult.cleared_page_ids: set[str]` — raw page IDs with dashes (consistent across import_.py → export.py → sync.py)
- `SyncResult.to_dict()` — returns `{imported, exported, carried_forward, errors}` (matches router return and API test assertions)
- `NotionSyncClient` method signatures consistent across client.py, tests, and sync.py usage
