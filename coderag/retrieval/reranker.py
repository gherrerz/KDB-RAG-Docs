"""Lightweight reranker driven by lexical overlap."""

from __future__ import annotations

from typing import Dict, List, Tuple

from coderag.core.models import ChunkRecord


def rerank_results(
    query: str,
    items: List[Tuple[ChunkRecord, float, Dict[str, float]]],
    top_k: int,
) -> List[Tuple[ChunkRecord, float, Dict[str, float]]]:
    """Rerank hybrid results using query token overlap as signal."""
    tokens = set(query.lower().split())
    rescored: List[Tuple[ChunkRecord, float, Dict[str, float]]] = []
    for chunk, score, parts in items:
        words = set(chunk.text.lower().split())
        overlap = len(tokens.intersection(words)) / max(len(tokens), 1)
        new_score = 0.75 * score + 0.25 * overlap
        diagnostics = dict(parts)
        diagnostics["overlap"] = overlap
        rescored.append((chunk, new_score, diagnostics))

    rescored.sort(key=lambda item: item[1], reverse=True)
    return rescored[:top_k]
