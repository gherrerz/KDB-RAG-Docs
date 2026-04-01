"""FastAPI backend exposing ingestion and query endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException

from coderag.core.models import (
    IngestionRequest,
    QueryRequest,
    ResetAllRequest,
    TdmQueryRequest,
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
        {
            "name": "tdm",
            "description": (
                "Additive TDM catalog and virtualization endpoints."
            ),
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


@app.get(
    "/readiness",
    tags=["health"],
    summary="Readiness check",
    description=(
        "Validate that the API process is ready to serve traffic and can "
        "access its critical runtime state."
    ),
    responses={
        503: {"description": "Service not ready to accept traffic."}
    },
)
def readiness() -> dict[str, str]:
    """Service readiness endpoint for orchestrators."""
    try:
        SERVICE.store.get_index_version()
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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


@app.post(
    "/tdm/ingest",
    tags=["tdm"],
    summary="Run TDM ingestion",
    description=(
        "Ingest SQL/OpenAPI/data-dictionary assets into additive TDM "
        "catalog tables."
    ),
    responses={
        404: {"description": "TDM capability disabled."},
        503: {"description": "TDM runtime validation error."},
    },
)
def ingest_tdm(request: IngestionRequest) -> dict[str, Any]:
    """Trigger additive TDM catalog ingestion."""
    if not SETTINGS.enable_tdm:
        raise HTTPException(
            status_code=404,
            detail="TDM endpoints are disabled.",
        )
    try:
        return SERVICE.ingest_tdm_assets(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/tdm/query",
    tags=["tdm"],
    summary="Run TDM catalog query",
    description=(
        "Query TDM catalog entities and typed graph paths for agent workflows."
    ),
    responses={
        404: {"description": "TDM capability disabled."},
        503: {"description": "TDM query error."},
    },
)
def query_tdm(request: TdmQueryRequest) -> dict[str, Any]:
    """Run additive TDM query mode."""
    if not SETTINGS.enable_tdm:
        raise HTTPException(
            status_code=404,
            detail="TDM endpoints are disabled.",
        )
    try:
        response = SERVICE.query_tdm(request)
        return response.model_dump()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/tdm/catalog/services/{service_name}",
    tags=["tdm"],
    summary="Get TDM service catalog",
    description="Return service-to-table mappings from TDM catalog.",
    responses={
        404: {"description": "TDM capability disabled."},
    },
)
def tdm_service_catalog(
    service_name: str,
    source_id: str | None = None,
) -> dict[str, Any]:
    """Return additive TDM catalog view by service."""
    if not SETTINGS.enable_tdm:
        raise HTTPException(
            status_code=404,
            detail="TDM endpoints are disabled.",
        )
    return SERVICE.get_tdm_service_catalog(
        service_name=service_name,
        source_id=source_id,
    )


@app.get(
    "/tdm/catalog/tables/{table_name}",
    tags=["tdm"],
    summary="Get TDM table catalog",
    description="Return table and column metadata from TDM catalog.",
    responses={
        404: {"description": "TDM capability disabled."},
    },
)
def tdm_table_catalog(
    table_name: str,
    source_id: str | None = None,
) -> dict[str, Any]:
    """Return additive TDM catalog view by table."""
    if not SETTINGS.enable_tdm:
        raise HTTPException(
            status_code=404,
            detail="TDM endpoints are disabled.",
        )
    return SERVICE.get_tdm_table_catalog(
        table_name=table_name,
        source_id=source_id,
    )


@app.post(
    "/tdm/virtualization/preview",
    tags=["tdm"],
    summary="Preview virtualization templates",
    description=(
        "Build lightweight mock/virtualization templates from TDM mappings."
    ),
    responses={
        404: {"description": "TDM capability disabled."},
        503: {"description": "TDM preview error."},
    },
)
def preview_tdm_virtualization(request: TdmQueryRequest) -> dict[str, Any]:
    """Return additive TDM virtualization previews."""
    if not SETTINGS.enable_tdm:
        raise HTTPException(
            status_code=404,
            detail="TDM endpoints are disabled.",
        )
    try:
        return SERVICE.preview_tdm_virtualization(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/tdm/synthetic/profile/{table_name}",
    tags=["tdm"],
    summary="Build synthetic profile plan",
    description=(
        "Build and persist a synthetic data profile plan from TDM table "
        "metadata."
    ),
    responses={
        404: {"description": "TDM capability disabled."},
        503: {"description": "Synthetic planning error."},
    },
)
def tdm_synthetic_profile(
    table_name: str,
    source_id: str | None = None,
    target_rows: int = 1000,
) -> dict[str, Any]:
    """Return additive synthetic profile plan for one table."""
    if not SETTINGS.enable_tdm:
        raise HTTPException(
            status_code=404,
            detail="TDM endpoints are disabled.",
        )
    try:
        return SERVICE.get_tdm_synthetic_profile(
            table_name=table_name,
            source_id=source_id,
            target_rows=target_rows,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
