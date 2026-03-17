import io
import sys
from unittest.mock import MagicMock, patch


def test_upload_scalar_returns_upload_response_shape(client):
    """Endpoint exists and returns correct response shape (mock parser)."""
    # Stub out the frontend.config dependency so lazy import succeeds
    mock_variable_config = MagicMock()
    mock_variable_config.SCALAR_RESULTS_TEMPLATE_HEADERS = []
    mock_scalar_service = MagicMock()
    mock_scalar_service.bulk_upsert_from_excel_ex.return_value = (0, 0, 0, ["No data in file"], [])

    fake_module = MagicMock()
    fake_module.ScalarResultsUploadService = mock_scalar_service

    with patch.dict(sys.modules, {
        "frontend": MagicMock(),
        "frontend.config": MagicMock(),
        "frontend.config.variable_config": mock_variable_config,
        "backend.services.bulk_uploads.scalar_results": fake_module,
    }):
        resp = client.post(
            "/api/bulk-uploads/scalar-results",
            files={"file": ("test.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "created" in body
    assert "errors" in body


def test_upload_requires_file(client):
    resp = client.post("/api/bulk-uploads/scalar-results")
    assert resp.status_code == 422
