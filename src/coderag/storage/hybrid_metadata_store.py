"""Hybrid metadata store used during the SQLite to Postgres cutover."""

from __future__ import annotations

from typing import Any

from coderag.core.models import (
    ChunkRecord,
    DocumentCatalogEntry,
    DocumentRecord,
    JobStatus,
)
from coderag.storage.postgres_document_chunk_store import PostgresDocumentChunkStore
from coderag.storage.postgres_job_state_store import PostgresJobStateStore
from coderag.storage.postgres_tdm_store import PostgresTdmStore


class HybridMetadataStore:
    """Route runtime metadata operations to Postgres stores."""

    def __init__(
        self,
        *,
        postgres_dsn: str,
    ) -> None:
        """Build the runtime store backed only by Postgres slices."""
        self._postgres_store = PostgresJobStateStore(postgres_dsn)
        self._postgres_document_store = PostgresDocumentChunkStore(postgres_dsn)
        self._postgres_tdm_store = PostgresTdmStore(postgres_dsn)

    def upsert_job(self, job: JobStatus) -> None:
        """Persist job snapshots in Postgres."""
        self._postgres_store.upsert_job(job)

    def upsert_document(self, doc: DocumentRecord) -> None:
        """Persist document rows in Postgres."""
        self._postgres_document_store.upsert_document(doc)

    def upsert_documents(self, docs: list[DocumentRecord]) -> int:
        """Persist many document rows in Postgres."""
        return self._postgres_document_store.upsert_documents(docs)

    def replace_chunks(self, source_id: str, chunks: list[ChunkRecord]) -> None:
        """Persist chunk replacement operations in Postgres."""
        self._postgres_document_store.replace_chunks(source_id, chunks)

    def list_chunks(self, source_id: str | None = None) -> list[ChunkRecord]:
        """Read chunks from Postgres."""
        return self._postgres_document_store.list_chunks(source_id=source_id)

    def get_document_map(
        self,
        source_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Read the document map from Postgres."""
        return self._postgres_document_store.get_document_map(source_id=source_id)

    def list_documents(
        self,
        source_id: str | None = None,
        tags: list[str] | None = None,
    ) -> list[DocumentCatalogEntry]:
        """Read the document catalog from Postgres."""
        return self._postgres_document_store.list_documents(
            source_id=source_id,
            tags=tags,
        )

    def get_document_by_id(
        self,
        document_id: str,
    ) -> DocumentCatalogEntry | None:
        """Read one persisted document from Postgres."""
        return self._postgres_document_store.get_document_by_id(document_id)

    def list_tag_facets(
        self,
        source_id: str | None = None,
    ) -> list[tuple[str, int]]:
        """Read tag facets from Postgres."""
        return self._postgres_document_store.list_tag_facets(source_id=source_id)

    def list_unique_tags(self, source_id: str | None = None) -> list[str]:
        """Read distinct normalized tags from Postgres."""
        return [
            tag
            for tag, _count in self._postgres_document_store.list_tag_facets(
                source_id=source_id
            )
        ]

    def replace_document_tags(
        self,
        document_id: str,
        tags: list[object],
    ) -> dict[str, Any] | None:
        """Update persisted document tags in Postgres."""
        return self._postgres_document_store.replace_document_tags(
            document_id,
            tags,
        )

    def find_documents_by_title_and_content_type(
        self,
        title: str,
        content_type: str,
    ) -> list[DocumentCatalogEntry]:
        """Read dedup lookup candidates from Postgres."""
        return self._postgres_document_store.find_documents_by_title_and_content_type(
            title,
            content_type,
        )

    def delete_document_by_id(self, document_id: str) -> int:
        """Delete document rows from Postgres."""
        return self._postgres_document_store.delete_document_by_id(document_id)

    def delete_chunks_by_document_id(self, document_id: str) -> int:
        """Delete chunk rows from Postgres."""
        return self._postgres_document_store.delete_chunks_by_document_id(
            document_id
        )

    def upsert_tdm_schema(
        self,
        schema_id: str,
        source_id: str,
        database_name: str,
        schema_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist TDM schema rows in Postgres."""
        self._postgres_tdm_store.upsert_tdm_schema(
            schema_id=schema_id,
            source_id=source_id,
            database_name=database_name,
            schema_name=schema_name,
            metadata=metadata,
        )

    def list_tdm_schemas(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read TDM schemas from Postgres."""
        return self._postgres_tdm_store.list_tdm_schemas(source_id=source_id)

    def upsert_tdm_table(
        self,
        table_id: str,
        source_id: str,
        schema_id: str,
        table_name: str,
        table_type: str = "table",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist TDM table rows in Postgres."""
        self._postgres_tdm_store.upsert_tdm_table(
            table_id=table_id,
            source_id=source_id,
            schema_id=schema_id,
            table_name=table_name,
            table_type=table_type,
            metadata=metadata,
        )

    def list_tdm_tables(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read TDM tables from Postgres."""
        return self._postgres_tdm_store.list_tdm_tables(source_id=source_id)

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
        """Persist TDM column rows in Postgres."""
        self._postgres_tdm_store.upsert_tdm_column(
            column_id=column_id,
            source_id=source_id,
            table_id=table_id,
            column_name=column_name,
            data_type=data_type,
            nullable=nullable,
            pii_class=pii_class,
            metadata=metadata,
        )

    def list_tdm_columns(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read TDM columns from Postgres."""
        return self._postgres_tdm_store.list_tdm_columns(source_id=source_id)

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
        """Persist TDM service mappings in Postgres."""
        self._postgres_tdm_store.upsert_tdm_service_mapping(
            mapping_id=mapping_id,
            source_id=source_id,
            service_name=service_name,
            endpoint=endpoint,
            method=method,
            table_id=table_id,
            metadata=metadata,
        )

    def list_tdm_service_mappings(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read TDM service mappings from Postgres."""
        return self._postgres_tdm_store.list_tdm_service_mappings(
            source_id=source_id
        )

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
        """Persist TDM masking rules in Postgres."""
        self._postgres_tdm_store.upsert_tdm_masking_rule(
            rule_id=rule_id,
            source_id=source_id,
            rule_name=rule_name,
            policy_type=policy_type,
            scope=scope,
            table_id=table_id,
            column_id=column_id,
            priority=priority,
            metadata=metadata,
        )

    def list_tdm_masking_rules(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read TDM masking rules from Postgres."""
        return self._postgres_tdm_store.list_tdm_masking_rules(
            source_id=source_id
        )

    def upsert_tdm_virtualization_artifact(
        self,
        artifact_id: str,
        source_id: str,
        service_name: str,
        artifact_type: str,
        content: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist TDM virtualization artifacts in Postgres."""
        self._postgres_tdm_store.upsert_tdm_virtualization_artifact(
            artifact_id=artifact_id,
            source_id=source_id,
            service_name=service_name,
            artifact_type=artifact_type,
            content=content,
            metadata=metadata,
        )

    def list_tdm_virtualization_artifacts(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read TDM virtualization artifacts from Postgres."""
        return self._postgres_tdm_store.list_tdm_virtualization_artifacts(
            source_id=source_id
        )

    def upsert_tdm_synthetic_profile(
        self,
        profile_id: str,
        source_id: str,
        profile_name: str,
        strategy: str = "template",
        target_table_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist TDM synthetic profiles in Postgres."""
        self._postgres_tdm_store.upsert_tdm_synthetic_profile(
            profile_id=profile_id,
            source_id=source_id,
            profile_name=profile_name,
            strategy=strategy,
            target_table_id=target_table_id,
            metadata=metadata,
        )

    def list_tdm_synthetic_profiles(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read TDM synthetic profiles from Postgres."""
        return self._postgres_tdm_store.list_tdm_synthetic_profiles(
            source_id=source_id
        )

    def get_job(self, job_id: str) -> JobStatus | None:
        """Read jobs from Postgres."""
        return self._postgres_store.get_job(job_id)

    def touch_job(self, job_id: str, status: str, message: str) -> JobStatus:
        """Update jobs in Postgres."""
        return self._postgres_store.touch_job(job_id, status, message)

    def append_job_event(
        self,
        job_id: str,
        ordinal: int,
        name: str,
        status: str,
        elapsed_ms: float,
        details: dict[str, Any],
    ) -> None:
        """Persist timeline events in Postgres."""
        self._postgres_store.append_job_event(
            job_id,
            ordinal,
            name,
            status,
            elapsed_ms,
            details,
        )

    def list_job_events(self, job_id: str) -> list[dict[str, Any]]:
        """Read timeline events from Postgres."""
        return self._postgres_store.list_job_events(job_id)

    def get_runtime_state(self, key: str) -> str | None:
        """Read runtime state values from Postgres."""
        return self._postgres_store.get_runtime_state(key)

    def set_runtime_state(self, key: str, value: str) -> None:
        """Persist runtime state values in Postgres."""
        self._postgres_store.set_runtime_state(key, value)

    def get_index_version(self) -> int:
        """Read shared index version from Postgres."""
        return self._postgres_store.get_index_version()

    def bump_index_version(self) -> int:
        """Increment shared index version in Postgres."""
        return self._postgres_store.bump_index_version()

    def clear_all_data(self) -> dict[str, int]:
        """Clear Postgres-managed runtime data while keeping schema intact."""
        deleted_document_data = self._postgres_document_store.clear_document_data()
        self._postgres_tdm_store.clear_tdm_data()
        deleted_postgres_jobs = self._postgres_store.clear_jobs()
        return {
            "deleted_documents": int(
                deleted_document_data.get("deleted_documents", 0)
            ),
            "deleted_chunks": int(deleted_document_data.get("deleted_chunks", 0)),
            "deleted_jobs": int(deleted_postgres_jobs),
        }