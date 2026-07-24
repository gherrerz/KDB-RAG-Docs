"""Ingestion-focused service extracted from the application facade."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import perf_counter

from coderag.core.models import (
    ChunkRecord,
    DeleteDocumentResponse,
    DocumentCatalogEntry,
    DocumentRecord,
    IngestionRequest,
    ResetAllResponse,
)
from coderag.core.protocols import (
    GraphEdgeRecord,
    GraphStoreProtocol,
    IngestionArtifactStoreProtocol,
    RuntimeStoreProtocol,
    VectorIndexProtocol,
)
from coderag.ingestion.chunker import build_chunks
from coderag.ingestion.graph_builder import build_graph_edges


def _document_dedup_key(document: DocumentRecord) -> tuple[str, str]:
    """Normalize document identity for pre-ingest deduplication."""
    return (
        document.title.strip().casefold(),
        document.content_type.strip().casefold(),
    )


class IngestionApplicationService:
    """Own ingestion lifecycle operations for the runtime facade."""

    def __init__(
        self,
        *,
        store: RuntimeStoreProtocol,
        vector_index: VectorIndexProtocol,
        graph_store: GraphStoreProtocol,
        ingestion_artifact_store: IngestionArtifactStoreProtocol,
        data_dir: Path,
        rebuild_indexes: Callable[[], None],
        is_graph_enabled: Callable[[], bool],
        delete_persisted_documents: Callable[
            [list[DocumentCatalogEntry], set[str] | None],
            dict[str, object],
        ],
        ingest_handler: Callable[
            [
                IngestionRequest,
                Callable[[dict[str, object]], None] | None,
                str | None,
            ],
            dict[str, object],
        ],
        is_legacy_staged_path: Callable[[Path, str], bool],
        clear_local_staging_mirror: Callable[[Path], tuple[int, list[str]]],
    ) -> None:
        """Build ingestion service from runtime collaborators."""
        self._store = store
        self._vector_index = vector_index
        self._graph_store = graph_store
        self._ingestion_artifact_store = ingestion_artifact_store
        self._data_dir = data_dir
        self._rebuild_indexes = rebuild_indexes
        self._is_graph_enabled = is_graph_enabled
        self._delete_persisted_documents = delete_persisted_documents
        self._ingest_handler = ingest_handler
        self._is_legacy_staged_path = is_legacy_staged_path
        self._clear_local_staging_mirror = clear_local_staging_mirror

    def ingest(
        self,
        request: IngestionRequest,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
        job_id: str | None = None,
    ) -> dict[str, object]:
        """Execute the configured ingestion handler."""
        return self._ingest_handler(request, progress_callback, job_id)

    def append_ingest_step(
        self,
        *,
        job_id: str,
        step_counter: int,
        started_at: float,
        name: str,
        details: dict[str, object],
        steps: list[dict[str, object]],
        format_elapsed_hhmmss: Callable[[float], str],
        progress_callback: Callable[[dict[str, object]], None] | None = None,
        status: str = "ok",
        progress_pct: float | None = None,
    ) -> int:
        """Append one ingestion step and propagate runtime progress state."""
        step_counter += 1
        elapsed_ms = round((perf_counter() - started_at) * 1000.0, 2)
        step_payload: dict[str, object] = {
            "name": name,
            "status": status,
            "details": details,
            "elapsed_hhmmss": format_elapsed_hhmmss(elapsed_ms),
        }
        if progress_pct is not None:
            step_payload["progress_pct"] = round(progress_pct, 2)

        steps.append(step_payload)

        details_with_progress = dict(details)
        if progress_pct is not None:
            details_with_progress["progress_pct"] = round(progress_pct, 2)

        self._store.append_job_event(
            job_id=job_id,
            ordinal=step_counter,
            name=name,
            status=status,
            elapsed_ms=elapsed_ms,
            details=details_with_progress,
        )

        if status == "failed":
            self._store.touch_job(job_id, "failed", f"FAILED | {name}")
        elif name != "ingestion_completed":
            pct = progress_pct if progress_pct is not None else 0.0
            self._store.touch_job(
                job_id,
                "running",
                f"{int(round(pct))}% | {name}",
            )

        if progress_callback is not None:
            progress_callback(
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

        return step_counter

    def build_loader_progress_step(
        self,
        *,
        event: str,
        payload: dict[str, object],
    ) -> tuple[str, dict[str, object], float]:
        """Build loader progress step details and mapped progress pct."""
        progress_pct = 10.0
        total = payload.get("total_files")
        processed = payload.get("processed_files")
        if isinstance(total, int) and total > 0 and isinstance(processed, int):
            progress_pct = 10.0 + (processed / total) * 20.0
        return event, payload, progress_pct

    def prepare_documents_for_ingest(
        self,
        documents: list[DocumentRecord],
        current_source_id: str,
    ) -> tuple[list[DocumentRecord], dict[str, object], dict[str, object]]:
        """Apply intra-batch and persisted deduplication before ingestion."""
        collapsed_documents, incoming_dedup_stats = (
            self._collapse_incoming_duplicate_documents(documents)
        )
        dedup_stats = self._deduplicate_documents_before_ingest(
            collapsed_documents,
            current_source_id,
        )
        return collapsed_documents, incoming_dedup_stats, dedup_stats

    def persist_chunk_graph_materialization(
        self,
        *,
        source_id: str,
        documents: list[DocumentRecord],
        chunks: list[ChunkRecord],
    ) -> dict[str, object]:
        """Persist documents/chunks and materialize graph state for one source."""
        persisted_documents = self._store.upsert_documents(documents)
        self._store.replace_chunks(source_id=source_id, chunks=chunks)

        edges: list[GraphEdgeRecord] = build_graph_edges(
            source_id=source_id,
            chunks=chunks,
        )

        if self._is_graph_enabled():
            persist_graph_details: dict[str, object] = {
                "edges": len(edges),
                "neo4j_enabled": True,
            }
            persist_graph_status = "ok"
            try:
                graph_metrics = self._graph_store.replace_edges(
                    source_id=source_id,
                    edges=edges,
                )
                if isinstance(graph_metrics, dict):
                    for key, value in graph_metrics.items():
                        persist_graph_details[f"neo4j_{key}"] = value
            except Exception as exc:
                persist_graph_status = "warning"
                persist_graph_details["neo4j_degraded"] = True
                persist_graph_details["neo4j_error"] = (
                    f"{exc.__class__.__name__}: {exc}"
                )
        else:
            persist_graph_details = {
                "edges": len(edges),
                "neo4j_enabled": False,
                "skipped": True,
                "reason": "USE_NEO4J=false",
            }
            persist_graph_status = "ok"

        return {
            "persisted_documents": persisted_documents,
            "edges": edges,
            "persist_graph_details": persist_graph_details,
            "persist_graph_status": persist_graph_status,
        }

    def build_chunks_with_progress(
        self,
        documents: list[DocumentRecord],
        progress_callback: Callable[[dict[str, int]], None] | None = None,
    ) -> tuple[list[ChunkRecord], int]:
        """Build semantic chunks while emitting coarse progress snapshots."""
        chunks: list[ChunkRecord] = []
        total_characters = 0
        total_documents = len(documents)

        for index, document in enumerate(documents, start=1):
            total_characters += len(document.content)
            chunks.extend(build_chunks(document))
            if (
                progress_callback is not None
                and (
                    index == 1
                    or index % 10 == 0
                    or index == total_documents
                )
            ):
                progress_callback(
                    {
                        "processed_documents": index,
                        "total_documents": total_documents,
                        "generated_chunks": len(chunks),
                    }
                )

        return chunks, total_characters

    def rebuild_indexes_after_ingest(
        self,
        *,
        chunks: list[ChunkRecord],
        rebuild_lexical_from_store: Callable[[], None],
    ) -> int:
        """Refresh lexical and vector indexes after one persisted ingest."""
        rebuild_lexical_from_store()
        self._vector_index.rebuild(chunks)
        return self._store.get_index_version()

    def build_completed_ingest_result(
        self,
        *,
        job_id: str,
        source_id: str,
        documents_count: int,
        chunks_count: int,
        steps: list[dict[str, object]],
        elapsed_hhmmss: str,
        load_stats: dict[str, object],
        incoming_dedup_stats: dict[str, object],
        dedup_stats: dict[str, object],
        persist_graph_details: dict[str, object],
    ) -> dict[str, object]:
        """Build the outward payload returned when ingestion completes."""
        deduplication_summary = {
            "incoming_batch": incoming_dedup_stats,
            "replaced_existing": dedup_stats,
        }
        # Contrato Hexa: idempotencia de tools de escritura. "created" es
        # false cuando la deduplicaci\u00f3n (title+content_type) reemplaz\u00f3 al
        # menos un documento ya persistido; true cuando el lote completo era
        # nuevo (sin coincidencias previas).
        created = int(dedup_stats.get("deleted_documents", 0) or 0) == 0

        return {
            "job_id": job_id,
            "status": "completed",
            "source_id": source_id,
            "documents": str(documents_count),
            "chunks": str(chunks_count),
            "created": created,
            "steps": steps,
            "progress_pct": 100.0,
            "metrics": {
                "elapsed_hhmmss": elapsed_hhmmss,
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
                "neo4j_degraded": bool(
                    persist_graph_details.get("neo4j_degraded", False)
                ),
                "neo4j_error": str(
                    persist_graph_details.get("neo4j_error", "")
                ),
            },
            "deduplication": deduplication_summary,
        }

    def build_failed_ingest_message(
        self,
        *,
        load_stats: dict[str, object],
        local_path: str,
    ) -> str:
        """Build one user-facing failure message for empty ingest sources."""
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

        return failure_message

    def build_failed_ingest_result(
        self,
        *,
        job_id: str,
        failure_message: str,
        steps: list[dict[str, object]],
    ) -> dict[str, object]:
        """Build outward payload returned when ingestion fails early."""
        return {
            "job_id": job_id,
            "status": "failed",
            "message": failure_message,
            "steps": steps,
            "progress_pct": 100.0,
        }

    def reset_all(self) -> ResetAllResponse:
        """Reset all persisted indexing artifacts across storage layers."""
        legacy_staged_documents = [
            document
            for document in self._store.list_documents()
            if self._is_legacy_staged_path(self._data_dir, document.path_or_url)
        ]
        deleted = self._store.clear_all_data()
        self._ingestion_artifact_store.clear_uploaded_artifacts()
        self._vector_index.clear_all()
        if legacy_staged_documents:
            deleted_staging_entries, staging_warnings = (
                self._clear_local_staging_mirror(self._data_dir)
            )
        else:
            deleted_staging_entries, staging_warnings = 0, []

        neo4j_enabled = self._is_graph_enabled()
        neo4j_edges_deleted = self._graph_store.clear_all_edges()

        self._store.bump_index_version()
        self._rebuild_indexes()

        return ResetAllResponse(
            status="completed",
            message=(
                "All repositories were cleared, indexes were reset, and "
                f"{deleted_staging_entries} legacy staging mirror entries were "
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
            deleted_jobs=deleted["deleted_jobs"],
            neo4j_enabled=neo4j_enabled,
            neo4j_edges_deleted=neo4j_edges_deleted,
        )

    def delete_document(self, document_id: str) -> DeleteDocumentResponse:
        """Delete one persisted document and refresh dependent indexes."""
        document = self._store.get_document_by_id(document_id)
        if document is None:
            raise KeyError(document_id)

        deleted = self._delete_persisted_documents([document], None)

        return DeleteDocumentResponse(
            status="completed",
            message=(
                "Document was deleted from persisted metadata, vector index, "
                "managed staging mirror, and Neo4j orphan cleanup."
            ),
            document_id=document.document_id,
            source_id=document.source_id,
            deleted_documents=int(deleted["deleted_documents"]),
            deleted_chunks=int(deleted["deleted_chunks"]),
            deleted_staging_files=int(deleted["deleted_staging_files"]),
            reindexed_sources=int(deleted["reindexed_sources"]),
            neo4j_nodes_deleted=int(deleted["neo4j_nodes_deleted"]),
        )

    def _deduplicate_documents_before_ingest(
        self,
        documents: list[DocumentRecord],
        current_source_id: str,
    ) -> dict[str, object]:
        """Delete older persisted documents matching title and content type."""
        duplicates_by_id: dict[str, DocumentCatalogEntry] = {}
        for document in documents:
            matches = self._store.find_documents_by_title_and_content_type(
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
        documents: list[DocumentRecord],
    ) -> tuple[list[DocumentRecord], dict[str, object]]:
        """Collapse duplicate documents detected inside one ingest batch."""
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
            "kept_document_ids": [
                document.document_id for document in collapsed
            ],
            "kept_paths": [document.path_or_url for document in collapsed],
            "resolution": "keep_last_by_sorted_path",
        }