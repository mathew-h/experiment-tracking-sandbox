"""Bulk-upload API endpoint tests.

Covers:
- Response shape for all 12 upload endpoints (mocked parsers)
- Auth rejection (401) for each endpoint family
- Required-file validation (422) for file-required endpoints
- Template downloads: 200 for valid types, 404 for no-template types
- Endpoint-specific: master-results sync (no file), timepoint-modifications form field
"""
from __future__ import annotations

import io
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser


# ---------------------------------------------------------------------------
# Extra fixtures (unauth client for 401 tests)
# ---------------------------------------------------------------------------

# Re-export db_session and client from conftest implicitly via pytest fixture injection.


@pytest.fixture()
def unauth_client(db_session):
    """Client with DB override but verify_firebase_token raises 401."""

    def override_get_db():
        yield db_session

    async def no_auth():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_firebase_token] = no_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_XLSX = io.BytesIO(b"fake-excel-content")
_FILE_PARAM = {"file": ("test.xlsx", _FAKE_XLSX, "application/vnd.ms-excel")}


def _mock_upload_response(
    created=1, updated=0, skipped=0, errors=None, warnings=None, feedbacks=None
):
    return (created, updated, skipped, errors or [], feedbacks or [])


def _mock_upload_response_with_warnings(
    created=1, updated=0, skipped=0, errors=None, warnings=None, feedbacks=None
):
    return (created, updated, skipped, errors or [], warnings or [], {})


def _assert_upload_shape(body: dict):
    assert "created" in body
    assert "updated" in body
    assert "skipped" in body
    assert "errors" in body


# ---------------------------------------------------------------------------
# Existing endpoints — shape tests
# ---------------------------------------------------------------------------

