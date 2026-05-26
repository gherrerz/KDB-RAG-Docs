"""Run PySide6 desktop UI."""

from __future__ import annotations

import os
import sys
from pathlib import Path


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

from coderag.ui.main_window import launch_ui


def _resolve_api_connect_host() -> str:
    """Resolve the host the desktop UI should use to reach the API."""
    explicit_ui_host = str(os.environ.get("UI_API_HOST", "")).strip()
    if explicit_ui_host:
        return explicit_ui_host

    api_host = str(os.environ.get("API_HOST", "")).strip()
    if api_host in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    if api_host:
        return api_host
    return "127.0.0.1"


def _resolve_api_base_url() -> str:
    """Resolve the backend base URL used by the desktop UI entrypoint."""
    explicit = str(os.environ.get("API_BASE_URL", "")).strip()
    if explicit:
        return explicit.rstrip("/")

    host = _resolve_api_connect_host()

    raw_port = str(
        os.environ.get("UI_API_PORT")
        or os.environ.get("API_PORT")
        or os.environ.get("PORT")
        or "8000"
    ).strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError(
            "UI_API_PORT/API_PORT/PORT must be an integer"
        ) from exc

    if port < 1 or port > 65535:
        raise ValueError(
            "UI_API_PORT/API_PORT/PORT must be between 1 and 65535"
        )
    return f"http://{host}:{port}"


if __name__ == "__main__":
    launch_ui(api_base_url=_resolve_api_base_url())
