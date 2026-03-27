"""Tests for async ingestion endpoint toggle behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient

from coderag.api import server


def test_async_ingest_disabled_returns_400() -> None:
    """Ensure async endpoint is guarded when USE_RQ is disabled."""
    client = TestClient(server.app)
    original = server.SETTINGS.use_rq
    server.SETTINGS.use_rq = False
    try:
        payload = {
            "source": {
                "source_type": "folder",
                "local_path": "sample_data",
            }
        }
        response = client.post("/sources/ingest/async", json=payload)
        assert response.status_code == 400
    finally:
        server.SETTINGS.use_rq = original


def test_reset_requires_confirmation() -> None:
    """Reject reset endpoint calls without explicit confirmation."""
    client = TestClient(server.app)
    response = client.post("/sources/reset", json={"confirm": False})
    assert response.status_code == 400


def test_reset_clears_ingested_data() -> None:
    """Ensure reset removes indexed content and leaves clean retrieval state."""
    client = TestClient(server.app)
    original_neo4j = server.SETTINGS.use_neo4j
    server.SETTINGS.use_neo4j = False
    try:
        payload = {
            "source": {
                "source_type": "folder",
                "local_path": "sample_data",
            }
        }
        ingest_response = client.post("/sources/ingest", json=payload)
        assert ingest_response.status_code == 200

        query_payload = {
            "question": "Who works on Project Atlas?",
            "force_fallback": True,
        }
        before_reset = client.post("/query", json=query_payload)
        assert before_reset.status_code == 200
        assert len(before_reset.json().get("citations", [])) > 0

        reset_response = client.post("/sources/reset", json={"confirm": True})
        assert reset_response.status_code == 200
        body = reset_response.json()
        assert body["status"] == "completed"
        assert body["deleted_documents"] >= 1
        assert body["deleted_chunks"] >= 1
        assert body["deleted_jobs"] >= 1

        after_reset = client.post("/query", json=query_payload)
        assert after_reset.status_code == 200
        assert len(after_reset.json().get("citations", [])) == 0
    finally:
        server.SETTINGS.use_neo4j = original_neo4j
