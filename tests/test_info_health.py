"""Contract tests for GET /info y GET /health (contrato de integración MCP Hexa)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from coderag.api import server
from coderag.api.mcp_server import MCP_SENSITIVE_FIELDS, MCP_SERVER_TYPE


def test_info_endpoint_returns_mcp_contract_shape() -> None:
    """GET /info expone metadata estática del contrato MCP Hexa, sin auth."""
    client = TestClient(server.app)

    response = client.get("/info")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == server.SETTINGS.mcp_server_name
    assert payload["server_type"] == MCP_SERVER_TYPE
    assert payload["sensitive_fields"] == MCP_SENSITIVE_FIELDS
    assert isinstance(payload["version"], str)
    assert isinstance(payload["description"], str)


def test_health_endpoint_returns_mcp_contract_shape() -> None:
    """GET /health expone status/name/version/uptime_s/dependencies, sin auth."""
    client = TestClient(server.app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"healthy", "degraded", "unhealthy"}
    assert payload["name"] == server.SETTINGS.mcp_server_name
    assert isinstance(payload["version"], str)
    assert isinstance(payload["uptime_s"], int)
    assert isinstance(payload["dependencies"], dict)
    for dependency in payload["dependencies"].values():
        assert dependency["status"] in {"healthy", "unhealthy"}
        assert isinstance(dependency["latency_ms"], (int, float))
