"""PostgreSQL-backed lexical retrieval for Docs document chunks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import bindparam, delete, func, literal, literal_column, select
from sqlalchemy.dialects.postgresql import JSONB, insert

from coderag.core.models import ChunkRecord
from coderag.storage.postgres_schema import chunks_table, lexical_corpus_table
from coderag.storage.postgres_session import PostgresSessionFactory


def _build_weighted_fts_vector() -> Any:
    """Build one weighted tsvector prioritizing title and section labels."""
    title_and_section = func.concat_ws(
        literal(" "),
        func.coalesce(bindparam("title"), literal("")),
        func.coalesce(bindparam("section_name"), literal("")),
    )
    return (
        func.setweight(
            func.to_tsvector(bindparam("lang"), title_and_section),
            literal_column("'A'"),
        )
        .op("||")(
            func.setweight(
                func.to_tsvector(
                    bindparam("lang"),
                    func.coalesce(bindparam("path_or_url"), literal("")),
                ),
                literal_column("'B'"),
            )
        )
        .op("||")(
            func.setweight(
                func.to_tsvector(
                    bindparam("lang"),
                    func.coalesce(bindparam("text"), literal("")),
                ),
                literal_column("'C'"),
            )
        )
    )


def _build_upsert_statement() -> Any:
    """Create the batch upsert used for rebuilding the lexical corpus."""
    insert_stmt = insert(lexical_corpus_table).values(
        {
            "chunk_id": bindparam("chunk_id"),
            "document_id": bindparam("document_id"),
            "source_id": bindparam("source_id"),
            "title": bindparam("title"),
            "path_or_url": bindparam("path_or_url"),
            "section_name": bindparam("section_name"),
            "text": bindparam("text"),
            "metadata_json": bindparam("metadata_json", type_=JSONB),
            "fts_vector": _build_weighted_fts_vector(),
        }
    )
    return insert_stmt.on_conflict_do_update(
        index_elements=[lexical_corpus_table.c.chunk_id],
        set_={
            "document_id": insert_stmt.excluded.document_id,
            "source_id": insert_stmt.excluded.source_id,
            "title": insert_stmt.excluded.title,
            "path_or_url": insert_stmt.excluded.path_or_url,
            "section_name": insert_stmt.excluded.section_name,
            "text": insert_stmt.excluded.text,
            "metadata_json": insert_stmt.excluded.metadata_json,
            "fts_vector": insert_stmt.excluded.fts_vector,
        },
    )


UPSERT_LEXICAL_CHUNKS = _build_upsert_statement()


class LexicalStore:
    """Persist and query a weighted PostgreSQL FTS corpus for Docs."""

    backend_label = "lexical"

    def __init__(
        self,
        postgres_dsn: str,
        fts_language: str = "english",
        *,
        session_factory: PostgresSessionFactory | None = None,
    ) -> None:
        """Create the store using the shared Postgres session factory."""
        self._lang = str(fts_language or "english")
        self._session_factory = session_factory or PostgresSessionFactory(
            postgres_dsn
        )

    @staticmethod
    def _coerce_metadata_dict(value: object) -> dict[str, Any]:
        """Normalize JSON metadata payloads back to dictionaries."""
        if isinstance(value, dict):
            return dict(value)
        return {}

    def rebuild(
        self,
        chunks: Sequence[ChunkRecord],
        document_map: Mapping[str, Mapping[str, object]],
    ) -> None:
        """Replace the full lexical corpus from the persisted chunk snapshot."""
        rows: list[dict[str, object]] = []
        for chunk in chunks:
            document_meta = document_map.get(chunk.document_id, {})
            rows.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "source_id": chunk.source_id,
                    "title": str(document_meta.get("title", "") or ""),
                    "path_or_url": str(
                        document_meta.get("path_or_url", "") or ""
                    ),
                    "section_name": chunk.section_name,
                    "text": chunk.text,
                    "metadata_json": dict(chunk.metadata),
                    "lang": self._lang,
                }
            )

        with self._session_factory.get_connection() as connection:
            connection.execute(delete(lexical_corpus_table))
            if rows:
                connection.execute(UPSERT_LEXICAL_CHUNKS, rows)

    def search(
        self,
        query: str,
        top_n: int,
        source_id: str | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        """Search the PostgreSQL lexical corpus and return scored chunks."""
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return []

        allowed_document_ids = [
            document_id for document_id in (document_ids or []) if document_id
        ]
        ts_query = func.plainto_tsquery(self._lang, normalized_query)
        score = func.ts_rank_cd(
            lexical_corpus_table.c.fts_vector,
            ts_query,
        ).label("score")
        statement = (
            select(
                chunks_table.c.chunk_id,
                chunks_table.c.document_id,
                chunks_table.c.source_id,
                chunks_table.c.section_name,
                chunks_table.c.text,
                chunks_table.c.start_ref,
                chunks_table.c.end_ref,
                chunks_table.c.entity_name,
                chunks_table.c.entity_type,
                chunks_table.c.metadata_json,
                score,
            )
            .select_from(
                lexical_corpus_table.join(
                    chunks_table,
                    lexical_corpus_table.c.chunk_id
                    == chunks_table.c.chunk_id,
                )
            )
            .where(lexical_corpus_table.c.fts_vector.op("@@")(ts_query))
            .order_by(score.desc())
            .limit(top_n)
        )
        if source_id:
            statement = statement.where(
                lexical_corpus_table.c.source_id == source_id
            )
        if allowed_document_ids:
            statement = statement.where(
                lexical_corpus_table.c.document_id.in_(allowed_document_ids)
            )

        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()

        results: list[tuple[ChunkRecord, float]] = []
        for row in rows:
            results.append(
                (
                    ChunkRecord(
                        chunk_id=str(row["chunk_id"]),
                        document_id=str(row["document_id"]),
                        source_id=str(row["source_id"]),
                        section_name=str(row["section_name"]),
                        text=str(row["text"]),
                        start_ref=int(row["start_ref"]),
                        end_ref=int(row["end_ref"]),
                        entity_name=(
                            str(row["entity_name"])
                            if row["entity_name"] is not None
                            else None
                        ),
                        entity_type=(
                            str(row["entity_type"])
                            if row["entity_type"] is not None
                            else None
                        ),
                        metadata=self._coerce_metadata_dict(
                            row["metadata_json"]
                        ),
                    ),
                    float(row["score"]),
                )
            )
        return results

    def clear_all(self) -> None:
        """Delete the complete lexical corpus, used by global reset flows."""
        with self._session_factory.get_connection() as connection:
            connection.execute(delete(lexical_corpus_table))

    def ping(self) -> None:
        """Validate that the lexical corpus table is reachable in Postgres."""
        statement = select(lexical_corpus_table.c.chunk_id).limit(1)
        with self._session_factory.get_connection() as connection:
            connection.execute(statement).first()

    def health_snapshot(self) -> dict[str, int | bool]:
        """Return a compact snapshot of lexical corpus state for readiness."""
        statement = select(
            func.count().label("corpus_rows"),
            func.count(
                func.distinct(lexical_corpus_table.c.document_id)
            ).label("document_count"),
            func.count(
                func.distinct(lexical_corpus_table.c.source_id)
            ).label("source_count"),
        )
        with self._session_factory.get_connection() as connection:
            row = connection.execute(statement).mappings().one()

        corpus_rows = int(row.get("corpus_rows") or 0)
        document_count = int(row.get("document_count") or 0)
        source_count = int(row.get("source_count") or 0)
        return {
            "indexed": corpus_rows > 0,
            "corpus_rows": corpus_rows,
            "document_count": document_count,
            "source_count": source_count,
        }