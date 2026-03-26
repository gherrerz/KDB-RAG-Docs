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
