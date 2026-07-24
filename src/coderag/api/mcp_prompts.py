"""Prompts MCP para guiar a los agentes en el uso de las tools documentales.

``fastapi-mcp`` solo deriva *tools* del OpenAPI; no expone prompts. Este módulo
registra prompts sobre el servidor MCP low-level subyacente (``mcp.server``) para
enseñar a los agentes *cuándo* y *cómo* usar ``query``/``retrieval_only`` para
responder preguntas sobre documentos ingeridos, cómo ingerir archivos nuevos y
seguir su progreso, y cómo administrar el catálogo de documentos ya ingeridos.

Se registra tras construir ``FastApiMCP`` y antes de ``mount_http`` para que el
servidor anuncie la capability ``prompts`` en el handshake.
"""

from __future__ import annotations

from mcp.server.lowlevel import Server
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
)

# --- Texto de los prompts ---------------------------------------------------
#
# Se usan placeholders con formato ``{pregunta}`` / ``{source_id}`` que se
# rellenan en ``get_prompt`` con los argumentos recibidos. El contenido está en
# español (coherente con el proyecto); los nombres de tools/campos se mantienen
# en inglés.

_QUERY_GUIDE = """\
Vas a responder una pregunta sobre los documentos ingeridos usando la tool MCP \
`query` (o su alias `retrieval_only`, mismo payload). Esta tool ejecuta Hybrid \
RAG (vector Chroma + léxico Postgres FTS + expansión de grafo Neo4j opcional), \
rerankea la evidencia y **sintetiza una respuesta con un LLM** cuando \
`include_llm_answer=true`, devolviendo `answer` + `citations` (chunk_id, \
document_id, score, snippet, path_or_url, section_name, start_ref, end_ref) + \
`graph_paths` + `diagnostics`.

Antes de llamar:
1. Si conoces el documento exacto, filtra por `source_id` o `document_ids` para \
acotar la búsqueda; si no, deja ambos vacíos para buscar en todo el catálogo.
2. Usa el resource `rag://documents` (o la tool `list_documents`) para conocer \
qué documentos existen y sus `document_id`/`source_id` reales; no los inventes.

Parámetros de `QueryRequest`:
- `question` (requerido): la pregunta en lenguaje natural.
- `source_id` / `document_ids`: acotan la búsqueda a un origen o documentos \
específicos.
- `hops`: profundidad de expansión de grafo (default de runtime: 2).
- `include_llm_answer` (default `true`): si es `false`, obtienes evidencia sin \
síntesis LLM (más rápido, más barato, sin `answer` generado).
- `force_fallback`: fuerza el modo degradado (solo para diagnóstico).
- `llm_provider`: sobreescribe el proveedor LLM configurado (openai/gemini/vertex).

Política anti-alucinación: si `diagnostics` indica que no hay evidencia \
suficiente, la respuesta correcta es exactamente \
"No se encontro informacion en las fuentes indexadas."; no inventes contenido, \
entidades ni relaciones. Toda afirmación debe estar respaldada por `citations` \
o `graph_paths`.

Pregunta a resolver: **{pregunta}**
"""

_INGEST_WORKFLOW_GUIDE = """\
Flujo recomendado para ingerir documentos nuevos con este servidor MCP:

1. Consulta la tool `ingest_readiness` (o el resource `rag://ingest/readiness`) \
para verificar que las dependencias críticas (metadata store, léxico, Chroma, \
y opcionalmente Neo4j/Redis si `use_neo4j`/`use_rq` están activos) estén sanas \
antes de encolar una ingesta grande.
2. Codifica cada archivo en base64 y llama a `ingest_files_json` (síncrono, \
espera a que termine) o `ingest_files_json_async` (encola un job y responde de \
inmediato). Ambas tools aceptan `source_type`, `filters` y `tags` opcionales.
3. Si usaste la variante async, sondea `get_job` con el `job_id` devuelto hasta \
que `status` sea `completed` o `failed`.
4. Verifica el resultado con `list_documents` (o el resource `rag://documents`) \
y, si necesitas el texto completo de un documento puntual, usa \
`get_document_content` (o el resource `rag://documents/{{document_id}}`).

Deduplicación: la ingesta deduplica por `title + content_type`; volver a \
ingerir el mismo documento no crea duplicados (la respuesta indica \
`created: false` cuando ya existía).
"""

