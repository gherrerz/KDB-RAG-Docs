"""Focused tests for runtime store selection during legacy cutover."""

from __future__ import annotations

from pathlib import Path

import coderag.core.runtime as runtime
import coderag.storage.postgres_ingestion_artifact_store as artifact_module
import coderag.storage.hybrid_metadata_store as hybrid_module


def test_build_runtime_store_uses_sqlite_only_without_postgres(
    monkeypatch,
) -> None:
    """Legacy SQLite store should still be built only when Postgres is unset."""

    class _RecordingMetadataStore:
        def __init__(self, db_path: Path) -> None:
            self.db_path = db_path

    monkeypatch.setattr(runtime, "resolve_postgres_dsn", lambda settings: "")
    monkeypatch.setattr(runtime, "MetadataStore", _RecordingMetadataStore)

    store = runtime._build_runtime_store()

    assert isinstance(store, _RecordingMetadataStore)
    assert store.db_path == Path(runtime.SETTINGS.data_dir) / "metadata.db"


def test_build_runtime_store_does_not_instantiate_sqlite_when_postgres_exists(
    monkeypatch,
) -> None:
    """Postgres runtime should not touch metadata.db or a real SQLite store."""
    captured: dict[str, object] = {}

    class _FakeHybridStore:
        def __init__(self, *, sqlite_store, postgres_dsn: str) -> None:
            captured["sqlite_store"] = sqlite_store
            captured["postgres_dsn"] = postgres_dsn

    def _unexpected_metadata_store(_db_path: Path) -> object:
        raise AssertionError("MetadataStore must not be instantiated")

    monkeypatch.setattr(
        runtime,
        "resolve_postgres_dsn",
        lambda settings: "postgresql://docs:secret@db.local/docs",
    )
    monkeypatch.setattr(runtime, "MetadataStore", _unexpected_metadata_store)
    monkeypatch.setattr(hybrid_module, "HybridMetadataStore", _FakeHybridStore)

    store = runtime._build_runtime_store()

    assert isinstance(store, _FakeHybridStore)
    assert captured["postgres_dsn"] == "postgresql://docs:secret@db.local/docs"
    sqlite_store = captured["sqlite_store"]
    assert isinstance(sqlite_store, runtime.DisabledLegacyMetadataStore)
    assert sqlite_store.clear_all_data() == {
        "deleted_documents": 0,
        "deleted_chunks": 0,
        "deleted_graph_edges": 0,
        "deleted_jobs": 0,
    }
    try:
        getattr(sqlite_store, "list_documents")
    except AttributeError as exc:
        assert "SQLite fallback is disabled" in str(exc)
    else:  # pragma: no cover - defensive guard for regression clarity
        raise AssertionError("Expected disabled legacy fallback to raise")


def test_build_ingestion_artifact_store_uses_null_without_postgres(
    monkeypatch,
) -> None:
    """Runtime should expose no-op artifact store when Postgres is unset."""
    monkeypatch.setattr(runtime, "resolve_postgres_dsn", lambda settings: "")

    store = runtime._build_ingestion_artifact_store()

    assert isinstance(store, runtime.NullIngestionArtifactStore)


def test_build_ingestion_artifact_store_uses_postgres_when_configured(
    monkeypatch,
) -> None:
    """Runtime should build Postgres artifact store when DSN is configured."""
    captured: dict[str, object] = {}

    class _FakeArtifactStore:
        def __init__(self, postgres_dsn: str) -> None:
            captured["postgres_dsn"] = postgres_dsn

    monkeypatch.setattr(
        runtime,
        "resolve_postgres_dsn",
        lambda settings: "postgresql://docs:secret@db.local/docs",
    )
    monkeypatch.setattr(
        artifact_module,
        "PostgresIngestionArtifactStore",
        _FakeArtifactStore,
    )

    store = runtime._build_ingestion_artifact_store()

    assert isinstance(store, _FakeArtifactStore)
    assert captured["postgres_dsn"] == "postgresql://docs:secret@db.local/docs"