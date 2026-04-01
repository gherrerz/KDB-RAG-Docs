"""Assemble grounded context blocks for LLM answering."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from coderag.core.models import ChunkRecord, GraphPath


def _round_robin_chunks(chunks: List[ChunkRecord]) -> List[ChunkRecord]:
    """Interleave chunks by document to improve cross-document coverage."""
    by_doc: Dict[str, deque[ChunkRecord]] = {}
    order: List[str] = []
    for chunk in chunks:
        doc_id = chunk.document_id
        if doc_id not in by_doc:
            by_doc[doc_id] = deque()
            order.append(doc_id)
        by_doc[doc_id].append(chunk)

    interleaved: List[ChunkRecord] = []
    while True:
        emitted = False
        for doc_id in order:
            queue = by_doc[doc_id]
            if not queue:
                continue
            interleaved.append(queue.popleft())
            emitted = True
        if not emitted:
            break
    return interleaved


def assemble_context(
    chunks: List[ChunkRecord],
    graph_paths: List[GraphPath],
    max_chars: int,
    document_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Build compact context text from evidence chunks and graph paths."""
    document_map = document_map or {}

    def _doc_name(chunk: ChunkRecord) -> str:
        meta = document_map.get(chunk.document_id, {})
        path_or_url = str(meta.get("path_or_url") or "").strip()
        filename = ""
        if path_or_url:
            normalized = path_or_url.replace("\\", "/")
            filename = normalized.rsplit("/", 1)[-1].strip()

        title = str(meta.get("title") or "").strip()
        if title:
            if Path(title).suffix:
                return title
            if filename and Path(filename).suffix:
                return filename
            return title

        if filename:
            return filename

        return chunk.document_id

    ordered_chunks = _round_robin_chunks(chunks)
    chunk_blocks = [
        (
            f"[Documento {_doc_name(chunk)}] section={chunk.section_name} "
            f"ref=({chunk.start_ref}-{chunk.end_ref})\n{chunk.text}"
        )
        for chunk in ordered_chunks
    ]
    graph_blocks = [
        f"[GraphPath] {' -> '.join(path.nodes)}"
        for path in graph_paths
    ]

    if max_chars <= 0:
        return ""

    chunk_budget = max_chars
    if graph_blocks:
        chunk_budget = max(0, int(max_chars * 0.8))

    blocks: List[str] = []
    current_length = 0
    for block in chunk_blocks:
        separator_size = 2 if blocks else 0
        projected = current_length + separator_size + len(block)
        if projected > chunk_budget:
            break
        if separator_size:
            current_length += separator_size
        blocks.append(block)
        current_length += len(block)

    for block in graph_blocks:
        separator_size = 2 if blocks else 0
        projected = current_length + separator_size + len(block)
        if projected > max_chars:
            break
        if separator_size:
            current_length += separator_size
        blocks.append(block)
        current_length += len(block)

    return "\n\n".join(blocks)
