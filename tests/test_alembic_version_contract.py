"""Contract tests to prevent Alembic version-table regressions."""

from __future__ import annotations

import os
import re
from pathlib import Path

from coderag.storage import postgres_startup

_DOCS_VERSION_TABLE = "alembic_version_docs"
_CRITICAL_FILES = (
    Path("alembic.ini"),
    Path("migrations/env.py"),
    Path("src/coderag/storage/postgres_startup.py"),
)


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


def test_critical_files_do_not_use_legacy_alembic_version_literal() -> None:
    """Critical migration paths must never fallback to alembic_version."""
    legacy_pattern = re.compile(r"version_table\s*=\s*alembic_version(\s|$)")

    for file_path in _CRITICAL_FILES:
        content = file_path.read_text(encoding="utf-8")
        assert '"alembic_version"' not in content
        assert "'alembic_version'" not in content
        assert legacy_pattern.search(content) is None


def test_docs_version_table_is_explicit_in_all_critical_layers() -> None:
    """Config, migration env and runtime helpers must pin docs table."""
    alembic_ini = Path("alembic.ini").read_text(encoding="utf-8")
    migration_env = Path("migrations/env.py").read_text(encoding="utf-8")
    startup_module = Path("src/coderag/storage/postgres_startup.py").read_text(
        encoding="utf-8"
    )

    assert "version_table = alembic_version_docs" in alembic_ini
    assert 'return "alembic_version_docs"' in migration_env
    assert (
        '_DEFAULT_ALEMBIC_VERSION_TABLE = "alembic_version_docs"'
        in startup_module
    )


def test_bootstrap_helper_pins_docs_version_table() -> None:
    """Bootstrap helper should always resolve the docs version table."""
    dsn = _build_test_postgres_dsn(default_db="coipo_db")
    config = postgres_startup._build_alembic_config(dsn)

    assert config.get_main_option("version_table") == _DOCS_VERSION_TABLE