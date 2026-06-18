"""FastAPI backend exposing ingestion and query endpoints."""

from __future__ import annotations

import base64
import binascii
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.openapi.utils import get_openapi

from coderag.api.upload_ingestion import (
    StagedUploadFile,
    UploadIngestionAdapter,
    UploadIngestionError,
)
from coderag.core.models import (
    AdminResetRequest,
    DeleteDocumentResponse,
    DocumentContentResponse,
    FilesIngestionJsonRequest,
    IngestionRequest,
    ListDocumentTagsResponse,
    QueryRequest,
    ReplaceDocumentTagsRequest,
    ReplaceDocumentTagsResponse,
    TdmQueryRequest,
)
from coderag.core.runtime import RUNTIME
from coderag.core.service import SERVICE
from coderag.core.settings import SETTINGS
from coderag.ingestion.index_chroma import (
    build_remote_chroma_error_message,
    detect_remote_chroma_error_signal,
    describe_remote_chroma_auth_mode,
    describe_remote_chroma_target,
    expected_managed_chroma_hnsw_space,
    get_collection_hnsw_space,
)
from coderag.jobs.queue import (
    enqueue_ingest_job,
    enqueue_local_ingest_job,
    get_rq_job_status,
)


UPLOAD_INGESTION = UploadIngestionAdapter(
    base_dir=Path(SETTINGS.data_dir) / "upload_staging",
    max_upload_bytes=SETTINGS.upload_max_bytes,
)


def _artifact_files_payload(
    staged_files: list[StagedUploadFile],
) -> list[dict[str, Any]]:
    """Convert one staged batch to the payload shape expected by the store."""
    return [
        {
            "ordinal": item.ordinal,
            "original_filename": item.original_filename,
            "staged_filename": item.staged_filename,
            "media_type": item.media_type,
            "size_bytes": item.size_bytes,
            "content_hash": item.content_hash,
            "payload": item.payload,
        }
        for item in staged_files
    ]


def _run_reset_all(confirm: bool) -> dict[str, Any]:
    """Execute destructive reset only after explicit caller confirmation."""
    response = SERVICE.reset_all()
    return response.model_dump()


def _ensure_admin_reset_access(admin_token: str | None) -> None:
    """Protect the global reset endpoint with feature flag and token."""
    if not SETTINGS.admin_reset_enabled:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Administrative reset endpoint is disabled.",
                "code": "admin_reset_disabled",
            },
        )

    expected_token = (SETTINGS.admin_reset_token or "").strip()
    if (admin_token or "").strip() != expected_token:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Invalid administrative token for global reset.",
                "code": "invalid_admin_reset_token",
            },
        )
    return None


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


