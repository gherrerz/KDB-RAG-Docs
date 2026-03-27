"""Integration-style tests for ingestion and query."""

from __future__ import annotations

from coderag.core.models import IngestionRequest, QueryRequest, SourceConfig
from coderag.core.service import RagApplicationService


def test_ingest_and_query_roundtrip() -> None:
    """Ensure ingestion builds indexes and query returns citations."""
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


def test_reset_all_clears_repositories() -> None:
    """Ensure reset operation clears persisted and in-memory retrieval data."""
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
