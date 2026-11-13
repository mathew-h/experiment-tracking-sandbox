"""Issue #189 (backend sweep PR 1): the dead endpoints are unregistered.

Removed-route assertions go through the route registry, never HTTP 404 — the
SPA catch-all in backend/api/main.py answers unknown GET paths with index.html
(precedent: tests/api/test_notion_removed.py).
"""
from __future__ import annotations

import importlib.util

import pytest

from backend.api.main import app

REMOVED_ROUTES = (
    ("GET", "/api/dashboard/reactor-status"),
    ("GET", "/api/dashboard/timeline/{experiment_id}"),
    ("GET", "/api/chemicals/additives/{conditions_id}"),
    ("POST", "/api/chemicals/additives/{conditions_id}"),
)

# Still served; guards against the removal taking a neighbour with it.
KEPT_ROUTES = (
    ("GET", "/api/dashboard/"),
    ("GET", "/api/chemicals/compounds"),
    ("PATCH", "/api/additives/{additive_id}"),
    ("PUT", "/api/experiments/{experiment_id}/additives/{compound_id}"),
)

REMOVED_MODULES = (
    "backend.api.routes",
    "backend.services.database",
    "backend.services.experimental_conditions_service",
    "backend.services.bulk_uploads.experiment_additives",
    "backend.services.bulk_uploads.quick_upload",
    "backend.services.bulk_uploads.long_format",
    "backend.services.bulk_uploads.metric_groups",
    "legacy.streamlit_frontend",
)


def _registered() -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", None) or ()
    }


@pytest.mark.parametrize("method,path", REMOVED_ROUTES)
def test_removed_route_is_unregistered(method: str, path: str):
    assert (method, path) not in _registered()


@pytest.mark.parametrize("method,path", KEPT_ROUTES)
def test_neighbouring_route_is_still_registered(method: str, path: str):
    assert (method, path) in _registered()


@pytest.mark.parametrize("name", REMOVED_MODULES)
def test_removed_module_is_gone(name: str):
    # find_spec raises ModuleNotFoundError when a parent package is missing,
    # and returns a namespace spec for a leftover __pycache__-only directory.
    try:
        spec = importlib.util.find_spec(name)
    except ModuleNotFoundError:
        spec = None
    assert spec is None or spec.origin is None, name