def _format_exception_detail(
    exc: Exception,
    operation: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build structured exception payload for API diagnostics."""
    payload: dict[str, Any] = {
        "operation": operation,
        "error_type": exc.__class__.__name__,
        "error": str(exc),
    }
    if context:
        payload["context"] = context
    return payload


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
        "REST API for ingestion and hybrid retrieval (lexical + vector + graph) "
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


def _mark_admin_reset_header_required(schema: dict[str, object]) -> None:
    """Align published OpenAPI with the effective reset contract."""
    path_item = schema.get("paths", {}).get("/admin/reset", {}).get("post", {})
    parameters = path_item.get("parameters", [])
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        if (
            parameter.get("in") == "header"
            and parameter.get("name") == "X-Admin-Reset-Token"
        ):
            parameter["required"] = True
            return


def _restore_binary_upload_format(node: object) -> None:
    """Re-add ``format: binary`` to binary string schemas for Swagger UI.

    FastAPI emits OpenAPI 3.1, where ``UploadFile`` binaries are described as
    ``type: string`` plus ``contentMediaType``. The bundled Swagger UI only
    renders a file picker when ``format: binary`` is present, so file upload
    fields otherwise degrade to plain text boxes. This walks the schema tree
    and restores ``format: binary`` wherever a binary string is declared,
    keeping ``contentMediaType`` intact.
    """
    if isinstance(node, dict):
        if (
            node.get("type") == "string"
            and node.get("contentMediaType")
            and "format" not in node
        ):
            node["format"] = "binary"
        for value in node.values():
            _restore_binary_upload_format(value)
    elif isinstance(node, list):
        for item in node:
            _restore_binary_upload_format(item)


def custom_openapi() -> dict[str, object]:
    """Publish OpenAPI adjusted to the service's effective HTTP contract."""
    if app.openapi_schema is not None:
        return cast(dict[str, object], app.openapi_schema)

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    _mark_admin_reset_header_required(schema)
    _restore_binary_upload_format(schema)
    app.openapi_schema = schema
    return cast(dict[str, object], app.openapi_schema)


app.openapi = custom_openapi


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
    checks = {
        "runtime_store": _check_runtime_store(),
        "lexical": _check_lexical_runtime(),
        "chroma": _check_chroma_runtime(),
    }
    failures = [
        f"{name}: {item.get('detail', '')}"
        for name, item in checks.items()
        if bool(item.get("required")) and not bool(item.get("ok"))
    ]
    if failures:
        raise HTTPException(status_code=503, detail="; ".join(failures))
    return {"status": "ready"}


def _make_check(
    required: bool,
    ok: bool,
    detail: str,
    **extra: Any,
) -> dict[str, Any]:
    """Build one normalized dependency check payload."""
    payload = {
        "required": required,
        "ok": ok,
        "detail": detail,
    }
    payload.update(extra)
    return payload


def _check_runtime_store() -> dict[str, Any]:
    """Validate local metadata store readiness used for job tracking."""
    try:
        SERVICE.store.get_index_version()
        return _make_check(True, True, "metadata store reachable")
    except Exception as exc:
        return _make_check(True, False, str(exc))


def _describe_postgres_target() -> str:
    """Describe the configured Postgres target for runtime diagnostics."""
    host = str(getattr(SETTINGS, "postgres_host", "") or "").strip()
    database = str(getattr(SETTINGS, "postgres_db", "") or "").strip()
    port = int(getattr(SETTINGS, "postgres_port", 5432) or 5432)
    if not host or not database:
        return "unconfigured"
    return f"{host}:{port}/{database}"


def _check_lexical_runtime() -> dict[str, Any]:
    """Validate the Postgres lexical backend used by the query path."""
    lexical_index = SERVICE.lexical_index
    backend = str(getattr(lexical_index, "backend_label", "unknown") or "unknown")
    fts_language = str(
        getattr(SETTINGS, "lexical_fts_language", "english") or "english"
    )
    target = _describe_postgres_target()

    if backend != "lexical":
        return _make_check(
            True,
            False,
            "Postgres lexical backend is unavailable; configure POSTGRES_*.",
            signal="lexical_backend_unavailable",
            backend=backend,
            fts_language=fts_language,
            target=target,
        )

    try:
        probe = getattr(lexical_index, "ping", None)
        if callable(probe):
            probe()
        snapshot_fn = getattr(lexical_index, "health_snapshot", None)
        snapshot: dict[str, Any] = {}
        if callable(snapshot_fn):
            raw_snapshot = snapshot_fn()
            if isinstance(raw_snapshot, dict):
                snapshot = dict(raw_snapshot)

        indexed = bool(snapshot.get("indexed", False))
        corpus_rows = int(snapshot.get("corpus_rows", 0) or 0)
        document_count = int(snapshot.get("document_count", 0) or 0)
        source_count = int(snapshot.get("source_count", 0) or 0)
        detail = (
            "lexical backend reachable "
            f"backend={backend} "
            f"fts_language={fts_language} "
            f"target={target} "
            f"indexed={str(indexed).lower()} "
            f"corpus_rows={corpus_rows} "
            f"documents={document_count} "
            f"sources={source_count}"
        )
        return _make_check(
            True,
            True,
            detail,
            signal="lexical_ready",
            backend=backend,
            fts_language=fts_language,
            target=target,
            indexed=indexed,
            corpus_rows=corpus_rows,
            document_count=document_count,
            source_count=source_count,
        )
    except Exception as exc:
        return _make_check(
            True,
            False,
            f"lexical backend probe failed: {exc}",
            signal="lexical_unreachable",
            backend=backend,
            fts_language=fts_language,
            target=target,
        )


def _collection_names_from_runtime(client: Any) -> list[str]:
    """Normalize collection names across Chroma client versions."""
    list_collections = getattr(client, "list_collections", None)
    if not callable(list_collections):
        return [SETTINGS.chroma_collection]

    raw_collections = list_collections()
    names: list[str] = []
    for item in raw_collections:
        name = getattr(item, "name", item)
        normalized = str(name).strip()
        if normalized:
            names.append(normalized)
    return sorted(names)


def _validate_runtime_collection_space(collection: Any) -> str | None:
    """Ensure the managed collection uses the configured HNSW space."""
    detected_space = get_collection_hnsw_space(collection)
    expected_space = expected_managed_chroma_hnsw_space()
    if detected_space and detected_space != expected_space:
        collection_name = str(
            getattr(collection, "name", SETTINGS.chroma_collection)
        )
        raise RuntimeError(
            "Chroma HNSW space mismatch "
            f"configured={expected_space} "
            f"detected={detected_space} "
            f"collection={collection_name}"
        )
    return detected_space


def _check_chroma_runtime() -> dict[str, Any]:
    """Validate Chroma connectivity for the supported remote runtime mode."""
    if not SETTINGS.use_chroma:
        return _make_check(
            True,
            False,
            "USE_CHROMA=false",
            signal="chroma_disabled",
            mode=SETTINGS.chroma_mode,
            collection=SETTINGS.chroma_collection,
        )

    if SETTINGS.chroma_mode != "remote":
        return _make_check(
            True,
            False,
            "embedded chroma mode is no longer supported in the Docs runtime; "
            "configure CHROMA_MODE=remote",
            signal="chroma_mode_unsupported",
            mode=SETTINGS.chroma_mode,
            collection=SETTINGS.chroma_collection,
            expected_hnsw_space=expected_managed_chroma_hnsw_space(),
        )

    collection_name = SETTINGS.chroma_collection
    try:
        vector_index = SERVICE.vector_index
        client = vector_index._ensure_client()
        heartbeat = getattr(client, "heartbeat", None)
        if callable(heartbeat):
            heartbeat()
        collection_names = _collection_names_from_runtime(client)
        collection = vector_index._ensure_collection()
        collection_name = str(
            getattr(collection, "name", SETTINGS.chroma_collection)
        )
        detected_space = _validate_runtime_collection_space(collection)
        detail = (
            "remote chroma reachable "
            f"target={describe_remote_chroma_target()} "
            f"auth={describe_remote_chroma_auth_mode()} "
            f"collections={len(collection_names)} "
            f"collection={collection_name}"
        )
        if detected_space:
            detail = f"{detail} hnsw={detected_space}"
        return _make_check(
            True,
            True,
            detail,
            signal="chroma_ready",
            mode="remote",
            target=describe_remote_chroma_target(),
            auth_mode=describe_remote_chroma_auth_mode(),
            collections_count=len(collection_names),
            collection=collection_name,
            heartbeat_ok=True,
            hnsw_space=detected_space,
            expected_hnsw_space=expected_managed_chroma_hnsw_space(),
        )
    except Exception as exc:
        signal = detect_remote_chroma_error_signal(exc)
        return _make_check(
            True,
            False,
            build_remote_chroma_error_message(
                operation="readiness_check",
                exc=exc,
                collection_name=collection_name,
            ),
            signal=signal,
            mode="remote",
            target=describe_remote_chroma_target(),
            auth_mode=describe_remote_chroma_auth_mode(),
            collection=collection_name,
            expected_hnsw_space=expected_managed_chroma_hnsw_space(),
        )


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


def _parse_catalog_tags(tags_raw: str | None) -> list[str]:
    """Parse optional catalog tags query parameter using CSV semantics."""
    if not tags_raw or not tags_raw.strip():
        return []

    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in tags_raw.split(","):
        tag = raw_tag.strip()
        if not tag:
            continue
        tag_key = tag.casefold()
        if tag_key in seen:
            continue
        seen.add(tag_key)
        tags.append(tag)
    return tags


def list_documents(
    source_id: str | None = None,
    tags: str | None = None,
) -> dict[str, Any]:
    """Expose ingested document metadata for UI selectors and diagnostics."""
    parsed_tags = _parse_catalog_tags(tags)
    documents = SERVICE.list_documents(source_id=source_id, tags=parsed_tags)
    return {
        "source_id": source_id,
        "tags": parsed_tags,
        "count": len(documents),
        "documents": [item.model_dump(mode="json") for item in documents],
    }


@app.get(
    "/sources/tags",
    operation_id="list_document_tags",
    tags=["ingestion"],
    summary="List persisted document tags",
    description=(
        "Return the distinct tags currently present in persisted documents, "
        "optionally filtered by source_id."
    ),
)
def list_document_tags(
    source_id: str | None = None,
) -> ListDocumentTagsResponse:
    """Expose the current aggregated tag catalog for persisted documents."""
    return SERVICE.list_document_tags(source_id=source_id)


app.get(
    "/sources/documents",
    operation_id="list_documents",
    tags=["ingestion"],
    summary="List ingested documents",
    description=(
        "Return lightweight metadata for documents currently persisted in the "
        "local catalog, optionally filtered by source_id."
    ),
)(list_documents)


@app.get(
    "/sources/documents/{document_id}/content",
    operation_id="get_document_content",
    tags=["ingestion"],
    summary="Get full persisted document content",
    description=(
        "Return the full text content currently persisted for one ingested "
        "document, addressed by document_id."
    ),
    responses={
        404: {"description": "Document not found for the provided id."}
    },
)
def get_document_content(document_id: str) -> DocumentContentResponse:
    """Expose one persisted document payload with full text content."""
    try:
        return SERVICE.get_document_content(document_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {document_id}",
        ) from exc


@app.delete(
    "/sources/documents/{document_id}",
    operation_id="delete_document",
    tags=["ingestion"],
    summary="Delete one ingested document",
    description=(
        "Delete a persisted document by document_id, including SQLite "
        "metadata/chunks, Chroma vectors, managed staging mirror copy when "
        "present, graph resync for the affected source, and Neo4j orphan "
        "Entity cleanup after resync."
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


@app.put(
    "/sources/documents/{document_id}/tags",
    operation_id="replace_document_tags",
    tags=["ingestion"],
    summary="Replace tags for one ingested document",
    description=(
        "Replace the full tag set for one persisted document without "
        "changing its indexed content."
    ),
    responses={
        404: {"description": "Document not found for the provided id."}
    },
)
def replace_document_tags(
    document_id: str,
    request: ReplaceDocumentTagsRequest,
) -> ReplaceDocumentTagsResponse:
    """Replace all tags for one persisted document."""
    try:
        return SERVICE.replace_document_tags(document_id, request)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {document_id}",
        ) from exc


@app.get(
    "/sources/ingest/readiness",
    operation_id="ingest_readiness",
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
        "lexical": _check_lexical_runtime(),
        "chroma": _check_chroma_runtime(),
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
        raise HTTPException(
            status_code=503,
            detail=_format_exception_detail(
                exc,
                operation="ingest_source",
                context={
                    "source_type": request.source.source_type,
                    "has_local_path": bool(request.source.local_path),
                },
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_format_exception_detail(
                exc,
                operation="ingest_source",
                context={
                    "source_type": request.source.source_type,
                    "has_local_path": bool(request.source.local_path),
                },
            ),
        ) from exc


@app.post(
    "/sources/ingest/files",
    operation_id="ingest_source_files",
    tags=["ingestion"],
    summary="Run synchronous ingestion from uploaded files",
    description=(
        "Upload one or more supported documents via multipart/form-data, "
        "stage them server-side in one batch directory, and execute the "
        "same synchronous ingestion pipeline."
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
def ingest_source_files(
    files: list[UploadFile] = File(...),
    source_type: str = Form("folder"),
    filters: str | None = Form(None),
    tags: str | None = Form(None),
) -> dict[str, Any]:
    """Trigger ingestion pipeline from one uploaded batch."""
    staged_dir: Path | None = None
    filenames = [item.filename for item in files]
    try:
        staged_batch = UPLOAD_INGESTION.stage_uploads_batch(files)
        staged_dir = staged_batch.staged_dir
        parsed_filters = UPLOAD_INGESTION.parse_filters(filters)
        parsed_tags = UPLOAD_INGESTION.parse_tags(tags)
        request = UPLOAD_INGESTION.build_request(
            staged_dir=staged_dir,
            source_type=source_type,
            filters=parsed_filters,
            tags=parsed_tags,
        )
        return SERVICE.ingest(request)
    except UploadIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=_format_exception_detail(
                exc,
                operation="ingest_source_files",
                context={
                    "filenames": filenames,
                    "file_count": len(files),
                    "source_type": source_type,
                    "has_filters": bool(filters and filters.strip()),
                    "has_tags": bool(tags and tags.strip()),
                },
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_format_exception_detail(
                exc,
                operation="ingest_source_files",
                context={
                    "filenames": filenames,
                    "file_count": len(files),
                    "source_type": source_type,
                    "has_filters": bool(filters and filters.strip()),
                    "has_tags": bool(tags and tags.strip()),
                    "staged_dir": str(staged_dir) if staged_dir else None,
                },
            ),
        ) from exc
    finally:
        if staged_dir is not None:
            UPLOAD_INGESTION.cleanup(staged_dir)


@app.post(
    "/sources/ingest/files/async",
    operation_id="ingest_source_files_async",
    tags=["ingestion"],
    summary="Enqueue asynchronous ingestion from uploaded files",
    description=(
        "Upload one or more supported documents via multipart/form-data and "
        "enqueue asynchronous ingestion. Uploaded batches are persisted as "
        "temporary Postgres artifacts so workers can rehydrate them without "
        "depending on a shared staging volume."
    ),
    responses={
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
def ingest_source_files_async(
    files: list[UploadFile] = File(...),
    source_type: str = Form("folder"),
    filters: str | None = Form(None),
    tags: str | None = Form(None),
) -> dict[str, str]:
    """Enqueue async ingestion pipeline from one uploaded batch."""
    artifact_id: str | None = None
    filenames = [item.filename for item in files]
    try:
        captured_files = UPLOAD_INGESTION.collect_uploads(files)
        parsed_filters = UPLOAD_INGESTION.parse_filters(filters)
        parsed_tags = UPLOAD_INGESTION.parse_tags(tags)

        artifact_id = RUNTIME.ingestion_artifact_store.create_uploaded_batch_artifact(
            source_type=source_type,
            origin_path_or_url=None,
            files=_artifact_files_payload(captured_files),
        )
        request = UPLOAD_INGESTION.build_request(
            staged_dir=None,
            source_type=source_type,
            filters=parsed_filters,
            tags=parsed_tags,
            artifact_id=artifact_id,
        )
        payload = request.model_dump()

        if SETTINGS.use_rq:
            try:
                job_id = enqueue_ingest_job(payload)
                message = "Upload ingestion job enqueued"
            except Exception as exc:
                if not _is_queue_connection_error(exc):
                    raise
                job_id = enqueue_local_ingest_job(payload)
                message = (
                    "RQ unavailable; upload ingestion job started "
                    "(local async worker fallback)"
                )
        else:
            job_id = enqueue_local_ingest_job(payload)
            message = "Upload ingestion job started (local async worker)"

        return {
            "job_id": job_id,
            "status": "queued",
            "message": message,
        }
    except UploadIngestionError as exc:
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_failed(
                artifact_id,
                str(exc),
            )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_failed(
                artifact_id,
                "HTTPException before async enqueue completed",
            )
        raise
    except Exception as exc:
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_failed(
                artifact_id,
                str(exc),
            )
        raise HTTPException(
            status_code=500,
            detail=_format_exception_detail(
                exc,
                operation="ingest_source_files_async",
                context={
                    "filenames": filenames,
                    "file_count": len(files),
                    "source_type": source_type,
                    "has_filters": bool(filters and filters.strip()),
                    "has_tags": bool(tags and tags.strip()),
                    "artifact_id": artifact_id,
                    "use_rq": SETTINGS.use_rq,
                },
            ),
        ) from exc


def _decode_uploaded_payloads(
    request: FilesIngestionJsonRequest,
) -> list[tuple[str, bytes, str | None]]:
    """Decode base64 JSON file payloads into ``(filename, bytes, media_type)``.

    MCP-friendly counterpart to multipart parsing: raises ``UploadIngestionError``
    (mapped to 422 by the endpoints) when any ``content_base64`` is malformed.
    """
    decoded: list[tuple[str, bytes, str | None]] = []
    for item in request.files:
        try:
            payload = base64.b64decode(item.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise UploadIngestionError(
                f"content_base64 inválido para '{item.filename}'."
            ) from exc
        decoded.append((item.filename, payload, item.media_type))
    return decoded


@app.post(
    "/sources/ingest/files/json",
    operation_id="ingest_files_json",
    tags=["ingestion"],
    summary="Run synchronous ingestion from base64 JSON files",
    description=(
        "MCP-friendly alternative to /sources/ingest/files: upload one or more "
        "supported documents as base64-encoded content in a JSON body, stage "
        "them server-side, and execute the same synchronous ingestion pipeline."
    ),
    responses={
        422: {
            "description": (
                "Invalid base64 content, unsupported extension, "
                "or malformed payload."
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
def ingest_files_json(request: FilesIngestionJsonRequest) -> dict[str, Any]:
    """Trigger ingestion pipeline from one base64-encoded JSON batch."""
    staged_dir: Path | None = None
    filenames = [item.filename for item in request.files]
    try:
        decoded = _decode_uploaded_payloads(request)
        captured_files = UPLOAD_INGESTION.collect_payloads(decoded)
        staged_batch = UPLOAD_INGESTION.materialize_batch(captured_files)
        staged_dir = staged_batch.staged_dir
        ingestion_request = UPLOAD_INGESTION.build_request(
            staged_dir=staged_dir,
            source_type=request.source_type,
            filters=request.filters,
            tags=request.tags,
        )
        return SERVICE.ingest(ingestion_request)
    except UploadIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=_format_exception_detail(
                exc,
                operation="ingest_files_json",
                context={
                    "filenames": filenames,
                    "file_count": len(request.files),
                    "source_type": request.source_type,
                    "has_filters": bool(request.filters),
                    "has_tags": bool(request.tags),
                },
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_format_exception_detail(
                exc,
                operation="ingest_files_json",
                context={
                    "filenames": filenames,
                    "file_count": len(request.files),
                    "source_type": request.source_type,
                    "has_filters": bool(request.filters),
                    "has_tags": bool(request.tags),
                    "staged_dir": str(staged_dir) if staged_dir else None,
                },
            ),
        ) from exc
    finally:
        if staged_dir is not None:
            UPLOAD_INGESTION.cleanup(staged_dir)


@app.post(
    "/sources/ingest/files/json/async",
    operation_id="ingest_files_json_async",
    tags=["ingestion"],
    summary="Enqueue asynchronous ingestion from base64 JSON files",
    description=(
        "MCP-friendly alternative to /sources/ingest/files/async: upload one or "
        "more supported documents as base64-encoded content in a JSON body and "
        "enqueue asynchronous ingestion. Uploaded batches are persisted as "
        "temporary Postgres artifacts so workers can rehydrate them."
    ),
    responses={
        422: {
            "description": (
                "Invalid base64 content, unsupported extension, "
                "or malformed payload."
            )
        },
        500: {"description": "Queue or local async worker startup error."},
    },
)
def ingest_files_json_async(
    request: FilesIngestionJsonRequest,
) -> dict[str, str]:
    """Enqueue async ingestion pipeline from one base64-encoded JSON batch."""
    artifact_id: str | None = None
    filenames = [item.filename for item in request.files]
    try:
        decoded = _decode_uploaded_payloads(request)
        captured_files = UPLOAD_INGESTION.collect_payloads(decoded)

        artifact_id = RUNTIME.ingestion_artifact_store.create_uploaded_batch_artifact(
            source_type=request.source_type,
            origin_path_or_url=None,
            files=_artifact_files_payload(captured_files),
        )
        ingestion_request = UPLOAD_INGESTION.build_request(
            staged_dir=None,
            source_type=request.source_type,
            filters=request.filters,
            tags=request.tags,
            artifact_id=artifact_id,
        )
        payload = ingestion_request.model_dump()

        if SETTINGS.use_rq:
            try:
                job_id = enqueue_ingest_job(payload)
                message = "Upload ingestion job enqueued"
            except Exception as exc:
                if not _is_queue_connection_error(exc):
                    raise
                job_id = enqueue_local_ingest_job(payload)
                message = (
                    "RQ unavailable; upload ingestion job started "
                    "(local async worker fallback)"
                )
        else:
            job_id = enqueue_local_ingest_job(payload)
            message = "Upload ingestion job started (local async worker)"

        return {
            "job_id": job_id,
            "status": "queued",
            "message": message,
        }
    except UploadIngestionError as exc:
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_failed(
                artifact_id,
                str(exc),
            )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_failed(
                artifact_id,
                "HTTPException before async enqueue completed",
            )
        raise
    except Exception as exc:
        if artifact_id:
            RUNTIME.ingestion_artifact_store.mark_processing_failed(
                artifact_id,
                str(exc),
            )
        raise HTTPException(
            status_code=500,
            detail=_format_exception_detail(
                exc,
                operation="ingest_files_json_async",
                context={
                    "filenames": filenames,
                    "file_count": len(request.files),
                    "source_type": request.source_type,
                    "has_filters": bool(request.filters),
                    "has_tags": bool(request.tags),
                    "artifact_id": artifact_id,
                    "use_rq": SETTINGS.use_rq,
                },
            ),
        ) from exc


@app.post(
    "/admin/reset",
    tags=["ingestion"],
    summary="Reset all ingestion artifacts",
    description=(
        "Clear persisted ingestion state, TDM metadata, staging mirror, "
        "managed graph relationships, and reset runtime indexes. Requires "
        "administrative token and explicit confirmation in the request body."
    ),
    responses={
        403: {"description": "Missing or invalid admin reset token."},
        404: {"description": "Administrative reset endpoint disabled."},
        422: {"description": "Invalid reset confirmation payload."},
    },
)
def reset_sources(
    request: AdminResetRequest,
    x_admin_reset_token: str | None = Header(
        default=None,
        alias="X-Admin-Reset-Token",
    ),
) -> dict[str, Any]:
    """Clear persisted ingestion artifacts and reset runtime indexes."""
    _ensure_admin_reset_access(x_admin_reset_token)
    return _run_reset_all(confirm=request.confirm)


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
    operation_id="get_job",
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
    operation_id="query",
    tags=["query"],
    summary="Run hybrid query",
    description=(
        "Execute lexical + vector retrieval, graph expansion, and optional LLM "
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
    operation_id="retrieval_only",
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


# Montaje del servidor MCP al final del módulo: fastapi-mcp introspecta el
# OpenAPI en este punto, por lo que todas las rutas @app ya deben estar
# registradas. Coexiste con la API REST en el mismo proceso/puerto.
if SETTINGS.mcp_enabled:
    from coderag.api.mcp_server import setup_mcp

    setup_mcp(app)
