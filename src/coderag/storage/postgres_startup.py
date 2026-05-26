"""Bootstrap and validation helpers for the future PostgreSQL runtime."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Literal

from coderag.core.settings import Settings, resolve_postgres_dsn


PostgresStartupPolicy = Literal["auto_upgrade", "validate"]

_BOOTSTRAP_CACHE: dict[tuple[str, PostgresStartupPolicy], dict[str, Any]] = {}


def _repo_root() -> Path:
    """Resolve repository root from the current src layout."""
    return Path(__file__).resolve().parents[3]


def _build_alembic_config(postgres_dsn: str) -> Any:
    """Build Alembic configuration bound to the effective DSN."""
    from coderag.storage.postgres_session import to_sqlalchemy_postgres_url

    config_module = importlib.import_module("alembic.config")
    config_class = getattr(config_module, "Config")
    config = config_class(str(_repo_root() / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        to_sqlalchemy_postgres_url(postgres_dsn),
    )
    return config


def _read_database_heads(postgres_dsn: str) -> set[str]:
    """Read the currently applied Alembic heads from the database."""
    from coderag.storage.postgres_session import to_sqlalchemy_postgres_url

    migration_module = importlib.import_module("alembic.runtime.migration")
    sqlalchemy_module = importlib.import_module("sqlalchemy")
    migration_context = getattr(migration_module, "MigrationContext")
    create_engine = getattr(sqlalchemy_module, "create_engine")
    engine = create_engine(to_sqlalchemy_postgres_url(postgres_dsn))
    try:
        with engine.connect() as connection:
            context = migration_context.configure(connection)
            return set(context.get_current_heads())
    finally:
        engine.dispose()


def ensure_postgres_schema_ready(
    settings: Settings,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Validate or bootstrap the PostgreSQL migration chain when enabled."""
    postgres_dsn = resolve_postgres_dsn(settings)
    policy = settings.resolve_postgres_startup_policy()

    if not postgres_dsn:
        return {
            "enabled": False,
            "policy": policy,
            "action": "skipped",
            "current_heads": [],
            "expected_heads": [],
            "cached": False,
        }

    try:
        command_module = importlib.import_module("alembic.command")
        script_module = importlib.import_module("alembic.script")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PostgreSQL bootstrap requires Alembic to be installed. "
            "Install the runtime dependencies before enabling POSTGRES_HOST."
        ) from exc

    command = command_module
    script_directory = getattr(script_module, "ScriptDirectory")

    cache_key = (postgres_dsn, policy)
    if not force:
        cached = _BOOTSTRAP_CACHE.get(cache_key)
        if cached is not None:
            report = dict(cached)
            report["cached"] = True
            return report

    config = _build_alembic_config(postgres_dsn)
    script = script_directory.from_config(config)
    expected_heads = set(script.get_heads())
    current_heads = _read_database_heads(postgres_dsn)
    action = "validated"

    if not expected_heads:
        action = "no_migrations_registered"
    elif policy == "auto_upgrade" and current_heads != expected_heads:
        command.upgrade(config, "head")
        current_heads = _read_database_heads(postgres_dsn)
        action = "upgraded"
    elif current_heads != expected_heads:
        raise RuntimeError(
            "PostgreSQL is not aligned with the expected Alembic heads. "
            f"Current: {sorted(current_heads) or ['<none>']}. Expected: "
            f"{sorted(expected_heads) or ['<none>']}."
        )

    report = {
        "enabled": True,
        "policy": policy,
        "action": action,
        "current_heads": sorted(current_heads),
        "expected_heads": sorted(expected_heads),
        "cached": False,
    }
    _BOOTSTRAP_CACHE[cache_key] = dict(report)
    return report