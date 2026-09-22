"""The ICP-OES upload route installs the parser's fixed-column list at runtime.

``backend/services/icp_service.py`` imports ``ICP_FIXED_ELEMENT_FIELDS`` from
``frontend.config.variable_config`` -- a Streamlit-era module that no longer
exists -- so the route fabricates that module before importing the service.
Whatever list it installs is what production stores in fixed columns. From
2026-05 to 2026-09 that list was a 27-element literal, so ``ag ce k la na pb sc
th v s`` landed in ``all_elements`` only and their fixed columns stayed NULL on
every production row. The route now mirrors ``ICP_ELEMENTS``; this pins that.
"""
from __future__ import annotations

import io
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

from backend.api.schemas.results import ICP_ELEMENTS


def test_icp_oes_route_installs_canonical_fixed_column_list(client):
    mock_icp = MagicMock()
    mock_icp.parse_and_process_icp_file_ex.return_value = ([{"experiment_fk": 1}], [], [], 0)
    mock_icp.bulk_create_icp_results.return_value = ([MagicMock()], 0, [])
    fake_service_mod = MagicMock()
    fake_service_mod.ICPService = mock_icp

    # A bare module with NO attributes forces the route's `hasattr` branch to
    # run -- the tests/conftest.py MagicMock stub would short-circuit it.
    bare_stub = ModuleType("frontend.config.variable_config")

    with patch.dict(sys.modules, {
        "frontend": ModuleType("frontend"),
        "frontend.config": ModuleType("frontend.config"),
        "frontend.config.variable_config": bare_stub,
        "backend.services.icp_service": fake_service_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/icp-oes",
            files={"file": ("icp.csv", io.BytesIO(b"fake"), "text/csv")},
        )
        assert resp.status_code == 200
        installed = getattr(bare_stub, "ICP_FIXED_ELEMENT_FIELDS", None)

    assert installed == list(ICP_ELEMENTS)
    assert "ti" in installed
    # The ten columns the old 27-element literal omitted.
    for el in ("ag", "ce", "k", "la", "na", "pb", "sc", "th", "v", "s"):
        assert el in installed, el
