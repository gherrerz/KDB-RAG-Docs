"""Hybrid reranker with lexical signals and diversity-aware selection."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Dict, Iterable, List, Set, Tuple

from coderag.core.models import ChunkRecord

TOKEN_PATTERN = re.compile(r"\b[\w\-]{2,}\b", re.UNICODE)
STOPWORDS = {
    "a",
    "al",
    "como",
    "con",
    "cual",
    "cuales",
    "de",
    "del",
    "el",
    "en",
    "es",
    "la",
    "las",
    "los",
    "para",
    "por",
    "que",
    "se",
    "su",
    "sus",
    "un",
    "una",
    "y",
}
COMPLEX_QUERY_HINTS = {
    "analiza",
    "causa",
    "comparar",
    "como",
    "conecta",
    "depende",
    "impacta",
    "multi",
    "relacion",
    "relaciona",
    "versus",
}


def _normalize_token(token: str) -> str:
    """Normalize token for robust lexical matching across accents/case."""
    lowered = token.casefold().strip("_-")
    if not lowered:
        return ""
    normalized = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _tokenize(text: str) -> List[str]:
    """Tokenize plain text using unicode-aware word extraction."""
    tokens: List[str] = []
    for token in TOKEN_PATTERN.findall(text):
        normalized = _normalize_token(token)
        if len(normalized) < 2:
            continue
        if normalized in STOPWORDS:
            continue
        tokens.append(normalized)
    return tokens


def _bigrams(tokens: Iterable[str]) -> Set[str]:
    """Build bigram signatures from normalized token sequence."""
    token_list = list(tokens)
    return {
        f"{token_list[idx]}::{token_list[idx + 1]}"
        for idx in range(len(token_list) - 1)
    }


def _query_is_complex(query: str, query_tokens: List[str]) -> bool:
    """Estimate whether query likely requires multi-hop/multi-doc evidence."""
    if len(query_tokens) >= 8:
        return True
    lowered = _normalize_token(query)
    if any(hint in lowered for hint in COMPLEX_QUERY_HINTS):
        return True
    connectors = lowered.count(" y ") + lowered.count(" o ")
    return connectors >= 2


def _diversify(
    ranked: List[Tuple[ChunkRecord, float, Dict[str, float]]],
    top_k: int,
    query_is_complex: bool,
) -> List[Tuple[ChunkRecord, float, Dict[str, float]]]:
    """Apply soft per-document cap to avoid single-document collapse."""
    if top_k <= 0:
        return []
    if not ranked:
        return []
    if not query_is_complex:
        return ranked[:top_k]

    per_doc_cap = max(1, min(3, top_k // 2))
    doc_counts: Dict[str, int] = defaultdict(int)
    selected: List[Tuple[ChunkRecord, float, Dict[str, float]]] = []
    selected_ids: Set[str] = set()

    for item in ranked:
        chunk = item[0]
        if doc_counts[chunk.document_id] >= per_doc_cap:
            continue
        selected.append(item)
        selected_ids.add(chunk.chunk_id)
        doc_counts[chunk.document_id] += 1
        if len(selected) >= top_k:
            break

    if len(selected) < top_k:
        for item in ranked:
            chunk = item[0]
            if chunk.chunk_id in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(chunk.chunk_id)
            if len(selected) >= top_k:
                break

    available_docs = {
        item[0].document_id
        for item in ranked
    }
    selected_docs = {
        item[0].document_id
        for item in selected
    }
    if len(selected_docs) < 2 and len(available_docs) >= 2:
        for candidate in ranked:
            candidate_doc = candidate[0].document_id
            if candidate_doc in selected_docs:
                continue
            if len(selected) >= top_k:
                selected[-1] = candidate
            else:
                selected.append(candidate)
            break

    return selected[:top_k]


def _jaccard_similarity(left: Set[str], right: Set[str]) -> float:
    """Return token-set similarity used by MMR redundancy penalty."""
    if not left or not right:
        return 0.0
    union = left.union(right)
    if not union:
        return 0.0
    return len(left.intersection(right)) / len(union)


def _mmr_select(
    ranked: List[Tuple[ChunkRecord, float, Dict[str, float]]],
    token_sets: Dict[str, Set[str]],
    top_k: int,
    lambda_param: float = 0.72,
) -> List[Tuple[ChunkRecord, float, Dict[str, float]]]:
    """Select results with Maximal Marginal Relevance for query diversity."""
    if top_k <= 0:
        return []
    if not ranked:
        return []

    # Limit candidate pool for predictable latency on large result sets.
    pool_size = min(len(ranked), max(top_k * 4, top_k))
    pool = ranked[:pool_size]
    selected_indices: List[int] = []
    remaining_indices = list(range(len(pool)))

    while remaining_indices and len(selected_indices) < top_k:
        best_index = remaining_indices[0]
        best_mmr_score = float("-inf")

        for candidate_index in remaining_indices:
            candidate_chunk = pool[candidate_index][0]
            candidate_tokens = token_sets.get(candidate_chunk.chunk_id, set())
            relevance = pool[candidate_index][1]

            redundancy = 0.0
            for selected_index in selected_indices:
                selected_chunk = pool[selected_index][0]
                selected_tokens = token_sets.get(
                    selected_chunk.chunk_id,
                    set(),
                )
                redundancy = max(
                    redundancy,
                    _jaccard_similarity(candidate_tokens, selected_tokens),
                )

            mmr_score = lambda_param * relevance
            mmr_score -= (1.0 - lambda_param) * redundancy
            if mmr_score > best_mmr_score:
                best_mmr_score = mmr_score
                best_index = candidate_index

        selected_indices.append(best_index)
        remaining_indices.remove(best_index)

    selected = [pool[index] for index in selected_indices]
    if len(selected) < top_k:
        selected_chunk_ids = {item[0].chunk_id for item in selected}
        for item in ranked:
            if item[0].chunk_id in selected_chunk_ids:
                continue
            selected.append(item)
            if len(selected) >= top_k:
                break

    return selected[:top_k]


def rerank_results(
    query: str,
    items: List[Tuple[ChunkRecord, float, Dict[str, float]]],
    top_k: int,
) -> List[Tuple[ChunkRecord, float, Dict[str, float]]]:
    """Rerank hybrid hits with lexical semantics and diversity controls."""
    query_tokens = _tokenize(query)
    query_token_set = set(query_tokens)
    query_bigrams = _bigrams(query_tokens)

    rescored: List[Tuple[ChunkRecord, float, Dict[str, float]]] = []
    token_sets: Dict[str, Set[str]] = {}
    for chunk, score, parts in items:
        chunk_tokens = _tokenize(chunk.text)
        chunk_token_set = set(chunk_tokens)
        token_sets[chunk.chunk_id] = chunk_token_set
        token_overlap = len(query_token_set.intersection(chunk_token_set)) / max(
            len(query_token_set),
            1,
        )
        chunk_bigrams = _bigrams(chunk_tokens)
        phrase_overlap = len(query_bigrams.intersection(chunk_bigrams)) / max(
            len(query_bigrams),
            1,
        )

        new_score = 0.65 * score + 0.25 * token_overlap + 0.10 * phrase_overlap
        diagnostics = dict(parts)
        diagnostics["token_overlap"] = token_overlap
        diagnostics["phrase_overlap"] = phrase_overlap
        rescored.append((chunk, new_score, diagnostics))

    rescored.sort(key=lambda item: item[1], reverse=True)
    query_is_complex = _query_is_complex(query, query_tokens)

    selected = rescored
    if query_is_complex:
        selected = _mmr_select(
            ranked=rescored,
            token_sets=token_sets,
            top_k=top_k,
        )

    return _diversify(
        ranked=selected,
        top_k=top_k,
        query_is_complex=query_is_complex,
    )
