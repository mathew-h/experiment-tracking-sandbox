from database.models.analysis import PXRFReading
from database.models.xrd import XRDPhase


def test_list_pxrf_empty(client):
    resp = client.get("/api/analysis/pxrf")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_xrd_phases_by_experiment(client):
    resp = client.get("/api/analysis/xrd/NONEXISTENT_EXP")
    assert resp.status_code == 200
    assert resp.json() == []
