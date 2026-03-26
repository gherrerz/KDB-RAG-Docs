"""PDF parsing placeholder for future extension."""

from __future__ import annotations

from pathlib import Path


def parse_pdf(file_path: Path) -> str:
    """Return a placeholder when PDF extraction is unavailable.

    PDF support can be added with pypdf or pymupdf in future revisions.
    """
    _ = file_path
    return ""
