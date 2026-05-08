"""Tests for multipart upload ingestion endpoint behavior."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from coderag.api import server


def test_upload_files_ingest_stages_single_file_and_runs_service() -> None:
    """Ingest one uploaded file through plural multipart endpoint."""
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
            "/sources/ingest/files",
            files=[
                (
                    "files",
                    (
                        "notes.md",
                        b"# Notes\nOwner: Project Atlas\n",
                        "text/markdown",
                    ),
                )
            ],
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


def test_upload_files_ingest_rejects_invalid_filters_json() -> None:
    """Reject malformed filters payload passed to plural endpoint."""
    client = TestClient(server.app)

    response = client.post(
        "/sources/ingest/files",
        files=[("files", ("notes.md", b"hello", "text/markdown"))],
        data={"filters": "not-json"},
    )

    assert response.status_code == 422
    assert "filters" in str(response.json().get("detail", "")).lower()


def test_upload_files_ingest_rejects_unsupported_extension_single_file() -> None:
    """Reject one uploaded file with unsupported extension via plural route."""
    client = TestClient(server.app)

    response = client.post(
        "/sources/ingest/files",
        files=[
            (
                "files",
                ("script.exe", b"binary", "application/octet-stream"),
            )
        ],
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


def test_upload_files_async_uses_local_queue_for_single_file() -> None:
    """Enqueue one uploaded file through plural async endpoint."""
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
            "/sources/ingest/files/async",
            files=[("files", ("notes.md", b"hello", "text/markdown"))],
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


def test_upload_files_async_rejects_rq_without_shared_staging_single_file() -> None:
    """Block plural async upload for one file when staging is not shared."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_shared = server.SETTINGS.upload_staging_shared

    server.SETTINGS.use_rq = True
    server.SETTINGS.upload_staging_shared = False
    try:
        response = client.post(
            "/sources/ingest/files/async",
            files=[("files", ("notes.md", b"hello", "text/markdown"))],
        )
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SETTINGS.upload_staging_shared = original_shared

    assert response.status_code == 409
    assert "upload_staging_shared" in str(
        response.json().get("detail", "")
    ).lower()


def test_upload_files_async_uses_rq_when_staging_is_shared_single_file() -> None:
    """Enqueue one uploaded file through plural async route with RQ."""
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
            "/sources/ingest/files/async",
            files=[("files", ("notes.md", b"hello", "text/markdown"))],
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


def test_upload_files_ingest_returns_structured_500_details() -> None:
    """Return structured diagnostics when plural sync upload crashes."""
    client = TestClient(server.app)
    original_ingest = server.SERVICE.ingest

    def _fake_ingest(_request):  # type: ignore[no-untyped-def]
        raise ValueError("simulated failure")

    server.SERVICE.ingest = _fake_ingest  # type: ignore[assignment]
    try:
        response = client.post(
            "/sources/ingest/files",
            files=[("files", ("notes.md", b"hello", "text/markdown"))],
            data={"source_type": "folder", "filters": ""},
        )
    finally:
        server.SERVICE.ingest = original_ingest  # type: ignore[assignment]

    assert response.status_code == 500
    detail = response.json().get("detail", {})
    assert detail.get("operation") == "ingest_source_files"
    assert detail.get("error_type") == "ValueError"
    assert detail.get("context", {}).get("filenames") == ["notes.md"]
    assert detail.get("context", {}).get("file_count") == 1


def test_upload_files_ingest_stages_batch_and_runs_service() -> None:
    """Ingest a multipart batch and clean staged directory after completion."""
    client = TestClient(server.app)
    original_ingest = server.SERVICE.ingest
    captured: dict[str, Path] = {}

    def _fake_ingest(request):  # type: ignore[no-untyped-def]
        staged_dir = Path(request.source.local_path or "")
        staged_files = sorted(item.name for item in staged_dir.iterdir())
        assert staged_files == ["notes.md", "plan.txt"]
        assert request.source.filters == {"domain": "qa"}
        captured["staged_dir"] = staged_dir
        return {
            "job_id": "upload-batch-job-1",
            "status": "completed",
            "message": "ok",
        }

    server.SERVICE.ingest = _fake_ingest  # type: ignore[assignment]
    try:
        response = client.post(
            "/sources/ingest/files",
            files=[
                ("files", ("notes.md", b"hello", "text/markdown")),
                ("files", ("plan.txt", b"world", "text/plain")),
            ],
            data={"source_type": "folder", "filters": '{"domain":"qa"}'},
        )
    finally:
        server.SERVICE.ingest = original_ingest  # type: ignore[assignment]

    assert response.status_code == 200
    assert response.json().get("status") == "completed"
    assert not captured["staged_dir"].exists()


