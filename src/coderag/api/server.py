"""FastAPI backend exposing ingestion and query endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException

from coderag.core.models import (
    IngestionRequest,
    QueryRequest,
    ResetAllRequest,
)
from coderag.core.service import SERVICE
from coderag.core.settings import SETTINGS
from coderag.jobs.queue import (
    enqueue_ingest_job,
    enqueue_local_ingest_job,
    get_rq_job_status,
)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Release service resources when application shuts down."""
    try:
        yield
    finally:
        SERVICE.close()


app = FastAPI(
    title="RAG Hybrid Response Validator",
    version="0.1.0",
    lifespan=_lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Service health endpoint."""
    return {"status": "ok"}


@app.post("/sources/ingest")
def ingest_source(request: IngestionRequest) -> dict[str, Any]:
    """Trigger source ingestion and indexing."""
    try:
        return SERVICE.ingest(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/sources/reset")
def reset_sources(request: ResetAllRequest) -> dict[str, Any]:
    """Clear all ingestion artifacts and reset indexes."""
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Reset requires explicit confirmation.",
        )
    response = SERVICE.reset_all()
    return response.model_dump()


@app.post("/sources/ingest/async")
def ingest_source_async(request: IngestionRequest) -> dict[str, str]:
    """Enqueue ingestion job in Redis RQ when enabled."""
    try:
        if SETTINGS.use_rq:
            job_id = enqueue_ingest_job(request.model_dump())
            message = "Ingestion job enqueued"
        else:
            job_id = enqueue_local_ingest_job(request.model_dump())
            message = "Ingestion job started (local async worker)"
        return {
            "job_id": job_id,
            "status": "queued",
            "message": message,
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
    try:
        response = SERVICE.query(request)
        return response.model_dump()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/query/retrieval")
def retrieval_only(request: QueryRequest) -> dict:
    """Alias endpoint returning same payload for diagnostics compatibility."""
    try:
        response = SERVICE.query(request)
        return response.model_dump()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
