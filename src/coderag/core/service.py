"""Application service orchestrating ingestion and query flows."""

from __future__ import annotations

import os
import shutil
import stat
import uuid
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

from coderag.core.composition import (
    ServiceDependencies,
    build_service_dependencies,
)
from coderag.core.index_coordinator_service import RetrievalIndexCoordinator
from coderag.core.ingestion_service import IngestionApplicationService
from coderag.core.job_service import JobApplicationService
from coderag.core.lexical_index import QueryLexicalIndex
from coderag.core.query_service import QueryApplicationService
from coderag.core.tdm_ingestion_service import TdmIngestionApplicationService
from coderag.core.tdm_policy_service import TdmPolicyService
from coderag.core.tdm_query_service import TdmQueryApplicationService
from coderag.core.models import (
    DeleteDocumentResponse,
    DocumentTagFacet,
    DocumentRecord,
    DocumentCatalogEntry,
    IngestionRequest,
    ListDocumentTagsResponse,
    QueryRequest,
    QueryResponse,
    ReplaceDocumentTagsResponse,
    ReplaceDocumentTagsRequest,
    ResetAllResponse,
    TdmQueryRequest,
    TdmQueryResponse,
)
from coderag.core.protocols import (
    GraphStoreProtocol,
    LlmClientProtocol,
    RuntimeStoreProtocol,
    VectorIndexProtocol,
)
from coderag.core.runtime import RUNTIME
from coderag.core.settings import SETTINGS
from coderag.ingestion.document_loader import load_documents
from coderag.ingestion.graph_builder import build_graph_edges


REPO_ROOT = Path(__file__).resolve().parents[3]


