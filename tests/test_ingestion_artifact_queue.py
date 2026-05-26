"""Tests for async queue integration with ingestion artifacts."""

from __future__ import annotations

from pathlib import Path
import shutil
import threading

import pytest

from coderag.jobs import queue


class _RecordingArtifactStore:
    """Capture artifact lifecycle calls made by queue helpers."""

    def __init__(self) -> None:
        """Initialize empty call capture."""
        self.calls: list[tuple[str, str, str | None]] = []
        self.materialized_dir: str | None = None

    def attach_job(self, artifact_id: str, job_id: str) -> None:
        """Record job attachment."""
        self.calls.append(("attach_job", artifact_id, job_id))

    def mark_processing_started(self, artifact_id: str) -> None:
        """Record processing start."""
        self.calls.append(("started", artifact_id, None))

    def mark_processing_completed(self, artifact_id: str) -> None:
        """Record processing completion."""
        self.calls.append(("completed", artifact_id, None))

    def mark_processing_failed(
        self,
        artifact_id: str,
        error_message: str,
    ) -> None:
        """Record processing failure."""
        self.calls.append(("failed", artifact_id, error_message))

    def materialize_uploaded_batch(self, artifact_id: str) -> str:
        """Return one configured materialized directory for worker tests."""
        self.calls.append(("materialize", artifact_id, None))
        if self.materialized_dir is None:
            raise AssertionError("materialized_dir must be configured in test")
        return self.materialized_dir

    def clear_uploaded_artifacts(self) -> int:
        """Record artifact cleanup during reset tests."""
        self.calls.append(("clear", "artifacts", None))
        return 1


class _DummyThread:
    """Simple thread stand-in that avoids executing background work."""

    def __init__(self, target, args, daemon) -> None:  # type: ignore[no-untyped-def]
        """Store constructor args for assertions."""
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        """Mark the thread as started without executing the target."""
        self.started = True


def test_enqueue_local_ingest_job_persists_job_before_attaching_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local async enqueue should create the job row before artifact FK attach."""
    artifact_store = _RecordingArtifactStore()
    call_order: list[tuple[str, str]] = []

    def _touch_job(job_id: str, status: str, message: str) -> None:
        call_order.append(("touch_job", job_id))

    def _attach_job(artifact_id: str, job_id: str) -> None:
        call_order.append(("attach_job", job_id))
        artifact_store.calls.append(("attach_job", artifact_id, job_id))

    monkeypatch.setattr(queue.RUNTIME, "ingestion_artifact_store", artifact_store)
    monkeypatch.setattr(queue.RUNTIME.store, "touch_job", _touch_job)
    monkeypatch.setattr(artifact_store, "attach_job", _attach_job)
    monkeypatch.setattr(threading, "Thread", _DummyThread)

    job_id = queue.enqueue_local_ingest_job(
        {
            "source": {
                "source_type": "folder",
                "local_path": "sample_data",
                "artifact_id": "artifact-1",
            }
        }
    )

    assert call_order == [
        ("touch_job", job_id),
        ("attach_job", job_id),
    ]
    assert artifact_store.calls == [("attach_job", "artifact-1", job_id)]
    queue._LOCAL_THREADS.pop(job_id, None)


def test_enqueue_rq_ingest_job_persists_job_before_attaching_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RQ enqueue should create the job row before artifact FK attach."""
    artifact_store = _RecordingArtifactStore()
    call_order: list[tuple[str, str]] = []

    class _FakeRedis:
        @staticmethod
        def from_url(_url: str):
            return object()

    class _FakeQueue:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def enqueue(self, _func, *args, **kwargs):
            job_id = str(kwargs["job_id"])

            class _FakeJob:
                id = job_id

            return _FakeJob()

    def _touch_job(job_id: str, status: str, message: str) -> None:
        call_order.append(("touch_job", job_id))

    def _attach_job(artifact_id: str, job_id: str) -> None:
        call_order.append(("attach_job", job_id))
        artifact_store.calls.append(("attach_job", artifact_id, job_id))

    monkeypatch.setattr(queue.RUNTIME, "ingestion_artifact_store", artifact_store)
    monkeypatch.setattr(queue.RUNTIME.store, "touch_job", _touch_job)
    monkeypatch.setattr(artifact_store, "attach_job", _attach_job)
    monkeypatch.setattr(
        queue,
        "_load_rq_modules",
        lambda: (_FakeRedis, _FakeQueue, object),
    )

    job_id = queue.enqueue_ingest_job(
        {
            "source": {
                "source_type": "folder",
                "local_path": "sample_data",
                "artifact_id": "artifact-1",
            }
        }
    )

    assert job_id
    assert call_order == [
        ("touch_job", job_id),
        ("attach_job", job_id),
    ]
    assert artifact_store.calls == [("attach_job", "artifact-1", job_id)]


