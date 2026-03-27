"""Integration-style tests for ingestion and query."""

from __future__ import annotations

import hashlib

from coderag.core.models import IngestionRequest, QueryRequest, SourceConfig
from coderag.core.service import RagApplicationService
from coderag.core.settings import SETTINGS
from coderag.ingestion import index_chroma


def _fake_embed_text(
    text: str,
    size: int = 256,
    provider: str | None = None,
    model: str | None = None,
) -> list[float]:
    """Deterministic embedding stub for tests without external API calls."""
    buckets = [0.0] * max(size, 8)
    prefix = f"{provider or 'openai'}:{model or 'model'}".encode("utf-8")
    for token in text.lower().split():
        digest = hashlib.sha256(prefix + b"::" + token.encode("utf-8")).digest()
        buckets[digest[0] % len(buckets)] += 1.0
    return buckets


def test_ingest_and_query_roundtrip() -> None:
    """Ensure ingestion builds indexes and query returns citations."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"

    service = RagApplicationService()
    service.graph_store.replace_edges = lambda source_id, edges: None
    service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    service.graph_store.clear_all_edges = lambda: 0
    service.graph_store.close = lambda: None
    try:
        result = service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path="sample_data",
                )
            )
        )
        assert result["status"] == "completed"
        assert isinstance(result.get("steps"), list)
        assert len(result.get("steps", [])) > 0
        assert isinstance(result.get("metrics"), dict)

        response = service.query(
            QueryRequest(question="Who works on Project Atlas?")
        )
        assert response.answer
        assert len(response.citations) > 0
    finally:
        service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password


def test_reset_all_clears_repositories() -> None:
    """Ensure reset operation clears persisted and in-memory retrieval data."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"

    service = RagApplicationService()
    service.graph_store.replace_edges = lambda source_id, edges: None
    service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    service.graph_store.clear_all_edges = lambda: 0
    service.graph_store.close = lambda: None
    try:
        service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path="sample_data",
                )
            )
        )

        before_reset = service.query(
            QueryRequest(
                question="Who works on Project Atlas?",
                force_fallback=True,
            )
        )
        assert len(before_reset.citations) > 0

        reset = service.reset_all()
        assert reset.status == "completed"
        assert reset.deleted_documents >= 1
        assert reset.deleted_chunks >= 1
        assert reset.deleted_jobs >= 1

        after_reset = service.query(
            QueryRequest(
                question="Who works on Project Atlas?",
                force_fallback=True,
            )
        )
        assert len(after_reset.citations) == 0
    finally:
        service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password


def test_ingest_job_status_includes_steps_and_progress() -> None:
    """Ensure job polling payload exposes persisted timeline details."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"

    service = RagApplicationService()
    service.graph_store.replace_edges = lambda source_id, edges: None
    service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    service.graph_store.clear_all_edges = lambda: 0
    service.graph_store.close = lambda: None
    try:
        result = service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path="sample_data",
                )
            )
        )
        job_id = str(result.get("job_id", ""))
        assert job_id

        job = service.get_job(job_id)
        assert isinstance(job, dict)
        assert float(job.get("progress_pct", 0.0)) == 100.0

        steps = job.get("steps")
        assert isinstance(steps, list)
        assert len(steps) > 0
        assert any(
            isinstance(step, dict)
            and step.get("name") == "ingestion_completed"
            for step in steps
        )
    finally:
        service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password
