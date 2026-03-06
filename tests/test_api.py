"""API tests for primary endpoints."""

from fastapi.testclient import TestClient

from coderag.api import server

app = server.app


def test_get_missing_job_returns_404() -> None:
    """Returns not found for unknown ingestion job id."""
    client = TestClient(app)
    response = client.get("/jobs/non-existent")
    assert response.status_code == 404


def test_admin_reset_returns_summary(monkeypatch) -> None:
    """Returns clear summary payload when reset operation succeeds."""

    def fake_reset_all_data() -> tuple[list[str], list[str]]:
        return ["BM25 en memoria", "Grafo Neo4j"], ["warning de prueba"]

    monkeypatch.setattr(server.jobs, "reset_all_data", fake_reset_all_data)
    client = TestClient(app)

    response = client.post("/admin/reset")
    assert response.status_code == 200

    payload = response.json()
    assert payload["message"] == "Limpieza total completada"
    assert "BM25 en memoria" in payload["cleared"]
    assert "warning de prueba" in payload["warnings"]
