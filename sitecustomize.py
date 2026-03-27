"""Automatically add src/ to sys.path for local execution."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    """Prepend src path so imports resolve with src layout."""
    repo_root = Path(__file__).resolve().parent
    src_dir = repo_root / "src"
    if not src_dir.exists():
        return
    src_path = str(src_dir)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


_ensure_src_on_path()
