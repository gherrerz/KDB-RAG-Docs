"""Tests for local folder staging before ingestion requests."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from coderag.core.settings import SETTINGS
from coderag.ui import main_window
from coderag.ui import staging


def test_stage_folder_source_returns_data_dir_backed_runtime_path(
    tmp_path: Path,
) -> None:
    """Stage selected folder and return runtime path rooted in data_dir."""
    source = tmp_path / "docs"
    source.mkdir(parents=True, exist_ok=True)
    (source / "a.md").write_text("content", encoding="utf-8")

    original_root = staging.REPO_ROOT
    original_data_dir = SETTINGS.data_dir
    staging.REPO_ROOT = tmp_path
    SETTINGS.data_dir = tmp_path / "runtime-storage"
    expected_staging_root = SETTINGS.data_dir / "ingestion_staging"
    try:
        runtime_path, metadata = staging.stage_folder_source("docs")
    finally:
        staging.REPO_ROOT = original_root
        SETTINGS.data_dir = original_data_dir

    staged_dir = Path(runtime_path)
    assert staged_dir.parent == expected_staging_root
    assert staged_dir.exists()
    assert (staged_dir / "a.md").exists()
    assert metadata["runtime_local_path"] == runtime_path


def test_prepare_ingestion_payload_stages_folder(monkeypatch) -> None:
    """Rewrite folder payload path to staging runtime path before API call."""

    def _fake_stage(local_path: str):
        return (
            "storage/ingestion_staging/test_case",
            {
                "source_path": local_path,
                "staged_path": "X",
                "runtime_local_path": "storage/ingestion_staging/test_case",
            },
        )

    monkeypatch.setattr(main_window, "stage_folder_source", _fake_stage)
    payload = {
        "source": {
            "source_type": "folder",
            "local_path": "C:/storage/example",
            "filters": {},
        }
    }

    prepared, update = main_window._prepare_ingestion_payload(payload)

    assert prepared["source"]["local_path"] == "storage/ingestion_staging/test_case"
    assert isinstance(update, dict)
    assert update.get("status") == "running"
    assert payload["source"]["local_path"] == "C:/storage/example"


def test_prepare_ingestion_payload_keeps_confluence_unchanged() -> None:
    """Skip staging for non-folder sources."""
    payload = {
        "source": {
            "source_type": "confluence",
            "base_url": "https://company.atlassian.net/wiki",
            "token": "x",
            "filters": {},
        }
    }

    prepared, update = main_window._prepare_ingestion_payload(payload)

    assert prepared == payload
    assert update is None