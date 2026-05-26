# pyright: reportMissingImports=false

"""PostgreSQL-backed async ingestion artifact storage for the Docs cutover."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, insert, select, update

from coderag.storage.postgres_schema import (
    ingestion_artifact_files_table,
    ingestion_artifacts_table,
)
from coderag.storage.postgres_session import PostgresSessionFactory


class PostgresIngestionArtifactStore:
    """Persist upload batches and processing status in PostgreSQL."""

    def __init__(
        self,
        postgres_dsn: str,
        *,
        session_factory: PostgresSessionFactory | None = None,
    ) -> None:
        """Create the store using a reusable SQLAlchemy session factory."""
        self._session_factory = session_factory or PostgresSessionFactory(
            postgres_dsn
        )

    @staticmethod
    def _now() -> datetime:
        """Return a timezone-aware timestamp for writes."""
        return datetime.now(UTC)

    @staticmethod
    def _manifest_entry(file_entry: dict[str, Any]) -> dict[str, Any]:
        """Build one JSON-safe manifest entry from a staged upload file."""
        return {
            "ordinal": int(file_entry["ordinal"]),
            "original_filename": str(file_entry["original_filename"]),
            "staged_filename": str(file_entry["staged_filename"]),
            "media_type": (
                str(file_entry["media_type"])
                if file_entry.get("media_type") is not None
                else None
            ),
            "size_bytes": int(file_entry["size_bytes"]),
            "content_hash": (
                str(file_entry["content_hash"])
                if file_entry.get("content_hash") is not None
                else None
            ),
        }

    @staticmethod
    def _coerce_manifest_list(value: Any) -> list[dict[str, Any]]:
        """Normalize persisted manifest payloads to a list of dicts."""
        if not isinstance(value, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(dict(item))
        return normalized

    def _purge_artifact_payload(
        self,
        artifact_id: str,
        *,
        connection: Any,
    ) -> None:
        """Delete persisted artifact file payload rows for one artifact."""
        statement = delete(ingestion_artifact_files_table).where(
            ingestion_artifact_files_table.c.artifact_id == artifact_id
        )
        connection.execute(statement)

    def create_uploaded_batch_artifact(
        self,
        *,
        source_type: str,
        origin_path_or_url: str | None,
        files: list[dict[str, Any]],
    ) -> str:
        """Persist one uploaded batch and return its artifact id."""
        artifact_id = uuid4().hex
        now = self._now()
        manifest = [self._manifest_entry(file_entry) for file_entry in files]
        total_size_bytes = sum(int(file_entry["size_bytes"]) for file_entry in files)

        artifact_statement = insert(ingestion_artifacts_table).values(
            artifact_id=artifact_id,
            job_id=None,
            source_type=source_type,
            artifact_type="upload-batch",
            origin_path_or_url=origin_path_or_url,
            file_manifest=manifest,
            file_count=len(files),
            total_size_bytes=total_size_bytes,
            processing_status="staged",
            error_message=None,
            created_at=now,
            processing_started_at=None,
            processing_completed_at=None,
            expires_at=now + timedelta(hours=24),
            cleanup_at=None,
        )
        file_rows = [
            {
                "artifact_id": artifact_id,
                "ordinal": int(file_entry["ordinal"]),
                "original_filename": str(file_entry["original_filename"]),
                "media_type": (
                    str(file_entry["media_type"])
                    if file_entry.get("media_type") is not None
                    else None
                ),
                "size_bytes": int(file_entry["size_bytes"]),
                "content_hash": (
                    str(file_entry["content_hash"])
                    if file_entry.get("content_hash") is not None
                    else None
                ),
                "payload": bytes(file_entry["payload"]),
                "created_at": now,
            }
            for file_entry in files
        ]

        with self._session_factory.get_connection() as connection:
            connection.execute(artifact_statement)
            if file_rows:
                connection.execute(insert(ingestion_artifact_files_table).values(file_rows))
        return artifact_id

    def attach_job(self, artifact_id: str, job_id: str) -> None:
        """Attach one async job id to an already persisted upload artifact."""
        statement = (
            update(ingestion_artifacts_table)
            .where(ingestion_artifacts_table.c.artifact_id == artifact_id)
            .values(
                job_id=job_id,
                processing_status="queued",
                error_message=None,
            )
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def mark_processing_started(self, artifact_id: str) -> None:
        """Mark one artifact as actively being processed."""
        statement = (
            update(ingestion_artifacts_table)
            .where(ingestion_artifacts_table.c.artifact_id == artifact_id)
            .values(
                processing_status="processing",
                processing_started_at=self._now(),
                error_message=None,
            )
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def mark_processing_completed(self, artifact_id: str) -> None:
        """Mark one artifact as processed and ready for staged cleanup."""
        now = self._now()
        statement = (
            update(ingestion_artifacts_table)
            .where(ingestion_artifacts_table.c.artifact_id == artifact_id)
            .values(
                processing_status="completed",
                processing_completed_at=now,
                cleanup_at=now,
                error_message=None,
            )
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)
            self._purge_artifact_payload(artifact_id, connection=connection)

    def mark_processing_failed(
        self,
        artifact_id: str,
        error_message: str,
    ) -> None:
        """Mark one artifact as failed and ready for staged cleanup."""
        now = self._now()
        statement = (
            update(ingestion_artifacts_table)
            .where(ingestion_artifacts_table.c.artifact_id == artifact_id)
            .values(
                processing_status="failed",
                processing_completed_at=now,
                cleanup_at=now,
                error_message=error_message,
            )
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)
            self._purge_artifact_payload(artifact_id, connection=connection)

    def materialize_uploaded_batch(self, artifact_id: str) -> str:
        """Restore one uploaded batch to a temporary directory for workers."""
        artifact_statement = select(
            ingestion_artifacts_table.c.file_manifest,
        ).where(ingestion_artifacts_table.c.artifact_id == artifact_id)
        file_statement = (
            select(
                ingestion_artifact_files_table.c.ordinal,
                ingestion_artifact_files_table.c.original_filename,
                ingestion_artifact_files_table.c.payload,
            )
            .where(ingestion_artifact_files_table.c.artifact_id == artifact_id)
            .order_by(ingestion_artifact_files_table.c.ordinal.asc())
        )
        with self._session_factory.get_connection() as connection:
            artifact_row = connection.execute(artifact_statement).mappings().one_or_none()
            file_rows = connection.execute(file_statement).mappings().all()

        if artifact_row is None:
            raise KeyError(f"Unknown artifact_id: {artifact_id}")
        if not file_rows:
            raise ValueError(f"Artifact has no persisted files: {artifact_id}")

        manifest_rows = self._coerce_manifest_list(artifact_row["file_manifest"])
        manifest_by_ordinal = {
            int(item.get("ordinal", -1)): item
            for item in manifest_rows
            if isinstance(item.get("ordinal"), int)
        }

        temp_dir = Path(tempfile.mkdtemp(prefix="coderag-artifact-"))
        for row in file_rows:
            ordinal = int(row["ordinal"])
            manifest = manifest_by_ordinal.get(ordinal, {})
            target_name = row["original_filename"]
            staged_filename = manifest.get("staged_filename")
            if isinstance(staged_filename, str) and staged_filename.strip():
                target_name = staged_filename.strip()

            destination = temp_dir / str(target_name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(bytes(row["payload"]))

        return str(temp_dir)

    def clear_uploaded_artifacts(self) -> int:
        """Delete persisted upload artifacts during a full reset."""
        statement = delete(ingestion_artifacts_table)
        with self._session_factory.get_connection() as connection:
            result = connection.execute(statement)
        return max(0, int(result.rowcount or 0))

    def purge_expired_uploaded_artifacts(self) -> int:
        """Delete expired artifact metadata that already passed their TTL."""
        statement = delete(ingestion_artifacts_table).where(
            ingestion_artifacts_table.c.expires_at <= self._now()
        )
        with self._session_factory.get_connection() as connection:
            result = connection.execute(statement)
        return max(0, int(result.rowcount or 0))