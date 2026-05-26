"""Run FastAPI backend with Uvicorn."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


def _repo_root() -> Path:
    """Return repository root path for local script execution."""
    return Path(__file__).resolve().parent.parent


def _ensure_repo_cwd() -> None:
    """Pin CWD to repository root for deterministic relative paths."""
    os.chdir(_repo_root())


def _bootstrap_src_path() -> None:
    """Ensure src layout package is importable for local execution."""
    src_dir = Path(__file__).resolve().parent
    src_path = str(src_dir)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


_ensure_repo_cwd()
_bootstrap_src_path()


def _resolve_bind_host_port() -> tuple[str, int]:
    """Resolve host and port used by the local Uvicorn entrypoint."""
    host = str(os.environ.get("API_HOST", "0.0.0.0")).strip() or "0.0.0.0"
    raw_port = str(
        os.environ.get("API_PORT") or os.environ.get("PORT") or "8000"
    ).strip()

    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("API_PORT/PORT must be an integer") from exc

    if port < 1 or port > 65535:
        raise ValueError("API_PORT/PORT must be between 1 and 65535")
    return host, port


if __name__ == "__main__":
    host, port = _resolve_bind_host_port()
    uvicorn.run("coderag.api.server:app", host=host, port=port)
