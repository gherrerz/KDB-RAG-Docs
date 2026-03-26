"""File discovery for folder-based ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

ALLOWED_EXTENSIONS = {
    ".md",
    ".txt",
    ".html",
    ".htm",
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".xlsx",
}


def scan_folder(path: Path) -> List[Path]:
    """Return supported files recursively from a root path."""
    if not path.exists():
        return []
    files: Iterable[Path] = path.rglob("*")
    return [
        file_path
        for file_path in files
        if file_path.is_file()
        and file_path.suffix.lower() in ALLOWED_EXTENSIONS
    ]
