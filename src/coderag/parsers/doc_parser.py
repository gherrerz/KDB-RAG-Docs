"""Legacy DOC parser with best-effort text extraction."""

from __future__ import annotations

import re
from pathlib import Path


_ASCII_PATTERN = re.compile(rb"[ -~]{4,}")
_TEXT_PATTERN = re.compile(r"[ -~]{4,}")


def _ascii_chunks(data: bytes) -> list[str]:
    """Extract ASCII-like byte sequences from binary data."""
    return [chunk.decode("latin1", errors="ignore") for chunk in _ASCII_PATTERN.findall(data)]


def _utf16_chunks(data: bytes) -> list[str]:
    """Extract UTF-16LE textual sequences from binary data."""
    text = data.decode("utf-16le", errors="ignore")
    return _TEXT_PATTERN.findall(text)


def _normalize(chunks: list[str]) -> str:
    """Normalize, deduplicate, and join extracted text chunks."""
    seen: set[str] = set()
    ordered: list[str] = []
    for chunk in chunks:
        line = " ".join(chunk.split()).strip()
        if len(line) < 4:
            continue
        if line in seen:
            continue
        seen.add(line)
        ordered.append(line)
    return "\n".join(ordered[:300])


def parse_doc(file_path: Path) -> str:
    """Extract plain text from legacy .doc files.

    The parser uses a robust fallback strategy over binary streams to avoid
    hard dependency on external converters.
    """
    try:
        data = file_path.read_bytes()
    except OSError:
        return ""

    chunks = _ascii_chunks(data)
    chunks.extend(_utf16_chunks(data))
    return _normalize(chunks)
