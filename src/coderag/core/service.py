"""Application service orchestrating ingestion and query flows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from time import perf_counter
from typing import Callable, Dict, List, Optional

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
from coderag.retrieval.hybrid_search import hybrid_search
from coderag.retrieval.reranker import rerank_results


def _format_elapsed_hhmmss(elapsed_ms: float) -> str:
    """Convert elapsed milliseconds to HH:MM:SS for public payloads."""
    safe_ms = max(0.0, float(elapsed_ms))
    total_seconds = int(safe_ms // 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _as_public_timed_payload(payload: Dict[str, object]) -> Dict[str, object]:
    """Replace elapsed_ms fields with elapsed_hhmmss in outward payloads."""
    public_payload = dict(payload)

    raw_elapsed = public_payload.pop("elapsed_ms", None)
    if isinstance(raw_elapsed, (int, float)):
        public_payload["elapsed_hhmmss"] = _format_elapsed_hhmmss(
            float(raw_elapsed)
        )

    details = public_payload.get("details")
    if isinstance(details, dict):
        details_public = dict(details)
        details_elapsed = details_public.pop("elapsed_ms", None)
        if isinstance(details_elapsed, (int, float)):
            details_public["elapsed_hhmmss"] = _format_elapsed_hhmmss(
                float(details_elapsed)
            )
        public_payload["details"] = details_public

    return public_payload


class RagApplicationService:
    """Coordinates indexing and retrieval pipeline for API and UI."""

    def __init__(self) -> None:
        SETTINGS.require_chroma_enabled()
        SETTINGS.require_neo4j_enabled()
        self.store = RUNTIME.store
        self.bm25_index = BM25Index()
        self.vector_index = LocalVectorIndex(
            size=SETTINGS.embedding_size,
            provider=SETTINGS.llm_provider,
            model=SETTINGS.llm_embedding,
        )
        self.llm = ProviderLlmClient()
        self.graph_store = GraphStore()
        self._loaded_index_version = -1
        self.rebuild_indexes()

    def rebuild_indexes(self, source_id: Optional[str] = None) -> None:
        """Rebuild retrieval indexes from persisted chunks."""
        chunks = self.store.list_chunks(source_id=source_id)
        self.bm25_index.rebuild(chunks)
        self.vector_index.rebuild(chunks)
        self._loaded_index_version = self.store.get_index_version()

    def _refresh_indexes_after_external_update(self) -> None:
        """Refresh in-memory retrieval state after external ingestion.

        The async worker already persists vector updates into Chroma. During
        API-side refresh we only need to rebuild BM25 from SQLite chunks and
        update the loaded version marker. This avoids re-embedding all chunks
        on the first query after async ingestion.
        """
        chunks = self.store.list_chunks()
        self.bm25_index.rebuild(chunks)
        self._loaded_index_version = self.store.get_index_version()

    def _ensure_fresh_indexes(self) -> None:
        """Refresh indexes when a different process updated persisted state."""
        current_version = self.store.get_index_version()
        if current_version == self._loaded_index_version:
            return
        self._refresh_indexes_after_external_update()

    def close(self) -> None:
        """Release external resources held by the service."""
        self.graph_store.close()
        self.vector_index.close()

    def reset_all(self) -> ResetAllResponse:
        """Reset all persisted indexing artifacts across storage layers."""
        deleted = self.store.clear_all_data()
        self.vector_index.clear_all()

        neo4j_enabled = True
        neo4j_edges_deleted = self.graph_store.clear_all_edges()

        self.store.bump_index_version()

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

    def ingest(
        self,
        request: IngestionRequest,
        progress_callback: Optional[
            Callable[[Dict[str, object]], None]
        ] = None,
        job_id: Optional[str] = None,
    ) -> Dict[str, object]:
        """Run full ingestion pipeline and persist generated artifacts."""
        if not job_id:
            job_id = uuid.uuid4().hex[:12]
        self.store.touch_job(job_id, "running", "Starting ingestion")

        started_at = perf_counter()
        steps: List[Dict[str, object]] = []
        step_counter = 0

        def _emit_progress(payload: Dict[str, object]) -> None:
            """Push live progress snapshots when callback is provided."""
            if progress_callback is None:
                return
            progress_callback(payload)

        def _add_step(
            name: str,
            details: Dict[str, object],
            status: str = "ok",
            progress_pct: float | None = None,
        ) -> None:
            nonlocal step_counter
            step_counter += 1
            elapsed_ms = round((perf_counter() - started_at) * 1000.0, 2)
            step_payload: Dict[str, object] = {
                "name": name,
                "status": status,
                "details": details,
                "elapsed_hhmmss": _format_elapsed_hhmmss(elapsed_ms),
            }
            if progress_pct is not None:
                step_payload["progress_pct"] = round(progress_pct, 2)
            steps.append(step_payload)
            details_with_progress = dict(details)
            if progress_pct is not None:
                details_with_progress["progress_pct"] = round(progress_pct, 2)
            self.store.append_job_event(
                job_id=job_id,
                ordinal=step_counter,
                name=name,
                status=status,
                elapsed_ms=elapsed_ms,
                details=details_with_progress,
            )

            if status == "failed":
                self.store.touch_job(job_id, "failed", f"FAILED | {name}")
            elif name != "ingestion_completed":
                pct = progress_pct if progress_pct is not None else 0.0
                self.store.touch_job(
                    job_id,
                    "running",
                    f"{int(round(pct))}% | {name}",
                )

            _emit_progress(
                {
                    "job_id": job_id,
                    "status": (
                        "failed"
                        if status == "failed"
                        else (
                            "completed"
                            if name == "ingestion_completed"
                            else "running"
                        )
                    ),
                    "step": step_payload,
                    "steps": steps,
                }
            )

        def _loader_progress(
            event: str,
            payload: Dict[str, object],
        ) -> None:
            progress_pct = 10.0
            total = payload.get("total_files")
            processed = payload.get("processed_files")
            if isinstance(total, int) and total > 0 and isinstance(processed, int):
                progress_pct = 10.0 + (processed / total) * 20.0
            _add_step(event, payload, progress_pct=progress_pct)

        documents, load_stats = load_documents(
            request.source,
            progress_callback=_loader_progress,
        )
        _add_step("load_documents", load_stats, progress_pct=30.0)
        if not documents:
            local_path = request.source.local_path or "<not-set>"
            failure_reason = str(load_stats.get("failure_reason", ""))
            source_path = str(load_stats.get("source_path", local_path))
            supported_ext = ".md, .txt, .html, .htm, .pdf, .docx, .doc, "
            supported_ext += ".pptx, .xlsx"

            if failure_reason == "path_not_set":
                failure_message = (
                    "Source path is empty. Configure a local folder path "
                    "before ingestion."
                )
            elif failure_reason == "path_not_found":
                suggestions = load_stats.get("suggested_paths", [])
                suggestion_text = ""
                if isinstance(suggestions, list) and suggestions:
                    shown = "; ".join(str(item) for item in suggestions[:3])
                    suggestion_text = f" Nearby folders: {shown}."
                failure_message = (
                    f"Source path does not exist: '{source_path}'."
                    f"{suggestion_text}"
                )
            elif failure_reason == "path_not_directory":
                failure_message = (
                    f"Source path is not a directory: '{source_path}'."
                )
            else:
                scanned = int(load_stats.get("total_files_seen", 0))
                failure_message = (
                    "No supported documents found in source path "
                    f"'{source_path}'. Files scanned: {scanned}. "
                    f"Supported: {supported_ext}"
                )

            scan_errors = load_stats.get("scan_error_examples", [])
            if isinstance(scan_errors, list) and scan_errors:
                failure_message += f" Scan warning: {scan_errors[0]}"

            self.store.touch_job(
                job_id,
                "failed",
                failure_message,
            )
            _add_step(
                "ingestion_failed",
                {"reason": failure_message},
                status="failed",
                progress_pct=100.0,
            )
            return {
                "job_id": job_id,
                "status": "failed",
                "message": failure_message,
                "steps": steps,
                "progress_pct": 100.0,
            }

        source_id = documents[0].source_id
        chunks = []
        total_characters = 0
        total_documents = len(documents)
        for index, doc in enumerate(documents, start=1):
            total_characters += len(doc.content)
            chunks.extend(build_chunks(doc))
            if index == 1 or index % 10 == 0 or index == total_documents:
                _add_step(
                    "chunk_progress",
                    {
                        "processed_documents": index,
                        "total_documents": total_documents,
                        "generated_chunks": len(chunks),
                    },
                    progress_pct=30.0 + (index / total_documents) * 20.0,
                )

        persisted_documents = self.store.upsert_documents(documents)
        _add_step(
            "persist_documents",
            {
                "documents": persisted_documents,
                "source_id": source_id,
            },
            progress_pct=52.0,
        )

        _add_step(
            "chunk_documents",
            {
                "documents": len(documents),
                "chunks": len(chunks),
                "total_characters": total_characters,
            },
            progress_pct=55.0,
        )

        self.store.replace_chunks(source_id=source_id, chunks=chunks)
        _add_step(
            "persist_chunks",
            {
                "source_id": source_id,
                "chunks": len(chunks),
            },
            progress_pct=65.0,
        )

        edges = build_graph_edges(source_id=source_id, chunks=chunks)
        _add_step(
            "build_graph_edges",
            {
                "edges": len(edges),
            },
            progress_pct=75.0,
        )

        self.store.replace_graph_edges(source_id=source_id, edges=edges)
        graph_metrics = self.graph_store.replace_edges(
            source_id=source_id,
            edges=edges,
        )
        persist_graph_details: Dict[str, object] = {
            "edges": len(edges),
            "neo4j_enabled": self.graph_store.is_enabled(),
        }
        if isinstance(graph_metrics, dict):
            for key, value in graph_metrics.items():
                persist_graph_details[f"neo4j_{key}"] = value
        _add_step(
            "persist_graph",
            persist_graph_details,
            progress_pct=85.0,
        )

        self.rebuild_indexes(source_id=source_id)
        _add_step(
            "rebuild_indexes",
            {
                "source_id": source_id,
            },
            progress_pct=95.0,
        )

        elapsed_ms = round((perf_counter() - started_at) * 1000.0, 2)
        _add_step(
            "ingestion_completed",
            {
                "elapsed_hhmmss": _format_elapsed_hhmmss(elapsed_ms),
            },
            progress_pct=100.0,
        )

        self.store.touch_job(
            job_id,
            "completed",
            f"Indexed {len(documents)} docs and {len(chunks)} chunks",
        )
        self.store.bump_index_version()
        return {
            "job_id": job_id,
            "status": "completed",
            "source_id": source_id,
            "documents": str(len(documents)),
            "chunks": str(len(chunks)),
            "steps": steps,
            "progress_pct": 100.0,
            "metrics": {
                "elapsed_hhmmss": _format_elapsed_hhmmss(elapsed_ms),
                "discovered_files": load_stats.get("discovered_files", 0),
                "parsed_documents": load_stats.get("parsed_documents", 0),
                "skipped_empty": load_stats.get("skipped_empty", 0),
            },
        }

    def get_job(self, job_id: str) -> Optional[Dict[str, object]]:
        """Retrieve job status by id."""
        job = self.store.get_job(job_id)
        if job is None:
            return None
        events = self.store.list_job_events(job_id)
        progress_pct = 0.0
        if events:
            last_details = events[-1].get("details", {})
            if isinstance(last_details, dict):
                pct = last_details.get("progress_pct")
                if isinstance(pct, (int, float)):
                    progress_pct = float(pct)
        if job.status == "completed":
            progress_pct = 100.0

        public_events = [_as_public_timed_payload(event) for event in events]

        return {
            "job_id": job.job_id,
            "status": job.status,
            "message": job.message,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "progress_pct": round(progress_pct, 2),
            "steps": public_events,
        }

    def query(self, request: QueryRequest) -> QueryResponse:
        """Run hybrid retrieval + graph expansion + grounded answering."""
        try:
            self._ensure_fresh_indexes()
        except Exception as exc:
            raise RuntimeError(
                "Failed to refresh retrieval indexes after async ingestion."
            ) from exc

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
            source_id=request.source_id,
        )
        reranked = rerank_results(request.question, hits, top_k=top_k)
        chunks = [item[0] for item in reranked]

        graph_paths: List[GraphPath] = self.graph_store.expand_paths(
            query=request.question,
            hops=max(1, hops),
            max_paths=6,
        )

        context = assemble_context(
            chunks=chunks,
            graph_paths=graph_paths,
            max_chars=SETTINGS.max_context_chars,
        )

        requested_mode = (
            "with_llm"
            if request.include_llm_answer
            else "retrieval_only"
        )
        effective_mode = requested_mode

        provider = SETTINGS.resolve_llm_provider(request.llm_provider)
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
                llm_model_effective = SETTINGS.resolve_answer_model(
                    llm_provider_effective
                )
            try:
                answer = self.llm.answer(
                    question=request.question,
                    chunks=chunks,
                    context=context,
                    provider=provider,
                    force_fallback=request.force_fallback,
                    strict=not request.force_fallback,
                )
            except RuntimeError as exc:
                llm_error = str(exc)
                raise RuntimeError(llm_error) from exc
        else:
            effective_mode = "retrieval_only"

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
