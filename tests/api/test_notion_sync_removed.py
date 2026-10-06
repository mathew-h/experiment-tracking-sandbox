"""Issue #122 PR-E (E1, absorbs #117): the Notion sync integration is gone.

Removed-route assertions go through the route registry, never HTTP 404 — the
SPA catch-all in backend/api/main.py answers unknown GET paths with index.html
(precedent: tests/api/test_bulk_uploads.py::test_master_results_config_endpoints_removed).
"""
from __future__ import annotations

import importlib.util

from backend.api.main import app
from backend.config.settings import Settings


def test_notion_sync_routes_are_unregistered():
    assert [r.path for r in app.routes if "notion" in getattr(r, "path", "")] == []


def test_settings_have_no_notion_fields():
    for name in ("notion_token", "notion_database_id", "notion_data_source_id", "notion_sync_hour"):
        assert name not in Settings.model_fields, name


def test_settings_ignore_stale_notion_env_keys(monkeypatch):
    """A deployed .env or environment may still carry NOTION_TOKEN=... —
    Settings is extra="ignore", so it must construct and must not grow the
    attribute. Exercises both the environment path and the kwargs path."""
    monkeypatch.setenv("NOTION_TOKEN", "stale-env")
    monkeypatch.setenv("NOTION_SYNC_HOUR", "notanint")
    s = Settings(_env_file=None, notion_token="stale", notion_sync_hour=6)
    assert not hasattr(s, "notion_token")
    assert not hasattr(s, "notion_sync_hour")


def test_notion_sync_package_is_gone():
    # A leftover backend/services/notion_sync/__pycache__/ directory would still
    # resolve as a namespace package, so this only passes once the directory is
    # removed entirely, not just its .py files.
    assert importlib.util.find_spec("backend.services.notion_sync") is None


def test_change_request_routes_are_unregistered():
    """The three /experiments/{id}/change-requests routes left with the Notion sync
    (#122 PR-E). Their data lives in experiment_notes since the 021 backfill."""
    assert [r.path for r in app.routes if "change-requests" in getattr(r, "path", "")] == []
