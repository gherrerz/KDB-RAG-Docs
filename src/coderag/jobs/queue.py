"""Redis + RQ queue helpers for async ingestion."""

from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, Optional

from coderag.core.models import IngestionRequest
from coderag.core.service import RagApplicationService
from coderag.core.runtime import RUNTIME
from coderag.core.settings import SETTINGS


_LOCAL_THREADS: dict[str, threading.Thread] = {}


def _load_rq_modules():
    """Load rq and redis lazily to keep optional dependency behavior."""
    from redis import Redis
    from rq import Queue
    from rq.job import Job

    return Redis, Queue, Job


def ingest_task(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Background task entrypoint executed by RQ worker."""
    try:
        request = IngestionRequest.model_validate(payload)
        service = RagApplicationService()
        return service.ingest(request, job_id=job_id)
    except Exception as exc:  # pragma: no cover - worker boundary
        RUNTIME.store.touch_job(
            job_id,
            "failed",
            f"FAILED | rq worker: {exc}",
        )
        raise


def _run_local_ingest_job(job_id: str, payload: Dict[str, Any]) -> None:
    """Execute local background ingestion and persist terminal job state."""
    request = IngestionRequest.model_validate(payload)
    from coderag.core.service import SERVICE

    try:
        SERVICE.ingest(request, job_id=job_id)
    except Exception as exc:  # pragma: no cover - defensive worker boundary
        RUNTIME.store.touch_job(
            job_id,
            "failed",
            f"FAILED | local worker: {exc}",
        )
    finally:
        _LOCAL_THREADS.pop(job_id, None)


def enqueue_local_ingest_job(payload: Dict[str, Any]) -> str:
    """Enqueue ingestion in a local background thread and return job id."""
    job_id = uuid.uuid4().hex[:12]
    RUNTIME.store.touch_job(job_id, "queued", "Ingestion job queued")

    thread = threading.Thread(
        target=_run_local_ingest_job,
        args=(job_id, payload),
        daemon=True,
    )
    _LOCAL_THREADS[job_id] = thread
    thread.start()
    return job_id


def enqueue_ingest_job(payload: Dict[str, Any]) -> str:
    """Enqueue ingestion task and return RQ job id."""
    Redis, Queue, _ = _load_rq_modules()
    redis_conn = Redis.from_url(SETTINGS.redis_url)
    queue = Queue("ingestion", connection=redis_conn)
    job_id = uuid.uuid4().hex[:12]
    job = queue.enqueue(
        ingest_task,
        job_id,
        payload,
        job_id=job_id,
        job_timeout=SETTINGS.rq_ingest_job_timeout_sec,
    )
    RUNTIME.store.touch_job(job_id, "queued", "Ingestion job enqueued")
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
