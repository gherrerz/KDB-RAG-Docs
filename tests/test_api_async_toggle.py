"""Tests for async ingestion endpoint toggle behavior."""

from __future__ import annotations

import hashlib
import time

from fastapi.testclient import TestClient

from coderag.api import server
from coderag.ingestion import index_chroma


def _fake_embed_text(
    text: str,
    size: int = 256,
    provider: str | None = None,
    model: str | None = None,
) -> list[float]:
    """Return deterministic vectors for API tests without external calls."""
    buckets = [0.0] * max(size, 8)
    prefix = f"{provider or 'openai'}:{model or 'model'}".encode("utf-8")
    for token in text.lower().split():
        digest = hashlib.sha256(prefix + b"::" + token.encode("utf-8")).digest()
        buckets[digest[0] % len(buckets)] += 1.0
    return buckets


def test_async_ingest_uses_local_worker_when_rq_disabled() -> None:
    """Ensure async endpoint works via local worker when USE_RQ is disabled."""
    client = TestClient(server.app)
    original = server.SETTINGS.use_rq
    original_embed = index_chroma.embed_text
    original_provider = server.SETTINGS.llm_provider
    original_openai_key = server.SETTINGS.openai_api_key
    original_replace_edges = server.SERVICE.graph_store.replace_edges
    original_expand_paths = server.SERVICE.graph_store.expand_paths
    original_clear_all_edges = server.SERVICE.graph_store.clear_all_edges
    original_neo4j = server.SETTINGS.use_neo4j
    original_neo4j_uri = server.SETTINGS.neo4j_uri
    original_neo4j_user = server.SETTINGS.neo4j_user
    original_neo4j_password = server.SETTINGS.neo4j_password

    server.SETTINGS.use_rq = False
    server.SETTINGS.use_neo4j = True
    server.SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    server.SETTINGS.neo4j_user = "neo4j"
    server.SETTINGS.neo4j_password = "password"
    server.SETTINGS.llm_provider = "openai"
    server.SETTINGS.openai_api_key = "test-key"
    index_chroma.embed_text = _fake_embed_text
    server.SERVICE.graph_store.replace_edges = lambda source_id, edges: None
    server.SERVICE.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    server.SERVICE.graph_store.clear_all_edges = lambda: 0

    try:
        payload = {
            "source": {
                "source_type": "folder",
                "local_path": "sample_data",
            }
        }
        response = client.post("/sources/ingest/async", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "queued"
        job_id = body["job_id"]
        assert isinstance(job_id, str) and job_id

        deadline = time.monotonic() + 20.0
        seen_progress = False
        final_status = ""
        while time.monotonic() < deadline:
            job_response = client.get(f"/jobs/{job_id}")
            assert job_response.status_code == 200
            job_payload = job_response.json()
            final_status = str(job_payload.get("status", ""))
            if isinstance(job_payload.get("progress_pct"), (int, float)):
                if float(job_payload["progress_pct"]) > 0.0:
                    seen_progress = True
            if final_status in {"completed", "failed"}:
                break
            time.sleep(0.2)

        assert seen_progress
        assert final_status == "completed"
    finally:
        server.SETTINGS.use_rq = original
        server.SETTINGS.use_neo4j = original_neo4j
        server.SETTINGS.neo4j_uri = original_neo4j_uri
        server.SETTINGS.neo4j_user = original_neo4j_user
        server.SETTINGS.neo4j_password = original_neo4j_password
        server.SETTINGS.llm_provider = original_provider
        server.SETTINGS.openai_api_key = original_openai_key
        index_chroma.embed_text = original_embed
        server.SERVICE.graph_store.replace_edges = original_replace_edges
        server.SERVICE.graph_store.expand_paths = original_expand_paths
        server.SERVICE.graph_store.clear_all_edges = original_clear_all_edges


def test_reset_requires_confirmation() -> None:
    """Reject reset endpoint calls without explicit confirmation."""
    client = TestClient(server.app)
    response = client.post("/sources/reset", json={"confirm": False})
    assert response.status_code == 400


def test_reset_clears_ingested_data() -> None:
    """Ensure reset removes indexed content and leaves clean retrieval state."""
    client = TestClient(server.app)
    original_neo4j = server.SETTINGS.use_neo4j
    original_neo4j_uri = server.SETTINGS.neo4j_uri
    original_neo4j_user = server.SETTINGS.neo4j_user
    original_neo4j_password = server.SETTINGS.neo4j_password
    original_embed = index_chroma.embed_text
    original_provider = server.SETTINGS.llm_provider
    original_openai_key = server.SETTINGS.openai_api_key
    original_replace_edges = server.SERVICE.graph_store.replace_edges
    original_expand_paths = server.SERVICE.graph_store.expand_paths
    original_clear_all_edges = server.SERVICE.graph_store.clear_all_edges

    server.SETTINGS.use_neo4j = True
    server.SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    server.SETTINGS.neo4j_user = "neo4j"
    server.SETTINGS.neo4j_password = "password"
    server.SETTINGS.llm_provider = "openai"
    server.SETTINGS.openai_api_key = "test-key"
    index_chroma.embed_text = _fake_embed_text
    server.SERVICE.graph_store.replace_edges = lambda source_id, edges: None
    server.SERVICE.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    server.SERVICE.graph_store.clear_all_edges = lambda: 0
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
        server.SETTINGS.neo4j_uri = original_neo4j_uri
        server.SETTINGS.neo4j_user = original_neo4j_user
        server.SETTINGS.neo4j_password = original_neo4j_password
        server.SETTINGS.llm_provider = original_provider
        server.SETTINGS.openai_api_key = original_openai_key
        index_chroma.embed_text = original_embed
        server.SERVICE.graph_store.replace_edges = original_replace_edges
        server.SERVICE.graph_store.expand_paths = original_expand_paths
        server.SERVICE.graph_store.clear_all_edges = original_clear_all_edges
