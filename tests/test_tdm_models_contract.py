"""Contract tests for additive TDM models and legacy compatibility."""

from __future__ import annotations

from coderag.core.models import QueryRequest, TdmIngestRequest, TdmQueryRequest


def test_legacy_query_request_contract_unchanged() -> None:
    """Keep existing QueryRequest payload fields valid without TDM params."""
    payload = QueryRequest(question="estado de servicio")

    dumped = payload.model_dump()
    assert "question" in dumped
    assert "include_llm_answer" in dumped
    assert "source_id" in dumped
    assert "hops" in dumped
    assert "llm_provider" in dumped
    assert "force_fallback" in dumped


def test_tdm_ingest_request_is_additive() -> None:
    """Create TDM ingest payload without affecting existing ingestion model."""
    request = TdmIngestRequest(
        source={
            "source_type": "folder",
            "local_path": "sample_data",
            "filters": {},
        }
    )
    assert request.include_masking_hints is True
    assert request.include_virtualization_hints is True


def test_tdm_query_request_defaults() -> None:
    """Ensure TDM query request has optional, safe defaults."""
    request = TdmQueryRequest(question="que tablas usa billing-api")

    assert request.source_id is None
    assert request.service_name is None
    assert request.table_name is None
    assert request.include_virtualization_preview is False
