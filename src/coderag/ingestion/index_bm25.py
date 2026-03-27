"""BM25 indexing and scoring utilities."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from rank_bm25 import BM25Okapi

from coderag.core.models import ChunkRecord


class BM25Index:
    """In-memory BM25 index over chunk texts."""

    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._chunks: List[ChunkRecord] = []

    def rebuild(self, chunks: Sequence[ChunkRecord]) -> None:
        """Recreate index from current chunks."""
        self._chunks = list(chunks)
        tokens = [chunk.text.lower().split() for chunk in self._chunks]
        self._bm25 = BM25Okapi(tokens) if tokens else None

    def search(
        self,
        query: str,
        top_n: int,
        source_id: Optional[str] = None,
    ) -> List[Tuple[ChunkRecord, float]]:
        """Return BM25 results sorted by score."""
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(query.lower().split())
        ranked = sorted(
            enumerate(scores),
            key=lambda item: item[1],
            reverse=True,
        )
        results: List[Tuple[ChunkRecord, float]] = []
        for idx, score in ranked[:top_n]:
            chunk = self._chunks[idx]
            if source_id and chunk.source_id != source_id:
                continue
            results.append((chunk, float(score)))
            if len(results) >= top_n:
                break
        return results


def normalize_scores(
    values: List[Tuple[ChunkRecord, float]],
) -> Dict[str, float]:
    """Normalize scores to [0, 1] by maximum value."""
    if not values:
        return {}
    max_score = max(score for _, score in values) or 1.0
    return {chunk.chunk_id: score / max_score for chunk, score in values}
