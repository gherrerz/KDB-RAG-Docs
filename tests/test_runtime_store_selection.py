"""Focused tests for runtime store selection during legacy cutover."""

from __future__ import annotations

import os

# Ensure runtime import does not attempt a real Postgres connection in test collection.
for _env_name in (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DSN",
    "DATABASE_URL",
):
    os.environ.pop(_env_name, None)

import importlib
import sys


def _build_test_postgres_dsn(default_db: str = "coderag_docs") -> str:
    """Build a DSN for tests from env vars without hardcoded credentials."""
    host = os.environ.get("POSTGRES_HOST", "localhost").strip() or "localhost"
    port = os.environ.get("POSTGRES_PORT", "5432").strip() or "5432"
    database = os.environ.get("POSTGRES_DB", default_db).strip() or default_db
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()

    if user and password:
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return f"postgresql://{host}:{port}/{database}"


_TEST_POSTGRES_DSN = _build_test_postgres_dsn()


def _import_runtime_module(monkeypatch):
    """Import runtime with patched bootstrap dependencies for hermetic tests."""
    import coderag.core.settings as settings_module
    import coderag.storage.hybrid_metadata_store as hybrid_module
    import coderag.storage.postgres_ingestion_artifact_store as artifact_module
    import coderag.storage.postgres_startup as startup_module

    class _BootstrapHybridStore:
        def __init__(self, *, postgres_dsn: str) -> None:
            self.postgres_dsn = postgres_dsn

    class _BootstrapArtifactStore:
        def __init__(self, postgres_dsn: str) -> None:
            self.postgres_dsn = postgres_dsn

    monkeypatch.setattr(
        settings_module,
        "resolve_postgres_dsn",
        lambda settings: _TEST_POSTGRES_DSN,
    )
    monkeypatch.setattr(
        startup_module,
        "ensure_postgres_schema_ready",
        lambda settings, force=False: {
            "policy": "validate",
            "action": "validated",
            "current_heads": [],
            "expected_heads": [],
            "cached": False,
        },
    )
    monkeypatch.setattr(
        hybrid_module,
        "HybridMetadataStore",
        _BootstrapHybridStore,
    )
    monkeypatch.setattr(
        artifact_module,
        "PostgresIngestionArtifactStore",
        _BootstrapArtifactStore,
    )

    sys.modules.pop("coderag.core.runtime", None)
    return importlib.import_module("coderag.core.runtime")


def test_build_runtime_store_requires_postgres_configuration(
    monkeypatch,
) -> None:
    """Runtime store builder should fail fast when Postgres is unset."""
    runtime = _import_runtime_module(monkeypatch)

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
    import coderag.storage.hybrid_metadata_store as hybrid_module

    runtime = _import_runtime_module(monkeypatch)
    captured: dict[str, object] = {}

    class _FakeHybridStore:
        def __init__(self, *, postgres_dsn: str) -> None:
            captured["postgres_dsn"] = postgres_dsn

    monkeypatch.setattr(
        runtime,
        "resolve_postgres_dsn",
        lambda settings: _TEST_POSTGRES_DSN,
    )
    monkeypatch.setattr(hybrid_module, "HybridMetadataStore", _FakeHybridStore)

    store = runtime._build_runtime_store()

    assert isinstance(store, _FakeHybridStore)
    assert captured["postgres_dsn"] == _TEST_POSTGRES_DSN


def test_build_ingestion_artifact_store_requires_postgres_configuration(
    monkeypatch,
) -> None:
    """Artifact store builder should fail fast when Postgres is unset."""
    runtime = _import_runtime_module(monkeypatch)

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
    import coderag.storage.postgres_ingestion_artifact_store as artifact_module

    runtime = _import_runtime_module(monkeypatch)
    captured: dict[str, object] = {}

    class _FakeArtifactStore:
        def __init__(self, postgres_dsn: str) -> None:
            captured["postgres_dsn"] = postgres_dsn

    monkeypatch.setattr(
        runtime,
        "resolve_postgres_dsn",
        lambda settings: _TEST_POSTGRES_DSN,
    )
    monkeypatch.setattr(
        artifact_module,
        "PostgresIngestionArtifactStore",
        _FakeArtifactStore,
    )

    store = runtime._build_ingestion_artifact_store()

    assert isinstance(store, _FakeArtifactStore)
    assert captured["postgres_dsn"] == _TEST_POSTGRES_DSN