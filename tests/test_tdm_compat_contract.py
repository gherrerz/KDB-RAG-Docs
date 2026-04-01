"""Compatibility contract tests for legacy API behavior with TDM enabled."""

from __future__ import annotations

from fastapi.testclient import TestClient

from coderag.api import server


class _QueryResponseStub:
    """Minimal stub matching expected service query response contract."""

    def model_dump(self):
        return {
            "answer": "ok",
            "citations": [],
            "graph_paths": [],
            "diagnostics": {"mode": "legacy"},
        }


def test_legacy_endpoints_still_work_with_tdm_flags_enabled() -> None:
    """Keep core endpoints compatible even when TDM feature flags are on."""
    client = TestClient(server.app)

    original_enable_tdm = server.SETTINGS.enable_tdm
    original_masking = server.SETTINGS.tdm_enable_masking
    original_virtualization = server.SETTINGS.tdm_enable_virtualization
    original_synthetic = server.SETTINGS.tdm_enable_synthetic
    original_ingest = server.SERVICE.ingest
    original_query = server.SERVICE.query
    original_reset = server.SERVICE.reset_all

    server.SETTINGS.enable_tdm = True
    server.SETTINGS.tdm_enable_masking = True
    server.SETTINGS.tdm_enable_virtualization = True
    server.SETTINGS.tdm_enable_synthetic = True

    server.SERVICE.ingest = lambda request: {
        "job_id": "job-1",
        "status": "completed",
        "source_id": "src-1",
        "documents": "1",
        "chunks": "1",
        "steps": [],
        "progress_pct": 100.0,
        "metrics": {
            "elapsed_hhmmss": "00:00:00",
            "discovered_files": 1,
            "parsed_documents": 1,
            "skipped_empty": 0,
        },
    }
    server.SERVICE.query = lambda request: _QueryResponseStub()

    class _ResetResponseStub:
        def model_dump(self):
            return {
                "status": "completed",
                "message": "ok",
                "deleted_documents": 0,
                "deleted_chunks": 0,
                "deleted_graph_edges": 0,
                "deleted_jobs": 0,
                "neo4j_enabled": True,
                "neo4j_edges_deleted": 0,
            }

    server.SERVICE.reset_all = lambda: _ResetResponseStub()

    try:
        assert client.get("/health").status_code == 200

        ingest_response = client.post(
            "/sources/ingest",
            json={
                "source": {
                    "source_type": "folder",
                    "local_path": "sample_data",
                    "filters": {},
                }
            },
        )
        assert ingest_response.status_code == 200
        body = ingest_response.json()
        assert body["status"] == "completed"
        assert "metrics" in body

        query_response = client.post(
            "/query",
            json={
                "question": "estado de servicio",
                "include_llm_answer": False,
            },
        )
        assert query_response.status_code == 200
        query_body = query_response.json()
        assert "answer" in query_body
        assert "citations" in query_body
        assert "graph_paths" in query_body
        assert "diagnostics" in query_body

        reset_response = client.post("/sources/reset", json={"confirm": True})
        assert reset_response.status_code == 200
        assert reset_response.json().get("status") == "completed"
    finally:
        server.SETTINGS.enable_tdm = original_enable_tdm
        server.SETTINGS.tdm_enable_masking = original_masking
        server.SETTINGS.tdm_enable_virtualization = original_virtualization
        server.SETTINGS.tdm_enable_synthetic = original_synthetic
        server.SERVICE.ingest = original_ingest
        server.SERVICE.query = original_query
        server.SERVICE.reset_all = original_reset
