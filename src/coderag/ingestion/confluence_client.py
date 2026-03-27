"""Minimal Confluence client placeholder for future expansion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ConfluenceClient:
    """Simple no-op client to keep architecture extensible."""

    base_url: str
    token: str

    def fetch_pages(self, filters: Dict[str, str]) -> List[Dict[str, str]]:
        """Fetch pages from Confluence API.

        This MVP implementation returns an empty list so local folder mode can
        run without external dependencies.
        """
        _ = filters
        return []
