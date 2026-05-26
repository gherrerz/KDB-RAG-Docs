# pyright: reportMissingImports=false

"""PostgreSQL-backed document and chunk storage for the Docs cutover."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from coderag.core.models import ChunkRecord, DocumentCatalogEntry, DocumentRecord
from coderag.storage.postgres_schema import (
    chunks_table,
    documents_table,
)
from coderag.storage.postgres_session import PostgresSessionFactory


class PostgresDocumentChunkStore:
    """Persist documents, chunks, and catalog views in PostgreSQL."""

    def __init__(
        self,
        postgres_dsn: str,
        *,
        session_factory: PostgresSessionFactory | None = None,
    ) -> None:
        """Create the store using a reusable SQLAlchemy session factory."""
        self._session_factory = session_factory or PostgresSessionFactory(
            postgres_dsn
        )

    @staticmethod
    def _normalize_tags(tags: Iterable[object]) -> list[str]:
        """Return stable, deduplicated tags suitable for persistence."""
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_tag in tags:
            tag = str(raw_tag or "").strip()
            if not tag:
                continue
            tag_key = tag.casefold()
            if tag_key in seen:
                continue
            seen.add(tag_key)
            normalized.append(tag)
        return normalized

    @classmethod
    def _document_metadata_payload(
        cls,
        doc: DocumentRecord,
    ) -> dict[str, Any]:
        """Keep document metadata and explicit tag payload aligned."""
        metadata = dict(doc.metadata)
        metadata["tags"] = cls._normalize_tags(doc.tags)
        return metadata

    @classmethod
    def _parse_tags_value(cls, raw_tags: Any) -> list[str]:
        """Decode persisted tags payload into a normalized list."""
        if isinstance(raw_tags, list):
            return cls._normalize_tags(raw_tags)
        if isinstance(raw_tags, str) and raw_tags.strip():
            try:
                parsed = json.loads(raw_tags)
            except json.JSONDecodeError:
                return []
            if isinstance(parsed, list):
                return cls._normalize_tags(parsed)
        return []

    @staticmethod
    def _coerce_metadata_dict(raw_value: Any) -> dict[str, Any]:
        """Normalize JSON metadata payloads to dictionaries."""
        if isinstance(raw_value, dict):
            return dict(raw_value)
        if isinstance(raw_value, str) and raw_value.strip():
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @classmethod
    def _row_to_chunk(cls, row: dict[str, Any]) -> ChunkRecord:
        """Convert one SQLAlchemy row mapping to ChunkRecord."""
        return ChunkRecord(
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
            metadata=cls._coerce_metadata_dict(row["metadata_json"]),
        )

    def upsert_document(self, doc: DocumentRecord) -> None:
        """Insert or update one persisted document row."""
        self.upsert_documents([doc])

    def upsert_documents(self, docs: Iterable[DocumentRecord]) -> int:
        """Insert or update many documents in one PostgreSQL transaction."""
        rows = []
        for doc in docs:
            rows.append(
                {
                    "document_id": doc.document_id,
                    "source_id": doc.source_id,
                    "title": doc.title,
                    "content": doc.content,
                    "path_or_url": doc.path_or_url,
                    "content_type": doc.content_type,
                    "updated_at": doc.updated_at,
                    "tags_json": self._normalize_tags(doc.tags),
                    "metadata_json": self._document_metadata_payload(doc),
                }
            )
        if not rows:
            return 0

        insert_stmt = insert(documents_table)
        statement = insert_stmt.values(rows).on_conflict_do_update(
            index_elements=[documents_table.c.document_id],
            set_={
                "source_id": insert_stmt.excluded.source_id,
                "title": insert_stmt.excluded.title,
                "content": insert_stmt.excluded.content,
                "path_or_url": insert_stmt.excluded.path_or_url,
                "content_type": insert_stmt.excluded.content_type,
                "updated_at": insert_stmt.excluded.updated_at,
                "tags_json": insert_stmt.excluded.tags_json,
                "metadata_json": insert_stmt.excluded.metadata_json,
            },
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)
        return len(rows)

    def replace_chunks(
        self,
        source_id: str,
        chunks: Iterable[ChunkRecord],
    ) -> None:
        """Replace all chunks for one source in a single transaction."""
        rows = [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "source_id": chunk.source_id,
                "section_name": chunk.section_name,
                "text": chunk.text,
                "start_ref": chunk.start_ref,
                "end_ref": chunk.end_ref,
                "entity_name": chunk.entity_name,
                "entity_type": chunk.entity_type,
                "metadata_json": dict(chunk.metadata),
            }
            for chunk in chunks
        ]

        with self._session_factory.get_connection() as connection:
            connection.execute(
                delete(chunks_table).where(chunks_table.c.source_id == source_id)
            )
            if rows:
                connection.execute(insert(chunks_table).values(rows))

    def list_chunks(self, source_id: str | None = None) -> list[ChunkRecord]:
        """Return stored chunks, optionally filtered by source."""
        statement = select(
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
        )
        if source_id:
            statement = statement.where(chunks_table.c.source_id == source_id)
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()
        return [self._row_to_chunk(dict(row)) for row in rows]

    def get_document_map(
        self,
        source_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Return quick metadata map keyed by document_id."""
        statement = select(
            documents_table.c.document_id,
            documents_table.c.title,
            documents_table.c.path_or_url,
        )
        if source_id:
            statement = statement.where(documents_table.c.source_id == source_id)
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()
        return {
            str(row["document_id"]): {
                "title": str(row["title"]),
                "path_or_url": str(row["path_or_url"]),
            }
            for row in rows
        }

    def list_documents(
        self,
        source_id: str | None = None,
        tags: Iterable[str] | None = None,
    ) -> list[DocumentCatalogEntry]:
        """Return lightweight document metadata for UI and API catalog views."""
        requested_tags = self._normalize_tags(tags or [])
        requested_tag_keys = {tag.casefold() for tag in requested_tags}
        statement = (
            select(
                documents_table.c.document_id,
                documents_table.c.source_id,
                documents_table.c.title,
                documents_table.c.path_or_url,
                documents_table.c.content_type,
                documents_table.c.updated_at,
                documents_table.c.tags_json,
            )
            .order_by(
                func.lower(documents_table.c.title).asc(),
                func.lower(documents_table.c.path_or_url).asc(),
            )
        )
        if source_id:
            statement = statement.where(documents_table.c.source_id == source_id)
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()

        documents: list[DocumentCatalogEntry] = []
        for row in rows:
            row_tags = self._parse_tags_value(row["tags_json"])
            if requested_tag_keys:
                row_tag_keys = {tag.casefold() for tag in row_tags}
                if not row_tag_keys.intersection(requested_tag_keys):
                    continue
            documents.append(
                DocumentCatalogEntry(
                    document_id=str(row["document_id"]),
                    source_id=str(row["source_id"]),
                    title=str(row["title"]),
                    path_or_url=str(row["path_or_url"]),
                    content_type=str(row["content_type"]),
                    updated_at=row["updated_at"],
                    tags=row_tags,
                )
            )
        return documents

    def get_document_by_id(
        self,
        document_id: str,
    ) -> DocumentCatalogEntry | None:
        """Return one persisted document entry by document id."""
        statement = select(
            documents_table.c.document_id,
            documents_table.c.source_id,
            documents_table.c.title,
            documents_table.c.path_or_url,
            documents_table.c.content_type,
            documents_table.c.updated_at,
            documents_table.c.tags_json,
        ).where(documents_table.c.document_id == document_id)
        with self._session_factory.get_connection() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        return DocumentCatalogEntry(
            document_id=str(row["document_id"]),
            source_id=str(row["source_id"]),
            title=str(row["title"]),
            path_or_url=str(row["path_or_url"]),
            content_type=str(row["content_type"]),
            updated_at=row["updated_at"],
            tags=self._parse_tags_value(row["tags_json"]),
        )

    def list_tag_facets(
        self,
        source_id: str | None = None,
    ) -> list[tuple[str, int]]:
        """Return persisted tag facets with document counts."""
        statement = select(documents_table.c.tags_json)
        if source_id:
            statement = statement.where(documents_table.c.source_id == source_id)
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).all()

        counts: dict[str, tuple[str, int]] = {}
        for row in rows:
            for tag in self._parse_tags_value(row[0]):
                tag_key = tag.casefold()
                display_tag, current_count = counts.get(tag_key, (tag, 0))
                counts[tag_key] = (display_tag, current_count + 1)
        items = [
            (display_tag, document_count)
            for display_tag, document_count in counts.values()
        ]
        return sorted(items, key=lambda item: (str.casefold(item[0]), item[1]))

    def replace_document_tags(
        self,
        document_id: str,
        tags: Iterable[object],
    ) -> dict[str, Any] | None:
        """Replace persisted tags for one document while keeping metadata aligned."""
        normalized_tags = self._normalize_tags(tags)
        statement = select(
            documents_table.c.source_id,
            documents_table.c.tags_json,
            documents_table.c.metadata_json,
        ).where(documents_table.c.document_id == document_id)
        with self._session_factory.get_connection() as connection:
            row = connection.execute(statement).mappings().one_or_none()
            if row is None:
                return None

            old_tags = self._parse_tags_value(row["tags_json"])
            metadata = self._coerce_metadata_dict(row["metadata_json"])
            metadata["tags"] = normalized_tags

            connection.execute(
                update(documents_table)
                .where(documents_table.c.document_id == document_id)
                .values(
                    tags_json=normalized_tags,
                    metadata_json=metadata,
                )
            )

        return {
            "source_id": str(row["source_id"]),
            "old_tags": old_tags,
            "new_tags": normalized_tags,
        }

    def find_documents_by_title_and_content_type(
        self,
        title: str,
        content_type: str,
    ) -> list[DocumentCatalogEntry]:
        """Return ingested documents matching title and content type."""
        statement = (
            select(
                documents_table.c.document_id,
                documents_table.c.source_id,
                documents_table.c.title,
                documents_table.c.path_or_url,
                documents_table.c.content_type,
                documents_table.c.updated_at,
                documents_table.c.tags_json,
            )
            .where(func.lower(documents_table.c.title) == title.strip().casefold())
            .where(
                func.lower(documents_table.c.content_type)
                == content_type.strip().casefold()
            )
            .order_by(
                documents_table.c.updated_at.desc(),
                func.lower(documents_table.c.path_or_url).asc(),
            )
        )
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            DocumentCatalogEntry(
                document_id=str(row["document_id"]),
                source_id=str(row["source_id"]),
                title=str(row["title"]),
                path_or_url=str(row["path_or_url"]),
                content_type=str(row["content_type"]),
                updated_at=row["updated_at"],
                tags=self._parse_tags_value(row["tags_json"]),
            )
            for row in rows
        ]

    def delete_document_by_id(self, document_id: str) -> int:
        """Delete one document row by document id."""
        statement = delete(documents_table).where(
            documents_table.c.document_id == document_id
        )
        with self._session_factory.get_connection() as connection:
            result = connection.execute(statement)
        return max(0, int(result.rowcount or 0))

    def delete_chunks_by_document_id(self, document_id: str) -> int:
        """Delete all chunk rows belonging to one document id."""
        statement = delete(chunks_table).where(
            chunks_table.c.document_id == document_id
        )
        with self._session_factory.get_connection() as connection:
            result = connection.execute(statement)
        return max(0, int(result.rowcount or 0))

    def clear_document_data(self) -> dict[str, int]:
        """Delete persisted documents and chunks while keeping schema intact."""
        with self._session_factory.get_connection() as connection:
            deleted_chunks = connection.execute(delete(chunks_table)).rowcount
            deleted_documents = connection.execute(
                delete(documents_table)
            ).rowcount
        return {
            "deleted_documents": max(0, int(deleted_documents or 0)),
            "deleted_chunks": max(0, int(deleted_chunks or 0)),
        }