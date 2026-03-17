from fastapi.testclient import TestClient
from backend.api.main import app


def test_health_check():
    with TestClient(app) as c:
        resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_openapi_schema_has_all_tags():
    with TestClient(app) as c:
        schema = c.get("/openapi.json").json()
    tag_names = {t["name"] for t in schema.get("tags", [])}
    for expected in ["experiments", "conditions", "results", "samples",
                     "chemicals", "analysis", "dashboard", "admin", "bulk-uploads"]:
        assert expected in tag_names, f"Missing tag: {expected}"
