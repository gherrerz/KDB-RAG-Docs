"""Regression tests for entrypoint CWD pinning."""

from __future__ import annotations

from pathlib import Path

import run_api
import run_ui


def test_run_api_pins_cwd_to_repo_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Ensure API entrypoint helper resets CWD to repository root."""
    monkeypatch.chdir(tmp_path)
    run_api._ensure_repo_cwd()

    assert Path.cwd() == run_api._repo_root()


def test_run_ui_pins_cwd_to_repo_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Ensure UI entrypoint helper resets CWD to repository root."""
    monkeypatch.chdir(tmp_path)
    run_ui._ensure_repo_cwd()

    assert Path.cwd() == run_ui._repo_root()
