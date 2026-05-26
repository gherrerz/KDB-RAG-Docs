"""Hybrid vector and lexical retrieval."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from coderag.core.lexical_index import QueryLexicalIndex
from coderag.core.models import ChunkRecord
from coderag.ingestion.index_chroma import LocalVectorIndex


def _normalize_scores(
    values: list[tuple[ChunkRecord, float]],
) -> dict[str, float]:
    """Normalize retrieval scores to [0, 1] by maximum value."""
    if not values:
        return {}
    max_score = max(score for _, score in values) or 1.0
    return {chunk.chunk_id: score / max_score for chunk, score in values}


def hybrid_search(
    query: str,
    lexical_index: QueryLexicalIndex,
    vector_index: LocalVectorIndex,
    top_n: int,
    alpha: float = 0.55,
    source_id: str | None = None,
    document_ids: Sequence[str] | None = None,
) -> list[tuple[ChunkRecord, float, dict[str, float]]]:
    """Combine lexical and vector scores into a unified ranking."""
    lexical_hits = lexical_index.search(
        query,
        top_n,
        source_id=source_id,
        document_ids=document_ids,
    )
    vector_hits = vector_index.search(
        query,
        top_n,
        source_id=source_id,
        document_ids=document_ids,
    )

    lexical_norm = _normalize_scores(lexical_hits)
    vector_norm = _normalize_scores(vector_hits)

    chunks: dict[str, ChunkRecord] = {}
    score_map: dict[str, float] = defaultdict(float)

    for chunk, _ in lexical_hits:
        chunks[chunk.chunk_id] = chunk
    for chunk, _ in vector_hits:
        chunks[chunk.chunk_id] = chunk

    for chunk_id in chunks:
        score_map[chunk_id] = (
            alpha * vector_norm.get(chunk_id, 0.0)
            + (1.0 - alpha) * lexical_norm.get(chunk_id, 0.0)
        )

    ranked = sorted(score_map.items(), key=lambda item: item[1], reverse=True)
    return [
        (
            chunks[chunk_id],
            score,
            {
                "vector": vector_norm.get(chunk_id, 0.0),
                "lexical": lexical_norm.get(chunk_id, 0.0),
            },
        )
        for chunk_id, score in ranked[:top_n]
    ]
