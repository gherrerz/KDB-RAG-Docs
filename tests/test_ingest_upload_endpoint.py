"""Tests for multipart upload ingestion endpoint behavior."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from coderag.api import server


class _RecordingArtifactStore:
    """Capture artifact creation calls made by the async upload endpoint."""

    def __init__(self) -> None:
        """Initialize empty call capture."""
        self.calls: list[tuple[str, object]] = []

    def create_uploaded_batch_artifact(self, **kwargs):  # type: ignore[no-untyped-def]
        """Record artifact creation payload and return one deterministic id."""
        self.calls.append(("create", kwargs))
        return "artifact-upload-1"

    def mark_processing_failed(self, artifact_id: str, error_message: str) -> None:
        """Record failure fallback calls for diagnostics."""
        self.calls.append(("failed", {"artifact_id": artifact_id, "error_message": error_message}))


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


def test_upload_files_ingest_preserves_nested_logical_names() -> None:
    """Multipart upload should preserve nested logical paths within staging."""
    client = TestClient(server.app)
    original_ingest = server.SERVICE.ingest
    captured: dict[str, object] = {}

    def _fake_ingest(request):  # type: ignore[no-untyped-def]
        staged_dir = Path(request.source.local_path or "")
        nested_file = staged_dir / "sample_data" / "nested" / "notes.md"
        assert nested_file.exists()
        captured["logical_root"] = request.source.logical_root
        return {
            "job_id": "upload-job-nested-1",
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
                        "sample_data/nested/notes.md",
                        b"# Notes\nOwner: Project Atlas\n",
                        "text/markdown",
                    ),
                )
            ],
        )
    finally:
        server.SERVICE.ingest = original_ingest  # type: ignore[assignment]

    assert response.status_code == 200
    assert captured["logical_root"] == ""


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
    captured: dict[str, object] = {}

    def _fake_enqueue_local(payload, cleanup_staging_dir=None):  # type: ignore[no-untyped-def]
        captured["local_path"] = payload["source"].get("local_path")
        captured["artifact_id"] = payload["source"].get("artifact_id")
        captured["cleanup"] = cleanup_staging_dir
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
    assert captured["local_path"] is None
    assert isinstance(captured["artifact_id"], str)
    assert captured["artifact_id"]
    assert captured["cleanup"] is None


def test_upload_files_async_uses_rq_single_file() -> None:
    """Allow RQ async upload for one file via persisted artifacts."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_enqueue_rq = server.enqueue_ingest_job
    captured: dict[str, object] = {}

    def _fake_enqueue_rq(payload, cleanup_staging_dir=None):  # type: ignore[no-untyped-def]
        captured["local_path"] = payload["source"].get("local_path")
        captured["artifact_id"] = payload["source"].get("artifact_id")
        captured["cleanup"] = cleanup_staging_dir
        return "upload-rq-job-0"

    server.SETTINGS.use_rq = True
    server.enqueue_ingest_job = _fake_enqueue_rq  # type: ignore[assignment]
    try:
        response = client.post(
            "/sources/ingest/files/async",
            files=[("files", ("notes.md", b"hello", "text/markdown"))],
        )
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.enqueue_ingest_job = original_enqueue_rq  # type: ignore[assignment]

    assert response.status_code == 200
    assert response.json().get("job_id") == "upload-rq-job-0"
    assert captured["local_path"] is None
    assert isinstance(captured["artifact_id"], str)
    assert captured["artifact_id"]
    assert captured["cleanup"] is None


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


def test_upload_files_async_uses_local_queue_batch_upload() -> None:
    """Enqueue one uploaded batch in local async mode via artifacts."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_enqueue_local = server.enqueue_local_ingest_job
    captured: dict[str, object] = {}

    def _fake_enqueue_local(payload, cleanup_staging_dir=None):  # type: ignore[no-untyped-def]
        captured["local_path"] = payload["source"].get("local_path")
        captured["artifact_id"] = payload["source"].get("artifact_id")
        captured["cleanup"] = cleanup_staging_dir
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
    assert captured["local_path"] is None
    assert isinstance(captured["artifact_id"], str)
    assert captured["artifact_id"]
    assert captured["cleanup"] is None


def test_upload_files_async_persists_artifact_and_passes_artifact_id() -> None:
    """Async upload should persist one artifact and forward artifact_id."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_enqueue_local = server.enqueue_local_ingest_job
    original_artifact_store = server.RUNTIME.ingestion_artifact_store
    captured: dict[str, object] = {}
    artifact_store = _RecordingArtifactStore()

    def _fake_enqueue_local(payload, cleanup_staging_dir=None):  # type: ignore[no-untyped-def]
        captured["payload"] = payload
        captured["cleanup"] = cleanup_staging_dir
        return "upload-artifact-job-1"

    server.SETTINGS.use_rq = False
    server.enqueue_local_ingest_job = _fake_enqueue_local  # type: ignore[assignment]
    server.RUNTIME.ingestion_artifact_store = artifact_store  # type: ignore[assignment]
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
        server.RUNTIME.ingestion_artifact_store = original_artifact_store  # type: ignore[assignment]

    assert response.status_code == 200
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["source"]["artifact_id"] == "artifact-upload-1"
    assert artifact_store.calls
    created_call = artifact_store.calls[0]
    assert created_call[0] == "create"
    created_kwargs = created_call[1]
    assert isinstance(created_kwargs, dict)
    assert created_kwargs["source_type"] == "folder"
    files_payload = created_kwargs["files"]
    assert isinstance(files_payload, list)
    assert len(files_payload) == 2

    assert captured["cleanup"] is None


def test_upload_files_async_uses_rq_batch_upload() -> None:
    """Allow RQ async batch upload because workers rehydrate artifacts."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_enqueue_rq = server.enqueue_ingest_job
    captured: dict[str, object] = {}

    def _fake_enqueue_rq(payload, cleanup_staging_dir=None):  # type: ignore[no-untyped-def]
        captured["local_path"] = payload["source"].get("local_path")
        captured["artifact_id"] = payload["source"].get("artifact_id")
        captured["cleanup"] = cleanup_staging_dir
        return "upload-rq-job-2"

    server.SETTINGS.use_rq = True
    server.enqueue_ingest_job = _fake_enqueue_rq  # type: ignore[assignment]
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
        server.enqueue_ingest_job = original_enqueue_rq  # type: ignore[assignment]

    assert response.status_code == 200
    assert response.json().get("job_id") == "upload-rq-job-2"
    assert captured["local_path"] is None
    assert isinstance(captured["artifact_id"], str)
    assert captured["artifact_id"]
    assert captured["cleanup"] is None
