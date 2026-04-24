"""Application service orchestrating ingestion and query flows."""

from __future__ import annotations

import os
import shutil
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Callable, Dict, List, Optional

from coderag.core.models import (
    DeleteDocumentResponse,
    DocumentRecord,
    DocumentCatalogEntry,
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
from coderag.ingestion.tdm_graph_builder import build_tdm_typed_edges
from coderag.ingestion.graph_builder import build_graph_edges
from coderag.ingestion.index_bm25 import BM25Index
from coderag.ingestion.index_chroma import LocalVectorIndex
from coderag.ingestion.tdm_ingestion import ingest_tdm_assets
from coderag.llm.providerlmm_client import ProviderLlmClient
from coderag.retrieval.context_assembler import assemble_context
from coderag.retrieval.hybrid_search import hybrid_search
from coderag.retrieval.reranker import rerank_results
from coderag.tdm.masking_engine import apply_masking_rules_to_row
from coderag.tdm.synthetic_planner import build_synthetic_profile_plan
from coderag.tdm.virtualization_export import build_virtualization_templates


REPO_ROOT = Path(__file__).resolve().parents[3]


def _on_rmtree_error(func, path, _exc_info) -> None:
    """Retry file removal after clearing read-only attributes on Windows."""
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    func(path)


def _clear_local_staging_mirror(data_dir: Path) -> tuple[int, list[str]]:
    """Delete staged ingestion mirror entries and keep the root folder."""
    staging_dir = data_dir / "ingestion_staging"
    warnings: list[str] = []
    deleted_entries = 0
    staging_dir.mkdir(parents=True, exist_ok=True)

    for entry in list(staging_dir.iterdir()):
        try:
            if entry.is_dir():
                shutil.rmtree(entry, onerror=_on_rmtree_error)
            else:
                entry.unlink()
            deleted_entries += 1
        except PermissionError as exc:
            warnings.append(
                f"Could not fully remove staging entry '{entry}': {exc}"
            )
        except OSError as exc:
            warnings.append(
                f"Could not remove staging entry '{entry}': {exc}"
            )

    return deleted_entries, warnings


def _delete_staged_document_copy(
    data_dir: Path,
    path_or_url: str,
) -> tuple[bool, Optional[str]]:
    """Delete one staged document copy and prune empty parent folders."""
    if not path_or_url.strip():
        return False, None

    staging_dir = (data_dir / "ingestion_staging").resolve(strict=False)
    candidate = Path(path_or_url).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve(strict=False)
    else:
        candidate = candidate.resolve(strict=False)

    try:
        candidate.relative_to(staging_dir)
    except ValueError:
        return False, None

    if not candidate.exists() or candidate.is_dir():
        return False, None

    try:
        candidate.unlink()
    except PermissionError as exc:
        return False, f"Could not fully remove staged document '{candidate}': {exc}"
    except OSError as exc:
        return False, f"Could not remove staged document '{candidate}': {exc}"

    parent = candidate.parent
    while parent != staging_dir:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent

    return True, None


def _document_dedup_key(document: DocumentRecord) -> tuple[str, str]:
    """Normalize the document identity used by pre-ingest deduplication."""
    return (
        document.title.strip().casefold(),
        document.content_type.strip().casefold(),
    )


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

    def _rebuild_bm25_from_store(self) -> None:
        """Refresh BM25 from all persisted chunks without re-embedding all data."""
        self.bm25_index.rebuild(self.store.list_chunks())
        self._loaded_index_version = self.store.get_index_version()

    def _sync_graph_for_source(
        self,
        source_id: str,
    ) -> tuple[list[tuple[str, str, str, str]], Dict[str, object]]:
        """Recompute persisted graph state for one source from current chunks."""
        chunks = self.store.list_chunks(source_id=source_id)
        edges = build_graph_edges(source_id=source_id, chunks=chunks)
        self.store.replace_graph_edges(source_id=source_id, edges=edges)

        if not self.is_graph_enabled():
            return edges, {"neo4j_enabled": False, "skipped": True}

        graph_metrics = self.graph_store.replace_edges(
            source_id=source_id,
            edges=edges,
        )
        if isinstance(graph_metrics, dict):
            return edges, graph_metrics
        return edges, {}

    def _delete_persisted_documents(
        self,
        documents: List[DocumentCatalogEntry],
        skip_reindex_source_ids: Optional[set[str]] = None,
    ) -> Dict[str, object]:
        """Delete persisted documents across metadata, vector, staging, and graph."""
        if not documents:
            return {
                "matched_documents": 0,
                "deleted_documents": 0,
                "deleted_chunks": 0,
                "deleted_staging_files": 0,
                "reindexed_sources": 0,
                "replaced_document_ids": [],
                "replaced_paths": [],
                "staging_warnings": [],
            }

        deleted_documents = 0
        deleted_chunks = 0
        deleted_staging_files = 0
        affected_source_ids: set[str] = set()
        staging_warnings: list[str] = []

        for duplicate in documents:
            deleted_chunks += self.store.delete_chunks_by_document_id(
                duplicate.document_id
            )
            deleted_documents += self.store.delete_document_by_id(
                duplicate.document_id
            )
            self.vector_index.delete_document(duplicate.document_id)
            deleted_file, warning = _delete_staged_document_copy(
                SETTINGS.data_dir,
                duplicate.path_or_url,
            )
            if deleted_file:
                deleted_staging_files += 1
            if warning:
                staging_warnings.append(warning)
            affected_source_ids.add(duplicate.source_id)

        skipped_source_ids = skip_reindex_source_ids or set()
        rebuilt_source_ids = sorted(affected_source_ids - skipped_source_ids)
        for source_id in rebuilt_source_ids:
            self._sync_graph_for_source(source_id)

        self.store.bump_index_version()
        self._rebuild_bm25_from_store()

        return {
            "matched_documents": len(documents),
            "deleted_documents": deleted_documents,
            "deleted_chunks": deleted_chunks,
            "deleted_staging_files": deleted_staging_files,
            "reindexed_sources": len(rebuilt_source_ids),
            "replaced_document_ids": sorted(
                duplicate.document_id for duplicate in documents
            ),
            "replaced_paths": sorted(
                {
                    duplicate.path_or_url
                    for duplicate in documents
                    if duplicate.path_or_url.strip()
                }
            ),
            "staging_warnings": staging_warnings,
        }

    def _deduplicate_documents_before_ingest(
        self,
        documents,
        current_source_id: str,
    ) -> Dict[str, object]:
        """Remove older ingested documents that match title + content type."""
        duplicates_by_id: dict[str, DocumentCatalogEntry] = {}
        for document in documents:
            matches = self.store.find_documents_by_title_and_content_type(
                title=document.title,
                content_type=document.content_type,
            )
            for match in matches:
                duplicates_by_id.setdefault(match.document_id, match)

        if not duplicates_by_id:
            return self._delete_persisted_documents([])

        return self._delete_persisted_documents(
            list(duplicates_by_id.values()),
            skip_reindex_source_ids={current_source_id},
        )

    def _collapse_incoming_duplicate_documents(
        self,
        documents: List[DocumentRecord],
    ) -> tuple[List[DocumentRecord], Dict[str, object]]:
        """Collapse duplicate documents within one ingestion batch."""
        kept_by_key: dict[tuple[str, str], DocumentRecord] = {}
        skipped_documents: list[str] = []

        for document in documents:
            key = _document_dedup_key(document)
            previous = kept_by_key.get(key)
            if previous is not None:
                skipped_documents.append(previous.document_id)
            kept_by_key[key] = document

        collapsed = list(kept_by_key.values())
        return collapsed, {
            "input_documents": len(documents),
            "kept_documents": len(collapsed),
            "skipped_documents": len(skipped_documents),
            "skipped_document_ids": skipped_documents,
            "kept_document_ids": [document.document_id for document in collapsed],
            "kept_paths": [document.path_or_url for document in collapsed],
            "resolution": "keep_last_by_sorted_path",
        }

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

    def is_graph_enabled(self) -> bool:
        """Return whether graph-backed runtime features are enabled."""
        return self.graph_store.is_enabled()

    def is_tdm_graph_enabled(self) -> bool:
        """Return whether TDM can use graph-backed capabilities."""
        return bool(SETTINGS.enable_tdm and self.is_graph_enabled())

    def _ensure_tdm_graph_enabled(self) -> None:
        """Require both TDM feature flag and Neo4j graph runtime."""
        self._ensure_tdm_enabled()
        if not self.is_graph_enabled():
            raise RuntimeError(
                "TDM is unavailable because USE_NEO4J=false. "
                "Enable Neo4j graph runtime to use TDM endpoints."
            )

    def reset_all(self) -> ResetAllResponse:
        """Reset all persisted indexing artifacts across storage layers."""
        deleted = self.store.clear_all_data()
        self.vector_index.clear_all()
        deleted_staging_entries, staging_warnings = _clear_local_staging_mirror(
            SETTINGS.data_dir
        )

        neo4j_enabled = self.is_graph_enabled()
        neo4j_edges_deleted = self.graph_store.clear_all_edges()

        self.store.bump_index_version()

        # Rebuild both retrieval indexes from now-empty metadata tables.
        self.rebuild_indexes()

        return ResetAllResponse(
            status="completed",
            message=(
                "All repositories were cleared, indexes were reset, and "
                f"{deleted_staging_entries} staging mirror entries were "
                "removed."
                + (
                    " Some staging entries could not be removed due to file "
                    "locks."
                    if staging_warnings
                    else ""
                )
            ),
            deleted_documents=deleted["deleted_documents"],
            deleted_chunks=deleted["deleted_chunks"],
            deleted_graph_edges=deleted["deleted_graph_edges"],
            deleted_jobs=deleted["deleted_jobs"],
            neo4j_enabled=neo4j_enabled,
            neo4j_edges_deleted=neo4j_edges_deleted,
        )

    def delete_document(self, document_id: str) -> DeleteDocumentResponse:
        """Delete one persisted document and refresh dependent indexes."""
        document = self.store.get_document_by_id(document_id)
        if document is None:
            raise KeyError(document_id)

        deleted = self._delete_persisted_documents([document])

        return DeleteDocumentResponse(
            status="completed",
            message=(
                "Document was deleted from persisted metadata, vector index, "
                "and managed staging mirror."
            ),
            document_id=document.document_id,
            source_id=document.source_id,
            deleted_documents=int(deleted["deleted_documents"]),
            deleted_chunks=int(deleted["deleted_chunks"]),
            deleted_staging_files=int(deleted["deleted_staging_files"]),
            reindexed_sources=int(deleted["reindexed_sources"]),
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

        documents, incoming_dedup_stats = (
            self._collapse_incoming_duplicate_documents(documents)
        )
        _add_step(
            "deduplicate_incoming_batch",
            incoming_dedup_stats,
            progress_pct=35.0,
        )

        source_id = documents[0].source_id
        dedup_stats = self._deduplicate_documents_before_ingest(
            documents=documents,
            current_source_id=source_id,
        )
        _add_step(
            "deduplicate_documents",
            dedup_stats,
            progress_pct=42.0,
        )

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
                    progress_pct=42.0 + (index / total_documents) * 13.0,
                )

        persisted_documents = self.store.upsert_documents(documents)
        _add_step(
            "persist_documents",
            {
                "documents": persisted_documents,
                "source_id": source_id,
            },
            progress_pct=58.0,
        )

        _add_step(
            "chunk_documents",
            {
                "documents": len(documents),
                "chunks": len(chunks),
                "total_characters": total_characters,
            },
            progress_pct=62.0,
        )

        self.store.replace_chunks(source_id=source_id, chunks=chunks)
        _add_step(
            "persist_chunks",
            {
                "source_id": source_id,
                "chunks": len(chunks),
            },
            progress_pct=70.0,
        )

        edges = build_graph_edges(source_id=source_id, chunks=chunks)
        _add_step(
            "build_graph_edges",
            {
                "edges": len(edges),
            },
            progress_pct=78.0,
        )

        self.store.replace_graph_edges(source_id=source_id, edges=edges)
        if self.is_graph_enabled():
            graph_metrics = self.graph_store.replace_edges(
                source_id=source_id,
                edges=edges,
            )
            persist_graph_details: Dict[str, object] = {
                "edges": len(edges),
                "neo4j_enabled": True,
            }
            if isinstance(graph_metrics, dict):
                for key, value in graph_metrics.items():
                    persist_graph_details[f"neo4j_{key}"] = value
        else:
            persist_graph_details = {
                "edges": len(edges),
                "neo4j_enabled": False,
                "skipped": True,
                "reason": "USE_NEO4J=false",
            }
        _add_step(
            "persist_graph",
            persist_graph_details,
            progress_pct=86.0,
        )

        self._rebuild_bm25_from_store()
        self.vector_index.rebuild(chunks)
        self._loaded_index_version = self.store.get_index_version()
        _add_step(
            "rebuild_indexes",
            {
                "source_id": source_id,
                "bm25_scope": "global",
                "vector_scope": "source",
            },
            progress_pct=95.0,
        )

        elapsed_ms = round((perf_counter() - started_at) * 1000.0, 2)
        deduplication_summary = {
            "incoming_batch": incoming_dedup_stats,
            "replaced_existing": dedup_stats,
        }
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
                "incoming_duplicates_skipped": incoming_dedup_stats.get(
                    "skipped_documents", 0
                ),
                "existing_duplicates_replaced": dedup_stats.get(
                    "deleted_documents", 0
                ),
                "staging_files_deleted": dedup_stats.get(
                    "deleted_staging_files", 0
                ),
            },
            "deduplication": deduplication_summary,
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

    def list_documents(
        self,
        source_id: Optional[str] = None,
    ) -> List[DocumentCatalogEntry]:
        """Return document catalog entries for optional source filter."""
        return self.store.list_documents(source_id=source_id)

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
            document_ids=request.document_ids,
        )
        reranked = rerank_results(request.question, hits, top_k=top_k)
        chunks = [item[0] for item in reranked]

        graph_paths: List[GraphPath] = []
        if self.is_graph_enabled():
            try:
                graph_paths = self.graph_store.expand_paths(
                    query=request.question,
                    hops=max(1, hops),
                    max_paths=6,
                    source_id=request.source_id,
                )
            except TypeError:
                # Backward-compatibility for test doubles with old signature.
                graph_paths = self.graph_store.expand_paths(
                    query=request.question,
                    hops=max(1, hops),
                    max_paths=6,
                )

        doc_map = self.store.get_document_map(source_id=request.source_id)

        context = assemble_context(
            chunks=chunks,
            graph_paths=graph_paths,
            max_chars=SETTINGS.max_context_chars,
            document_map=doc_map,
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
                    doc_map=doc_map,
                )
            except RuntimeError as exc:
                llm_error = str(exc)
                raise RuntimeError(llm_error) from exc
        else:
            effective_mode = "retrieval_only"

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
            "retrieval_unique_documents": len(
                {item[0].document_id for item in hits}
            ),
            "reranked_unique_documents": len(
                {chunk.document_id for chunk in chunks}
            ),
            "document_filter_count": len(request.document_ids),
            "graph_paths": len(graph_paths),
            "neo4j_enabled": self.is_graph_enabled(),
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

    def ingest_tdm_assets(self, request: IngestionRequest) -> Dict[str, object]:
        """Ingest TDM metadata assets into additive catalog tables."""
        self._ensure_tdm_graph_enabled()

        summary = ingest_tdm_assets(
            source=request.source,
            store=self.store,
        )
        source_id = str(summary.get("source_id", ""))
        if source_id:
            schemas = self.store.list_tdm_schemas(source_id=source_id)
            tables = self.store.list_tdm_tables(source_id=source_id)
            columns = self.store.list_tdm_columns(source_id=source_id)
            mappings = self.store.list_tdm_service_mappings(source_id=source_id)
            masking_rules = self.store.list_tdm_masking_rules(
                source_id=source_id,
            )
            typed_edges = build_tdm_typed_edges(
                source_id=source_id,
                schemas=schemas,
                tables=tables,
                columns=columns,
                mappings=mappings,
                masking_rules=masking_rules,
            )
            graph_metrics = self.graph_store.replace_tdm_edges(
                source_id=source_id,
                typed_edges=typed_edges,
            )
            summary["tdm_graph_edges"] = len(typed_edges)
            summary["tdm_graph_batches"] = int(
                graph_metrics.get("batches_written", 0)
            )

        return {
            "status": "completed",
            **summary,
        }

    @staticmethod
    def _ensure_tdm_enabled() -> None:
        """Guard additive TDM routes behind explicit feature flags."""
        if not SETTINGS.enable_tdm:
            raise RuntimeError(
                "TDM endpoints are disabled. Set ENABLE_TDM=true to enable."
            )

    def query_tdm(self, request: "TdmQueryRequest") -> "TdmQueryResponse":
        """Run TDM catalog query mode for agent-facing workflows."""
        self._ensure_tdm_graph_enabled()

        tables = self.store.list_tdm_tables(source_id=request.source_id)
        columns = self.store.list_tdm_columns(source_id=request.source_id)
        mappings = self.store.list_tdm_service_mappings(
            source_id=request.source_id,
        )
        masking_rules = self.store.list_tdm_masking_rules(
            source_id=request.source_id,
        )

        findings: List[Dict[str, object]] = []
        if request.service_name:
            findings.extend(
                item
                for item in mappings
                if str(item.get("service_name", "")).casefold()
                == request.service_name.casefold()
            )
        if request.table_name:
            matching_tables = [
                table
                for table in tables
                if str(table.get("table_name", "")).casefold()
                == request.table_name.casefold()
            ]
            findings.extend(matching_tables)

            matched_table_ids = {
                str(table.get("table_id"))
                for table in matching_tables
                if table.get("table_id")
            }
            findings.extend(
                column
                for column in columns
                if str(column.get("table_id", "")) in matched_table_ids
            )

        if not findings:
            findings = mappings[:10]

        if SETTINGS.tdm_enable_masking and findings:
            masking_rules_by_column: Dict[str, List[Dict[str, object]]] = {}
            for rule in masking_rules:
                column_id = str(rule.get("column_id") or "").strip()
                if not column_id:
                    continue
                masking_rules_by_column.setdefault(column_id, []).append(rule)

            for item in findings:
                if not isinstance(item, dict):
                    continue
                column_id = str(item.get("column_id") or "").strip()
                if not column_id:
                    continue
                rules = masking_rules_by_column.get(column_id, [])
                if not rules:
                    continue
                preview_input = {
                    str(item.get("column_name") or "column"):
                    f"sample_{item.get('column_name', 'value')}"
                }
                preview_rules = [
                    {
                        "column_name": str(item.get("column_name") or ""),
                        "policy_type": str(rule.get("policy_type") or "mask"),
                    }
                    for rule in rules
                ]
                item["masking_preview"] = apply_masking_rules_to_row(
                    row=preview_input,
                    rules=preview_rules,
                    seed="tdm-preview",
                )

        tdm_paths = self.graph_store.expand_tdm_paths(
            query=request.question,
            hops=2,
            max_paths=6,
            source_id=request.source_id,
        )
        answer = (
            f"TDM query processed for '{request.question}'. "
            f"Found {len(findings)} catalog items and {len(tdm_paths)} graph paths."
        )

        from coderag.core.models import TdmQueryResponse

        return TdmQueryResponse(
            answer=answer,
            findings=list(findings),
            diagnostics={
                "tables": len(tables),
                "columns": len(columns),
                "service_mappings": len(mappings),
                "masking_rules": len(masking_rules),
                "graph_paths": len(tdm_paths),
                "service_filter": request.service_name,
                "table_filter": request.table_name,
                "source_id": request.source_id,
                "masking_enabled": SETTINGS.tdm_enable_masking,
                "synthetic_enabled": SETTINGS.tdm_enable_synthetic,
                "virtualization_enabled": SETTINGS.tdm_enable_virtualization,
            },
        )

    def get_tdm_service_catalog(
        self,
        service_name: str,
        source_id: Optional[str] = None,
    ) -> Dict[str, object]:
        """Return TDM catalog data for one service name."""
        self._ensure_tdm_graph_enabled()
        mappings = self.store.list_tdm_service_mappings(source_id=source_id)
        selected = [
            item
            for item in mappings
            if str(item.get("service_name", "")).casefold()
            == service_name.casefold()
        ]
        return {
            "service_name": service_name,
            "source_id": source_id,
            "mappings": selected,
            "count": len(selected),
        }

    def get_tdm_table_catalog(
        self,
        table_name: str,
        source_id: Optional[str] = None,
    ) -> Dict[str, object]:
        """Return TDM catalog data for one table name."""
        self._ensure_tdm_graph_enabled()
        tables = self.store.list_tdm_tables(source_id=source_id)
        matched_tables = [
            table
            for table in tables
            if str(table.get("table_name", "")).casefold()
            == table_name.casefold()
        ]
        table_ids = {
            str(table.get("table_id"))
            for table in matched_tables
            if table.get("table_id")
        }
        columns = [
            column
            for column in self.store.list_tdm_columns(source_id=source_id)
            if str(column.get("table_id", "")) in table_ids
        ]
        return {
            "table_name": table_name,
            "source_id": source_id,
            "tables": matched_tables,
            "columns": columns,
            "count": len(matched_tables),
        }

    def preview_tdm_virtualization(
        self,
        request: "TdmQueryRequest",
    ) -> Dict[str, object]:
        """Build lightweight virtualization preview from TDM catalog data."""
        self._ensure_tdm_graph_enabled()
        if not SETTINGS.tdm_enable_virtualization:
            raise RuntimeError(
                "TDM virtualization is disabled. Set "
                "TDM_ENABLE_VIRTUALIZATION=true to enable."
            )

        mappings = self.store.list_tdm_service_mappings(
            source_id=request.source_id,
        )
        templates = build_virtualization_templates(
            source_id=request.source_id or "global",
            mappings=mappings,
            service_name_filter=request.service_name,
        )[:20]

        for template in templates:
            self.store.upsert_tdm_virtualization_artifact(
                artifact_id=str(template.get("artifact_id")),
                source_id=str(request.source_id or "global"),
                service_name=str(template.get("service_name")),
                artifact_type=str(template.get("artifact_type")),
                content=dict(template.get("content") or {}),
                metadata=dict(template.get("metadata") or {}),
            )

        return {
            "source_id": request.source_id,
            "service_name": request.service_name,
            "templates": templates,
            "count": len(templates),
        }

    def get_tdm_synthetic_profile(
        self,
        table_name: str,
        source_id: Optional[str] = None,
        target_rows: int = 1000,
    ) -> Dict[str, object]:
        """Build and persist a synthetic profile plan for one table."""
        self._ensure_tdm_graph_enabled()
        if not SETTINGS.tdm_enable_synthetic:
            raise RuntimeError(
                "TDM synthetic planning is disabled. Set "
                "TDM_ENABLE_SYNTHETIC=true to enable."
            )

        table_catalog = self.get_tdm_table_catalog(
            table_name=table_name,
            source_id=source_id,
        )
        columns = list(table_catalog.get("columns", []))
        plan = build_synthetic_profile_plan(
            table_name=table_name,
            columns=columns,
            target_rows=target_rows,
        )

        profile_id = (
            f"syn-{table_name.casefold().replace(' ', '-')}-"
            f"{max(1, int(target_rows))}"
        )
        table_rows = list(table_catalog.get("tables", []))
        target_table_id = None
        if table_rows:
            target_table_id = table_rows[0].get("table_id")

        self.store.upsert_tdm_synthetic_profile(
            profile_id=profile_id,
            source_id=source_id or "global",
            profile_name=f"synthetic-{table_name}",
            strategy="template",
            target_table_id=str(target_table_id) if target_table_id else None,
            metadata={"plan": plan},
        )

        return {
            "source_id": source_id,
            "table_name": table_name,
            "profile_id": profile_id,
            "plan": plan,
        }


SERVICE = RagApplicationService()