def test_upload_files_ingest_dedupes_sanitized_name_collisions() -> None:
    """Keep both files when names collide after sanitization."""
    client = TestClient(server.app)
    original_ingest = server.SERVICE.ingest
    captured: dict[str, Path] = {}

    def _fake_ingest(request):  # type: ignore[no-untyped-def]
        staged_dir = Path(request.source.local_path or "")
        staged_files = sorted(item.name for item in staged_dir.iterdir())
        assert staged_files == ["Doc.md", "doc_2.md"]
        captured["staged_dir"] = staged_dir
        return {
            "job_id": "upload-batch-job-2",
            "status": "completed",
            "message": "ok",
        }

    server.SERVICE.ingest = _fake_ingest  # type: ignore[assignment]
    try:
        response = client.post(
            "/sources/ingest/files",
            files=[
                ("files", ("Doc.md", b"first", "text/markdown")),
                ("files", ("doc.md", b"second", "text/markdown")),
            ],
            data={"source_type": "folder"},
        )
    finally:
        server.SERVICE.ingest = original_ingest  # type: ignore[assignment]

    assert response.status_code == 200
    assert not captured["staged_dir"].exists()


def test_upload_files_ingest_rejects_unsupported_extension() -> None:
    """Reject batch when any file has unsupported extension."""
    client = TestClient(server.app)

    response = client.post(
        "/sources/ingest/files",
        files=[
            ("files", ("ok.md", b"hello", "text/markdown")),
            ("files", ("bad.exe", b"binary", "application/octet-stream")),
        ],
    )

    assert response.status_code == 422
    assert "unsupported file extension" in str(
        response.json().get("detail", "")
    ).lower()


def test_upload_files_ingest_rejects_empty_batch() -> None:
    """Reject multipart request without required files form parts."""
    client = TestClient(server.app)

    response = client.post(
        "/sources/ingest/files",
        data={"source_type": "folder"},
    )

    assert response.status_code == 422


def test_upload_files_async_uses_local_queue_and_passes_cleanup_dir() -> None:
    """Enqueue one staged batch in local async mode."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_enqueue_local = server.enqueue_local_ingest_job
    captured: dict[str, str] = {}

    def _fake_enqueue_local(payload, cleanup_staging_dir=None):  # type: ignore[no-untyped-def]
        captured["local_path"] = str(payload["source"]["local_path"])
        captured["cleanup"] = str(cleanup_staging_dir)
        return "upload-files-local-job-1"

    server.SETTINGS.use_rq = False
    server.enqueue_local_ingest_job = _fake_enqueue_local  # type: ignore[assignment]
    try:
        response = client.post(
            "/sources/ingest/files/async",
            files=[
                ("files", ("one.md", b"a", "text/markdown")),
                ("files", ("two.md", b"b", "text/markdown")),
            ],
            data={"filters": '{"domain":"qa"}'},
        )
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.enqueue_local_ingest_job = original_enqueue_local  # type: ignore[assignment]

    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "queued"
    assert body.get("job_id") == "upload-files-local-job-1"
    assert captured["local_path"] == captured["cleanup"]
    staged_dir = Path(captured["local_path"])
    assert staged_dir.exists()
    server.UPLOAD_INGESTION.cleanup(staged_dir)


def test_upload_files_async_rejects_rq_without_shared_staging() -> None:
    """Block RQ async batch upload when staging volume is not shared."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_shared = server.SETTINGS.upload_staging_shared

    server.SETTINGS.use_rq = True
    server.SETTINGS.upload_staging_shared = False
    try:
        response = client.post(
            "/sources/ingest/files/async",
            files=[
                ("files", ("one.md", b"a", "text/markdown")),
                ("files", ("two.md", b"b", "text/markdown")),
            ],
        )
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SETTINGS.upload_staging_shared = original_shared

    assert response.status_code == 409
    assert "upload_staging_shared" in str(
        response.json().get("detail", "")
    ).lower()
