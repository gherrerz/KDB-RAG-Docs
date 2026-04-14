"""Tests for async ingestion endpoint toggle behavior."""

from __future__ import annotations

import hashlib
import time

from fastapi.testclient import TestClient

from coderag.api import server
from coderag.ingestion import index_chroma


def _looks_like_hhmmss(value: object) -> bool:
    """Validate expected HH:MM:SS format used in public time payloads."""
    if not isinstance(value, str):
        return False
    parts = value.split(":")
    if len(parts) != 3:
        return False
    return all(part.isdigit() and len(part) == 2 for part in parts)


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
        steps = job_payload.get("steps", [])
        assert isinstance(steps, list)
        if steps:
            first_step = steps[0]
            assert isinstance(first_step, dict)
            assert "elapsed_ms" not in first_step
            assert _looks_like_hhmmss(first_step.get("elapsed_hhmmss"))
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


def test_async_ingest_falls_back_to_local_when_redis_unavailable() -> None:
    """Fallback to local worker when USE_RQ=true but Redis is unavailable."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_enqueue_rq = server.enqueue_ingest_job
    original_enqueue_local = server.enqueue_local_ingest_job

    server.SETTINGS.use_rq = True
    server.enqueue_ingest_job = (  # type: ignore[assignment]
        lambda payload: (_ for _ in ()).throw(
            RuntimeError("Error 10061 connecting to localhost:6379")
        )
    )
    server.enqueue_local_ingest_job = (  # type: ignore[assignment]
        lambda payload: "local-job-1"
    )

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
        assert body["job_id"] == "local-job-1"
        assert "fallback" in str(body.get("message", "")).casefold()
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.enqueue_ingest_job = original_enqueue_rq  # type: ignore[assignment]
        server.enqueue_local_ingest_job = original_enqueue_local  # type: ignore[assignment]


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


def test_core_endpoints_degrade_cleanly_when_neo4j_disabled() -> None:
    """Keep standard ingest/query/reset operational when USE_NEO4J=false."""
    client = TestClient(server.app)
    original_neo4j = server.SETTINGS.use_neo4j
    original_embed = index_chroma.embed_text
    original_provider = server.SETTINGS.llm_provider
    original_openai_key = server.SETTINGS.openai_api_key

    server.SETTINGS.use_neo4j = False
    server.SETTINGS.llm_provider = "openai"
    server.SETTINGS.openai_api_key = "test-key"
    index_chroma.embed_text = _fake_embed_text

    try:
        payload = {
            "source": {
                "source_type": "folder",
                "local_path": "sample_data",
            }
        }
        ingest_response = client.post("/sources/ingest", json=payload)
        assert ingest_response.status_code == 200
        ingest_body = ingest_response.json()
        assert ingest_body["status"] == "completed"

        query_payload = {
            "question": "Who works on Project Atlas?",
            "force_fallback": True,
        }
        query_response = client.post("/query", json=query_payload)
        assert query_response.status_code == 200
        query_body = query_response.json()
        assert query_body["graph_paths"] == []
        assert query_body.get("diagnostics", {}).get("neo4j_enabled") is False

        readiness_response = client.get("/sources/ingest/readiness")
        assert readiness_response.status_code == 200
        readiness_body = readiness_response.json()
        assert readiness_body["ready"] is True
        assert readiness_body["checks"]["neo4j"]["required"] is False

        reset_response = client.post("/sources/reset", json={"confirm": True})
        assert reset_response.status_code == 200
        reset_body = reset_response.json()
        assert reset_body["neo4j_enabled"] is False
        assert reset_body["neo4j_edges_deleted"] == 0
    finally:
        server.SETTINGS.use_neo4j = original_neo4j
        server.SETTINGS.llm_provider = original_provider
        server.SETTINGS.openai_api_key = original_openai_key
        index_chroma.embed_text = original_embed


def test_get_job_prefers_rq_status_when_local_state_is_stale() -> None:
    """Expose live RQ status when local job row is still queued."""
    client = TestClient(server.app)

    original_use_rq = server.SETTINGS.use_rq
    original_get_job = server.SERVICE.get_job
    original_get_rq_job_status = server.get_rq_job_status

    server.SETTINGS.use_rq = True
    server.SERVICE.get_job = lambda job_id: {
        "job_id": job_id,
        "status": "queued",
        "message": "Ingestion job enqueued",
        "progress_pct": 0.0,
        "steps": [],
    }
    server.get_rq_job_status = lambda job_id: {
        "job_id": job_id,
        "status": "completed",
        "message": "completed",
        "progress_pct": 100.0,
    }

    try:
        response = client.get("/jobs/job-123")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["progress_pct"] == 100.0
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SERVICE.get_job = original_get_job
        server.get_rq_job_status = original_get_rq_job_status


def test_get_job_keeps_local_status_when_rq_is_unreachable() -> None:
    """Avoid 500 in /jobs when Redis is unavailable during RQ lookup."""
    client = TestClient(server.app)

    original_use_rq = server.SETTINGS.use_rq
    original_get_job = server.SERVICE.get_job
    original_get_rq_job_status = server.get_rq_job_status

    server.SETTINGS.use_rq = True
    server.SERVICE.get_job = lambda job_id: {
        "job_id": job_id,
        "status": "running",
        "message": "local async worker",
        "progress_pct": 10.0,
        "steps": [],
    }
    server.get_rq_job_status = (  # type: ignore[assignment]
        lambda job_id: (_ for _ in ()).throw(
            RuntimeError("Error 10061 connecting to localhost:6379")
        )
    )

    try:
        response = client.get("/jobs/local-job")
        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] == "local-job"
        assert body["status"] == "running"
        assert body["message"] == "local async worker"
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SERVICE.get_job = original_get_job
        server.get_rq_job_status = original_get_rq_job_status


def test_ingest_readiness_reports_sync_recommendation_when_async_unready() -> None:
    """Return recommendation=sync when required async dependencies fail."""
    client = TestClient(server.app)

    original_use_rq = server.SETTINGS.use_rq
    original_use_neo4j = server.SETTINGS.use_neo4j
    original_runtime_check = server._check_runtime_store
    original_neo4j_check = server._check_neo4j_runtime
    original_redis_check = server._check_redis_runtime
    original_worker_check = server._check_rq_worker_runtime

    server.SETTINGS.use_rq = True
    server.SETTINGS.use_neo4j = True
    server._check_runtime_store = lambda: {
        "required": True,
        "ok": True,
        "detail": "metadata store reachable",
    }
    server._check_neo4j_runtime = lambda: {
        "required": True,
        "ok": False,
        "detail": "Neo4j connectivity check failed.",
    }
    server._check_redis_runtime = lambda: {
        "required": True,
        "ok": True,
        "detail": "redis reachable",
    }
    server._check_rq_worker_runtime = lambda: {
        "required": True,
        "ok": True,
        "detail": "workers=1",
    }

    try:
        response = client.get("/sources/ingest/readiness")
        assert response.status_code == 200
        body = response.json()
        assert body["ready"] is False
        assert body["recommendation"] == "sync"
        assert body["checks"]["neo4j"]["ok"] is False
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SETTINGS.use_neo4j = original_use_neo4j
        server._check_runtime_store = original_runtime_check
        server._check_neo4j_runtime = original_neo4j_check
        server._check_redis_runtime = original_redis_check
        server._check_rq_worker_runtime = original_worker_check
