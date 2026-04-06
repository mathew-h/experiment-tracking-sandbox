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
