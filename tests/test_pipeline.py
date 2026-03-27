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
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"

    service = RagApplicationService()
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


def test_reset_all_clears_repositories() -> None:
    """Ensure reset operation clears persisted and in-memory retrieval data."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"

    service = RagApplicationService()
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
