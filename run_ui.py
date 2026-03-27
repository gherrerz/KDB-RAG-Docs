"""Run PySide6 desktop UI."""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_src_path() -> None:
    """Ensure src layout package is importable for local execution."""
    repo_root = Path(__file__).resolve().parent
    src_dir = repo_root / "src"
    if not src_dir.exists():
        return
    src_path = str(src_dir)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


_bootstrap_src_path()

from coderag.ui.main_window import launch_ui


if __name__ == "__main__":
    launch_ui()
