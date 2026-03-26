"""Assemble grounded context blocks for LLM answering."""

from __future__ import annotations

from typing import List

from coderag.core.models import ChunkRecord, GraphPath


def assemble_context(
    chunks: List[ChunkRecord],
    graph_paths: List[GraphPath],
    max_chars: int,
) -> str:
    """Build compact context text from evidence chunks and graph paths."""
    chunk_blocks = [
        (
            f"[Chunk {chunk.chunk_id}] section={chunk.section_name} "
            f"ref=({chunk.start_ref}-{chunk.end_ref})\n{chunk.text}"
        )
        for chunk in chunks
    ]
    graph_blocks = [
        f"[GraphPath] {' -> '.join(path.nodes)}"
        for path in graph_paths
    ]
    context = "\n\n".join(chunk_blocks + graph_blocks)
    return context[:max_chars]