def test_scalar_results_returns_upload_response_shape(client):
    mock_vc = MagicMock()
    mock_vc.SCALAR_RESULTS_TEMPLATE_HEADERS = []
    mock_svc = MagicMock()
    mock_svc.bulk_upsert_from_excel_ex.return_value = (1, 0, 0, [], [])

    fake_mod = MagicMock()
    fake_mod.ScalarResultsUploadService = mock_svc

    with patch.dict(sys.modules, {
        "frontend": MagicMock(),
        "frontend.config": MagicMock(),
        "frontend.config.variable_config": mock_vc,
        "backend.services.bulk_uploads.scalar_results": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/scalar-results",
            files={"file": ("test.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


def test_scalar_results_requires_file(client):
    resp = client.post("/api/bulk-uploads/scalar-results")
    assert resp.status_code == 422


def test_new_experiments_returns_upload_response_shape(client):
    mock_svc = MagicMock()
    mock_svc.bulk_upsert_from_excel.return_value = (2, 0, 0, [], [], {})
    fake_mod = MagicMock()
    fake_mod.NewExperimentsUploadService = mock_svc

    with patch.dict(sys.modules, {"backend.services.bulk_uploads.new_experiments": fake_mod}):
        resp = client.post(
            "/api/bulk-uploads/new-experiments",
            files={"file": ("test.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


def test_pxrf_returns_upload_response_shape(client):
    mock_vc = MagicMock()
    mock_pxrf = MagicMock()
    mock_pxrf.ingest_from_bytes.return_value = (3, 0, 0, [])
    fake_mod = MagicMock()
    fake_mod.PXRFUploadService = mock_pxrf

    with patch.dict(sys.modules, {
        "frontend": MagicMock(),
        "frontend.config": MagicMock(),
        "frontend.config.variable_config": mock_vc,
        "backend.services.bulk_uploads.pxrf_data": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/pxrf",
            files={"file": ("test.csv", io.BytesIO(b"fake"), "text/csv")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


def test_aeris_xrd_returns_upload_response_shape(client):
    mock_svc = MagicMock()
    mock_svc.bulk_upsert_from_excel.return_value = (5, 2, 0, [])
    fake_mod = MagicMock()
    fake_mod.AerisXRDUploadService = mock_svc

    with patch.dict(sys.modules, {"backend.services.bulk_uploads.aeris_xrd": fake_mod}):
        resp = client.post(
            "/api/bulk-uploads/aeris-xrd",
            files={"file": ("test.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


# ---------------------------------------------------------------------------
# New endpoints — shape tests
# ---------------------------------------------------------------------------

def test_master_results_upload_returns_response_shape(client):
    mock_svc = MagicMock()
    mock_svc.from_bytes.return_value = (3, 1, 0, [], [])
    fake_mod = MagicMock()
    fake_mod.MasterBulkUploadService = mock_svc

    with patch.dict(sys.modules, {"backend.services.bulk_uploads.master_bulk_upload": fake_mod}):
        resp = client.post(
            "/api/bulk-uploads/master-results",
            files={"file": ("master.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


def test_master_results_sync_no_file_returns_response_shape(client):
    """POST to master-results without a file triggers sync_from_path."""
    mock_svc = MagicMock()
    mock_svc.sync_from_path.return_value = (2, 0, 0, [], [])
    fake_mod = MagicMock()
    fake_mod.MasterBulkUploadService = mock_svc

    with patch.dict(sys.modules, {"backend.services.bulk_uploads.master_bulk_upload": fake_mod}):
        resp = client.post("/api/bulk-uploads/master-results")
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


def test_icp_oes_returns_upload_response_shape(client):
    stub_vc = MagicMock()
    stub_vc.ICP_FIXED_ELEMENT_FIELDS = ["fe", "si", "mg"]
    mock_icp = MagicMock()
    mock_icp.parse_and_process_icp_file.return_value = ([{"experiment_fk": 1}], [])
    mock_icp.bulk_create_icp_results.return_value = ([MagicMock()], [])
    fake_mod = MagicMock()
    fake_mod.ICPService = mock_icp

    with patch.dict(sys.modules, {
        "frontend": MagicMock(),
        "frontend.config": MagicMock(),
        "frontend.config.variable_config": stub_vc,
        "backend.services.icp_service": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/icp-oes",
            files={"file": ("icp.csv", io.BytesIO(b"fake"), "text/csv")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


def test_xrd_mineralogy_returns_upload_response_shape(client):
    mock_svc = MagicMock()
    mock_svc.upload.return_value = (4, 1, 0, [])
    fake_mod = MagicMock()
    fake_mod.XRDAutoDetectService = mock_svc

    with patch.dict(sys.modules, {"backend.services.bulk_uploads.xrd_upload": fake_mod}):
        resp = client.post(
            "/api/bulk-uploads/xrd-mineralogy",
            files={"file": ("xrd.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


def test_timepoint_modifications_returns_upload_response_shape(client):
    mock_svc = MagicMock()
    mock_svc.bulk_set_from_bytes.return_value = (3, 0, [], [])
    fake_mod = MagicMock()
    fake_mod.TimepointModificationsService = mock_svc

    with patch.dict(sys.modules, {
        "backend.services.bulk_uploads.timepoint_modifications": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/timepoint-modifications",
            files={"file": ("mods.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
            data={"overwrite_existing": "false"},
        )
    assert resp.status_code == 200
    body = resp.json()
    _assert_upload_shape(body)
    assert body["created"] == 0  # timepoint endpoint always returns created=0


def test_rock_inventory_returns_upload_response_shape(client):
    mock_svc = MagicMock()
    mock_svc.bulk_upsert_samples.return_value = (2, 1, 0, 0, [], [])
    fake_mod = MagicMock()
    fake_mod.RockInventoryService = mock_svc

    with patch.dict(sys.modules, {"backend.services.bulk_uploads.rock_inventory": fake_mod}):
        resp = client.post(
            "/api/bulk-uploads/rock-inventory",
            files={"file": ("rocks.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


def test_chemical_inventory_returns_upload_response_shape(client):
    mock_svc = MagicMock()
    mock_svc.bulk_upsert_from_excel.return_value = (5, 2, 0, [])
    fake_mod = MagicMock()
    fake_mod.ChemicalInventoryService = mock_svc

    with patch.dict(sys.modules, {
        "backend.services.bulk_uploads.chemical_inventory": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/chemical-inventory",
            files={"file": ("chems.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


def test_elemental_composition_returns_upload_response_shape(client):
    mock_svc = MagicMock()
    mock_svc.bulk_upsert_wide_from_excel.return_value = (10, 3, 0, [])
    fake_mod = MagicMock()
    fake_mod.ElementalCompositionService = mock_svc

    with patch.dict(sys.modules, {
        "backend.services.bulk_uploads.actlabs_titration_data": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/elemental-composition",
            files={"file": ("elem.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


def test_actlabs_rock_returns_upload_response_shape(client):
    mock_svc = MagicMock()
    mock_svc.import_excel.return_value = (6, 1, 0, [])
    fake_mod = MagicMock()
    fake_mod.ActlabsRockTitrationService = mock_svc

    with patch.dict(sys.modules, {
        "backend.services.bulk_uploads.actlabs_titration_data": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/actlabs-rock",
            files={"file": ("rock.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


def test_experiment_status_returns_upload_response_shape(client):
    mock_preview = MagicMock()
    mock_preview.errors = []
    mock_preview.to_ongoing = []
    mock_preview.to_completed = []
    mock_preview.missing_ids = []

    mock_svc = MagicMock()
    mock_svc.preview_status_changes_from_excel.return_value = mock_preview
    mock_svc.apply_status_changes.return_value = (0, 0, {}, [])
    fake_mod = MagicMock()
    fake_mod.ExperimentStatusService = mock_svc

    with patch.dict(sys.modules, {
        "backend.services.bulk_uploads.experiment_status": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/experiment-status",
            files={"file": ("status.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    _assert_upload_shape(resp.json())


# ---------------------------------------------------------------------------
# Auth rejection tests (sample of endpoints)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("endpoint", [
    "/api/bulk-uploads/scalar-results",
    "/api/bulk-uploads/new-experiments",
    "/api/bulk-uploads/xrd-mineralogy",
    "/api/bulk-uploads/timepoint-modifications",
    "/api/bulk-uploads/rock-inventory",
    "/api/bulk-uploads/chemical-inventory",
    "/api/bulk-uploads/elemental-composition",
    "/api/bulk-uploads/actlabs-rock",
    "/api/bulk-uploads/experiment-status",
    "/api/bulk-uploads/icp-oes",
    "/api/bulk-uploads/aeris-xrd",
])
def test_upload_endpoint_requires_auth(unauth_client, endpoint):
    """Every upload endpoint rejects requests without a valid auth token."""
    resp = unauth_client.post(
        endpoint,
        files={"file": ("test.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
    )
    assert resp.status_code == 401


def test_master_results_sync_requires_auth(unauth_client):
    resp = unauth_client.post("/api/bulk-uploads/master-results")
    assert resp.status_code == 401


def test_template_download_requires_auth(unauth_client):
    resp = unauth_client.get("/api/bulk-uploads/templates/scalar-results")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Required file validation (422)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("endpoint", [
    "/api/bulk-uploads/new-experiments",
    "/api/bulk-uploads/pxrf",
    "/api/bulk-uploads/aeris-xrd",
    "/api/bulk-uploads/xrd-mineralogy",
    "/api/bulk-uploads/rock-inventory",
    "/api/bulk-uploads/chemical-inventory",
    "/api/bulk-uploads/elemental-composition",
    "/api/bulk-uploads/actlabs-rock",
    "/api/bulk-uploads/experiment-status",
    "/api/bulk-uploads/icp-oes",
])
def test_upload_requires_file(client, endpoint):
    """Endpoints with required file return 422 when no file is supplied."""
    resp = client.post(endpoint)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Template download tests
# ---------------------------------------------------------------------------

_TEMPLATE_TYPES = [
    "scalar-results",
    "new-experiments",
    "rock-inventory",
    "chemical-inventory",
    "elemental-composition",
    "experiment-status",
    "timepoint-modifications",
    "xrd-mineralogy",
]

_NO_TEMPLATE_TYPES = [
    "master-results",
    "icp-oes",
    "aeris-xrd",
    "actlabs-rock",
    "pxrf",
]


@pytest.mark.parametrize("upload_type", _TEMPLATE_TYPES)
def test_template_download_returns_xlsx(client, upload_type):
    """Valid template types return 200 with an Excel content-type."""
    resp = client.get(f"/api/bulk-uploads/templates/{upload_type}")
    assert resp.status_code == 200, f"{upload_type}: {resp.text}"
    assert "spreadsheetml" in resp.headers.get("content-type", "")


@pytest.mark.parametrize("upload_type", _NO_TEMPLATE_TYPES)
def test_template_download_returns_404_for_no_template_types(client, upload_type):
    """Upload types without a template return 404."""
    resp = client.get(f"/api/bulk-uploads/templates/{upload_type}")
    assert resp.status_code == 404


def test_template_download_unknown_type_returns_404(client):
    resp = client.get("/api/bulk-uploads/templates/nonexistent-type")
    assert resp.status_code == 404


def test_xrd_template_experiment_mode(client):
    """XRD template accepts ?mode=experiment and returns an Excel file."""
    resp = client.get("/api/bulk-uploads/templates/xrd-mineralogy?mode=experiment")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers.get("content-type", "")
