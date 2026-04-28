"""FastAPI backend exposing ingestion and query endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from coderag.api.upload_ingestion import (
    UploadIngestionAdapter,
    UploadIngestionError,
)
from coderag.core.models import (
    DeleteDocumentResponse,
    IngestionRequest,
    QueryRequest,
    TdmQueryRequest,
)
from coderag.core.service import SERVICE
from coderag.core.settings import SETTINGS
from coderag.jobs.queue import (
    enqueue_ingest_job,
    enqueue_local_ingest_job,
    get_rq_job_status,
)


UPLOAD_INGESTION = UploadIngestionAdapter(
    base_dir=Path(SETTINGS.data_dir) / "upload_staging",
    max_upload_bytes=SETTINGS.upload_max_bytes,
)


def _run_reset_all(confirm: bool) -> dict[str, Any]:
    """Execute destructive reset only after explicit caller confirmation."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Reset requires explicit confirmation.",
        )
    response = SERVICE.reset_all()
    return response.model_dump()


def _is_queue_connection_error(exc: Exception) -> bool:
    """Return true when async queue failure looks like Redis connectivity."""
    detail = str(exc).casefold()
    exc_name = exc.__class__.__name__.casefold()
    return (
        "error 10061" in detail
        or "connection refused" in detail
        or "connecting to localhost:6379" in detail
        or (
            "connection" in exc_name
            and (
                "redis" in detail
                or "localhost:6379" in detail
                or ":6379" in detail
            )
        )
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


def _make_check(required: bool, ok: bool, detail: str) -> dict[str, Any]:
    """Build one normalized dependency check payload."""
    return {
        "required": required,
        "ok": ok,
        "detail": detail,
    }


def _check_runtime_store() -> dict[str, Any]:
    """Validate local metadata store readiness used for job tracking."""
    try:
        SERVICE.store.get_index_version()
        return _make_check(True, True, "metadata store reachable")
    except Exception as exc:
        return _make_check(True, False, str(exc))


def _check_neo4j_runtime() -> dict[str, Any]:
    """Validate Neo4j connectivity when graph runtime is required."""
    required = bool(SETTINGS.use_neo4j)
    if not required:
        return _make_check(False, True, "USE_NEO4J=false")
    try:
        SERVICE.graph_store._get_driver()
        return _make_check(True, True, "neo4j reachable")
    except Exception as exc:
        return _make_check(True, False, str(exc))


def _check_redis_runtime() -> dict[str, Any]:
    """Validate Redis connectivity when async queue mode is enabled."""
    required = bool(SETTINGS.use_rq)
    if not required:
        return _make_check(False, True, "USE_RQ=false")

    try:
        from redis import Redis

        client = Redis.from_url(
            SETTINGS.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        return _make_check(True, True, "redis reachable")
    except Exception as exc:
        return _make_check(True, False, str(exc))


def _check_rq_worker_runtime() -> dict[str, Any]:
    """Validate that at least one RQ worker is registered when USE_RQ=true."""
    required = bool(SETTINGS.use_rq)
    if not required:
        return _make_check(False, True, "USE_RQ=false")

    try:
        from redis import Redis

        client = Redis.from_url(
            SETTINGS.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        workers = int(client.scard("rq:workers"))
        if workers > 0:
            return _make_check(True, True, f"workers={workers}")
        return _make_check(True, False, "workers=0")
    except Exception as exc:
        return _make_check(True, False, str(exc))


def _tdm_disabled_because_neo4j() -> bool:
    """Return whether TDM is enabled but graph runtime is disabled."""
    return bool(SETTINGS.enable_tdm and not SETTINGS.use_neo4j)


def _tdm_disabled_detail() -> dict[str, Any]:
    """Build shared diagnostics payload for TDM disabled mode."""
    return {
        "status": "disabled",
        "message": "TDM is unavailable because USE_NEO4J=false.",
        "tdm_enabled": True,
        "neo4j_enabled": False,
        "reason": "USE_NEO4J=false",
    }


@app.get(
    "/sources/documents",
    tags=["ingestion"],
    summary="List ingested documents",
    description=(
        "Return lightweight metadata for documents currently persisted in the "
        "local catalog, optionally filtered by source_id."
    ),
)
def list_documents(source_id: str | None = None) -> dict[str, Any]:
    """Expose ingested document metadata for UI selectors and diagnostics."""
    documents = SERVICE.list_documents(source_id=source_id)
    return {
        "source_id": source_id,
        "count": len(documents),
        "documents": [item.model_dump(mode="json") for item in documents],
    }


@app.delete(
    "/sources/documents/{document_id}",
    tags=["ingestion"],
    summary="Delete one ingested document",
    description=(
        "Delete a persisted document by document_id, including SQLite "
        "metadata/chunks, Chroma vectors, managed staging mirror copy when "
        "present, and graph resync for the affected source."
    ),
    responses={
        404: {"description": "Document not found for the provided id."}
    },
)
def delete_document(document_id: str) -> DeleteDocumentResponse:
    """Expose one-document deletion without changing ingest dedup behavior."""
    try:
        response = SERVICE.delete_document(document_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {document_id}",
        ) from exc
    return response


@app.get(
    "/sources/ingest/readiness",
    tags=["ingestion"],
    summary="Get ingestion readiness diagnostics",
    description=(
        "Return operational readiness checks used by UI before running async "
        "ingestion."
    ),
)
def ingest_readiness() -> dict[str, Any]:
    """Expose dependency checks for async ingestion mode selection."""
    checks = {
        "runtime_store": _check_runtime_store(),
        "neo4j": _check_neo4j_runtime(),
        "redis": _check_redis_runtime(),
        "rq_worker": _check_rq_worker_runtime(),
    }
    required_checks_ok = [
        item["ok"]
        for item in checks.values()
        if bool(item.get("required"))
    ]
    ready = all(required_checks_ok) if required_checks_ok else True
    recommendation = "async" if ready else "sync"
    return {
        "ready": ready,
        "recommendation": recommendation,
        "use_rq": SETTINGS.use_rq,
        "use_neo4j": SETTINGS.use_neo4j,
        "checks": checks,
    }


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
    "/sources/ingest/file",
    tags=["ingestion"],
    summary="Run synchronous ingestion from uploaded file",
    description=(
        "Upload one supported document via multipart/form-data, stage it "
        "server-side, and execute the same synchronous ingestion pipeline."
    ),
    responses={
        422: {
            "description": (
                "Invalid multipart payload, unsupported extension, "
                "or malformed filters JSON."
            )
        },
        503: {
            "description": (
                "Strict runtime unavailable (for example Chroma disabled, "
                "missing embedding provider credentials, or provider error)."
            )
        },
    },
)
def ingest_source_file(
    file: UploadFile = File(...),
    source_type: str = Form("folder"),
    filters: str | None = Form(None),
) -> dict[str, Any]:
    """Trigger ingestion pipeline from one uploaded file."""
    staged_dir: Path | None = None
    try:
        staged_dir = UPLOAD_INGESTION.stage_upload(file)
        parsed_filters = UPLOAD_INGESTION.parse_filters(filters)
        request = UPLOAD_INGESTION.build_request(
            staged_dir=staged_dir,
            source_type=source_type,
            filters=parsed_filters,
        )
        return SERVICE.ingest(request)
    except UploadIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        if staged_dir is not None:
            UPLOAD_INGESTION.cleanup(staged_dir)


@app.post(
    "/sources/ingest/file/async",
    tags=["ingestion"],
    summary="Enqueue asynchronous ingestion from uploaded file",
    description=(
        "Upload one supported document via multipart/form-data and enqueue "
        "asynchronous ingestion. When USE_RQ=true, enable "
        "UPLOAD_STAGING_SHARED=true only if API and worker share the same "
        "staging volume path."
    ),
    responses={
        409: {
            "description": (
                "USE_RQ requires UPLOAD_STAGING_SHARED=true for upload async "
                "because workers must read the staged file path."
            )
        },
        422: {
            "description": (
                "Invalid multipart payload, unsupported extension, "
                "or malformed filters JSON."
            )
        },
        500: {
            "description": "Queue or local async worker startup error."
        },
    },
)
def ingest_source_file_async(
    file: UploadFile = File(...),
    source_type: str = Form("folder"),
    filters: str | None = Form(None),
) -> dict[str, str]:
    """Enqueue async ingestion pipeline from one uploaded file."""
    staged_dir: Path | None = None
    try:
        staged_dir = UPLOAD_INGESTION.stage_upload(file)
        parsed_filters = UPLOAD_INGESTION.parse_filters(filters)
        request = UPLOAD_INGESTION.build_request(
            staged_dir=staged_dir,
            source_type=source_type,
            filters=parsed_filters,
        )
        payload = request.model_dump()
        cleanup_staging_dir = str(staged_dir)

        if SETTINGS.use_rq and not SETTINGS.upload_staging_shared:
            UPLOAD_INGESTION.cleanup(staged_dir)
            staged_dir = None
            raise HTTPException(
                status_code=409,
                detail=(
                    "Upload async with USE_RQ=true requires "
                    "UPLOAD_STAGING_SHARED=true and a shared volume between "
                    "API and worker pods."
                ),
            )

        if SETTINGS.use_rq:
            try:
                job_id = enqueue_ingest_job(
                    payload,
                    cleanup_staging_dir=cleanup_staging_dir,
                )
                message = "Upload ingestion job enqueued"
            except Exception as exc:
                if not _is_queue_connection_error(exc):
                    UPLOAD_INGESTION.cleanup(staged_dir)
                    staged_dir = None
                    raise
                job_id = enqueue_local_ingest_job(
                    payload,
                    cleanup_staging_dir=cleanup_staging_dir,
                )
                message = (
                    "RQ unavailable; upload ingestion job started "
                    "(local async worker fallback)"
                )
        else:
            job_id = enqueue_local_ingest_job(
                payload,
                cleanup_staging_dir=cleanup_staging_dir,
            )
            message = "Upload ingestion job started (local async worker)"

        staged_dir = None
        return {
            "job_id": job_id,
            "status": "queued",
            "message": message,
        }
    except UploadIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if staged_dir is not None:
            UPLOAD_INGESTION.cleanup(staged_dir)


@app.delete(
    "/sources/reset",
    tags=["ingestion"],
    summary="Reset all ingestion artifacts",
    description=(
        "Clear persisted ingestion state, TDM metadata, staging mirror, "
        "managed graph relationships, and reset runtime indexes. Requires "
        "explicit confirmation through the confirm query parameter."
    ),
    responses={
        400: {"description": "Missing confirmation (confirm=false)."}
    },
)
def reset_sources(confirm: bool = False) -> dict[str, Any]:
    """Clear persisted ingestion artifacts and reset runtime indexes."""
    return _run_reset_all(confirm=confirm)


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
            try:
                job_id = enqueue_ingest_job(request.model_dump())
                message = "Ingestion job enqueued"
            except Exception as exc:
                if not _is_queue_connection_error(exc):
                    raise
                job_id = enqueue_local_ingest_job(request.model_dump())
                message = (
                    "RQ unavailable; ingestion job started "
                    "(local async worker fallback)"
                )
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

    if SETTINGS.use_rq:
        rq_job: dict[str, Any] | None = None
        try:
            rq_job = get_rq_job_status(job_id)
        except Exception as exc:
            # If Redis is temporarily unavailable, keep local status polling
            # operational for local async fallback jobs.
            if not _is_queue_connection_error(exc):
                raise
        if rq_job is not None:
            if job is None:
                return rq_job

            merged = dict(job)
            merged.update(rq_job)

            # Keep local timeline/progress breadcrumbs when RQ payload lacks them.
            if "steps" not in merged and "steps" in job:
                merged["steps"] = job["steps"]
            if "progress_pct" not in merged and "progress_pct" in job:
                merged["progress_pct"] = job["progress_pct"]
            return merged

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
    if _tdm_disabled_because_neo4j():
        payload = _tdm_disabled_detail()
        return {
            "status": payload["status"],
            "message": payload["message"],
            "source_id": None,
            "diagnostics": payload,
        }
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
    if _tdm_disabled_because_neo4j():
        payload = _tdm_disabled_detail()
        return {
            "answer": payload["message"],
            "findings": [],
            "diagnostics": payload,
        }
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
    if _tdm_disabled_because_neo4j():
        payload = _tdm_disabled_detail()
        return {
            "service_name": service_name,
            "source_id": source_id,
            "mappings": [],
            "count": 0,
            "diagnostics": payload,
        }
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
    if _tdm_disabled_because_neo4j():
        payload = _tdm_disabled_detail()
        return {
            "table_name": table_name,
            "source_id": source_id,
            "tables": [],
            "columns": [],
            "count": 0,
            "diagnostics": payload,
        }
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
    if _tdm_disabled_because_neo4j():
        payload = _tdm_disabled_detail()
        return {
            "source_id": request.source_id,
            "service_name": request.service_name,
            "templates": [],
            "count": 0,
            "diagnostics": payload,
        }
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
    if _tdm_disabled_because_neo4j():
        payload = _tdm_disabled_detail()
        return {
            "source_id": source_id,
            "table_name": table_name,
            "profile_id": None,
            "plan": {},
            "diagnostics": payload,
        }
    try:
        return SERVICE.get_tdm_synthetic_profile(
            table_name=table_name,
            source_id=source_id,
            target_rows=target_rows,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
