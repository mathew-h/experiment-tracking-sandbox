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
PROP_CHANGE_STATUS = "Change Request Status"  # select: Pending | In Progress | Completed
PROP_EXPERIMENT_ID = "Experiment ID"       # rich_text (written by export)
PROP_EXPERIMENT_DESC = "Experiment Description"  # rich_text (written by export)
PROP_DATE_STARTED = "Date Started"         # date (written by export)

STATUS_PENDING = "Pending"
STATUS_IN_PROGRESS = "In Progress"
STATUS_COMPLETED = "Completed"


class NotionSyncClient:
    """Thin wrapper around notion-client SDK for reactor dashboard operations."""

    def __init__(self, token: str, database_id: str) -> None:
        self._client = Client(auth=token)
        self._database_id = database_id

    def query_all_rows(self) -> list[dict]:
        """Fetch all pages from the reactor dashboard database in a single API call.

        Note: The Notion API returns at most 100 results per call. The reactor
        dashboard has 18 rows, well within this limit. If the database grows
        beyond 100 rows, implement cursor-based pagination here.
        """
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
        date_started: str | None,
    ) -> None:
        """Write experiment details to a Notion reactor row.

        Args:
            page_id: Notion page ID (with or without hyphens).
            experiment_id: User-defined experiment identifier e.g. "SERUM_MH_101".
            description: Experiment description text (first note).
            date_started: ISO date string e.g. "2026-03-15", or None if unknown.
        """
        properties: dict = {
            PROP_EXPERIMENT_ID: {"rich_text": [{"text": {"content": experiment_id}}]},
            PROP_EXPERIMENT_DESC: {"rich_text": [{"text": {"content": description}}]},
        }
        if date_started:
            properties[PROP_DATE_STARTED] = {"date": {"start": date_started}}
        self.update_page(page_id, properties)

    def set_status_pending(self, page_id: str) -> None:
        """Set Change Request Status to Pending."""
        self.update_page(page_id, {
            PROP_CHANGE_STATUS: {"select": {"name": STATUS_PENDING}},
        })

    def clear_experiment_info(self, page_id: str) -> None:
        """Clear experiment fields for an idle reactor slot."""
        self.update_page(page_id, {
            PROP_EXPERIMENT_ID: {"rich_text": []},
            PROP_EXPERIMENT_DESC: {"rich_text": []},
            PROP_DATE_STARTED: {"date": None},
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
