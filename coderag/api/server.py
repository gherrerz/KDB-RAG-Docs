"""FastAPI backend exposing ingestion and query endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from coderag.core.models import IngestionRequest, QueryRequest
from coderag.core.service import SERVICE
from coderag.core.settings import SETTINGS
from coderag.jobs.queue import enqueue_ingest_job, get_rq_job_status

app = FastAPI(title="RAG Hybrid Response Validator", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Service health endpoint."""
    return {"status": "ok"}


@app.post("/sources/ingest")
def ingest_source(request: IngestionRequest) -> dict[str, Any]:
    """Trigger source ingestion and indexing."""
    return SERVICE.ingest(request)


@app.post("/sources/ingest/async")
def ingest_source_async(request: IngestionRequest) -> dict[str, str]:
    """Enqueue ingestion job in Redis RQ when enabled."""
    if not SETTINGS.use_rq:
        raise HTTPException(
            status_code=400,
            detail="Async ingestion disabled. Set USE_RQ=true.",
        )
    try:
        job_id = enqueue_ingest_job(request.model_dump())
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Ingestion job enqueued",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """Return ingestion job status."""
    job = SERVICE.get_job(job_id)
    if job is None and SETTINGS.use_rq:
        job = get_rq_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/query")
def query(request: QueryRequest) -> dict:
    """Run full RAG response pipeline."""
    response = SERVICE.query(request)
    return response.model_dump()


@app.post("/query/retrieval")
def retrieval_only(request: QueryRequest) -> dict:
    """Alias endpoint returning same payload for diagnostics compatibility."""
    response = SERVICE.query(request)
    return response.model_dump()
