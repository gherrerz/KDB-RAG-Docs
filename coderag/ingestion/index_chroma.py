"""Local vector index emulating Chroma collection behavior."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from coderag.core.models import ChunkRecord
from coderag.core.settings import SETTINGS
from coderag.ingestion.embedding import embed_text


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity for normalized vectors."""
    return float(sum(x * y for x, y in zip(a, b)))


class LocalVectorIndex:
    """Simple vector index with deterministic embeddings."""

    def __init__(
        self,
        size: int = 256,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self.size = size
        self.embedding_provider = SETTINGS.resolve_embedding_provider(provider)
        self.embedding_model = SETTINGS.resolve_embedding_model(
            provider_override=self.embedding_provider,
            model_override=model,
        )
        self._vectors: Dict[str, List[float]] = {}
        self._chunks: Dict[str, ChunkRecord] = {}

    def rebuild(self, chunks: Sequence[ChunkRecord]) -> None:
        """Rebuild vector cache from chunks."""
        self._vectors = {
            chunk.chunk_id: embed_text(
                chunk.text,
                self.size,
                provider=self.embedding_provider,
                model=self.embedding_model,
            )
            for chunk in chunks
        }
        self._chunks = {chunk.chunk_id: chunk for chunk in chunks}

    def search(
        self,
        query: str,
        top_n: int,
    ) -> List[Tuple[ChunkRecord, float]]:
        """Vector similarity search using pseudo embeddings."""
        if not self._vectors:
            return []
        query_vec = embed_text(
            query,
            self.size,
            provider=self.embedding_provider,
            model=self.embedding_model,
        )
        ranked = sorted(
            (
                (chunk_id, cosine_similarity(query_vec, vector))
                for chunk_id, vector in self._vectors.items()
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        return [
            (self._chunks[chunk_id], score)
            for chunk_id, score in ranked[:top_n]
        ]
