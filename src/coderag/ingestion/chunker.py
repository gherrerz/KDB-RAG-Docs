"""Chunking strategies for entity and section level splitting."""

from __future__ import annotations

import re
from typing import Iterable, List

from coderag.core.models import ChunkRecord, DocumentRecord

SECTION_PATTERN = re.compile(r"^#{1,6}\s+(?P<title>.+)$", re.MULTILINE)
ENTITY_PATTERN = re.compile(
    r"\b[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ\-]{2,}"
    r"(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ\-]{2,}){0,2}\b",
    re.UNICODE,
)


def _split_by_sections(text: str) -> Iterable[tuple[str, str]]:
    matches = list(SECTION_PATTERN.finditer(text))
    if not matches:
        yield "General", text
        return

    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        title = match.group("title").strip()
        body = text[start:end].strip()
        if body:
            yield title, body


def build_chunks(
    doc: DocumentRecord,
    max_chars: int = 900,
) -> List[ChunkRecord]:
    """Build semantic chunks from one document."""
    chunks: List[ChunkRecord] = []
    seq = 0
    for section_name, body in _split_by_sections(doc.content):
        pointer = 0
        while pointer < len(body):
            piece = body[pointer:pointer + max_chars].strip()
            if not piece:
                break
            entity = ENTITY_PATTERN.search(piece)
            chunk = ChunkRecord(
                chunk_id=f"{doc.document_id}-c{seq}",
                document_id=doc.document_id,
                source_id=doc.source_id,
                section_name=section_name,
                text=piece,
                start_ref=pointer,
                end_ref=min(pointer + max_chars, len(body)),
                entity_name=entity.group(0) if entity else None,
                entity_type="NamedEntity" if entity else None,
                metadata={"section": section_name},
            )
            chunks.append(chunk)
            pointer += max_chars
            seq += 1
    return chunks
