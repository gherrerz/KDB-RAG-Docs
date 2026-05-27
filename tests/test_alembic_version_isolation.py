"""Tests for Alembic version table isolation in Docs runtime."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from coderag.storage import postgres_startup


def _build_test_postgres_dsn(default_db: str) -> str:
    """Build a test DSN from env vars without hardcoded credentials."""
    host = os.environ.get("POSTGRES_HOST", "localhost").strip() or "localhost"
    port = os.environ.get("POSTGRES_PORT", "5432").strip() or "5432"
    database = os.environ.get("POSTGRES_DB", default_db).strip() or default_db
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()

    if user and password:
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return f"postgresql://{host}:{port}/{database}"


def test_alembic_ini_declares_docs_version_table() -> None:
    """Docs Alembic config should pin its own version table."""
    content = Path("alembic.ini").read_text(encoding="utf-8")

    assert "script_location = migrations" in content
    assert "version_table = alembic_version_docs" in content


def test_migrations_env_configures_docs_version_table() -> None:
    """Docs migration env should pass version_table in both modes."""
    content = Path("migrations/env.py").read_text(encoding="utf-8")

    assert 'config.get_main_option("version_table")' in content
    assert "version_table=_get_alembic_version_table()" in content


def test_build_alembic_config_sets_docs_version_table() -> None:
    """Bootstrap config should always resolve version_table for Docs."""
    config = postgres_startup._build_alembic_config(
        _build_test_postgres_dsn(default_db="coderag_docs")
    )

    assert config.get_main_option("version_table") == "alembic_version_docs"


def test_read_database_heads_uses_docs_version_table(monkeypatch) -> None:
    """Head inspection must target the Docs Alembic version table."""
    captured: dict[str, object] = {}

    class _FakeMigrationContext:
        def get_current_heads(self) -> list[str]:
            return ["0001_core_documents_jobs_runtime"]

    class _FakeEngine:
        def connect(self) -> "_FakeConnectionContext":
            return _FakeConnectionContext()

        def dispose(self) -> None:
            return None

    class _FakeConnectionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            tb: object,
        ) -> bool:
            return False

    def _fake_migration_configure(
        connection: object,
        opts: dict[str, object] | None = None,
    ) -> _FakeMigrationContext:
        captured["opts"] = opts or {}
        return _FakeMigrationContext()

    def _fake_import_module(name: str) -> object:
        if name == "alembic.runtime.migration":
            return SimpleNamespace(
                MigrationContext=SimpleNamespace(configure=_fake_migration_configure)
            )
        if name == "sqlalchemy":
            return SimpleNamespace(create_engine=lambda url: _FakeEngine())
        raise AssertionError(f"Unexpected module requested: {name}")

    monkeypatch.setattr(postgres_startup.importlib, "import_module", _fake_import_module)

    heads = postgres_startup._read_database_heads(
        _build_test_postgres_dsn(default_db="coderag_docs")
    )

    assert heads == {"0001_core_documents_jobs_runtime"}
    assert captured["opts"] == {"version_table": "alembic_version_docs"}
