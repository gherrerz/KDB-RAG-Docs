"""Shared SQLAlchemy connection helpers for Docs PostgreSQL storage."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.exc import OperationalError as SqlAlchemyOperationalError
from sqlalchemy.orm import Session, sessionmaker

from coderag.core.settings import resolve_postgres_dsn


def _describe_postgres_target(postgres_dsn: str) -> tuple[str, str]:
    """Summarize the DSN target without exposing credentials."""
    parsed = urlsplit(postgres_dsn)
    host = parsed.hostname or "<unknown-host>"
    port = parsed.port or 5432
    database = parsed.path.lstrip("/") or "<unknown-db>"
    return host, f"{host}:{port}/{database}"


def to_sqlalchemy_postgres_url(postgres_dsn: str) -> str:
    """Normalize DSN to an explicit SQLAlchemy psycopg URL."""
    normalized = postgres_dsn.strip()
    if normalized.startswith("postgresql+psycopg://"):
        return normalized
    if normalized.startswith("postgresql://"):
        return normalized.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )
    if normalized.startswith("postgres://"):
        return normalized.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )
    return normalized


def _coerce_positive_int(value: Any, default: int) -> int:
    """Normalize a positive integer or return a safe default."""
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized > 0 else default


def _coerce_positive_float(value: Any, default: float) -> float:
    """Normalize a positive float or return a safe default."""
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized > 0 else default


class PostgresSessionFactory:
    """Manage shared SQLAlchemy engine and sessions for Postgres."""

    def __init__(
        self,
        postgres_dsn: str,
        *,
        pool_size: int = 5,
        pool_timeout: float = 30.0,
    ) -> None:
        """Build a reusable SQLAlchemy session factory."""
        self._url = postgres_dsn
        self._pool_size = _coerce_positive_int(pool_size, 5)
        self._pool_timeout = _coerce_positive_float(pool_timeout, 30.0)
        self._engine = self._build_engine()
        self._session_factory = sessionmaker(
            bind=self._engine,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )

    @classmethod
    def from_settings(cls, settings: object) -> "PostgresSessionFactory":
        """Build the factory from Settings or test doubles."""
        postgres_dsn = resolve_postgres_dsn(settings)
        if not postgres_dsn:
            raise ValueError(
                "Could not build PostgresSessionFactory: empty DSN. Configure "
                "POSTGRES_HOST and valid credentials."
            )

        return cls(
            postgres_dsn,
            pool_size=getattr(settings, "postgres_pool_size", 5),
            pool_timeout=getattr(settings, "postgres_pool_timeout", 30.0),
        )

    @property
    def engine(self) -> Engine:
        """Expose the shared engine for SQL Core use cases."""
        return self._engine

    def _build_engine(self) -> Engine:
        """Create the SQLAlchemy engine with the configured pool."""
        return create_engine(
            to_sqlalchemy_postgres_url(self._url),
            pool_pre_ping=True,
            pool_size=self._pool_size,
            pool_timeout=self._pool_timeout,
        )

    @contextmanager
    def get_session(self) -> Iterator[Session]:
        """Open a SQLAlchemy session with normalized connection errors."""
        session = self._session_factory()
        try:
            yield session
        except SqlAlchemyOperationalError as exc:
            raise self._build_connection_error(exc) from exc
        finally:
            session.close()

    @contextmanager
    def get_connection(self) -> Iterator[Connection]:
        """Open a SQLAlchemy transaction-scoped connection."""
        try:
            with self._engine.begin() as connection:
                yield connection
        except SqlAlchemyOperationalError as exc:
            raise self._build_connection_error(exc) from exc

    def _build_connection_error(self, exc: Exception) -> RuntimeError:
        """Normalize operational errors without exposing credentials."""
        host, target = _describe_postgres_target(self._url)
        compose_hint = ""
        if host == "postgres":
            compose_hint = (
                " If you use docker-compose, host 'postgres' only exists when "
                "the remote profile is active."
            )
        return RuntimeError(
            "Could not connect to Postgres at "
            f"{target}. Check POSTGRES_HOST/POSTGRES_PORT and ensure the "
            f"host is reachable from this runtime.{compose_hint} Original "
            f"error: {exc}"
        )