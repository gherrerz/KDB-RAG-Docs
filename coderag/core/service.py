"""Application service orchestrating ingestion and query flows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from time import perf_counter
from typing import Dict, List, Optional

from coderag.core.models import (
    Evidence,
    GraphPath,
    IngestionRequest,
    QueryRequest,
    QueryResponse,
    ResetAllResponse,
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
        self.vector_index = LocalVectorIndex(
            size=SETTINGS.embedding_size,
            provider=SETTINGS.llm_provider,
            model=SETTINGS.llm_embedding,
        )
        self.llm = ProviderLlmClient()
        self.graph_store = GraphStore()
        self.rebuild_indexes()

    def rebuild_indexes(self, source_id: Optional[str] = None) -> None:
        """Rebuild in-memory indexes from persisted chunks."""
        chunks = self.store.list_chunks(source_id=source_id)
        self.bm25_index.rebuild(chunks)
        self.vector_index.rebuild(chunks)

    def close(self) -> None:
        """Release external resources held by the service."""
        self.graph_store.close()

    def reset_all(self) -> ResetAllResponse:
        """Reset all persisted and in-memory indexing artifacts."""
        deleted = self.store.clear_all_data()

        neo4j_enabled = self.graph_store.is_enabled()
        neo4j_edges_deleted = 0
        if neo4j_enabled:
            neo4j_edges_deleted = self.graph_store.clear_all_edges()

        # Rebuild both retrieval indexes from now-empty metadata tables.
        self.rebuild_indexes()

        return ResetAllResponse(
            status="completed",
            message=(
                "All repositories were cleared and indexes were reset."
            ),
            deleted_documents=deleted["deleted_documents"],
            deleted_chunks=deleted["deleted_chunks"],
            deleted_graph_edges=deleted["deleted_graph_edges"],
            deleted_jobs=deleted["deleted_jobs"],
            neo4j_enabled=neo4j_enabled,
            neo4j_edges_deleted=neo4j_edges_deleted,
        )

    def ingest(self, request: IngestionRequest) -> Dict[str, object]:
        """Run full ingestion pipeline and persist generated artifacts."""
        job_id = uuid.uuid4().hex[:12]
        self.store.touch_job(job_id, "running", "Starting ingestion")

        started_at = perf_counter()
        steps: List[Dict[str, object]] = []

        def _add_step(
            name: str,
            details: Dict[str, object],
            status: str = "ok",
        ) -> None:
            steps.append(
                {
                    "name": name,
                    "status": status,
                    "details": details,
                }
            )

        def _loader_progress(
            event: str,
            payload: Dict[str, object],
        ) -> None:
            _add_step(event, payload)

        documents, load_stats = load_documents(
            request.source,
            progress_callback=_loader_progress,
        )
        _add_step("load_documents", load_stats)
        if not documents:
            local_path = request.source.local_path or "<not-set>"
            failure_message = (
                "No supported documents found in source path "
                f"'{local_path}'. Supported: .md, .txt, .html, .htm, "
                ".pdf, .docx, .doc, .pptx, .xlsx"
            )
            self.store.touch_job(
                job_id,
                "failed",
                failure_message,
            )
            _add_step(
                "ingestion_failed",
                {"reason": failure_message},
                status="failed",
            )
            return {
                "job_id": job_id,
                "status": "failed",
                "message": failure_message,
                "steps": steps,
            }

        source_id = documents[0].source_id
        chunks = []
        total_characters = 0
        for doc in documents:
            self.store.upsert_document(doc)
            total_characters += len(doc.content)
            chunks.extend(build_chunks(doc))

        _add_step(
            "chunk_documents",
            {
                "documents": len(documents),
                "chunks": len(chunks),
                "total_characters": total_characters,
            },
        )

        self.store.replace_chunks(source_id=source_id, chunks=chunks)
        _add_step(
            "persist_chunks",
            {
                "source_id": source_id,
                "chunks": len(chunks),
            },
        )

        edges = build_graph_edges(source_id=source_id, chunks=chunks)
        _add_step(
            "build_graph_edges",
            {
                "edges": len(edges),
            },
        )

        self.store.replace_graph_edges(source_id=source_id, edges=edges)
        self.graph_store.replace_edges(source_id=source_id, edges=edges)
        _add_step(
            "persist_graph",
            {
                "edges": len(edges),
                "neo4j_enabled": self.graph_store.is_enabled(),
            },
        )

        self.rebuild_indexes(source_id=source_id)
        _add_step(
            "rebuild_indexes",
            {
                "source_id": source_id,
            },
        )

        elapsed_ms = round((perf_counter() - started_at) * 1000.0, 2)
        _add_step(
            "ingestion_completed",
            {
                "elapsed_ms": elapsed_ms,
            },
        )

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
            "steps": steps,
            "metrics": {
                "elapsed_ms": elapsed_ms,
                "discovered_files": load_stats.get("discovered_files", 0),
                "parsed_documents": load_stats.get("parsed_documents", 0),
                "skipped_empty": load_stats.get("skipped_empty", 0),
            },
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
            "embedding_provider": self.vector_index.embedding_provider,
            "embedding_model": self.vector_index.embedding_model,
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
