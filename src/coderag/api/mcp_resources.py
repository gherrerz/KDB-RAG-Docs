"""Resources MCP: guías estáticas + estado en vivo del catálogo documental.

``fastapi-mcp`` no expone resources; se registran sobre el servidor MCP low-level
subyacente (``mcp.server``). Hay dos familias:

- **Estáticos** (``rag://guide/*``): documentos markdown autorados que enseñan a
  los agentes a explotar las tools sin adivinar contratos ni capacidades.
- **Dinámicos** (``rag://documents``, ``rag://documents/{document_id}``,
  ``rag://ingest/readiness``): leen estado en vivo reutilizando el cliente HTTP
  ASGI interno de ``FastApiMCP`` (mismas rutas REST, mismo proceso) para que el
  agente descubra los documentos y su disponibilidad antes de consultar o ingerir.

Se registra tras construir ``FastApiMCP`` y antes de ``mount_http`` para que el
servidor anuncie la capability ``resources`` en el handshake.
"""

from __future__ import annotations

import json
import logging

import httpx
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import Resource, ResourceTemplate
from pydantic import AnyUrl

_log = logging.getLogger(__name__)

# Base URL del transporte ASGI interno de fastapi-mcp (server.py: _base_url).
_INTERNAL_BASE_URL = "http://apiserver"
_MD = "text/markdown"
_JSON = "application/json"

# --- Guías estáticas --------------------------------------------------------

_TOOLS_OVERVIEW = """\
# Tools MCP disponibles

Este servidor expone tools derivadas de la API REST de ingesta documental y \
consulta con RAG híbrido. Cuándo usar cada una:

| Tool | Uso |
|------|-----|
| `query` / `retrieval_only` | Pregunta sobre documentos ingeridos → evidencia + respuesta LLM (mismo payload, alias). |
| `list_documents` | Lista documentos ingeridos (o lee el resource `rag://documents`). |
| `list_document_tags` | Lista las etiquetas usadas en el catálogo. |
| `get_document_content` | Devuelve el texto completo de un documento por `document_id`. |
| `delete_document` | Elimina un documento (metadata, chunks, vectores, grafo). Destructivo. |
| `replace_document_tags` | Reemplaza el set de tags de un documento (idempotente). |
| `ingest_readiness` | Diagnóstico de dependencias antes de ingerir. |
| `ingest_files_json` | Ingesta síncrona de archivos (base64 JSON). |
| `ingest_files_json_async` | Ingesta asíncrona: encola un job y devuelve `job_id`. |
| `get_job` | Estado de un job de ingesta asíncrona. |

Regla de oro: antes de responder preguntas, confirma con `list_documents` (o el \
resource `rag://documents`) qué documentos existen; no inventes `document_id` \
ni contenido que no aparezca en el catálogo o en las citas.
"""

_QUERY_COOKBOOK = """\
# Cookbook de consulta y política anti-alucinación

## Acotar la búsqueda
- Si conoces el origen, pasa `source_id` o `document_ids` en `QueryRequest` para \
limitar la búsqueda a un subconjunto del catálogo.
- Si no conoces el origen exacto, deja ambos vacíos: la búsqueda híbrida cubre \
todo el catálogo indexado.

## Respuesta con o sin síntesis LLM
- `include_llm_answer=true` (default): obtienes `answer` redactada + `citations` \
+ `graph_paths` + `diagnostics`.
- `include_llm_answer=false`: obtienes evidencia recuperada sin síntesis LLM \
(más rápido, sin costo de generación).

## Multi-hop / grafo
- Ajusta `hops` para expandir más o menos saltos de grafo (default de runtime: 2). \
Prioriza siempre rutas de grafo (`graph_paths`) como soporte adicional cuando la \
pregunta requiere relacionar múltiples documentos.

## Política anti-alucinación (obligatoria)
1. No inventar entidades, relaciones ni citas.
2. Toda afirmación debe estar soportada por evidencia textual (`citations`) o \
una ruta de grafo (`graph_paths`).
3. Sin evidencia suficiente, la respuesta correcta es exactamente: \
"No se encontro informacion en las fuentes indexadas."
4. Si `diagnostics` indica que una capacidad está deshabilitada por flags \
(por ejemplo `use_neo4j=false`), infórmalo explícitamente en tu respuesta.
"""

