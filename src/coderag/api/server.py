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
    description=(
        "REST API for ingestion and hybrid retrieval (BM25 + vector + graph) "
        "with evidence-aware responses."
    ),
    openapi_tags=[
        {
            "name": "health",
            "description": "Service liveness endpoint.",
        },
        {
            "name": "ingestion",
            "description": (
                "Source ingestion operations (sync, async, status, and reset)."
            ),
        },
        {
            "name": "query",
            "description": "Hybrid retrieval and grounded answer endpoints.",
        },
    ],
    lifespan=_lifespan,
)


@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Validate that the API process is up and responding.",
)
def health() -> dict[str, str]:
    """Service health endpoint."""
    return {"status": "ok"}


@app.post(
    "/sources/ingest",
    tags=["ingestion"],
    summary="Run synchronous ingestion",
    description=(
        "Execute full ingestion and indexing in-process and return terminal "
        "status with metrics and step timeline."
    ),
    responses={
        503: {
            "description": (
                "Strict runtime unavailable (for example Chroma disabled, "
                "missing embedding provider credentials, or provider error)."
            )
        }
    },
)
def ingest_source(request: IngestionRequest) -> dict[str, Any]:
    """Trigger source ingestion and indexing."""
    try:
        return SERVICE.ingest(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/sources/reset",
    tags=["ingestion"],
    summary="Reset all ingestion artifacts",
    description=(
        "Clear documents/chunks/graph/job history and reset runtime indexes. "
        "Requires explicit confirmation in request body."
    ),
    responses={
        400: {"description": "Missing confirmation (confirm=false)."}
    },
)
def reset_sources(request: ResetAllRequest) -> dict[str, Any]:
    """Clear all ingestion artifacts and reset indexes."""
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Reset requires explicit confirmation.",
        )
    response = SERVICE.reset_all()
    return response.model_dump()


@app.post(
    "/sources/ingest/async",
    tags=["ingestion"],
    summary="Enqueue asynchronous ingestion",
    description=(
        "Create ingestion job and return job id for polling. Uses RQ when "
        "USE_RQ=true, otherwise starts local async worker."
    ),
    responses={
        500: {"description": "Queue or local async worker startup error."}
    },
)
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


@app.get(
    "/jobs/{job_id}",
    tags=["ingestion"],
    summary="Get ingestion job status",
    description=(
        "Return job status, message, progress, timestamps, and persisted "
        "timeline events when available."
    ),
    responses={
        404: {"description": "Job not found."}
    },
)
def get_job(job_id: str) -> dict[str, Any]:
    """Return ingestion job status."""
    job = SERVICE.get_job(job_id)
    if job is None and SETTINGS.use_rq:
        job = get_rq_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post(
    "/query",
    tags=["query"],
    summary="Run hybrid query",
    description=(
        "Execute BM25 + vector retrieval, graph expansion, and optional LLM "
        "answer generation with evidence and diagnostics."
    ),
    responses={
        503: {
            "description": (
                "Strict runtime error during query (for example provider "
                "failure, embedding failure, or index refresh issue)."
            )
        }
    },
)
def query(request: QueryRequest) -> dict:
    """Run full RAG response pipeline."""
    try:
        response = SERVICE.query(request)
        return response.model_dump()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/query/retrieval",
    tags=["query"],
    summary="Run query (retrieval alias)",
    description=(
        "Compatibility alias of /query that returns the same payload shape."
    ),
    responses={
        503: {
            "description": (
                "Strict runtime error during query (for example provider "
                "failure, embedding failure, or index refresh issue)."
            )
        }
    },
)
def retrieval_only(request: QueryRequest) -> dict:
    """Alias endpoint returning same payload for diagnostics compatibility."""
    try:
        response = SERVICE.query(request)
        return response.model_dump()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