_DOCUMENT_CATALOG_GUIDE = """\
Flujo recomendado para administrar el catálogo de documentos ya ingeridos:

1. Lista documentos con `list_documents` (filtra por `source_id` si conoces el \
origen) o consulta el resource `rag://documents` para el catálogo completo.
2. Lista las etiquetas existentes con `list_document_tags` para reutilizar \
convenciones de tagging ya usadas en el proyecto.
3. Para leer el contenido completo de un documento puntual, usa \
`get_document_content` (o el resource `rag://documents/{{document_id}}`) con el \
`document_id` exacto obtenido en el paso 1.
4. Para reemplazar el set completo de tags de un documento, usa \
`replace_document_tags`; esta operación es idempotente (`created: false` \
siempre, no crea un documento nuevo).
5. Para eliminar un documento (metadata, chunks, vectores y, si aplica, aristas \
de grafo), usa `delete_document`. Esta acción es destructiva e irreversible: \
confirma el `document_id` antes de invocarla.

Fundamenta siempre tus respuestas en el contenido real devuelto por estas \
tools; no asumas documentos ni tags que no aparezcan en el catálogo.
"""


# --- Definición declarativa de los prompts ----------------------------------

_ARG_PREGUNTA = PromptArgument(
    name="pregunta",
    description="Pregunta en lenguaje natural a resolver.",
    required=True,
)

_PROMPTS: list[Prompt] = [
    Prompt(
        name="query_guide",
        description=(
            "Guía para responder una pregunta con la tool query/retrieval_only "
            "(Hybrid RAG sobre documentos ingeridos, con citas)."
        ),
        arguments=[_ARG_PREGUNTA],
    ),
    Prompt(
        name="ingest_workflow_guide",
        description=(
            "Flujo end-to-end para ingerir documentos nuevos: readiness, "
            "ingest (sync/async), seguimiento de job y verificación."
        ),
        arguments=[],
    ),
    Prompt(
        name="document_catalog_guide",
        description=(
            "Flujo para administrar el catálogo: listar, leer contenido, "
            "gestionar tags y eliminar documentos."
        ),
        arguments=[],
    ),
]

_TEMPLATES: dict[str, str] = {
    "query_guide": _QUERY_GUIDE,
    "ingest_workflow_guide": _INGEST_WORKFLOW_GUIDE,
    "document_catalog_guide": _DOCUMENT_CATALOG_GUIDE,
}


def _render(name: str, arguments: dict[str, str] | None) -> str:
    """Rellena el template del prompt con los argumentos recibidos.

    ``ingest_workflow_guide`` y ``document_catalog_guide`` no toman argumentos.
    """
    template = _TEMPLATES[name]
    args = arguments or {}
    if name == "query_guide":
        return template.format(pregunta=args.get("pregunta", "<pregunta>"))
    return template.format()


def register_mcp_prompts(server: Server) -> int:
    """Registra los handlers de prompts sobre el servidor MCP low-level.

    Debe llamarse antes de ``mount_http`` para que la capability ``prompts`` se
    anuncie en el handshake. Devuelve la cantidad de prompts registrados.
    """

    @server.list_prompts()
    async def _list_prompts() -> list[Prompt]:
        return _PROMPTS

    @server.get_prompt()
    async def _get_prompt(
        name: str, arguments: dict[str, str] | None
    ) -> GetPromptResult:
        if name not in _TEMPLATES:
            raise ValueError(f"Prompt desconocido: {name}")
        prompt = next(p for p in _PROMPTS if p.name == name)
        return GetPromptResult(
            description=prompt.description,
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=_render(name, arguments)),
                )
            ],
        )

    return len(_PROMPTS)
