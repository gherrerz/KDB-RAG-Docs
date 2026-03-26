"""Integration-style tests for ingestion and query."""

from __future__ import annotations

from coderag.core.models import IngestionRequest, QueryRequest, SourceConfig
from coderag.core.service import RagApplicationService


def test_ingest_and_query_roundtrip() -> None:
    """Ensure ingestion builds indexes and query returns citations."""
    service = RagApplicationService()
    result = service.ingest(
        IngestionRequest(
            source=SourceConfig(
                source_type="folder",
                local_path="sample_data",
            )
        )
    )
    assert result["status"] == "completed"

    response = service.query(
        QueryRequest(question="Who works on Project Atlas?")
    )
    assert response.answer
    assert len(response.citations) > 0
