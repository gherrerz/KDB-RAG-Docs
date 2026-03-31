"""Assemble grounded context blocks for LLM answering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from coderag.core.models import ChunkRecord, GraphPath


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

    chunk_blocks = [
        (
            f"[Documento {_doc_name(chunk)}] section={chunk.section_name} "
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
