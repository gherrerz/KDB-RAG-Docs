"""Hybrid vector and BM25 retrieval."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from coderag.core.models import ChunkRecord
from coderag.ingestion.index_bm25 import BM25Index, normalize_scores
from coderag.ingestion.index_chroma import LocalVectorIndex


def hybrid_search(
    query: str,
    bm25_index: BM25Index,
    vector_index: LocalVectorIndex,
    top_n: int,
    alpha: float = 0.55,
    source_id: Optional[str] = None,
) -> List[Tuple[ChunkRecord, float, Dict[str, float]]]:
    """Combine BM25 and vector scores into a unified ranking."""
    bm25_hits = bm25_index.search(query, top_n, source_id=source_id)
    vector_hits = vector_index.search(query, top_n, source_id=source_id)

    bm25_norm = normalize_scores(bm25_hits)
    vector_norm = normalize_scores(vector_hits)

    chunks: Dict[str, ChunkRecord] = {}
    score_map: Dict[str, float] = defaultdict(float)

    for chunk, _ in bm25_hits:
        chunks[chunk.chunk_id] = chunk
    for chunk, _ in vector_hits:
        chunks[chunk.chunk_id] = chunk

    for chunk_id in chunks:
        score_map[chunk_id] = (
            alpha * vector_norm.get(chunk_id, 0.0)
            + (1.0 - alpha) * bm25_norm.get(chunk_id, 0.0)
        )

    ranked = sorted(score_map.items(), key=lambda item: item[1], reverse=True)
    return [
        (
            chunks[chunk_id],
            score,
            {
                "vector": vector_norm.get(chunk_id, 0.0),
                "bm25": bm25_norm.get(chunk_id, 0.0),
            },
        )
        for chunk_id, score in ranked[:top_n]
    ]
