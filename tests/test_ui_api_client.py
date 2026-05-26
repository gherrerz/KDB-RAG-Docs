"""Unit tests for UiApiClient routing and payload helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coderag.ui.api_client import UiApiClient


def test_ui_api_client_sync_ingestion_uses_sync_endpoint() -> None:
    """Route sync ingestion mode to /sources/ingest without polling."""
    client = UiApiClient()
    captured: list[tuple[str, dict[str, object], int]] = []

    def _fake_post(path: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        captured.append((path, payload, timeout))
        return {"status": "completed", "path": path}

    client.post_json = _fake_post  # type: ignore[method-assign]

    result = client.ingest(
        {
            "_ingestion_mode": "sync",
            "source": {
                "source_type": "confluence",
                "base_url": "https://example.atlassian.net/wiki",
                "token": "x",
                "filters": {},
            },
        }
    )

    assert result["status"] == "completed"
    assert captured[0][0] == "/sources/ingest"


def test_ui_api_client_async_ingestion_polls_job() -> None:
    """Route async ingestion mode to enqueue endpoint and poll completion."""
    client = UiApiClient()
    captured: list[tuple[str, dict[str, object], int]] = []

    def _fake_post(path: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        captured.append((path, payload, timeout))
        return {"status": "queued", "job_id": "job-1"}

    client.post_json = _fake_post  # type: ignore[method-assign]
    client.poll_job = lambda job_id, timeout_seconds, on_update=None: {  # type: ignore[method-assign]
        "status": "completed",
        "job_id": job_id,
    }

    result = client.ingest(
        {
            "_ingestion_mode": "async",
            "source": {
                "source_type": "confluence",
                "base_url": "https://example.atlassian.net/wiki",
                "token": "x",
                "filters": {},
            },
        }
    )

    assert result["status"] == "completed"
    assert result["job_id"] == "job-1"
    assert captured[0][0] == "/sources/ingest/async"


def test_ui_api_client_upload_async_uses_multipart_and_polling(
    tmp_path: Path,
) -> None:
    """Route upload async mode to multipart async endpoint and poll."""
    client = UiApiClient()
    first_file = tmp_path / "sample.md"
    second_file = tmp_path / "notes.txt"
    first_file.write_text("hello", encoding="utf-8")
    second_file.write_text("world", encoding="utf-8")

    captured: list[
        tuple[
            str,
            list[tuple[Path, str]],
            str,
            dict[str, Any],
            list[str],
            int,
        ]
    ] = []

    def _fake_post_multipart(
        path: str,
        upload_entries: list[tuple[Path, str]],
        source_type: str,
        filters: dict[str, object],
        tags: list[str],
        timeout: int,
    ) -> dict[str, object]:
        captured.append((path, upload_entries, source_type, filters, tags, timeout))
        return {"status": "queued", "job_id": "upload-job-1"}

    client.post_multipart = _fake_post_multipart  # type: ignore[method-assign]
    client.poll_job = lambda job_id, timeout_seconds, on_update=None: {  # type: ignore[method-assign]
        "status": "completed",
        "job_id": job_id,
    }

    result = client.ingest(
        {
            "_ingestion_channel": "upload_file",
            "_ingestion_mode": "async",
            "source": {
                "source_type": "folder",
                "local_path": f"{first_file};{second_file}",
                "filters": {},
                "tags": ["release"],
            },
        }
    )

    assert result["status"] == "completed"
    assert result["job_id"] == "upload-job-1"
    assert captured[0][0] == "/sources/ingest/files/async"
    assert captured[0][1] == [(first_file, first_file.name), (second_file, second_file.name)]
    assert captured[0][4] == ["release"]


def test_ui_api_client_list_documents_builds_encoded_path() -> None:
    """Build query string with source_id and tags for document listing."""
    client = UiApiClient()
    captured: list[tuple[str, int]] = []

    def _fake_get(path: str, timeout: int) -> dict[str, object]:
        captured.append((path, timeout))
        return {"count": 0, "documents": []}

    client.get_json = _fake_get  # type: ignore[method-assign]

    result = client.list_documents("src-1", ["finance", "urgent"])

    assert result["count"] == 0
    assert captured[0][0] == "/sources/documents?source_id=src-1&tags=finance%2Curgent"
