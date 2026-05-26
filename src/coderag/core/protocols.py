"""Runtime contracts used to decouple service dependencies."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from coderag.core.models import (
    ChunkRecord,
    DocumentCatalogEntry,
    DocumentRecord,
    GraphPath,
    JobStatus,
)


GraphEdgeRecord = tuple[str, str, str, str, str]
TdmTypedEdge = tuple[str, str, str, str]


class RuntimeStoreProtocol(Protocol):
    """Persistent store contract used by service and queue code paths."""

    def get_index_version(self) -> int:
        """Return the current retrieval index version counter."""

    def bump_index_version(self) -> int:
        """Increment and return the shared retrieval index version."""

    def upsert_documents(self, docs: list[DocumentRecord]) -> int:
        """Persist many document rows and return affected count."""

    def replace_chunks(self, source_id: str, chunks: list[ChunkRecord]) -> None:
        """Replace all chunks for one source id."""

    def list_chunks(self, source_id: str | None = None) -> list[ChunkRecord]:
        """Return chunks optionally filtered by source id."""

    def get_document_map(
        self,
        source_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Return metadata map keyed by document id."""

    def list_documents(
        self,
        source_id: str | None = None,
        tags: list[str] | None = None,
    ) -> list[DocumentCatalogEntry]:
        """Return catalog entries for UI/API filtering."""

    def get_document_by_id(
        self,
        document_id: str,
    ) -> DocumentCatalogEntry | None:
        """Return one catalog entry by persisted document id."""

    def list_tag_facets(
        self,
        source_id: str | None = None,
    ) -> list[tuple[str, int]]:
        """Return normalized tag facets with document counts."""

    def replace_document_tags(
        self,
        document_id: str,
        tags: list[object],
    ) -> dict[str, Any] | None:
        """Replace persisted tags for one document id."""

    def find_documents_by_title_and_content_type(
        self,
        title: str,
        content_type: str,
    ) -> list[DocumentCatalogEntry]:
        """Return existing docs used for deduplication lookups."""

    def delete_document_by_id(self, document_id: str) -> int:
        """Delete one document row by id."""

    def delete_chunks_by_document_id(self, document_id: str) -> int:
        """Delete all chunks linked to one document id."""

    def replace_graph_edges(
        self,
        source_id: str,
        edges: list[GraphEdgeRecord],
    ) -> None:
        """Replace stored graph edges for one source id."""

    def list_graph_edges(
        self,
        source_id: str | None = None,
    ) -> list[tuple[str, str, str]]:
        """List stored graph edges for one source or globally."""

    def upsert_job(self, job: JobStatus) -> None:
        """Persist one job snapshot."""

    def get_job(self, job_id: str) -> JobStatus | None:
        """Return one job by id when available."""

    def touch_job(self, job_id: str, status: str, message: str) -> JobStatus:
        """Upsert one job state transition quickly."""

    def append_job_event(
        self,
        job_id: str,
        ordinal: int,
        name: str,
        status: str,
        elapsed_ms: float,
        details: dict[str, Any],
    ) -> None:
        """Persist one timeline event for progress polling."""

    def list_job_events(self, job_id: str) -> list[dict[str, Any]]:
        """Return ordered timeline events for one job id."""

    def clear_all_data(self) -> dict[str, int]:
        """Delete persisted rows while preserving schema."""

    def upsert_tdm_schema(
        self,
        schema_id: str,
        source_id: str,
        database_name: str,
        schema_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist one TDM schema row."""

    def list_tdm_schemas(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List TDM schemas for one source or globally."""

    def upsert_tdm_table(
        self,
        table_id: str,
        source_id: str,
        schema_id: str,
        table_name: str,
        table_type: str = "table",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist one TDM table row."""

    def list_tdm_tables(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List TDM tables for one source or globally."""

    def upsert_tdm_column(
        self,
        column_id: str,
        source_id: str,
        table_id: str,
        column_name: str,
        data_type: str,
        nullable: bool = True,
        pii_class: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist one TDM column row."""

    def list_tdm_columns(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List TDM columns for one source or globally."""

    def upsert_tdm_service_mapping(
        self,
        mapping_id: str,
        source_id: str,
        service_name: str,
        endpoint: str,
        method: str,
        table_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist one service-to-table TDM mapping."""

    def list_tdm_service_mappings(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List TDM service mappings for one source or globally."""

    def upsert_tdm_masking_rule(
        self,
        rule_id: str,
        source_id: str,
        rule_name: str,
        policy_type: str,
        scope: str,
        table_id: str | None = None,
        column_id: str | None = None,
        priority: int = 100,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist one TDM masking rule."""

    def list_tdm_masking_rules(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List TDM masking rules for one source or globally."""

    def upsert_tdm_virtualization_artifact(
        self,
        artifact_id: str,
        source_id: str,
        service_name: str,
        artifact_type: str,
        content: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist one generated TDM virtualization artifact."""

    def upsert_tdm_synthetic_profile(
        self,
        profile_id: str,
        source_id: str,
        profile_name: str,
        strategy: str = "template",
        target_table_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist one generated synthetic profile specification."""


class IngestionArtifactStoreProtocol(Protocol):
    """Artifact persistence contract used by API and queue modules."""

    def create_uploaded_batch_artifact(
        self,
        *,
        source_type: str,
        origin_path_or_url: str | None,
        files: list[dict[str, Any]],
    ) -> str | None:
        """Persist one uploaded batch and return artifact id when available."""

    def attach_job(self, artifact_id: str, job_id: str) -> None:
        """Associate one artifact with one queued job id."""

    def mark_processing_started(self, artifact_id: str) -> None:
        """Mark one artifact as started."""

    def mark_processing_completed(self, artifact_id: str) -> None:
        """Mark one artifact as completed."""

    def mark_processing_failed(self, artifact_id: str, error_message: str) -> None:
        """Mark one artifact as failed with diagnostic detail."""

    def materialize_uploaded_batch(self, artifact_id: str) -> str | None:
        """Hydrate one artifact payload into a local worker directory."""

    def clear_uploaded_artifacts(self) -> int:
        """Delete all stored artifacts and return affected count."""

    def purge_expired_uploaded_artifacts(self) -> int:
        """Delete expired artifact metadata rows and return affected count."""


class VectorIndexProtocol(Protocol):
    """Vector index contract used by the application service."""

    embedding_provider: str
    embedding_model: str | None

    def rebuild(self, chunks: Sequence[ChunkRecord]) -> None:
        """Replace vectors for all chunks in the provided snapshot."""

    def search(
        self,
        query: str,
        top_n: int,
        source_id: str | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        """Return vector hits sorted by descending similarity score."""

    def delete_document(self, document_id: str) -> None:
        """Delete vectors linked to one document id."""

    def clear_all(self) -> None:
        """Reset managed vectors."""

    def close(self) -> None:
        """Release vector backend resources when applicable."""


class LlmClientProtocol(Protocol):
    """Answer generation contract used by the query service."""

    def answer(
        self,
        question: str,
        chunks: list[ChunkRecord],
        context: str | None = None,
        provider: str = "local",
        force_fallback: bool = False,
        strict: bool = False,
        doc_map: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        """Generate one answer grounded in the provided retrieval context."""


class GraphStoreProtocol(Protocol):
    """Neo4j graph adapter contract used by ingestion and query flows."""

    def close(self) -> None:
        """Release graph backend resources when initialized."""

    def is_enabled(self) -> bool:
        """Return whether graph integration is configured and enabled."""

    def replace_edges(
        self,
        source_id: str,
        edges: Iterable[GraphEdgeRecord],
    ) -> dict[str, int]:
        """Replace graph edges for one source and return write metrics."""

    def clear_all_edges(self) -> int:
        """Delete all managed graph relationships."""

    def replace_tdm_edges(
        self,
        source_id: str,
        typed_edges: Iterable[TdmTypedEdge],
    ) -> dict[str, int]:
        """Replace typed TDM edges for one source and return metrics."""

    def expand_tdm_paths(
        self,
        query: str,
        hops: int,
        max_paths: int,
        source_id: str | None = None,
        rel_types: list[str] | None = None,
    ) -> list[GraphPath]:
        """Expand typed TDM graph paths for one query."""

    def expand_paths(
        self,
        query: str,
        hops: int,
        max_paths: int,
        source_id: str | None = None,
    ) -> list[GraphPath]:
        """Expand generic graph paths for one query."""