def test_run_local_ingest_job_rehydrates_payload_from_artifact_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local worker should rehydrate artifact files and clean temp materialization."""
    artifact_store = _RecordingArtifactStore()
    materialized_dir = tmp_path / "materialized"
    materialized_dir.mkdir(parents=True, exist_ok=True)
    (materialized_dir / "notes.md").write_text("hello", encoding="utf-8")
    artifact_store.materialized_dir = str(materialized_dir)
    monkeypatch.setattr(queue.RUNTIME, "ingestion_artifact_store", artifact_store)
    monkeypatch.setattr(queue.RUNTIME.store, "touch_job", lambda *args, **kwargs: None)

    import coderag.core.service as service_module

    original_service = service_module.SERVICE

    class _FakeService:
        def ingest(self, request, job_id=None):  # type: ignore[no-untyped-def]
            assert request.source.local_path == str(materialized_dir)
            assert request.source.artifact_id == "artifact-1"
            assert job_id == "job-1"
            return {"status": "completed"}

    service_module.SERVICE = _FakeService()  # type: ignore[assignment]
    try:
        queue._run_local_ingest_job(
            "job-1",
            {
                "source": {
                    "source_type": "folder",
                    "artifact_id": "artifact-1",
                }
            },
        )
    finally:
        service_module.SERVICE = original_service  # type: ignore[assignment]
        queue._LOCAL_THREADS.pop("job-1", None)

    assert artifact_store.calls == [
        ("materialize", "artifact-1", None),
        ("started", "artifact-1", None),
        ("completed", "artifact-1", None),
    ]
    assert not materialized_dir.exists()


def test_ingest_task_marks_artifact_failed_on_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """RQ worker entrypoint should mark artifact failure when ingest crashes."""
    artifact_store = _RecordingArtifactStore()
    materialized_dir = tmp_path / "materialized"
    materialized_dir.mkdir(parents=True, exist_ok=True)
    artifact_store.materialized_dir = str(materialized_dir)
    failures: list[tuple[str, str, str]] = []
    monkeypatch.setattr(queue.RUNTIME, "ingestion_artifact_store", artifact_store)
    monkeypatch.setattr(
        queue.RUNTIME.store,
        "touch_job",
        lambda job_id, status, message: failures.append((job_id, status, message)),
    )

    class _FailingService:
        def ingest(self, request, job_id=None):  # type: ignore[no-untyped-def]
            raise ValueError("simulated failure")

    monkeypatch.setattr(queue, "RagApplicationService", _FailingService)

    with pytest.raises(ValueError, match="simulated failure"):
        queue.ingest_task(
            "job-1",
            {
                "source": {
                    "source_type": "folder",
                    "local_path": "sample_data",
                    "artifact_id": "artifact-1",
                }
            },
        )

    assert artifact_store.calls == [
        ("materialize", "artifact-1", None),
        ("started", "artifact-1", None),
        ("failed", "artifact-1", "simulated failure"),
    ]
    assert failures == [
        ("job-1", "failed", "FAILED | rq worker: simulated failure")
    ]
    assert not materialized_dir.exists()


def test_ingest_task_rehydrates_payload_from_artifact_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """RQ worker should rehydrate local_path from persisted artifact files."""
    artifact_store = _RecordingArtifactStore()
    materialized_dir = tmp_path / "materialized"
    materialized_dir.mkdir(parents=True, exist_ok=True)
    (materialized_dir / "notes.md").write_text("hello", encoding="utf-8")
    artifact_store.materialized_dir = str(materialized_dir)
    monkeypatch.setattr(queue.RUNTIME, "ingestion_artifact_store", artifact_store)
    monkeypatch.setattr(queue.RUNTIME.store, "touch_job", lambda *args, **kwargs: None)

    class _FakeService:
        def ingest(self, request, job_id=None):  # type: ignore[no-untyped-def]
            assert request.source.local_path == str(materialized_dir)
            assert request.source.artifact_id == "artifact-1"
            assert job_id == "job-1"
            return {"status": "completed"}

    monkeypatch.setattr(queue, "RagApplicationService", _FakeService)

    result = queue.ingest_task(
        "job-1",
        {
            "source": {
                "source_type": "folder",
                "local_path": "missing-staged-dir",
                "artifact_id": "artifact-1",
            }
        },
    )

    assert result == {"status": "completed"}
    assert artifact_store.calls == [
        ("materialize", "artifact-1", None),
        ("started", "artifact-1", None),
        ("completed", "artifact-1", None),
    ]
    assert not materialized_dir.exists()


def test_reset_all_clears_uploaded_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reset should clear persisted upload artifacts with other state."""
    import coderag.core.service as service_module

    artifact_store = _RecordingArtifactStore()
    monkeypatch.setattr(service_module.RUNTIME, "ingestion_artifact_store", artifact_store)
    monkeypatch.setattr(
        service_module.SERVICE.store,
        "clear_all_data",
        lambda: {
            "deleted_documents": 0,
            "deleted_chunks": 0,
            "deleted_graph_edges": 0,
            "deleted_jobs": 0,
        },
    )
    monkeypatch.setattr(service_module.SERVICE.store, "bump_index_version", lambda: 1)
    monkeypatch.setattr(service_module.SERVICE.store, "list_documents", lambda source_id=None, tags=None: [])
    monkeypatch.setattr(service_module.SERVICE.vector_index, "clear_all", lambda: None)
    monkeypatch.setattr(service_module.SERVICE.graph_store, "clear_all_edges", lambda: 0)
    monkeypatch.setattr(service_module.SERVICE, "rebuild_indexes", lambda source_id=None: None)
    monkeypatch.setattr(service_module.SERVICE, "is_graph_enabled", lambda: False)
    monkeypatch.setattr(service_module, "_clear_local_staging_mirror", lambda data_dir: (0, []))
    monkeypatch.setattr(service_module.SETTINGS, "data_dir", tmp_path)

    response = service_module.SERVICE.reset_all()

    assert response.status == "completed"
    assert ("clear", "artifacts", None) in artifact_store.calls