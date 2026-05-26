"""Query-focused service extracted from the application facade."""

from __future__ import annotations

from datetime import UTC, datetime

from coderag.core.lexical_index import QueryLexicalIndex
from coderag.core.models import Evidence, GraphPath, QueryRequest, QueryResponse
from coderag.core.protocols import (
    GraphStoreProtocol,
    LlmClientProtocol,
    RuntimeStoreProtocol,
    VectorIndexProtocol,
)
from coderag.core.settings import Settings
from coderag.retrieval.context_assembler import assemble_context
from coderag.retrieval.hybrid_search import hybrid_search
from coderag.retrieval.reranker import rerank_results


class QueryApplicationService:
    """Own hybrid retrieval and answer grounding operations."""

    def __init__(
        self,
        *,
        store: RuntimeStoreProtocol,
        lexical_index: QueryLexicalIndex,
        vector_index: VectorIndexProtocol,
        llm: LlmClientProtocol,
        graph_store: GraphStoreProtocol,
        settings: Settings,
    ) -> None:
        """Build query service from current runtime collaborators."""
        self._store = store
        self._lexical_index = lexical_index
        self._vector_index = vector_index
        self._llm = llm
        self._graph_store = graph_store
        self._settings = settings

    def query(self, request: QueryRequest) -> QueryResponse:
        """Run hybrid retrieval, optional graph expansion, and LLM grounding."""
        top_n = self._settings.retrieval_top_n
        top_k = self._settings.rerank_top_k
        hops = (
            request.hops
            if request.hops is not None
            else self._settings.graph_hops
        )

        hits = hybrid_search(
            query=request.question,
            lexical_index=self._lexical_index,
            vector_index=self._vector_index,
            top_n=top_n,
            source_id=request.source_id,
            document_ids=request.document_ids,
        )
        reranked = rerank_results(request.question, hits, top_k=top_k)
        chunks = [item[0] for item in reranked]

        graph_paths: list[GraphPath] = []
        if self._graph_store.is_enabled():
            graph_paths = self._expand_graph_paths(request=request, hops=hops)

        doc_map = self._store.get_document_map(source_id=request.source_id)

        context = assemble_context(
            chunks=chunks,
            graph_paths=graph_paths,
            max_chars=self._settings.max_context_chars,
            document_map=doc_map,
        )

        requested_mode = (
            "with_llm"
            if request.include_llm_answer
            else "retrieval_only"
        )
        effective_mode = requested_mode

        provider = self._settings.resolve_llm_provider(request.llm_provider)
        answer = ""
        llm_invoked = False
        llm_provider_effective: str | None = None
        llm_model_effective: str | None = None
        llm_error: str | None = None

        if request.include_llm_answer:
            llm_invoked = True
            llm_provider_effective = (
                "local" if request.force_fallback else provider
            )
            if llm_provider_effective != "local":
                llm_model_effective = self._settings.resolve_answer_model(
                    llm_provider_effective
                )
            try:
                answer = self._llm.answer(
                    question=request.question,
                    chunks=chunks,
                    context=context,
                    provider=provider,
                    force_fallback=request.force_fallback,
                    strict=not request.force_fallback,
                    doc_map=doc_map,
                )
            except RuntimeError as exc:
                llm_error = str(exc)
                raise RuntimeError(llm_error) from exc
        else:
            effective_mode = "retrieval_only"

        citations: list[Evidence] = []
        for chunk, score, _parts in reranked:
            meta = doc_map.get(chunk.document_id, {})
            citations.append(
                Evidence(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    score=score,
                    snippet=chunk.text[:280],
                    path_or_url=meta.get("path_or_url", ""),
                    section_name=chunk.section_name,
                    start_ref=chunk.start_ref,
                    end_ref=chunk.end_ref,
                )
            )

        diagnostics = {
            "retrieval_candidates": len(hits),
            "reranked": len(reranked),
            "retrieval_unique_documents": len(
                {item[0].document_id for item in hits}
            ),
            "reranked_unique_documents": len(
                {chunk.document_id for chunk in chunks}
            ),
            "document_filter_count": len(request.document_ids),
            "graph_paths": len(graph_paths),
            "neo4j_enabled": self._graph_store.is_enabled(),
            "requested_mode": requested_mode,
            "effective_mode": effective_mode,
            "llm_invoked": llm_invoked,
            "llm_provider": provider,
            "llm_provider_effective": llm_provider_effective,
            "llm_model_effective": llm_model_effective,
            "llm_error": llm_error,
            "llm_context_includes_graph": bool(
                request.include_llm_answer and graph_paths
            ),
            "embedding_provider": self._vector_index.embedding_provider,
            "embedding_model": self._vector_index.embedding_model,
            "llm_fallback_forced": request.force_fallback,
            "lexical_backend": getattr(
                self._lexical_index,
                "backend_label",
                "lexical",
            ),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return QueryResponse(
            answer=answer,
            citations=citations,
            graph_paths=graph_paths,
            diagnostics=diagnostics,
        )

    def _expand_graph_paths(
        self,
        *,
        request: QueryRequest,
        hops: int,
    ) -> list[GraphPath]:
        """Expand graph paths with compatibility for legacy test doubles."""
        try:
            return self._graph_store.expand_paths(
                query=request.question,
                hops=max(1, hops),
                max_paths=6,
                source_id=request.source_id,
            )
        except TypeError:
            return self._graph_store.expand_paths(
                query=request.question,
                hops=max(1, hops),
                max_paths=6,
            )