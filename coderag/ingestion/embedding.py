"""Deterministic local embedding generator."""

from __future__ import annotations

import hashlib
import math
from typing import List

from coderag.core.settings import SETTINGS


def _normalize_vector(values: List[float]) -> List[float]:
    """Normalize vector to unit norm when possible."""
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0:
        return values
    return [v / norm for v in values]


def _fit_vector_size(values: List[float], size: int) -> List[float]:
    """Fit vector length to requested size using truncate/pad strategy."""
    if len(values) > size:
        fitted = values[:size]
    elif len(values) < size:
        fitted = values + [0.0] * (size - len(values))
    else:
        fitted = values
    return _normalize_vector(fitted)


def _embed_text_local(
    text: str,
    size: int,
    provider: str,
    model: str,
) -> List[float]:
    """Generate deterministic pseudo-embedding keyed by provider/model."""
    buckets = [0.0] * size
    prefix = f"{provider}:{model}".encode("utf-8")
    for token in text.lower().split():
        digest = hashlib.sha256(prefix + b"::" + token.encode("utf-8")).digest()
        idx = digest[0] % size
        buckets[idx] += 1.0
    return _normalize_vector(buckets)


def embed_text(
    text: str,
    size: int = 256,
    provider: str | None = None,
    model: str | None = None,
) -> List[float]:
    """Embed text with configured provider/model and local deterministic fallback."""
    effective_provider = SETTINGS.resolve_embedding_provider(provider)
    effective_model = SETTINGS.resolve_embedding_model(
        provider_override=effective_provider,
        model_override=model,
    )

    # In this MVP we keep deterministic local vectors and key them by
    # provider/model so environment-selected embedding settings are applied.
    vector = _embed_text_local(
        text=text,
        size=size,
        provider=effective_provider,
        model=effective_model,
    )
    return _fit_vector_size(vector, size)
