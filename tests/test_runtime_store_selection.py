"""Focused tests for runtime store selection during legacy cutover."""

from __future__ import annotations

import coderag.core.runtime as runtime
import coderag.storage.postgres_ingestion_artifact_store as artifact_module
import coderag.storage.hybrid_metadata_store as hybrid_module


def test_build_runtime_store_requires_postgres_configuration(
    monkeypatch,
) -> None:
    """Runtime store builder should fail fast when Postgres is unset."""

    monkeypatch.setattr(runtime, "resolve_postgres_dsn", lambda settings: "")

    try:
        runtime._build_runtime_store()
    except RuntimeError as exc:
        assert "Postgres runtime store is required" in str(exc)
    else:  # pragma: no cover - defensive guard for regression clarity
        raise AssertionError("Expected runtime store builder to fail")


def test_build_runtime_store_does_not_instantiate_sqlite_when_postgres_exists(
    monkeypatch,
) -> None:
    """Postgres runtime should build store router with DSN only."""
    captured: dict[str, object] = {}

    class _FakeHybridStore:
        def __init__(self, *, postgres_dsn: str) -> None:
            captured["postgres_dsn"] = postgres_dsn

    monkeypatch.setattr(
        runtime,
        "resolve_postgres_dsn",
        lambda settings: "postgresql://docs:secret@db.local/docs",
    )
    monkeypatch.setattr(hybrid_module, "HybridMetadataStore", _FakeHybridStore)

    store = runtime._build_runtime_store()

    assert isinstance(store, _FakeHybridStore)
    assert captured["postgres_dsn"] == "postgresql://docs:secret@db.local/docs"


def test_build_ingestion_artifact_store_requires_postgres_configuration(
    monkeypatch,
) -> None:
    """Artifact store builder should fail fast when Postgres is unset."""
    monkeypatch.setattr(runtime, "resolve_postgres_dsn", lambda settings: "")

    try:
        runtime._build_ingestion_artifact_store()
    except RuntimeError as exc:
        assert "Postgres ingestion artifacts store is required" in str(exc)
    else:  # pragma: no cover - defensive guard for regression clarity
        raise AssertionError("Expected ingestion artifacts builder to fail")


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