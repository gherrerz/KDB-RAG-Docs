"""Tests for ingestion mode routing behavior in MainWindow."""

from __future__ import annotations

from typing import Any

from coderag.ui.main_window import MainWindow


def _build_lightweight_window() -> MainWindow:
    """Create a non-Qt-initialized MainWindow instance for method tests."""
    window = MainWindow.__new__(MainWindow)
    window.api_base_url = "http://127.0.0.1:8000"
    return window


def test_main_window_sync_ingestion_uses_sync_endpoint() -> None:
    """Route sync ingestion mode to /sources/ingest without polling."""
    window = _build_lightweight_window()

    captured: list[tuple[str, dict[str, Any], int]] = []

    def _fake_post(path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        captured.append((path, payload, timeout))
        return {"status": "completed", "path": path}

    window._post_json = _fake_post  # type: ignore[method-assign]
    window._poll_job = lambda *args, **kwargs: {"status": "failed"}  # type: ignore[method-assign]

    result = window.ingest(
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


def test_main_window_async_ingestion_uses_async_endpoint_and_polling() -> None:
    """Route async ingestion mode to enqueue endpoint and poll for completion."""
    window = _build_lightweight_window()

    captured: list[tuple[str, dict[str, Any], int]] = []

    def _fake_post(path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        captured.append((path, payload, timeout))
        return {"status": "queued", "job_id": "job-1"}

    window._post_json = _fake_post  # type: ignore[method-assign]
    window._poll_job = (  # type: ignore[method-assign]
        lambda job_id, timeout_seconds, on_update=None: {
            "status": "completed",
            "job_id": job_id,
        }
    )

    result = window.ingest(
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


def test_main_window_ingest_readiness_calls_expected_endpoint() -> None:
    """Fetch async-ingestion readiness from dedicated API endpoint."""
    window = _build_lightweight_window()

    captured: list[tuple[str, int]] = []

    def _fake_get(path: str, timeout: int) -> dict[str, Any]:
        captured.append((path, timeout))
        return {"ready": True}

    window._get_json = _fake_get  # type: ignore[method-assign]

    result = window.ingest_readiness()

    assert result["ready"] is True
    assert captured[0][0] == "/sources/ingest/readiness"


def test_main_window_list_documents_builds_expected_path() -> None:
    """Fetch document catalog through dedicated GET route with source filter."""
    window = _build_lightweight_window()

    captured: list[tuple[str, int]] = []

    def _fake_get(path: str, timeout: int) -> dict[str, Any]:
        captured.append((path, timeout))
        return {"count": 0, "documents": []}

    window._get_json = _fake_get  # type: ignore[method-assign]

    result = window.list_documents("src-1")

    assert result["count"] == 0
    assert captured[0][0] == "/sources/documents?source_id=src-1"


def test_main_window_reset_uses_delete_sources_reset_endpoint() -> None:
    """Route full reset through canonical DELETE /sources/reset endpoint."""
    window = _build_lightweight_window()

    captured: list[tuple[str, int]] = []

    def _fake_delete(path: str, timeout: int) -> dict[str, Any]:
        captured.append((path, timeout))
        return {"status": "completed"}

    window._delete_json = _fake_delete  # type: ignore[method-assign]

    result = window.reset_all()

    assert result["status"] == "completed"
    assert captured[0][0] == "/sources/reset?confirm=true"
