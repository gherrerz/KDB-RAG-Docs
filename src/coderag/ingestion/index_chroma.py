"""ChromaDB-backed vector index used in runtime."""

from __future__ import annotations

import gc
import json
import os
import shutil
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb import errors as chroma_errors

InvalidDimensionException = chroma_errors.InvalidDimensionException
InvalidArgumentError = getattr(chroma_errors, "InvalidArgumentError", ValueError)
InvalidCollectionException = getattr(
    chroma_errors,
    "InvalidCollectionException",
    chroma_errors.NotFoundError,
)

from coderag.core.models import ChunkRecord
from coderag.core.settings import SETTINGS
from coderag.ingestion.embedding import embed_text


class ChromaVectorIndex:
    """Persistent vector index backed by ChromaDB."""

    def __init__(
        self,
        size: int = 256,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        SETTINGS.require_chroma_enabled()
        self.size = size
        self.embedding_provider = SETTINGS.resolve_embedding_provider(provider)
        self.embedding_model = model or SETTINGS.llm_embedding
        self.embedding_workers = max(1, SETTINGS.ingest_embedding_workers)
        self.upsert_batch_size = max(1, SETTINGS.chroma_upsert_batch_size)
        self._persist_dir = SETTINGS.chroma_persist_dir
        self._client = self._create_client(self._persist_dir)
        self._collection = self._get_or_create_collection()

    @staticmethod
    def _create_client(persist_dir: Path):
        """Create one Chroma persistent client rooted at persist_dir."""
        persist_dir.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(persist_dir))

    @staticmethod
    def _on_rmtree_error(func, path, _exc_info) -> None:
        """Retry physical deletion after clearing read-only flags."""
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)

    @staticmethod
    def _dispose_client(client: Any) -> None:
        """Release client-side Chroma resources before filesystem reset."""
        close = getattr(client, "close", None)
        if callable(close):
            close()
        clear_cache = getattr(client, "clear_system_cache", None)
        if callable(clear_cache):
            clear_cache()

    def _get_or_create_collection(self) -> Collection:
        """Return active Chroma collection with cosine distance config."""
        return self._ensure_client().get_or_create_collection(
            name=SETTINGS.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    def _ensure_client(self):
        """Recover the persistent client when another flow cleared it."""
        if self._client is None:
            self._client = self._create_client(self._persist_dir)
        return self._client

    def _ensure_collection(self) -> Collection:
        """Recover the active collection handle when another flow cleared it."""
        if self._collection is None:
            self._collection = self._get_or_create_collection()
        return self._collection

    @staticmethod
    def _as_metadata(chunk: ChunkRecord) -> dict[str, object]:
        """Convert chunk to Chroma metadata with primitive values only."""
        return {
            "document_id": chunk.document_id,
            "source_id": chunk.source_id,
            "section_name": chunk.section_name,
            "start_ref": int(chunk.start_ref),
            "end_ref": int(chunk.end_ref),
            "entity_name": chunk.entity_name or "",
            "entity_type": chunk.entity_type or "",
            "extra_metadata": json.dumps(chunk.metadata, ensure_ascii=True),
        }

    @staticmethod
    def _from_record(
        chunk_id: str,
        text: str,
        metadata: dict[str, object],
    ) -> ChunkRecord:
        """Rebuild chunk record from Chroma query payload."""
        raw_extra = metadata.get("extra_metadata", "{}")
        parsed_extra = {}
        if isinstance(raw_extra, str) and raw_extra.strip():
            try:
                parsed_extra = json.loads(raw_extra)
            except json.JSONDecodeError:
                parsed_extra = {}

        return ChunkRecord(
            chunk_id=chunk_id,
            document_id=str(metadata.get("document_id", "")),
            source_id=str(metadata.get("source_id", "")),
            section_name=str(metadata.get("section_name", "")),
            text=text,
            start_ref=int(metadata.get("start_ref", 0)),
            end_ref=int(metadata.get("end_ref", 0)),
            entity_name=str(metadata.get("entity_name") or "") or None,
            entity_type=str(metadata.get("entity_type") or "") or None,
            metadata=parsed_extra if isinstance(parsed_extra, dict) else {},
        )

    def _clear_source(self, source_id: str) -> None:
        """Delete existing vectors belonging to one source."""
        try:
            self._ensure_collection().delete(where={"source_id": source_id})
        except InvalidCollectionException:
            # Another process may recreate the collection (e.g. reset).
            self._collection = self._get_or_create_collection()
            self._collection.delete(where={"source_id": source_id})

    def delete_document(self, document_id: str) -> None:
        """Delete existing vectors belonging to one document."""
        try:
            self._ensure_collection().delete(where={"document_id": document_id})
        except InvalidCollectionException:
            self._collection = self._get_or_create_collection()
            self._collection.delete(where={"document_id": document_id})

    def _embed_chunks(self, chunks: Sequence[ChunkRecord]) -> List[List[float]]:
        """Generate embeddings with bounded parallelism for I/O providers."""
        if not chunks:
            return []
        if len(chunks) == 1 or self.embedding_workers <= 1:
            return [
                embed_text(
                    chunk.text,
                    self.size,
                    provider=self.embedding_provider,
                    model=self.embedding_model,
                )
                for chunk in chunks
            ]

        max_workers = min(self.embedding_workers, len(chunks))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(
                executor.map(
                    lambda chunk: embed_text(
                        chunk.text,
                        self.size,
                        provider=self.embedding_provider,
                        model=self.embedding_model,
                    ),
                    chunks,
                )
            )

    def rebuild(self, chunks: Sequence[ChunkRecord]) -> None:
        """Replace vectors for affected source ids in Chroma collection."""
        if not chunks:
            return

        source_ids = {chunk.source_id for chunk in chunks}
        def _upsert_all() -> None:
            for source_id in source_ids:
                self._clear_source(source_id)

            for start in range(0, len(chunks), self.upsert_batch_size):
                batch = chunks[start:start + self.upsert_batch_size]
                ids = [chunk.chunk_id for chunk in batch]
                documents = [chunk.text for chunk in batch]
                metadatas = [self._as_metadata(chunk) for chunk in batch]
                embeddings = self._embed_chunks(batch)
                self._ensure_collection().upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )

        try:
            _upsert_all()
        except (
            InvalidDimensionException,
            InvalidArgumentError,
            InvalidCollectionException,
        ):
            # Auto-heal when persisted collection was created with another
            # embedding dimensionality or when a stale collection handle was
            # invalidated by another process.
            try:
                self.clear_all()
                _upsert_all()
            except Exception:
                # On Windows, file locks from another process can temporarily
                # block collection recreation. Keep BM25 available and let the
                # next reset/ingestion retry vector rebuilding.
                return

    def search(
        self,
        query: str,
        top_n: int,
        source_id: Optional[str] = None,
        document_ids: Optional[Sequence[str]] = None,
    ) -> List[Tuple[ChunkRecord, float]]:
        """Search similar chunks in Chroma using query embeddings."""
        if top_n <= 0:
            return []
        allowed_document_ids = {
            document_id
            for document_id in (document_ids or [])
            if document_id
        }
        try:
            if self._ensure_collection().count() == 0:
                return []
        except InvalidCollectionException:
            self._collection = self._get_or_create_collection()
            if self._collection.count() == 0:
                return []

        query_vec = embed_text(
            query,
            self.size,
            provider=self.embedding_provider,
            model=self.embedding_model,
        )

        where_clause: dict[str, Any] | None = None
        if source_id and allowed_document_ids:
            where_clause = {
                "$and": [
                    {"source_id": source_id},
                    {"document_id": {"$in": sorted(allowed_document_ids)}},
                ]
            }
        elif source_id:
            where_clause = {"source_id": source_id}
        elif allowed_document_ids:
            if len(allowed_document_ids) == 1:
                where_clause = {"document_id": next(iter(allowed_document_ids))}
            else:
                where_clause = {
                    "document_id": {"$in": sorted(allowed_document_ids)}
                }

        try:
            params = {
                "query_embeddings": [query_vec],
                "n_results": max(top_n, len(allowed_document_ids) or top_n),
                "include": ["documents", "metadatas", "distances"],
            }
            if where_clause is not None:
                params["where"] = where_clause
            payload = self._collection.query(**params)
        except (
            InvalidDimensionException,
            InvalidArgumentError,
            InvalidCollectionException,
        ):
            try:
                payload = self._collection.query(
                    query_embeddings=[query_vec],
                    n_results=max(top_n * 5, len(allowed_document_ids) * 5, top_n),
                    include=["documents", "metadatas", "distances"],
                )
            except (
                InvalidDimensionException,
                InvalidArgumentError,
                InvalidCollectionException,
            ):
                return []

        ids = payload.get("ids", [[]])
        documents = payload.get("documents", [[]])
        metadatas = payload.get("metadatas", [[]])
        distances = payload.get("distances", [[]])
        if not ids or not ids[0]:
            return []

        results: List[Tuple[ChunkRecord, float]] = []
        for chunk_id, document, metadata, distance in zip(
            ids[0],
            documents[0],
            metadatas[0],
            distances[0],
        ):
            if not isinstance(metadata, dict):
                continue
            chunk = self._from_record(
                chunk_id=str(chunk_id),
                text=str(document),
                metadata=metadata,
            )
            if source_id and chunk.source_id != source_id:
                continue
            if (
                allowed_document_ids
                and chunk.document_id not in allowed_document_ids
            ):
                continue
            score = max(0.0, 1.0 - float(distance))
            results.append((chunk, score))
            if len(results) >= top_n:
                break
        return results

    def clear_all(self) -> None:
        """Delete persisted Chroma data on disk and recreate clean state."""
        try:
            self._ensure_client().delete_collection(name=SETTINGS.chroma_collection)
        except (ValueError, InvalidCollectionException):
            # Chroma raises when the collection is already missing; reset must
            # stay idempotent for API/UI flows.
            pass
        self._collection = None
        self._dispose_client(self._client)
        self._client = None
        gc.collect()
        if self._persist_dir.exists():
            shutil.rmtree(
                self._persist_dir,
                onerror=self._on_rmtree_error,
            )
        self._client = self._create_client(self._persist_dir)
        self._collection = self._get_or_create_collection()

    def close(self) -> None:
        """Release client resources (no-op for current Chroma client)."""
        return


# Backward compatibility for imports in other modules.
LocalVectorIndex = ChromaVectorIndex
