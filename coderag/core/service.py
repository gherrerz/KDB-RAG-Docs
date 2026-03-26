"""Application service orchestrating ingestion and query flows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Dict, List, Optional

from coderag.core.models import (
    Evidence,
    GraphPath,
    IngestionRequest,
    QueryRequest,
    QueryResponse,
)
from coderag.core.graph_store import GraphStore
from coderag.core.runtime import RUNTIME
from coderag.core.settings import SETTINGS
from coderag.ingestion.chunker import build_chunks
from coderag.ingestion.document_loader import load_documents
from coderag.ingestion.graph_builder import build_graph_edges
from coderag.ingestion.index_bm25 import BM25Index
from coderag.ingestion.index_chroma import LocalVectorIndex
from coderag.llm.providerlmm_client import ProviderLlmClient
from coderag.retrieval.context_assembler import assemble_context
from coderag.retrieval.graph_expand import build_graph, expand_paths
from coderag.retrieval.hybrid_search import hybrid_search
from coderag.retrieval.reranker import rerank_results


class RagApplicationService:
    """Coordinates indexing and retrieval pipeline for API and UI."""

    def __init__(self) -> None:
        self.store = RUNTIME.store
        self.bm25_index = BM25Index()
        self.vector_index = LocalVectorIndex(size=SETTINGS.embedding_size)
        self.llm = ProviderLlmClient()
        self.graph_store = GraphStore()
        self.rebuild_indexes()

    def rebuild_indexes(self, source_id: Optional[str] = None) -> None:
        """Rebuild in-memory indexes from persisted chunks."""
        chunks = self.store.list_chunks(source_id=source_id)
        self.bm25_index.rebuild(chunks)
        self.vector_index.rebuild(chunks)

    def ingest(self, request: IngestionRequest) -> Dict[str, str]:
        """Run full ingestion pipeline and persist generated artifacts."""
        job_id = uuid.uuid4().hex[:12]
        self.store.touch_job(job_id, "running", "Starting ingestion")

        documents = load_documents(request.source)
        if not documents:
            self.store.touch_job(
                job_id,
                "failed",
                "No documents found for configured source",
            )
            return {"job_id": job_id, "status": "failed"}

        source_id = documents[0].source_id
        chunks = []
        for doc in documents:
            self.store.upsert_document(doc)
            chunks.extend(build_chunks(doc))

        self.store.replace_chunks(source_id=source_id, chunks=chunks)
        edges = build_graph_edges(source_id=source_id, chunks=chunks)
        self.store.replace_graph_edges(source_id=source_id, edges=edges)
        self.graph_store.replace_edges(source_id=source_id, edges=edges)

        self.rebuild_indexes(source_id=source_id)
        self.store.touch_job(
            job_id,
            "completed",
            f"Indexed {len(documents)} docs and {len(chunks)} chunks",
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "source_id": source_id,
            "documents": str(len(documents)),
            "chunks": str(len(chunks)),
        }

    def get_job(self, job_id: str) -> Optional[Dict[str, str]]:
        """Retrieve job status by id."""
        job = self.store.get_job(job_id)
        if job is None:
            return None
        return {
            "job_id": job.job_id,
            "status": job.status,
            "message": job.message,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }

    def query(self, request: QueryRequest) -> QueryResponse:
        """Run hybrid retrieval + graph expansion + grounded answering."""
        top_n = SETTINGS.retrieval_top_n
        top_k = SETTINGS.rerank_top_k
        hops = (
            request.hops
            if request.hops is not None
            else SETTINGS.graph_hops
        )

        hits = hybrid_search(
            query=request.question,
            bm25_index=self.bm25_index,
            vector_index=self.vector_index,
            top_n=top_n,
        )
        reranked = rerank_results(request.question, hits, top_k=top_k)
        chunks = [item[0] for item in reranked]

        graph_paths: List[GraphPath] = self.graph_store.expand_paths(
            query=request.question,
            hops=max(1, hops),
            max_paths=6,
        )
        if not graph_paths:
            edges = self.store.list_graph_edges(source_id=request.source_id)
            graph = build_graph(edges)
            graph_paths = expand_paths(
                request.question,
                graph,
                hops=max(1, hops),
                max_paths=6,
            )

        _context = assemble_context(
            chunks=chunks,
            graph_paths=graph_paths,
            max_chars=SETTINGS.max_context_chars,
        )

        provider = SETTINGS.resolve_llm_provider(request.llm_provider)
        answer = self.llm.answer(
            request.question,
            chunks,
            provider=provider,
            force_fallback=request.force_fallback,
        )

        doc_map = self.store.get_document_map(source_id=request.source_id)
        citations: List[Evidence] = []
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
            "graph_paths": len(graph_paths),
            "llm_provider": provider,
            "llm_fallback_forced": request.force_fallback,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return QueryResponse(
            answer=answer,
            citations=citations,
            graph_paths=graph_paths,
            diagnostics=diagnostics,
        )


SERVICE = RagApplicationService()
