"""Deterministic local embedding generator."""

from __future__ import annotations

import hashlib
import math
from typing import List


def embed_text(text: str, size: int = 256) -> List[float]:
    """Generate a deterministic pseudo-embedding for offline execution."""
    buckets = [0.0] * size
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = digest[0] % size
        buckets[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in buckets))
    if norm == 0:
        return buckets
    return [v / norm for v in buckets]
