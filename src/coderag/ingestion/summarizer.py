"""Text summarization utilities used for document-level chunks."""

from __future__ import annotations


def simple_summary(text: str, max_chars: int = 400) -> str:
    """Create a concise summary from raw content."""
    compact = " ".join(text.split())
    return compact[:max_chars]
