"""Alembic environment for the future PostgreSQL schema in Docs."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from coderag.core.settings import get_settings, resolve_postgres_dsn
from coderag.storage.postgres_schema import POSTGRES_SCHEMA_METADATA
from coderag.storage.postgres_session import to_sqlalchemy_postgres_url


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = POSTGRES_SCHEMA_METADATA


def _get_alembic_version_table() -> str:
    """Resolve the Alembic version table used by this project."""
    configured_table = (config.get_main_option("version_table") or "").strip()
    if configured_table:
        return configured_table
    return "alembic_version_docs"


def _has_explicit_sqlalchemy_url(configured_url: str) -> bool:
    """Return whether Alembic already has a usable SQLAlchemy URL."""
    normalized = configured_url.strip()
    if not normalized:
        return False
    return normalized not in {
        "postgres://",
        "postgresql://",
        "postgresql+psycopg://",
    }


def _get_postgres_url() -> str:
    """Resolve the PostgreSQL URL used by Alembic."""
    configured_url = (config.get_main_option("sqlalchemy.url") or "").strip()
    if _has_explicit_sqlalchemy_url(configured_url):
        return configured_url

    settings = get_settings()
    postgres_url = resolve_postgres_dsn(settings)
    if not postgres_url:
        raise RuntimeError(
            "No PostgreSQL DSN could be resolved for Alembic. Configure "
            "POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER and "
            "POSTGRES_PASSWORD before running migrations."
        )
    return to_sqlalchemy_postgres_url(postgres_url)


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    context.configure(
        url=_get_postgres_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table=_get_alembic_version_table(),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_postgres_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table=_get_alembic_version_table(),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()