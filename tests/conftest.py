"""Pytest bootstrap for src layout imports."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    """Prepend src path so tests can import coderag package."""
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if not src_dir.exists():
        return
    src_path = str(src_dir)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


_ensure_src_on_path()
