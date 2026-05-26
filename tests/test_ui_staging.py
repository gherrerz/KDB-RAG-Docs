"""Tests for local folder ingestion preparation in the desktop UI."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from coderag.ui import main_window


def test_collect_upload_file_paths_expands_directories_recursively(
    tmp_path: Path,
) -> None:
    """Expand selected directories into supported files for multipart upload."""
    source = tmp_path / "docs"
    nested = source / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    (source / "a.md").write_text("content", encoding="utf-8")
    (nested / "b.txt").write_text("content", encoding="utf-8")
    (nested / "ignore.bin").write_bytes(b"x")

    collected = main_window._collect_upload_file_paths(str(source))

    assert collected == [source / "a.md", nested / "b.txt"]


def test_collect_upload_entries_preserves_logical_folder_prefix(
    tmp_path: Path,
) -> None:
    """Directory uploads should preserve one stable logical root prefix."""
    source = tmp_path / "sample_data"
    nested = source / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    (source / "a.md").write_text("content", encoding="utf-8")
    (nested / "b.txt").write_text("content", encoding="utf-8")

    entries = main_window._collect_upload_entries(str(source))

    assert entries == [
        (source / "a.md", "sample_data/a.md"),
        (nested / "b.txt", "sample_data/nested/b.txt"),
    ]


def test_ingest_routes_folder_source_via_upload() -> None:
    """Folder sources should route through multipart upload instead of JSON."""
    calls: list[str] = []

    class _Window:
        def _ingest_via_upload(self, payload, on_update=None):  # type: ignore[no-untyped-def]
            calls.append("upload")
            return {"status": "queued", "job_id": "job-1"}

        def _post_json(self, path, payload, timeout):  # type: ignore[no-untyped-def]
            calls.append("json")
            return {"status": "completed"}

    payload = {
        "source": {
            "source_type": "folder",
            "local_path": "C:/storage/example",
            "filters": {},
        },
        "_ingestion_channel": "json_folder",
        "_ingestion_mode": "async",
    }

    result = main_window.MainWindow.ingest(_Window(), payload)

    assert result["status"] == "queued"
    assert calls == ["upload"]


def test_prepare_ingestion_payload_keeps_confluence_unchanged() -> None:
    """Non-folder sources should keep using JSON ingestion path."""
    payload = {
        "source": {
            "source_type": "confluence",
            "base_url": "https://company.atlassian.net/wiki",
            "token": "x",
            "filters": {},
        }
    }

    calls: list[str] = []

    class _Window:
        def _ingest_via_upload(self, payload, on_update=None):  # type: ignore[no-untyped-def]
            calls.append("upload")
            return {"status": "failed"}

        def _post_json(self, path, body, timeout):  # type: ignore[no-untyped-def]
            calls.append(path)
            return {"status": "completed", "path": path, "payload": body}

    result = main_window.MainWindow.ingest(_Window(), payload)

    assert result["status"] == "completed"
    assert calls == ["/sources/ingest/async"]