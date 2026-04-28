"""Tests for multipart upload ingestion endpoint behavior."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from coderag.api import server


def test_upload_ingest_stages_file_and_runs_service() -> None:
    """Ingest uploaded file through multipart endpoint and clean staging."""
    client = TestClient(server.app)
    original_ingest = server.SERVICE.ingest
    captured: dict[str, Path] = {}

    def _fake_ingest(request):  # type: ignore[no-untyped-def]
        staged_dir = Path(request.source.local_path or "")
        staged_file = staged_dir / "notes.md"
        assert staged_file.exists()
        assert "Project Atlas" in staged_file.read_text(encoding="utf-8")
        assert request.source.filters == {"domain": "qa"}
        captured["staged_dir"] = staged_dir
        return {
            "job_id": "upload-job-1",
            "status": "completed",
            "message": "ok",
        }

    server.SERVICE.ingest = _fake_ingest  # type: ignore[assignment]
    try:
        response = client.post(
            "/sources/ingest/file",
            files={
                "file": (
                    "notes.md",
                    b"# Notes\nOwner: Project Atlas\n",
                    "text/markdown",
                )
            },
            data={
                "source_type": "folder",
                "filters": '{"domain":"qa"}',
            },
        )
    finally:
        server.SERVICE.ingest = original_ingest  # type: ignore[assignment]

    assert response.status_code == 200
    assert response.json().get("status") == "completed"
    staged_dir = captured["staged_dir"]
    assert not staged_dir.exists()


def test_upload_ingest_rejects_invalid_filters_json() -> None:
    """Reject malformed filters payload passed as multipart form text."""
    client = TestClient(server.app)

    response = client.post(
        "/sources/ingest/file",
        files={"file": ("notes.md", b"hello", "text/markdown")},
        data={"filters": "not-json"},
    )

    assert response.status_code == 422
    assert "filters" in str(response.json().get("detail", "")).lower()


def test_upload_ingest_rejects_unsupported_extension() -> None:
    """Reject uploads with extensions not supported by folder ingestion."""
    client = TestClient(server.app)

    response = client.post(
        "/sources/ingest/file",
        files={"file": ("script.exe", b"binary", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert "unsupported file extension" in str(
        response.json().get("detail", "")
    ).lower()


def test_json_ingest_endpoint_remains_compatible() -> None:
    """Keep the original JSON ingestion contract unchanged."""
    client = TestClient(server.app)
    original_ingest = server.SERVICE.ingest

    def _fake_ingest(request):  # type: ignore[no-untyped-def]
        assert request.source.local_path == "sample_data"
        return {
            "job_id": "json-job-1",
            "status": "completed",
            "message": "ok",
        }

    server.SERVICE.ingest = _fake_ingest  # type: ignore[assignment]
    try:
        response = client.post(
            "/sources/ingest",
            json={
                "source": {
                    "source_type": "folder",
                    "local_path": "sample_data",
                }
            },
        )
    finally:
        server.SERVICE.ingest = original_ingest  # type: ignore[assignment]

    assert response.status_code == 200
    assert response.json().get("status") == "completed"


def test_upload_async_uses_local_queue_and_passes_cleanup_dir() -> None:
    """Enqueue upload ingestion in local async mode and pass cleanup path."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_enqueue_local = server.enqueue_local_ingest_job
    captured: dict[str, str] = {}

    def _fake_enqueue_local(payload, cleanup_staging_dir=None):  # type: ignore[no-untyped-def]
        captured["local_path"] = str(payload["source"]["local_path"])
        captured["cleanup"] = str(cleanup_staging_dir)
        return "upload-local-job-1"

    server.SETTINGS.use_rq = False
    server.enqueue_local_ingest_job = _fake_enqueue_local  # type: ignore[assignment]
    try:
        response = client.post(
            "/sources/ingest/file/async",
            files={"file": ("notes.md", b"hello", "text/markdown")},
            data={"filters": '{"domain":"qa"}'},
        )
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.enqueue_local_ingest_job = original_enqueue_local  # type: ignore[assignment]

    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "queued"
    assert body.get("job_id") == "upload-local-job-1"
    assert captured["local_path"] == captured["cleanup"]


def test_upload_async_rejects_rq_without_shared_staging() -> None:
    """Block RQ upload async when staging is not shared between pods."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_shared = server.SETTINGS.upload_staging_shared

    server.SETTINGS.use_rq = True
    server.SETTINGS.upload_staging_shared = False
    try:
        response = client.post(
            "/sources/ingest/file/async",
            files={"file": ("notes.md", b"hello", "text/markdown")},
        )
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SETTINGS.upload_staging_shared = original_shared

    assert response.status_code == 409
    assert "upload_staging_shared" in str(
        response.json().get("detail", "")
    ).lower()


def test_upload_async_uses_rq_when_staging_is_shared() -> None:
    """Enqueue upload ingestion through RQ when shared staging is enabled."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_shared = server.SETTINGS.upload_staging_shared
    original_enqueue_rq = server.enqueue_ingest_job
    captured: dict[str, str] = {}

    def _fake_enqueue_rq(payload, cleanup_staging_dir=None):  # type: ignore[no-untyped-def]
        captured["local_path"] = str(payload["source"]["local_path"])
        captured["cleanup"] = str(cleanup_staging_dir)
        return "upload-rq-job-1"

    server.SETTINGS.use_rq = True
    server.SETTINGS.upload_staging_shared = True
    server.enqueue_ingest_job = _fake_enqueue_rq  # type: ignore[assignment]
    try:
        response = client.post(
            "/sources/ingest/file/async",
            files={"file": ("notes.md", b"hello", "text/markdown")},
        )
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SETTINGS.upload_staging_shared = original_shared
        server.enqueue_ingest_job = original_enqueue_rq  # type: ignore[assignment]

    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "queued"
    assert body.get("job_id") == "upload-rq-job-1"
    assert captured["local_path"] == captured["cleanup"]


def test_upload_ingest_returns_structured_500_details() -> None:
    """Return structured diagnostics when sync upload ingestion crashes."""
    client = TestClient(server.app)
    original_ingest = server.SERVICE.ingest

    def _fake_ingest(_request):  # type: ignore[no-untyped-def]
        raise ValueError("simulated failure")

    server.SERVICE.ingest = _fake_ingest  # type: ignore[assignment]
    try:
        response = client.post(
            "/sources/ingest/file",
            files={"file": ("notes.md", b"hello", "text/markdown")},
            data={"source_type": "folder", "filters": ""},
        )
    finally:
        server.SERVICE.ingest = original_ingest  # type: ignore[assignment]

    assert response.status_code == 500
    detail = response.json().get("detail", {})
    assert detail.get("operation") == "ingest_source_file"
    assert detail.get("error_type") == "ValueError"
    assert detail.get("context", {}).get("filename") == "notes.md"