def _normalize_tags(tags: list[str] | None) -> list[str]:
    """Return stable, deduplicated document tags."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_tag in tags or []:
        tag = str(raw_tag or "").strip()
        if not tag:
            continue
        tag_key = tag.casefold()
        if tag_key in seen:
            continue
        seen.add(tag_key)
        normalized.append(tag)
    return normalized


def _default_logical_root_for_source(source) -> str | None:
    """Infer one stable logical root label for folder sources."""
    local_path = str(getattr(source, "local_path", "") or "").strip()
    if not local_path:
        return None

    candidate = Path(local_path).expanduser()
    if candidate.is_absolute():
        name = candidate.name.strip()
        return name or None

    normalized = local_path.replace("\\", "/").strip("/")
    return normalized or None


def _apply_tags_to_documents(
    documents: list[DocumentRecord],
    tags: list[str] | None,
) -> list[DocumentRecord]:
    """Attach one normalized tag set to every loaded document."""
    normalized_tags = _normalize_tags(tags)
    if not normalized_tags:
        return documents

    tagged_documents: list[DocumentRecord] = []
    for document in documents:
        metadata = dict(document.metadata)
        metadata["tags"] = normalized_tags
        tagged_documents.append(
            document.model_copy(
                update={
                    "tags": normalized_tags,
                    "metadata": metadata,
                }
            )
        )
    return tagged_documents


def _on_rmtree_error(func, path, _exc_info) -> None:
    """Retry file removal after clearing read-only attributes on Windows."""
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    func(path)


def _clear_local_staging_mirror(data_dir: Path) -> tuple[int, list[str]]:
    """Delete legacy staged mirror entries and keep the root folder."""
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


def _resolve_legacy_staged_candidate(
    data_dir: Path,
    path_or_url: str,
) -> Path | None:
    """Resolve one persisted path against the managed legacy staging mirror."""
    if not path_or_url.strip():
        return None

    staging_dir = (data_dir / "ingestion_staging").resolve(strict=False)
    candidate = Path(path_or_url).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(staging_dir)
        except ValueError:
            return None
        return resolved

    staged_candidate = (staging_dir / candidate).resolve(strict=False)
    if staged_candidate.exists() or staged_candidate.parent.exists():
        try:
            staged_candidate.relative_to(staging_dir)
        except ValueError:
            return None
        return staged_candidate

    repo_candidate = (REPO_ROOT / candidate).resolve(strict=False)
    try:
        repo_candidate.relative_to(staging_dir)
    except ValueError:
        return None
    return repo_candidate


def _is_legacy_staged_path(data_dir: Path, path_or_url: str) -> bool:
    """Return true when one persisted document path points into legacy staging."""
    return _resolve_legacy_staged_candidate(data_dir, path_or_url) is not None


def _delete_staged_document_copy(
    data_dir: Path,
    path_or_url: str,
) -> tuple[bool, str | None]:
    """Delete one staged document copy and prune empty parent folders."""
    candidate = _resolve_legacy_staged_candidate(data_dir, path_or_url)
    if candidate is None:
        return False, None

    staging_dir = (data_dir / "ingestion_staging").resolve(strict=False)

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


def _format_elapsed_hhmmss(elapsed_ms: float) -> str:
    """Convert elapsed milliseconds to HH:MM:SS for public payloads."""
    safe_ms = max(0.0, float(elapsed_ms))
    total_seconds = int(safe_ms // 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _as_public_timed_payload(payload: dict[str, object]) -> dict[str, object]:
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

    def __init__(
        self,
        dependencies: ServiceDependencies | None = None,
    ) -> None:
        resolved_dependencies = dependencies or build_service_dependencies(
            settings=SETTINGS,
            runtime_state=RUNTIME,
        )
        self.store: RuntimeStoreProtocol = resolved_dependencies.store
        self.lexical_index: QueryLexicalIndex = (
            resolved_dependencies.lexical_index
        )
        self.vector_index: VectorIndexProtocol = (
            resolved_dependencies.vector_index
        )
        self.llm: LlmClientProtocol = resolved_dependencies.llm_client
        self.graph_store: GraphStoreProtocol = resolved_dependencies.graph_store
        self.job_service = JobApplicationService(
            store=self.store,
            as_public_timed_payload=_as_public_timed_payload,
        )
        self._loaded_index_version = -1
        try:
            self.rebuild_indexes()
        except RuntimeError:
            # Keep imports/startup usable when the configured vector backend
            # is temporarily unavailable. Runtime operations that need Chroma
            # will still fail explicitly on use.
            self._loaded_index_version = self.store.get_index_version()

    def rebuild_indexes(self, source_id: str | None = None) -> None:
        """Rebuild retrieval indexes from persisted chunks."""
        self._loaded_index_version = self.index_coordinator.rebuild_indexes(
            source_id=source_id
        )

    def _build_index_coordinator(self) -> RetrievalIndexCoordinator:
        """Build index coordinator from current runtime collaborators."""
        return RetrievalIndexCoordinator(
            store=self.store,
            lexical_index=self.lexical_index,
            vector_index=self.vector_index,
        )

    @property
    def index_coordinator(self) -> RetrievalIndexCoordinator:
        """Return index coordinator bound to current runtime state."""
        return self._build_index_coordinator()

    def _build_ingestion_service(self) -> IngestionApplicationService:
        """Build ingestion service from the current runtime collaborators."""
        return IngestionApplicationService(
            store=self.store,
            vector_index=self.vector_index,
            graph_store=self.graph_store,
            ingestion_artifact_store=RUNTIME.ingestion_artifact_store,
            data_dir=SETTINGS.data_dir,
            rebuild_indexes=self.rebuild_indexes,
            is_graph_enabled=self.is_graph_enabled,
            delete_persisted_documents=self._delete_persisted_documents,
            ingest_handler=self._ingest_impl,
            is_legacy_staged_path=_is_legacy_staged_path,
            clear_local_staging_mirror=_clear_local_staging_mirror,
        )

    @property
    def ingestion_service(self) -> IngestionApplicationService:
        """Return ingestion service bound to current runtime state."""
        return self._build_ingestion_service()

    def _build_query_service(self) -> QueryApplicationService:
        """Build query service from the current runtime collaborators."""
        return QueryApplicationService(
            store=self.store,
            lexical_index=self.lexical_index,
            vector_index=self.vector_index,
            llm=self.llm,
            graph_store=self.graph_store,
            settings=SETTINGS,
        )

    @property
    def query_service(self) -> QueryApplicationService:
        """Return query service bound to current runtime state."""
        return self._build_query_service()

    def _build_tdm_query_service(self) -> TdmQueryApplicationService:
        """Build TDM query service from the current runtime collaborators."""
        return TdmQueryApplicationService(
            store=self.store,
            graph_store=self.graph_store,
            settings=SETTINGS,
            ensure_tdm_graph_enabled=self._ensure_tdm_graph_enabled,
        )

    @property
    def tdm_query_service(self) -> TdmQueryApplicationService:
        """Return TDM query service bound to current runtime state."""
        return self._build_tdm_query_service()

    def _build_tdm_ingestion_service(self) -> TdmIngestionApplicationService:
        """Build TDM ingestion service from current runtime collaborators."""
        return TdmIngestionApplicationService(
            store=self.store,
            graph_store=self.graph_store,
            ensure_tdm_graph_enabled=self._ensure_tdm_graph_enabled,
        )

    @property
    def tdm_ingestion_service(self) -> TdmIngestionApplicationService:
        """Return TDM ingestion service bound to current runtime state."""
        return self._build_tdm_ingestion_service()

    def _build_tdm_policy_service(self) -> TdmPolicyService:
        """Build TDM policy service from current runtime collaborators."""
        return TdmPolicyService(
            settings=SETTINGS,
            is_graph_enabled=self.is_graph_enabled,
        )

    @property
    def tdm_policy_service(self) -> TdmPolicyService:
        """Return TDM policy service bound to current runtime state."""
        return self._build_tdm_policy_service()

    def _rebuild_lexical_from_store(self) -> None:
        """Refresh lexical retrieval from persisted chunks without re-embedding."""
        self._loaded_index_version = (
            self.index_coordinator.rebuild_lexical_from_store()
        )

    def _sync_graph_for_source(
        self,
        source_id: str,
    ) -> tuple[list[tuple[str, str, str, str]], dict[str, object]]:
        """Recompute graph state for one source from current chunks."""
        chunks = self.store.list_chunks(source_id=source_id)
        edges = build_graph_edges(source_id=source_id, chunks=chunks)

        if not self.is_graph_enabled():
            return edges, {"neo4j_enabled": False, "skipped": True}

        try:
            graph_metrics = self.graph_store.replace_edges(
                source_id=source_id,
                edges=edges,
            )
        except Exception as exc:
            return edges, {
                "neo4j_enabled": True,
                "neo4j_degraded": True,
                "neo4j_error": (
                    f"{exc.__class__.__name__}: {exc}"
                ),
            }

        if isinstance(graph_metrics, dict):
            return edges, graph_metrics
        return edges, {}

    def _delete_persisted_documents(
        self,
        documents: list[DocumentCatalogEntry],
        skip_reindex_source_ids: set[str] | None = None,
    ) -> dict[str, object]:
        """Delete persisted documents across metadata, vector, staging, and graph."""
        if not documents:
            return {
                "matched_documents": 0,
                "deleted_documents": 0,
                "deleted_chunks": 0,
                "deleted_staging_files": 0,
                "neo4j_nodes_deleted": 0,
                "reindexed_sources": 0,
                "replaced_document_ids": [],
                "replaced_paths": [],
                "staging_warnings": [],
            }

        deleted_documents = 0
        deleted_chunks = 0
        deleted_staging_files = 0
        neo4j_nodes_deleted = 0
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
            _edges, graph_metrics = self._sync_graph_for_source(source_id)
            nodes_deleted = graph_metrics.get("nodes_deleted", 0)
            if isinstance(nodes_deleted, int):
                neo4j_nodes_deleted += nodes_deleted

        self.store.bump_index_version()
        self._rebuild_lexical_from_store()

        return {
            "matched_documents": len(documents),
            "deleted_documents": deleted_documents,
            "deleted_chunks": deleted_chunks,
            "deleted_staging_files": deleted_staging_files,
            "neo4j_nodes_deleted": neo4j_nodes_deleted,
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

    def _refresh_indexes_after_external_update(self) -> None:
        """Refresh in-memory retrieval state after external ingestion.

        The async worker already persists vector updates into Chroma. During
        API-side refresh we only need to rebuild the Postgres lexical corpus
        from persisted chunks and update the loaded version marker. This
        avoids re-embedding all chunks on the first query after async
        ingestion.
        """
        self._loaded_index_version = (
            self.index_coordinator.refresh_after_external_update()
        )

    def _ensure_fresh_indexes(self) -> None:
        """Refresh indexes when a different process updated persisted state."""
        self._loaded_index_version = self.index_coordinator.ensure_fresh_indexes(
            self._loaded_index_version
        )

    def close(self) -> None:
        """Release external resources held by the service."""
        self.graph_store.close()
        self.vector_index.close()

    def is_graph_enabled(self) -> bool:
        """Return whether graph-backed runtime features are enabled."""
        return self.graph_store.is_enabled()

    def is_tdm_graph_enabled(self) -> bool:
        """Return whether TDM can use graph-backed capabilities."""
        return self.tdm_policy_service.is_tdm_graph_enabled()

    def _ensure_tdm_graph_enabled(self) -> None:
        """Require both TDM feature flag and Neo4j graph runtime."""
        self.tdm_policy_service.ensure_tdm_graph_enabled()

    def reset_all(self) -> ResetAllResponse:
        """Reset all persisted indexing artifacts across storage layers."""
        return self.ingestion_service.reset_all()

    def delete_document(self, document_id: str) -> DeleteDocumentResponse:
        """Delete one persisted document and refresh dependent indexes."""
        return self.ingestion_service.delete_document(document_id)

    def ingest(
        self,
        request: IngestionRequest,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
        job_id: str | None = None,
    ) -> dict[str, object]:
        """Run full ingestion pipeline and persist generated artifacts."""
        return self.ingestion_service.ingest(
            request,
            progress_callback=progress_callback,
            job_id=job_id,
        )

    def _ingest_impl(
        self,
        request: IngestionRequest,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
        job_id: str | None = None,
    ) -> dict[str, object]:
        """Run full ingestion pipeline and persist generated artifacts."""
        if (
            request.source.source_type.strip().lower() == "folder"
            and request.source.logical_root is None
            and not request.source.artifact_id
        ):
            request = request.model_copy(
                update={
                    "source": request.source.model_copy(
                        update={
                            "logical_root": _default_logical_root_for_source(
                                request.source
                            )
                        }
                    )
                }
            )

        if not job_id:
            job_id = uuid.uuid4().hex[:12]
        self.store.touch_job(job_id, "running", "Starting ingestion")

        started_at = perf_counter()
        ingestion_service = self.ingestion_service
        steps: list[dict[str, object]] = []
        step_counter = 0

        def _add_step(
            name: str,
            details: dict[str, object],
            status: str = "ok",
            progress_pct: float | None = None,
        ) -> None:
            nonlocal step_counter
            step_counter = ingestion_service.append_ingest_step(
                job_id=job_id,
                name=name,
                details=details,
                status=status,
                progress_pct=progress_pct,
                step_counter=step_counter,
                started_at=started_at,
                steps=steps,
                format_elapsed_hhmmss=_format_elapsed_hhmmss,
                progress_callback=progress_callback,
            )

        def _loader_progress(
            event: str,
            payload: dict[str, object],
        ) -> None:
            step_name, step_details, progress_pct = (
                ingestion_service.build_loader_progress_step(
                    event=event,
                    payload=payload,
                )
            )
            _add_step(step_name, step_details, progress_pct=progress_pct)

        documents, load_stats = load_documents(
            request.source,
            progress_callback=_loader_progress,
        )
        documents = _apply_tags_to_documents(documents, request.source.tags)
        _add_step("load_documents", load_stats, progress_pct=30.0)
        if not documents:
            failure_message = ingestion_service.build_failed_ingest_message(
                load_stats=load_stats,
                local_path=request.source.local_path or "<not-set>",
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
                progress_pct=100.0,
            )
            return ingestion_service.build_failed_ingest_result(
                job_id=job_id,
                failure_message=failure_message,
                steps=steps,
            )

        source_id = documents[0].source_id

        documents, incoming_dedup_stats, dedup_stats = (
            ingestion_service.prepare_documents_for_ingest(
                documents=documents,
                current_source_id=source_id,
            )
        )
        _add_step(
            "deduplicate_incoming_batch",
            incoming_dedup_stats,
            progress_pct=35.0,
        )
        _add_step(
            "deduplicate_documents",
            dedup_stats,
            progress_pct=42.0,
        )

        def _on_chunk_progress(payload: dict[str, int]) -> None:
            """Emit chunking progress steps preserving public telemetry shape."""
            total_documents = int(payload.get("total_documents", 0))
            processed_documents = int(payload.get("processed_documents", 0))
            progress_pct = 42.0
            if total_documents > 0:
                progress_pct = 42.0 + (
                    processed_documents / total_documents
                ) * 13.0
            _add_step(
                "chunk_progress",
                {
                    "processed_documents": processed_documents,
                    "total_documents": total_documents,
                    "generated_chunks": int(
                        payload.get("generated_chunks", 0)
                    ),
                },
                progress_pct=progress_pct,
            )

        chunks, total_characters = ingestion_service.build_chunks_with_progress(
            documents=documents,
            progress_callback=_on_chunk_progress,
        )

        persistence_summary = (
            ingestion_service.persist_chunk_graph_materialization(
                source_id=source_id,
                documents=documents,
                chunks=chunks,
            )
        )
        persisted_documents = int(
            persistence_summary["persisted_documents"]
        )
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

        _add_step(
            "persist_chunks",
            {
                "source_id": source_id,
                "chunks": len(chunks),
            },
            progress_pct=70.0,
        )

        edges = persistence_summary["edges"]
        _add_step(
            "build_graph_edges",
            {
                "edges": len(edges),
            },
            progress_pct=78.0,
        )

        persist_graph_details = dict(
            persistence_summary["persist_graph_details"]
        )
        persist_graph_status = str(persistence_summary["persist_graph_status"])
        _add_step(
            "persist_graph",
            persist_graph_details,
            status=persist_graph_status,
            progress_pct=86.0,
        )

        self._loaded_index_version = (
            ingestion_service.rebuild_indexes_after_ingest(
                chunks=chunks,
                rebuild_lexical_from_store=self._rebuild_lexical_from_store,
            )
        )
        _add_step(
            "rebuild_indexes",
            {
                "source_id": source_id,
                "lexical_scope": "global",
                "vector_scope": "source",
            },
            progress_pct=95.0,
        )

        elapsed_ms = round((perf_counter() - started_at) * 1000.0, 2)
        elapsed_hhmmss = _format_elapsed_hhmmss(elapsed_ms)
        _add_step(
            "ingestion_completed",
            {
                "elapsed_hhmmss": elapsed_hhmmss,
            },
            progress_pct=100.0,
        )

        self.store.touch_job(
            job_id,
            "completed",
            f"Indexed {len(documents)} docs and {len(chunks)} chunks",
        )
        self.store.bump_index_version()
        return ingestion_service.build_completed_ingest_result(
            job_id=job_id,
            source_id=source_id,
            documents_count=len(documents),
            chunks_count=len(chunks),
            steps=steps,
            elapsed_hhmmss=elapsed_hhmmss,
            load_stats=load_stats,
            incoming_dedup_stats=incoming_dedup_stats,
            dedup_stats=dedup_stats,
            persist_graph_details=persist_graph_details,
        )

    def get_job(self, job_id: str) -> dict[str, object] | None:
        """Retrieve job status by id."""
        return self.job_service.get_job(job_id)

    def list_documents(
        self,
        source_id: str | None = None,
        tags: list[str] | None = None,
    ) -> list[DocumentCatalogEntry]:
        """Return document catalog entries for optional source filter."""
        return self.store.list_documents(source_id=source_id, tags=tags)

    def list_document_tags(
        self,
        source_id: str | None = None,
    ) -> ListDocumentTagsResponse:
        """Return aggregated tags present in persisted documents."""
        facets = self.store.list_tag_facets(source_id=source_id)
        tags = [tag for tag, _count in facets]
        return ListDocumentTagsResponse(
            source_id=source_id,
            count=len(tags),
            tags=tags,
            items=[
                DocumentTagFacet(tag=tag, document_count=document_count)
                for tag, document_count in facets
            ],
        )

    def replace_document_tags(
        self,
        document_id: str,
        request: ReplaceDocumentTagsRequest,
    ) -> ReplaceDocumentTagsResponse:
        """Replace all persisted tags for one document id."""
        result = self.store.replace_document_tags(
            document_id=document_id,
            tags=_normalize_tags(request.tags),
        )
        if result is None:
            raise KeyError(document_id)
        return ReplaceDocumentTagsResponse(
            status="updated",
            message="Tags replaced for document.",
            document_id=document_id,
            source_id=str(result["source_id"]),
            old_tags=list(result["old_tags"]),
            new_tags=list(result["new_tags"]),
        )

    def query(self, request: QueryRequest) -> QueryResponse:
        """Run hybrid retrieval + graph expansion + grounded answering."""
        try:
            self._ensure_fresh_indexes()
        except Exception as exc:
            raise RuntimeError(
                "Failed to refresh retrieval indexes after async ingestion."
            ) from exc
        return self.query_service.query(request)

    def ingest_tdm_assets(self, request: IngestionRequest) -> dict[str, object]:
        """Ingest TDM metadata assets into additive catalog tables."""
        return self.tdm_ingestion_service.ingest_tdm_assets(request)

    def _ensure_tdm_enabled(self) -> None:
        """Guard additive TDM routes behind explicit feature flags."""
        self.tdm_policy_service.ensure_tdm_enabled()

    def query_tdm(self, request: TdmQueryRequest) -> TdmQueryResponse:
        """Run TDM catalog query mode for agent-facing workflows."""
        return self.tdm_query_service.query_tdm(request)

    def get_tdm_service_catalog(
        self,
        service_name: str,
        source_id: str | None = None,
    ) -> dict[str, object]:
        """Return TDM catalog data for one service name."""
        return self.tdm_query_service.get_tdm_service_catalog(
            service_name=service_name,
            source_id=source_id,
        )

    def get_tdm_table_catalog(
        self,
        table_name: str,
        source_id: str | None = None,
    ) -> dict[str, object]:
        """Return TDM catalog data for one table name."""
        return self.tdm_query_service.get_tdm_table_catalog(
            table_name=table_name,
            source_id=source_id,
        )

    def preview_tdm_virtualization(
        self,
        request: TdmQueryRequest,
    ) -> dict[str, object]:
        """Build lightweight virtualization preview from TDM catalog data."""
        return self.tdm_query_service.preview_tdm_virtualization(request)

    def get_tdm_synthetic_profile(
        self,
        table_name: str,
        source_id: str | None = None,
        target_rows: int = 1000,
    ) -> dict[str, object]:
        """Build and persist a synthetic profile plan for one table."""
        return self.tdm_query_service.get_tdm_synthetic_profile(
            table_name=table_name,
            source_id=source_id,
            target_rows=target_rows,
        )


SERVICE = RagApplicationService()
