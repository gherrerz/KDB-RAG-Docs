"""Run FastAPI backend with Uvicorn."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


def _repo_root() -> Path:
    """Return repository root path for local script execution."""
    return Path(__file__).resolve().parent


def _ensure_repo_cwd() -> None:
    """Pin CWD to repository root for deterministic relative paths."""
    os.chdir(_repo_root())


def _bootstrap_src_path() -> None:
    """Ensure src layout package is importable for local execution."""
    repo_root = _repo_root()
    src_dir = repo_root / "src"
    if not src_dir.exists():
        return
    src_path = str(src_dir)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


_ensure_repo_cwd()
_bootstrap_src_path()


if __name__ == "__main__":
    uvicorn.run("coderag.api.server:app", host="0.0.0.0", port=8000)
