"""HTML parser for stripping tags to plain text."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup


def parse_html(file_path: Path) -> str:
    """Extract plain text from HTML files."""
    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    return soup.get_text("\n")
