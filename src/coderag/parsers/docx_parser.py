"""DOCX parser for extracting plain text paragraphs."""

from __future__ import annotations

from pathlib import Path


def parse_docx(file_path: Path) -> str:
    """Extract plain text from a DOCX file.

    Returns an empty string when parsing fails so ingestion can continue.
    """
    try:
        from docx import Document

        doc = Document(str(file_path))
        lines = [paragraph.text.strip() for paragraph in doc.paragraphs]
        return "\n".join(line for line in lines if line)
    except Exception:
        return ""
