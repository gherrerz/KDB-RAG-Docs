"""Markdown parser returning plain text."""

from __future__ import annotations

from pathlib import Path


def parse_markdown(file_path: Path) -> str:
    """Read markdown file as text."""
    return file_path.read_text(encoding="utf-8", errors="ignore")
