"""Runtime singletons used by UI and API in local deployments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from coderag.core.protocols import (
    IngestionArtifactStoreProtocol,
    RuntimeStoreProtocol,
)
from coderag.core.settings import SETTINGS, resolve_postgres_dsn
from coderag.storage.postgres_startup import ensure_postgres_schema_ready


class NullIngestionArtifactStore:
    """No-op artifact store used until Postgres async artifacts are enabled."""

    def create_uploaded_batch_artifact(
        self,
        *,
        source_type: str,
        origin_path_or_url: str | None,
        files: list[dict[str, Any]],
    ) -> str | None:
        """Skip artifact persistence when Postgres is not configured."""
        return None

    def attach_job(self, artifact_id: str, job_id: str) -> None:
        """Skip job attachment when Postgres is not configured."""

    def mark_processing_started(self, artifact_id: str) -> None:
        """Skip state changes when Postgres is not configured."""

    def mark_processing_completed(self, artifact_id: str) -> None:
        """Skip state changes when Postgres is not configured."""

    def mark_processing_failed(
        self,
        artifact_id: str,
        error_message: str,
    ) -> None:
        """Skip state changes when Postgres is not configured."""

    def materialize_uploaded_batch(self, artifact_id: str) -> str | None:
        """Skip artifact materialization when Postgres is not configured."""
        return None

    def clear_uploaded_artifacts(self) -> int:
        """Skip artifact cleanup when Postgres is not configured."""
        return 0

    def purge_expired_uploaded_artifacts(self) -> int:
        """Skip TTL cleanup when Postgres is not configured."""
        return 0


def _build_runtime_store() -> RuntimeStoreProtocol:
    """Build the runtime store for the final Postgres-only contract."""
    postgres_dsn = resolve_postgres_dsn(SETTINGS)
    if not postgres_dsn:
        raise RuntimeError(
            "Postgres runtime store is required. Configure POSTGRES_HOST, "
            "POSTGRES_DB, POSTGRES_USER, and POSTGRES_PASSWORD."
        )

    from coderag.storage.hybrid_metadata_store import HybridMetadataStore

    return HybridMetadataStore(
        postgres_dsn=postgres_dsn,
    )


def _build_ingestion_artifact_store() -> IngestionArtifactStoreProtocol:
    """Build the async ingestion artifact store for Postgres-only runtime."""
    postgres_dsn = resolve_postgres_dsn(SETTINGS)
    if not postgres_dsn:
        raise RuntimeError(
            "Postgres ingestion artifacts store is required. Configure "
            "POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, and "
            "POSTGRES_PASSWORD."
        )

    from coderag.storage.postgres_ingestion_artifact_store import (
        PostgresIngestionArtifactStore,
    )

    return PostgresIngestionArtifactStore(postgres_dsn)


@dataclass
class RuntimeState:
    """Shared state for lightweight local execution."""

    postgres_bootstrap_report: dict[str, Any] = field(
        default_factory=lambda: ensure_postgres_schema_ready(SETTINGS)
    )

    store: RuntimeStoreProtocol = field(default_factory=_build_runtime_store)
    ingestion_artifact_store: IngestionArtifactStoreProtocol = field(
        default_factory=_build_ingestion_artifact_store
    )


RUNTIME = RuntimeState()
