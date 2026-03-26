"""Dispatch parser by extension."""

from __future__ import annotations

from pathlib import Path

from coderag.parsers.doc_parser import parse_doc
from coderag.parsers.docx_parser import parse_docx
from coderag.parsers.html_parser import parse_html
from coderag.parsers.markdown_parser import parse_markdown
from coderag.parsers.pdf_parser import parse_pdf
from coderag.parsers.pptx_parser import parse_pptx
from coderag.parsers.xlsx_parser import parse_xlsx


def parse_by_extension(file_path: Path) -> str:
    """Parse supported file formats into plain text."""
    suffix = file_path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return parse_markdown(file_path)
    if suffix in {".html", ".htm"}:
        return parse_html(file_path)
    if suffix == ".pdf":
        return parse_pdf(file_path)
    if suffix == ".docx":
        return parse_docx(file_path)
    if suffix == ".doc":
        return parse_doc(file_path)
    if suffix == ".pptx":
        return parse_pptx(file_path)
    if suffix == ".xlsx":
        return parse_xlsx(file_path)
    return ""
