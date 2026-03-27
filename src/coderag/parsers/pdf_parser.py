"""PDF parser using pypdf with graceful fallback on parsing errors."""

from __future__ import annotations

from pathlib import Path


def parse_pdf(file_path: Path) -> str:
    """Extract plain text from a PDF file.

    Returns an empty string when extraction fails so ingestion can continue.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text.strip())
        return "\n\n".join(part for part in pages if part)
    except Exception:
        return ""