_PARAMETERS = """\
# Referencia de parámetros

`QueryRequest` (usado por `query` y `retrieval_only`, mismo payload):

| Parámetro | Default | Notas |
|-----------|---------|-------|
| `question` | — (requerido) | Pregunta en lenguaje natural. |
| `source_id` | `null` | Acota la búsqueda a un origen específico. |
| `document_ids` | `[]` | Acota la búsqueda a documentos concretos. |
| `hops` | `null` (usa default de runtime: 2) | Profundidad de expansión de grafo. |
| `include_llm_answer` | `true` | `false` retorna evidencia sin síntesis LLM. |
| `force_fallback` | `false` | Fuerza modo degradado (diagnóstico). |
| `llm_provider` | `null` (usa el configurado) | `local`/`openai`/`gemini`/`vertex`. |

`FilesIngestionJsonRequest` (usado por `ingest_files_json`/`ingest_files_json_async`):

| Parámetro | Default | Notas |
|-----------|---------|-------|
| `files` | — (requerido, ≥1) | Archivos codificados en base64. |
| `source_type` | `"folder"` | Tipo de origen declarado para el lote. |
| `filters` | `{}` | Filtros opcionales aplicados al escaneo. |
| `tags` | `[]` | Tags iniciales asignados a los documentos ingeridos. |

Defaults recomendados de retrieval híbrido (nivel runtime, no parámetros de \
request): `top_n=60` (hybrid), `top_k=15` (rerank), `hops=2` (graph), \
`max_context_chars=16000`.
"""

_CAPABILITIES = """\
# Capacidades reales (hoja anti-alucinación)

## Retrieval híbrido
Vector (Chroma remoto) + léxico (Postgres FTS, idioma parametrizable) + \
expansión de grafo (Neo4j, opcional vía `USE_NEO4J`) + multi-hop reasoning.

## Deduplicación
Los documentos se deduplican por `title + content_type`; volver a ingerir el \
mismo documento no genera duplicados (`created: false` en la respuesta).

## Storage
- Vector: Chroma remoto (HTTP, auth opcional). El modo embebido no es válido \
en runtime.
- Léxico: Postgres FTS.
- Grafo: Neo4j (degradación controlada si `USE_NEO4J=false`; infórmalo en la \
respuesta cuando `diagnostics` lo indique).
- Jobs async: Redis + RQ cuando `USE_RQ=true`; worker local en thread como \
fallback si Redis no está disponible.

## Proveedores LLM soportados
`local`, `openai` (Responses API), `gemini`, `vertex`/`vertex_ai`. Anthropic \
**no** es una capacidad implementada.

No asumas capacidades fuera de esta lista.
"""

_ERRORS = """\
# Contrato de errores y recuperación

| Código | Causa | Recuperación |
|--------|-------|--------------|
| 404 | `document_id` no existe en el catálogo. | Verifica con `list_documents` o el resource `rag://documents`. |
| 503 | Falla estricta durante `query`/`retrieval_only` (proveedor LLM, embeddings, o refresh de índice). | Revisa `ingest_readiness` y reintenta cuando las dependencias estén sanas. |
| 422 | Payload inválido (por ejemplo `files` vacío en ingesta). | Corrige el payload según el modelo `FilesIngestionJsonRequest`. |

Sin evidencia suficiente, la tool no falla: devuelve una respuesta con el texto \
exacto "No se encontro informacion en las fuentes indexadas." — no lo \
interpretes como error.
"""

_STATIC_RESOURCES: dict[str, tuple[str, str, str]] = {
    # uri: (nombre, descripción, contenido)
    "rag://guide/tools-overview": (
        "Overview de tools MCP",
        "Las tools disponibles y cuándo usar cada una.",
        _TOOLS_OVERVIEW,
    ),
    "rag://guide/query-cookbook": (
        "Cookbook de consulta y anti-alucinación",
        "Cómo acotar búsquedas, usar hops/grafo y la política anti-alucinación.",
        _QUERY_COOKBOOK,
    ),
    "rag://guide/parameters": (
        "Referencia de parámetros",
        "Parámetros de query/retrieval_only e ingesta, defaults y tuning.",
        _PARAMETERS,
    ),
    "rag://guide/capabilities": (
        "Capacidades reales",
        "Retrieval híbrido, storage, deduplicación y proveedores LLM.",
        _CAPABILITIES,
    ),
    "rag://guide/errors": (
        "Contrato de errores",
        "Errores 404/422/503 y cómo recuperarse.",
        _ERRORS,
    ),
}

# --- Resources dinámicos ----------------------------------------------------

_DOCUMENTS_URI = "rag://documents"
_DOCUMENT_CONTENT_PREFIX = "rag://documents/"
_INGEST_READINESS_URI = "rag://ingest/readiness"


def _error_json(message: str, detail: object = None) -> str:
    payload: dict[str, object] = {"error": message}
    if detail is not None:
        payload["detail"] = detail
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def _read_documents(client: httpx.AsyncClient) -> ReadResourceContents:
    try:
        resp = await client.get(f"{_INTERNAL_BASE_URL}/sources/documents")
    except httpx.HTTPError as exc:  # red interna/ASGI caída
        _log.warning("resource rag://documents: fallo de transporte: %s", exc)
        return ReadResourceContents(
            content=_error_json("No se pudo consultar el catálogo de documentos."),
            mime_type=_JSON,
        )
    if resp.status_code != 200:
        return ReadResourceContents(
            content=_error_json(
                "El catálogo de documentos devolvió un estado inesperado.",
                {"status_code": resp.status_code},
            ),
            mime_type=_JSON,
        )
    return ReadResourceContents(content=resp.text, mime_type=_JSON)


