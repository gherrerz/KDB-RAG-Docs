"""Unit tests for QueryApplicationService extracted query logic."""

from __future__ import annotations

import pytest

from coderag.core import query_service as query_module
from coderag.core.models import ChunkRecord, GraphPath, QueryRequest
from coderag.core.query_service import QueryApplicationService


class _SettingsStub:
    """Minimal settings collaborator for query service tests."""

    retrieval_top_n = 8
    rerank_top_k = 5
    graph_hops = 2
    max_context_chars = 2000

    def resolve_llm_provider(self, override: str | None = None) -> str:
        return override or "openai"

    def resolve_answer_model(
        self,
        provider: str,
        override: str | None = None,
    ) -> str:
        return override or f"{provider}-answer"


class _StoreStub:
    """Minimal metadata store collaborator for query service tests."""

    def get_document_map(
        self,
        source_id: str | None = None,
    ) -> dict[str, dict[str, object]]:
        _ = source_id
        return {
            "doc-1": {
                "path_or_url": "sample_data/engineering.md",
            }
        }


class _VectorIndexStub:
    """Minimal vector collaborator exposing embedding metadata only."""

    embedding_provider = "openai"
    embedding_model = "text-embedding-3-small"


class _LlmStub:
    """LLM stub that records invocations and returns deterministic text."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def answer(
        self,
        *,
        question: str,
        chunks,
        context: str | None,
        provider: str,
        force_fallback: bool,
        strict: bool,
        doc_map,
    ) -> str:
        self.calls.append(
            {
                "question": question,
                "chunks": chunks,
                "context": context,
                "provider": provider,
                "force_fallback": force_fallback,
                "strict": strict,
                "doc_map": doc_map,
            }
        )
        return "answer-ok"


class _GraphStoreEnabledWithLegacySignature:
    """Graph stub with old expand_paths signature (no source_id kwarg)."""

    def is_enabled(self) -> bool:
        return True

    def expand_paths(
        self,
        *,
        query: str,
        hops: int,
        max_paths: int,
    ) -> list[GraphPath]:
        _ = (query, hops, max_paths)
        return [GraphPath(nodes=["A", "B"], relationships=["RELATES_TO"])]


class _GraphStoreDisabled:
    """Graph stub with graph integration disabled."""

    def is_enabled(self) -> bool:
        return False


def _sample_chunk() -> ChunkRecord:
    """Build one deterministic chunk reused across tests."""
    return ChunkRecord(
        chunk_id="chunk-1",
        document_id="doc-1",
        source_id="src-1",
        section_name="Overview",
        text="Project Atlas ownership and delivery details",
        start_ref=0,
        end_ref=42,
    )


def test_query_retrieval_only_skips_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retrieval-only mode should skip llm invocation and keep empty answer."""
    chunk = _sample_chunk()

    monkeypatch.setattr(
        query_module,
        "hybrid_search",
        lambda **_kwargs: [(chunk, 0.9, [])],
    )
    monkeypatch.setattr(
        query_module,
        "rerank_results",
        lambda _question, hits, top_k: hits[:top_k],
    )
    monkeypatch.setattr(
        query_module,
        "assemble_context",
        lambda **_kwargs: "context",
    )

    llm = _LlmStub()
    service = QueryApplicationService(
        store=_StoreStub(),  # type: ignore[arg-type]
        lexical_index=object(),  # type: ignore[arg-type]
        vector_index=_VectorIndexStub(),  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        graph_store=_GraphStoreDisabled(),  # type: ignore[arg-type]
        settings=_SettingsStub(),  # type: ignore[arg-type]
    )

    result = service.query(
        QueryRequest(
            question="Who owns Project Atlas?",
            include_llm_answer=False,
        )
    )

    assert result.answer == ""
    assert len(result.citations) == 1
    assert result.diagnostics["effective_mode"] == "retrieval_only"
    assert result.diagnostics["llm_invoked"] is False
    assert result.diagnostics["neo4j_enabled"] is False
    assert llm.calls == []


def test_query_uses_graph_legacy_signature_and_fallback_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graph expansion should support legacy signature and fallback provider mode."""
    chunk = _sample_chunk()

    monkeypatch.setattr(
        query_module,
        "hybrid_search",
        lambda **_kwargs: [(chunk, 0.8, [])],
    )
    monkeypatch.setattr(
        query_module,
        "rerank_results",
        lambda _question, hits, top_k: hits[:top_k],
    )
    monkeypatch.setattr(
        query_module,
        "assemble_context",
        lambda **_kwargs: "assembled-context",
    )

    llm = _LlmStub()
    service = QueryApplicationService(
        store=_StoreStub(),  # type: ignore[arg-type]
        lexical_index=object(),  # type: ignore[arg-type]
        vector_index=_VectorIndexStub(),  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        graph_store=_GraphStoreEnabledWithLegacySignature(),  # type: ignore[arg-type]
        settings=_SettingsStub(),  # type: ignore[arg-type]
    )

    result = service.query(
        QueryRequest(
            question="Summarize Atlas dependencies",
            force_fallback=True,
            include_llm_answer=True,
        )
    )

    assert result.answer == "answer-ok"
    assert result.diagnostics["neo4j_enabled"] is True
    assert result.diagnostics["graph_paths"] == 1
    assert result.diagnostics["llm_provider"] == "openai"
    assert result.diagnostics["llm_provider_effective"] == "local"
    assert result.diagnostics["llm_model_effective"] is None
    assert len(llm.calls) == 1
    assert llm.calls[0]["strict"] is False


def test_query_raises_runtime_error_from_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RuntimeError from llm should bubble with original message."""
    chunk = _sample_chunk()

    monkeypatch.setattr(
        query_module,
        "hybrid_search",
        lambda **_kwargs: [(chunk, 0.8, [])],
    )
    monkeypatch.setattr(
        query_module,
        "rerank_results",
        lambda _question, hits, top_k: hits[:top_k],
    )
    monkeypatch.setattr(
        query_module,
        "assemble_context",
        lambda **_kwargs: "ctx",
    )

    class _FailingLlm:
        def answer(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("llm down")

    service = QueryApplicationService(
        store=_StoreStub(),  # type: ignore[arg-type]
        lexical_index=object(),  # type: ignore[arg-type]
        vector_index=_VectorIndexStub(),  # type: ignore[arg-type]
        llm=_FailingLlm(),  # type: ignore[arg-type]
        graph_store=_GraphStoreDisabled(),  # type: ignore[arg-type]
        settings=_SettingsStub(),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="llm down"):
        service.query(QueryRequest(question="Any question"))