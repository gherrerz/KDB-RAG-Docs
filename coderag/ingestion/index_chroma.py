"""ChromaDB-backed vector index used in runtime."""

from __future__ import annotations

import json
from typing import List, Sequence, Tuple

import chromadb
from chromadb.api.models.Collection import Collection

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
        persist_dir = SETTINGS.chroma_persist_dir
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=SETTINGS.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

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
        self._collection.delete(where={"source_id": source_id})

    def rebuild(self, chunks: Sequence[ChunkRecord]) -> None:
        """Replace vectors for affected source ids in Chroma collection."""
        if not chunks:
            return

        source_ids = {chunk.source_id for chunk in chunks}
        for source_id in source_ids:
            self._clear_source(source_id)

        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        metadatas = [self._as_metadata(chunk) for chunk in chunks]
        embeddings = [
            embed_text(
                chunk.text,
                self.size,
                provider=self.embedding_provider,
                model=self.embedding_model,
            )
            for chunk in chunks
        ]
        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def search(
        self,
        query: str,
        top_n: int,
    ) -> List[Tuple[ChunkRecord, float]]:
        """Search similar chunks in Chroma using query embeddings."""
        if top_n <= 0:
            return []

        query_vec = embed_text(
            query,
            self.size,
            provider=self.embedding_provider,
            model=self.embedding_model,
        )
        payload = self._collection.query(
            query_embeddings=[query_vec],
            n_results=top_n,
            include=["documents", "metadatas", "distances"],
        )

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
            score = max(0.0, 1.0 - float(distance))
            results.append((chunk, score))
        return results

    def clear_all(self) -> None:
        """Delete all vectors from active collection."""
        ids = self._collection.get(include=[]).get("ids", [])
        if ids:
            self._collection.delete(ids=ids)

    def close(self) -> None:
        """Release client resources (no-op for current Chroma client)."""
        return


# Backward compatibility for imports in other modules.
LocalVectorIndex = ChromaVectorIndex
