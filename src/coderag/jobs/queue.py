"""Redis + RQ queue helpers for async ingestion."""

from __future__ import annotations

import copy
import shutil
import threading
import uuid
from typing import Any, Dict, Optional

from coderag.core.models import IngestionRequest
from coderag.core.service import RagApplicationService
from coderag.core.runtime import RUNTIME
from coderag.core.settings import SETTINGS


_LOCAL_THREADS: dict[str, threading.Thread] = {}


def _artifact_id_from_payload(payload: Dict[str, Any]) -> str | None:
    """Extract optional artifact id from a serialized ingestion payload."""
    source = payload.get("source")
    if not isinstance(source, dict):
        return None
    artifact_id = source.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        return None
    return artifact_id.strip()


def _cleanup_staging_dir(staging_dir: Optional[str]) -> None:
    """Best-effort cleanup for staged upload directories."""
    if not staging_dir:
        return
    shutil.rmtree(staging_dir, ignore_errors=True)


def _prepare_worker_payload(
    payload: Dict[str, Any],
) -> tuple[Dict[str, Any], str | None]:
    """Rehydrate payload source paths from persisted upload artifacts."""
    artifact_id = _artifact_id_from_payload(payload)
    if not artifact_id:
        return payload, None

    materialized_dir = RUNTIME.ingestion_artifact_store.materialize_uploaded_batch(
        artifact_id
    )
    if not materialized_dir:
        return payload, None

    prepared_payload = copy.deepcopy(payload)
    source = prepared_payload.get("source")
    if not isinstance(source, dict):
        prepared_payload["source"] = {"local_path": materialized_dir}
    else:
        source["local_path"] = materialized_dir
    return prepared_payload, materialized_dir


def _load_rq_modules():
    """Load rq and redis lazily to keep optional dependency behavior."""
    from redis import Redis
    from rq import Queue
    from rq.job import Job

    return Redis, Queue, Job


def ingest_task(
    job_id: str,
    payload: Dict[str, Any],
    cleanup_staging_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Background task entrypoint executed by RQ worker."""
    artifact_id = _artifact_id_from_payload(payload)
    materialized_dir: str | None = None
    try:
        prepared_payload, materialized_dir = _prepare_worker_payload(payload)
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_started(artifact_id)
        request = IngestionRequest.model_validate(prepared_payload)
        service = RagApplicationService()
        result = service.ingest(request, job_id=job_id)
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_completed(
                artifact_id
            )
        return result
    except Exception as exc:  # pragma: no cover - worker boundary
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_failed(
                artifact_id,
                str(exc),
            )
        RUNTIME.store.touch_job(
            job_id,
            "failed",
            f"FAILED | rq worker: {exc}",
        )
        raise
    finally:
        _cleanup_staging_dir(materialized_dir)
        _cleanup_staging_dir(cleanup_staging_dir)


def _run_local_ingest_job(
    job_id: str,
    payload: Dict[str, Any],
    cleanup_staging_dir: Optional[str] = None,
) -> None:
    """Execute local background ingestion and persist terminal job state."""
    artifact_id = _artifact_id_from_payload(payload)
    materialized_dir: str | None = None
    from coderag.core.service import SERVICE

    try:
        prepared_payload, materialized_dir = _prepare_worker_payload(payload)
        request = IngestionRequest.model_validate(prepared_payload)
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_started(artifact_id)
        SERVICE.ingest(request, job_id=job_id)
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_completed(
                artifact_id
            )
    except Exception as exc:  # pragma: no cover - defensive worker boundary
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_failed(
                artifact_id,
                str(exc),
            )
        RUNTIME.store.touch_job(
            job_id,
            "failed",
            f"FAILED | local worker: {exc}",
        )
    finally:
        _cleanup_staging_dir(materialized_dir)
        _cleanup_staging_dir(cleanup_staging_dir)
        _LOCAL_THREADS.pop(job_id, None)


def enqueue_local_ingest_job(
    payload: Dict[str, Any],
    cleanup_staging_dir: Optional[str] = None,
) -> str:
    """Enqueue ingestion in a local background thread and return job id."""
    job_id = uuid.uuid4().hex[:12]
    artifact_id = _artifact_id_from_payload(payload)
    RUNTIME.store.touch_job(job_id, "queued", "Ingestion job queued")
    if artifact_id:
        RUNTIME.ingestion_artifact_store.attach_job(artifact_id, job_id)

    thread = threading.Thread(
        target=_run_local_ingest_job,
        args=(job_id, payload, cleanup_staging_dir),
        daemon=True,
    )
    _LOCAL_THREADS[job_id] = thread
    thread.start()
    return job_id


def enqueue_ingest_job(
    payload: Dict[str, Any],
    cleanup_staging_dir: Optional[str] = None,
) -> str:
    """Enqueue ingestion task and return RQ job id."""
    Redis, Queue, _ = _load_rq_modules()
    redis_conn = Redis.from_url(SETTINGS.redis_url)
    queue = Queue("ingestion", connection=redis_conn)
    job_id = uuid.uuid4().hex[:12]
    job = queue.enqueue(
        ingest_task,
        job_id,
        payload,
        cleanup_staging_dir,
        job_id=job_id,
        job_timeout=SETTINGS.rq_ingest_job_timeout_sec,
    )
    artifact_id = _artifact_id_from_payload(payload)
    RUNTIME.store.touch_job(job_id, "queued", "Ingestion job enqueued")
    if artifact_id:
        RUNTIME.ingestion_artifact_store.attach_job(artifact_id, job_id)
    return job.id


def get_rq_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Return async job status from Redis RQ."""
    try:
        Redis, _queue, Job = _load_rq_modules()
    except Exception:
        return None

    redis_conn = Redis.from_url(SETTINGS.redis_url)
    job = Job.fetch(job_id, connection=redis_conn)
    status = job.get_status(refresh=True)
    result = job.result if isinstance(job.result, dict) else None

    payload: Dict[str, Any] = {
        "job_id": job_id,
        "status": status,
        "message": "queued",
    }
    if result and "status" in result:
        payload["message"] = result.get("status", "completed")
        payload.update(result)
    return payload
