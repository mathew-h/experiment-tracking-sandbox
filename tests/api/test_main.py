from fastapi.testclient import TestClient
from backend.api.main import app, api_docs_kwargs
from backend.config.settings import Settings


def test_health_check():
    with TestClient(app) as c:
        resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_openapi_schema_has_all_tags():
    schema = app.openapi()
    tag_names = {t["name"] for t in schema.get("tags", [])}
    for expected in ["experiments", "conditions", "results", "samples",
                     "chemicals", "analysis", "dashboard", "admin", "bulk-uploads"]:
        assert expected in tag_names, f"Missing tag: {expected}"


def test_api_docs_disabled_by_default():
    kwargs = api_docs_kwargs(Settings(_env_file=None))
    assert kwargs == {"docs_url": None, "redoc_url": None, "openapi_url": None}


def test_api_docs_enabled_by_setting():
    kwargs = api_docs_kwargs(Settings(_env_file=None, enable_api_docs=True))
    assert kwargs == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }


def test_app_registers_docs_routes_only_when_enabled():
    """Check the route registry, not HTTP status: the SPA catch-all answers
    /docs with index.html when the frontend is built."""
    paths = {getattr(r, "path", None) for r in app.routes}
    enabled = app.openapi_url is not None
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert (path in paths) is enabled
