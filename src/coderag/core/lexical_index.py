"""Contracts and backend selection for Docs lexical retrieval."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from coderag.core.models import ChunkRecord
from coderag.core.settings import resolve_postgres_dsn
from coderag.storage.postgres_session import PostgresSessionFactory


@runtime_checkable
class QueryLexicalIndex(Protocol):
    """Minimal contract shared by query-time lexical backends."""

    backend_label: str

    def rebuild(
        self,
        chunks: Sequence[ChunkRecord],
        document_map: Mapping[str, Mapping[str, object]],
    ) -> None:
        """Rebuild the lexical corpus from the persisted chunk snapshot."""

    def search(
        self,
        query: str,
        top_n: int,
        source_id: str | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        """Return lexical hits sorted by descending score."""

    def clear_all(self) -> None:
        """Remove all indexed lexical corpus rows."""


class DisabledQueryLexicalIndex:
    """Explicit guard used when Postgres lexical storage is unavailable."""

    backend_label = "lexical_unavailable"

    @staticmethod
    def _error() -> RuntimeError:
        return RuntimeError(
            "LexicalStore Postgres es obligatorio en el runtime actual. "
            "Configure POSTGRES_*; BM25 legacy ya no esta soportado como "
            "backend activo."
        )

    def rebuild(
        self,
        chunks: Sequence[ChunkRecord],
        document_map: Mapping[str, Mapping[str, object]],
    ) -> None:
        """Fail explicitly instead of falling back to legacy BM25."""
        raise self._error()

    def search(
        self,
        query: str,
        top_n: int,
        source_id: str | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        """Fail explicitly instead of silently degrading query behavior."""
        raise self._error()

    def clear_all(self) -> None:
        """Fail explicitly because lexical storage is required operationally."""
        raise self._error()


def build_query_lexical_index(settings: object) -> QueryLexicalIndex:
    """Build the active lexical backend for Docs query-time retrieval."""
    postgres_dsn = resolve_postgres_dsn(settings)
    if not postgres_dsn:
        return DisabledQueryLexicalIndex()

    from coderag.storage.lexical_store import LexicalStore

    return LexicalStore(
        postgres_dsn,
        fts_language=getattr(settings, "lexical_fts_language", "english"),
        session_factory=PostgresSessionFactory.from_settings(settings),
    )