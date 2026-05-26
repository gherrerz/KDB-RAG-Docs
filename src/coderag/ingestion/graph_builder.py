"""Graph extraction from chunk entities."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from coderag.core.models import ChunkRecord

ENTITY_PATTERN = re.compile(
    r"\b[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ\-]{2,}"
    r"(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ\-]{2,}){0,2}\b",
    re.UNICODE,
)


def build_graph_edges(
    source_id: str,
    chunks: Iterable[ChunkRecord],
) -> list[tuple[str, str, str, str, str]]:
    """Create RELATES_TO edges for entities co-occurring in chunks."""
    edges: list[tuple[str, str, str, str, str]] = []
    for chunk in chunks:
        entities = list(dict.fromkeys(ENTITY_PATTERN.findall(chunk.text)))
        for idx in range(len(entities)):
            for jdx in range(idx + 1, len(entities)):
                src = entities[idx]
                tgt = entities[jdx]
                edge_key = f"{source_id}:{src}:{tgt}:{chunk.chunk_id}"
                edge_id = hashlib.sha1(edge_key.encode("utf-8")).hexdigest()
                edges.append((edge_id, src, "RELATES_TO", tgt, source_id))
    return edges
