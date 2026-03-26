"""Redis + RQ queue helpers for async ingestion."""

from __future__ import annotations

from typing import Any, Dict, Optional

from coderag.core.models import IngestionRequest
from coderag.core.service import RagApplicationService
from coderag.core.settings import SETTINGS


def _load_rq_modules():
    """Load rq and redis lazily to keep optional dependency behavior."""
    from redis import Redis
    from rq import Queue
    from rq.job import Job

    return Redis, Queue, Job


def ingest_task(payload: Dict[str, Any]) -> Dict[str, str]:
    """Background task entrypoint executed by RQ worker."""
    request = IngestionRequest.model_validate(payload)
    service = RagApplicationService()
    return service.ingest(request)


def enqueue_ingest_job(payload: Dict[str, Any]) -> str:
    """Enqueue ingestion task and return RQ job id."""
    Redis, Queue, _ = _load_rq_modules()
    redis_conn = Redis.from_url(SETTINGS.redis_url)
    queue = Queue("ingestion", connection=redis_conn)
    job = queue.enqueue(ingest_task, payload)
    return job.id


def get_rq_job_status(job_id: str) -> Optional[Dict[str, str]]:
    """Return async job status from Redis RQ."""
    try:
        Redis, _queue, Job = _load_rq_modules()
    except Exception:
        return None

    redis_conn = Redis.from_url(SETTINGS.redis_url)
    job = Job.fetch(job_id, connection=redis_conn)
    status = job.get_status(refresh=True)
    result = job.result if isinstance(job.result, dict) else None

    payload: Dict[str, str] = {
        "job_id": job_id,
        "status": status,
        "message": "queued",
    }
    if result and "status" in result:
        payload["message"] = result.get("status", "completed")
        payload.update(result)
    return payload