async def _read_document_content(
    client: httpx.AsyncClient, document_id: str
) -> ReadResourceContents:
    if not document_id:
        return ReadResourceContents(
            content=_error_json("Falta document_id en el URI del resource."),
            mime_type=_JSON,
        )
    try:
        resp = await client.get(
            f"{_INTERNAL_BASE_URL}/sources/documents/{document_id}/content"
        )
    except httpx.HTTPError as exc:
        _log.warning(
            "resource rag://documents/%s: fallo de transporte: %s",
            document_id,
            exc,
        )
        return ReadResourceContents(
            content=_error_json(
                f"No se pudo consultar el contenido de '{document_id}'."
            ),
            mime_type=_JSON,
        )
    if resp.status_code != 200:
        return ReadResourceContents(
            content=_error_json(
                f"El documento '{document_id}' devolvió un estado inesperado.",
                {"status_code": resp.status_code},
            ),
            mime_type=_JSON,
        )
    return ReadResourceContents(content=resp.text, mime_type=_JSON)


async def _read_ingest_readiness(client: httpx.AsyncClient) -> ReadResourceContents:
    try:
        resp = await client.get(f"{_INTERNAL_BASE_URL}/sources/ingest/readiness")
    except httpx.HTTPError as exc:
        _log.warning("resource rag://ingest/readiness: fallo de transporte: %s", exc)
        return ReadResourceContents(
            content=_error_json("No se pudo consultar la readiness de ingesta."),
            mime_type=_JSON,
        )
    if resp.status_code != 200:
        return ReadResourceContents(
            content=_error_json(
                "La readiness de ingesta devolvió un estado inesperado.",
                {"status_code": resp.status_code},
            ),
            mime_type=_JSON,
        )
    return ReadResourceContents(content=resp.text, mime_type=_JSON)


def register_mcp_resources(server: Server, http_client: httpx.AsyncClient) -> int:
    """Registra handlers de resources (estáticos + dinámicos) sobre el servidor.

    Debe llamarse antes de ``mount_http`` para anunciar la capability
    ``resources``. Devuelve la cantidad de resources fijos listados (los
    estáticos + ``rag://documents`` + ``rag://ingest/readiness``); el template
    de contenido por documento no cuenta como resource fijo.
    """

    fixed_resources: list[Resource] = [
        Resource(
            uri=AnyUrl(uri),
            name=name,
            description=description,
            mimeType=_MD,
        )
        for uri, (name, description, _content) in _STATIC_RESOURCES.items()
    ]
    fixed_resources.append(
        Resource(
            uri=AnyUrl(_DOCUMENTS_URI),
            name="Documentos ingeridos",
            description="Catálogo en vivo de documentos actualmente persistidos.",
            mimeType=_JSON,
        )
    )
    fixed_resources.append(
        Resource(
            uri=AnyUrl(_INGEST_READINESS_URI),
            name="Readiness de ingesta",
            description=(
                "Diagnóstico en vivo de dependencias (metadata store, léxico, "
                "Chroma, Neo4j, Redis/RQ) antes de ingerir."
            ),
            mimeType=_JSON,
        )
    )

    resource_templates: list[ResourceTemplate] = [
        ResourceTemplate(
            uriTemplate="rag://documents/{document_id}",
            name="Contenido de un documento",
            description=(
                "Texto completo persistido para un documento ingerido, "
                "addressado por document_id."
            ),
            mimeType=_JSON,
        )
    ]

    @server.list_resources()
    async def _list_resources() -> list[Resource]:
        return fixed_resources

    @server.list_resource_templates()
    async def _list_resource_templates() -> list[ResourceTemplate]:
        return resource_templates

    @server.read_resource()
    async def _read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
        uri_str = str(uri)
        static = _STATIC_RESOURCES.get(uri_str)
        if static is not None:
            return [ReadResourceContents(content=static[2], mime_type=_MD)]
        if uri_str == _DOCUMENTS_URI:
            return [await _read_documents(http_client)]
        if uri_str == _INGEST_READINESS_URI:
            return [await _read_ingest_readiness(http_client)]
        if uri_str.startswith(_DOCUMENT_CONTENT_PREFIX):
            document_id = uri_str[len(_DOCUMENT_CONTENT_PREFIX):]
            return [await _read_document_content(http_client, document_id)]
        raise ValueError(f"Resource desconocido: {uri_str}")

    return len(fixed_resources)
