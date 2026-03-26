"""Dispatch parser by extension."""

from __future__ import annotations

from pathlib import Path

from coderag.parsers.html_parser import parse_html
from coderag.parsers.markdown_parser import parse_markdown
from coderag.parsers.pdf_parser import parse_pdf


def parse_by_extension(file_path: Path) -> str:
    """Parse supported file formats into plain text."""
    suffix = file_path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return parse_markdown(file_path)
    if suffix in {".html", ".htm"}:
        return parse_html(file_path)
    if suffix == ".pdf":
        return parse_pdf(file_path)
    return ""
