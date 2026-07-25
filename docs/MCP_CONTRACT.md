# Contrato MCP — KDB-RAG-Docs

Documento de referencia autocontenido para integraciones externas (orquestadores
de agentes, gateways MCP, Hexa) que consuman el servidor MCP de este proyecto.
Describe las 3 superficies del protocolo (tools, prompts, resources), sus
payloads exactos de entrada/salida y todos los códigos de error posibles, sin
necesidad de leer el código fuente.

> Para el resto de la API REST (no-MCP) ver [API_REFERENCE.md](API_REFERENCE.md).
> Para variables de entorno ver [CONFIGURATION.md](CONFIGURATION.md).

## 1. Overview

| Aspecto | Valor |
| --- | --- |
| Nombre del servidor MCP | `documents-kdb-mcp` (default en código sin `MCP_SERVER_NAME`; el `.env.example` distribuido usa `docrag-mcp`) |
| Versión del servicio | `0.1.0` (`app.version`, expuesta en `/health` e `/info`) |
| Protocolo MCP | `mcp==1.28.1` |
| Envoltura HTTP | `fastapi-mcp==0.4.0` |
| Transporte | HTTP streamable (`Accept: application/json, text/event-stream`) |
| Endpoint de montaje | `POST/GET {MCP_MOUNT_PATH}` (default `/mcp`) |
| Coexistencia | El servidor MCP se monta sobre la misma app FastAPI y el mismo proceso/puerto que la API REST, después de registrar todas las rutas (`src/coderag/api/mcp_server.py::setup_mcp`). |
| server_type (`/info`) | `"tools"` — operaciones discretas y sincrónicas, no un pipeline de orquestación interna. |

Primitivas publicadas:

| Primitiva | Cantidad | Detalle |
| --- | --- | --- |
| Tools | 11 | Sección 4 |
| Prompts | 3 | Sección 5 |
| Resources | 8 (5 estáticos + 3 dinámicos) | Sección 6 |

Log de arranque esperado (`src/coderag/api/mcp_server.py::setup_mcp`):

```text
Servidor MCP montado en /mcp con 11 tools, 3 prompts y 8 resources.
```

## 2. Autenticación

Función `_ensure_mcp_access()` en `src/coderag/api/mcp_server.py`, aplicada como
dependencia de `AuthConfig` sobre **todo** el endpoint `/mcp` (todas las
tools comparten esta única puerta de entrada):

1. **Feature flag** — si `MCP_ENABLED=false`:
   - HTTP `404`
   - Body: `{"message": "El servidor MCP está deshabilitado.", "code": "mcp_disabled"}`
2. **Bearer token** — si `MCP_API_TOKEN` está configurado (no vacío):
   - Header requerido: `Authorization: Bearer {MCP_API_TOKEN}` (esquema
     case-insensitive, token con trim automático).
   - Si el header falta, no sigue el esquema `Bearer`, o el token no coincide:
     HTTP `401` con body
     `{"message": "Token inválido para el endpoint MCP.", "code": "invalid_mcp_token"}`.
3. **Sin token configurado** (`MCP_API_TOKEN=""`): el endpoint queda accesible
   solo protegido por el feature flag. Al arranque se emite una advertencia de
   seguridad (`MCP_ENABLED=true sin MCP_API_TOKEN: /mcp quedará accesible sin
   autenticación...`).

`GET /health` y `GET /info` **no** requieren autenticación (contrato Hexa).

### Headers de identidad (pass-through, opcionales)

El servidor MCP reenvía estos headers desde la conexión `/mcp` hacia cada
llamada interna de tool (allowlist de `fastapi-mcp`, declarados en el OpenAPI
de cada operación expuesta vía `Depends(identity_headers)`):

| Header | Obligatorio | Descripción |
| --- | --- | --- |
| `x-role-id` | No | Rol del llamante. |
| `x-user-id` | No | ID del usuario del llamante. |
| `x-country-id` | No | País del llamante. |

Por limitación de `fastapi-mcp==0.4.0` estos headers **no** aparecen como
argumentos JSON de la tool; se fijan una única vez en la conexión `/mcp`
(inicialización del cliente MCP o del gateway) y aplican a todas las llamadas
de esa sesión.

## 3. Endpoints públicos no-MCP

### 3.1 `GET /health`

Sin autenticación. Consolida el estado de `runtime_store`, `lexical` y
`chroma` (checks críticos). Respuesta esperada en menos de 2 segundos.

Modelo `McpHealthResponse` (`src/coderag/core/models.py`):

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `status` | `"healthy" \| "degraded" \| "unhealthy"` | Estado global consolidado. |
| `name` | `str` | Nombre del servidor MCP. |
| `version` | `str` | Versión semántica del servicio. |
| `uptime_s` | `int` | Segundos desde el arranque del proceso. |
| `dependencies` | `dict[str, McpDependencyStatus]` | Estado por dependencia. |

`McpDependencyStatus`: `status: "healthy" | "unhealthy"`, `latency_ms: float`.

Lógica de consolidación: si algún check **crítico** falla → `unhealthy`; si
solo falla un check **no crítico** (`neo4j`/`redis`/`rq_worker` cuando sus
flags están deshabilitados) → `degraded`; en otro caso → `healthy`.

Ejemplo de respuesta:

```json
{
  "status": "healthy",
  "name": "documents-kdb-mcp",
  "version": "0.1.0",
  "uptime_s": 3600,
  "dependencies": {
    "runtime_store": { "status": "healthy", "latency_ms": 12.5 },
    "lexical": { "status": "healthy", "latency_ms": 8.1 },
    "chroma": { "status": "healthy", "latency_ms": 21.3 }
  }
}
```

Códigos HTTP: `200` siempre (el estado degradado/unhealthy se refleja en el
body, no en el status code).

### 3.2 `GET /info`

Sin autenticación. Metadata estática, no depende de dependencias runtime.

Modelo `McpInfoResponse`:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `name` | `str` | Nombre único del servidor MCP. |
| `version` | `str` | Versión semántica del servicio. |
| `server_type` | `"tools" \| "agent"` | `"tools"` en este servidor. |
| `description` | `str` | Descripción legible del sistema integrado. |
| `sensitive_fields` | `list[str]` | Campos con contenido libre de usuario. |

Ejemplo de respuesta:

```json
{
  "name": "documents-kdb-mcp",
  "version": "0.1.0",
  "server_type": "tools",
  "description": "Ingesta y consulta documental empresarial con RAG híbrido (vector + lexical + grafo).",
  "sensitive_fields": ["query", "question", "content", "title", "tags", "answer"]
}
```

Códigos HTTP: `200` siempre.

### 3.3 `GET /readiness` (adyacente, no forma parte del contrato MCP)

Mismo criterio que `/health` pero con respuesta HTTP binaria para
orquestadores: `200 {"status": "ready"}` o `503` si algún check crítico falla.
Sin autenticación.

## 4. Tools MCP (11)

Tabla resumen (`operation_id` = nombre de la tool en `tools/list`):

| Tool | Método + path REST | Resumen |
| --- | --- | --- |
| `list_documents` | `GET /sources/documents` | Catálogo de documentos ingeridos. |
| `list_document_tags` | `GET /sources/tags` | Facetas de tags con recuento. |
| `get_document_content` | `GET /sources/documents/{document_id}/content` | Texto completo de un documento. |
| `delete_document` | `DELETE /sources/documents/{document_id}` | Elimina un documento (destructivo). |
| `replace_document_tags` | `PUT /sources/documents/{document_id}/tags` | Reemplaza el set completo de tags. |
| `ingest_readiness` | `GET /sources/ingest/readiness` | Diagnóstico de dependencias antes de ingerir. |
| `ingest_files_json` | `POST /sources/ingest/files/json` | Ingesta síncrona de archivos en base64. |
| `ingest_files_json_async` | `POST /sources/ingest/files/json/async` | Ingesta asíncrona de archivos en base64. |
| `get_job` | `GET /jobs/{job_id}` | Estado de un job de ingesta. |
| `query` | `POST /query` | Hybrid RAG con síntesis LLM. |
| `retrieval_only` | `POST /query/retrieval` | Alias de `query` (mismo contrato). |

Todos los errores de tools usan el shape estándar `{error, message, retryable}`
descrito en la Sección 7. Todas las llamadas se invocan como JSON-RPC 2.0
`tools/call` sobre el transporte `/mcp` ya autenticado (Sección 2).

---

### 4.1 `list_documents`

**Parámetros de entrada** (todos opcionales, mapean a query params GET):

| Campo | Tipo | Default | Descripción |
| --- | --- | --- | --- |
| `source_id` | `str \| null` | `null` | Filtra por fuente de ingesta. |
| `tags` | `str \| null` | `null` | CSV de tags (ej. `"finance,urgent"`); duplicados insensibles a mayúsculas se eliminan. |

**Respuesta:**

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `source_id` | `str \| null` | Eco del filtro aplicado. |
| `tags` | `list[str]` | Eco de los tags de filtro parseados. |
| `count` | `int` | Cantidad de documentos retornados. |
| `documents` | `list[DocumentCatalogEntry]` | Ver estructura abajo. |

`DocumentCatalogEntry`: `document_id: str`, `source_id: str`, `title: str`,
`path_or_url: str`, `content_type: str`, `updated_at: datetime`,
`tags: list[str]`.

**Errores:** ninguno (`200` siempre; lista vacía si no hay coincidencias).

**Ejemplo `tools/call`:**

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "method": "tools/call",
  "params": {
    "name": "list_documents",
    "arguments": { "tags": "finance" }
  }
}
```

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "result": {
    "content": [{
      "type": "text",
      "text": "{\"source_id\": null, \"tags\": [\"finance\"], \"count\": 1, \"documents\": [{\"document_id\": \"7f0a1c2b\", \"source_id\": \"f0e1d2c3b4a5\", \"title\": \"policy_finance\", \"path_or_url\": \"sample_data/policy_finance.md\", \"content_type\": \"text/markdown\", \"updated_at\": \"2026-01-01T00:00:00+00:00\", \"tags\": [\"finance\"]}]}"
    }]
  }
}
```

**Notas:** sin paginación; el catálogo completo se retorna en una sola llamada.

---

### 4.2 `list_document_tags`

**Parámetros:** `source_id: str | null` (opcional).

**Respuesta** (`ListDocumentTagsResponse`):

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `source_id` | `str \| null` | Eco del filtro aplicado. |
| `count` | `int` | Cantidad de tags distintos. |
| `tags` | `list[str]` | Lista plana de nombres de tag. |
| `items` | `list[DocumentTagFacet]` | `{tag: str, document_count: int}` por tag. |

**Errores:** ninguno (`200` siempre).

**Ejemplo `tools/call`:**

```json
{ "jsonrpc": "2.0", "id": 11, "method": "tools/call",
  "params": { "name": "list_document_tags", "arguments": {} } }
```

```json
{ "jsonrpc": "2.0", "id": 11, "result": { "content": [{ "type": "text",
  "text": "{\"source_id\": null, \"count\": 2, \"tags\": [\"finance\", \"urgent\"], \"items\": [{\"tag\": \"finance\", \"document_count\": 3}, {\"tag\": \"urgent\", \"document_count\": 1}]}" }] } }
```

---

### 4.3 `get_document_content`

**Parámetros:** `document_id: str` (requerido, path param).

**Respuesta** (`DocumentContentResponse`): `document_id: str`,
`source_id: str`, `title: str`, `content: str` (texto completo del
documento), `path_or_url: str`, `content_type: str`, `updated_at: datetime`,
`tags: list[str]`.

**Errores:**

| HTTP | Body | Causa |
| --- | --- | --- |
| `404` | `{"error": "DOCS_NOT_FOUND", "message": "Document not found: {document_id}", "retryable": false}` | El `document_id` no existe en el catálogo persistido. |

**Ejemplo `tools/call` (éxito):**

```json
{ "jsonrpc": "2.0", "id": 12, "method": "tools/call",
  "params": { "name": "get_document_content", "arguments": { "document_id": "7f0a1c2b" } } }
```

```json
{ "jsonrpc": "2.0", "id": 12, "result": { "content": [{ "type": "text",
  "text": "{\"document_id\": \"7f0a1c2b\", \"source_id\": \"f0e1d2c3b4a5\", \"title\": \"policy_finance\", \"content\": \"# Política de finanzas...\", \"path_or_url\": \"sample_data/policy_finance.md\", \"content_type\": \"text/markdown\", \"updated_at\": \"2026-01-01T00:00:00+00:00\", \"tags\": [\"finance\"]}" }] } }
```

**Ejemplo `tools/call` (error 404):**

```json
{ "jsonrpc": "2.0", "id": 12, "result": { "isError": true, "content": [{ "type": "text",
  "text": "{\"error\": \"DOCS_NOT_FOUND\", \"message\": \"Document not found: missing-id\", \"retryable\": false}" }] } }
```

> Nota de transporte: `fastapi-mcp==0.4.0` propaga el `status_code` HTTP
> original y serializa el `detail` como texto JSON dentro de `content`; no
> implementa aún `isError` estricto por tool (ver Sección 7).

**Notas:** único endpoint que retorna el texto íntegro del documento (no
fragmentos/chunks).

---

### 4.4 `delete_document`

**Parámetros:** `document_id: str` (requerido, path param). Sin cuerpo.

**Respuesta** (`DeleteDocumentResponse`):

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `status` | `str` | `"completed"`. |
| `message` | `str` | Descripción legible de las capas afectadas. |
| `document_id` | `str` | Eco del documento eliminado. |
| `source_id` | `str` | Fuente de ingesta original. |
| `deleted_documents` | `int` | Siempre `1` en éxito. |
| `deleted_chunks` | `int` | Chunks eliminados del índice. |
| `deleted_staging_files` | `int` | Archivos físicos de staging podados. |
| `reindexed_sources` | `int` | Fuentes cuyo grafo se resincronizó. |
| `neo4j_nodes_deleted` | `int` | Nodos `Entity` huérfanos podados en Neo4j. |
| `created` | `bool` | **Siempre `false`** (mutación, no creación; contrato Hexa de idempotencia). |

**Errores:**

| HTTP | Body | Causa |
| --- | --- | --- |
| `404` | `{"error": "DOCS_NOT_FOUND", "message": "Document not found: {document_id}", "retryable": false}` | El `document_id` no existe. |

**Ejemplo `tools/call`:**

```json
{ "jsonrpc": "2.0", "id": 13, "method": "tools/call",
  "params": { "name": "delete_document", "arguments": { "document_id": "7f0a1c2b" } } }
```

```json
{ "jsonrpc": "2.0", "id": 13, "result": { "content": [{ "type": "text",
  "text": "{\"status\": \"completed\", \"message\": \"Document was deleted from persisted metadata, vector index, managed staging mirror, and Neo4j orphan cleanup.\", \"document_id\": \"7f0a1c2b\", \"source_id\": \"f0e1d2c3b4a5\", \"deleted_documents\": 1, \"deleted_chunks\": 3, \"deleted_staging_files\": 1, \"reindexed_sources\": 1, \"neo4j_nodes_deleted\": 2, \"created\": false}" }] } }
```

**Notas:** **destructivo e irreversible**. Un cliente MCP debe confirmar
explícitamente con el usuario final antes de invocar esta tool.

---

### 4.5 `replace_document_tags`

**Parámetros:** `document_id: str` (requerido, path) + cuerpo
`ReplaceDocumentTagsRequest`: `tags: list[str] = []` (reemplaza el set
**completo**, no suma tags existentes).

**Respuesta** (`ReplaceDocumentTagsResponse`): `status: str`, `message: str`,
`document_id: str`, `source_id: str`, `old_tags: list[str]`,
`new_tags: list[str]`, `created: bool` (**siempre `false`**).

**Errores:**

| HTTP | Body | Causa |
| --- | --- | --- |
| `404` | `{"error": "DOCS_NOT_FOUND", "message": "Document not found: {document_id}", "retryable": false}` | El `document_id` no existe. |

**Ejemplo `tools/call`:**

```json
{ "jsonrpc": "2.0", "id": 14, "method": "tools/call",
  "params": { "name": "replace_document_tags",
    "arguments": { "document_id": "7f0a1c2b", "tags": ["legal", "approved"] } } }
```

```json
{ "jsonrpc": "2.0", "id": 14, "result": { "content": [{ "type": "text",
  "text": "{\"status\": \"updated\", \"message\": \"Tags replaced for document.\", \"document_id\": \"7f0a1c2b\", \"source_id\": \"f0e1d2c3b4a5\", \"old_tags\": [\"finance\", \"urgent\"], \"new_tags\": [\"legal\", \"approved\"], \"created\": false}" }] } }
```

**Notas:** operación idempotente — invocarla dos veces con el mismo `tags`
produce el mismo resultado sin efectos secundarios adicionales.

---

### 4.6 `ingest_readiness`

**Parámetros:** ninguno.

**Respuesta** (`dict[str, Any]`):

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `ready` | `bool` | `true` si todos los checks críticos pasan. |
| `recommendation` | `"async" \| "sync"` | Modo de ingesta recomendado. |
| `use_rq` | `bool` | Si el modo distribuido (Redis/RQ) está activo. |
| `use_neo4j` | `bool` | Si el grafo está activo. |
| `checks` | `dict[str, dict]` | Ver detalle abajo. |

Cada entrada de `checks` (`runtime_store`, `lexical`, `chroma` siempre
presentes; `neo4j`, `redis`, `rq_worker` presentes según flags) tiene la
forma `{"ok": bool, "required": bool, "detail": str, "signal": str?}`.

**Errores:** ninguno (`200` siempre; diagnosticable vía el campo `ready`).

**Ejemplo `tools/call`:**

```json
{ "jsonrpc": "2.0", "id": 15, "method": "tools/call",
  "params": { "name": "ingest_readiness", "arguments": {} } }
```

```json
{ "jsonrpc": "2.0", "id": 15, "result": { "content": [{ "type": "text",
  "text": "{\"ready\": true, \"recommendation\": \"async\", \"use_rq\": true, \"use_neo4j\": true, \"checks\": {\"runtime_store\": {\"ok\": true, \"required\": true, \"detail\": \"reachable\"}, \"lexical\": {\"ok\": true, \"required\": true, \"detail\": \"indexed\"}, \"chroma\": {\"ok\": true, \"required\": true, \"detail\": \"heartbeat ok\"}, \"neo4j\": {\"ok\": true, \"required\": true, \"detail\": \"reachable\"}, \"redis\": {\"ok\": true, \"required\": true, \"detail\": \"reachable\"}, \"rq_worker\": {\"ok\": true, \"required\": true, \"detail\": \"listening\"}}}" }] } }
```

---

### 4.7 `ingest_files_json`

**Cuerpo** (`FilesIngestionJsonRequest`):

| Campo | Tipo | Default | Descripción |
| --- | --- | --- | --- |
| `files` | `list[UploadedFilePayload]` | requerido, mín. 1 elemento | Archivos a ingerir. |
| `source_type` | `str` | `"folder"` | Único tipo soportado actualmente. |
| `filters` | `dict[str, Any]` | `{}` | Filtros de scanner (opcional). |
| `tags` | `list[str]` | `[]` | Tags aplicados al lote completo. |

`UploadedFilePayload`: `filename: str` (mín. 1 char), `content_base64: str`
(mín. 1 char, contenido del archivo codificado en base64), `media_type: str | null`.

**Respuesta** (`dict[str, object]`, resultado de ingesta completada):

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `job_id` | `str` | Identificador del job (síncrono, ya completado). |
| `status` | `"completed" \| "failed"` | Estado final del pipeline. |
| `source_id` | `str` | Fuente de ingesta creada/reutilizada. |
| `created` | `bool` | `true` si **todo** el lote era nuevo; `false` si la deduplicación global por `title + content_type` reemplazó al menos un documento existente. |
| `documents` | `str` | Cantidad de documentos procesados. |
| `chunks` | `str` | Cantidad de chunks generados. |
| `steps` | `list[dict]` | Historial de etapas del pipeline (`load_documents`, `chunking`, `rebuild_indexes`, ...). |
| `progress_pct` | `float` | `100` en éxito. |
| `metrics` | `dict` | Estadísticas de carga/dedup/chunking. |
| `deduplication` | `dict` | Detalle de `incoming_batch` y `replaced_existing`. |

**Errores:**

| HTTP | Body | Causa |
| --- | --- | --- |
| `422` | `{"error": "DOCS_VALIDATION", "message": "<detalle>", "retryable": false}` | Payload inválido (`files` vacío, base64 corrupto, tamaño excesivo). |
| `503` | `{"error": "DOCS_UNAVAILABLE", "message": "<detalle>", "retryable": true}` | Fallo de runtime (provider de embeddings/LLM, Chroma, Postgres). |
| `500` | `{"error": "DOCS_UNAVAILABLE", "message": "<detalle>", "retryable": true}` | Excepción no esperada durante la ingesta. |

**Ejemplo `tools/call`:**

```json
{ "jsonrpc": "2.0", "id": 16, "method": "tools/call",
  "params": { "name": "ingest_files_json", "arguments": {
    "files": [{ "filename": "nota.txt", "content_base64": "aG9sYSBkZXNkZSBtY3A=" }],
    "tags": ["smoke"] } } }
```

```json
{ "jsonrpc": "2.0", "id": 16, "result": { "content": [{ "type": "text",
  "text": "{\"job_id\": \"b6a1...\", \"status\": \"completed\", \"source_id\": \"f0e1d2c3b4a5\", \"created\": true, \"documents\": \"1\", \"chunks\": \"1\", \"progress_pct\": 100, \"steps\": [...], \"metrics\": {...}, \"deduplication\": {\"incoming_batch\": {\"input_documents\": 1, \"kept_documents\": 1, \"skipped_documents\": 0}, \"replaced_existing\": {\"matched_documents\": 0, \"deleted_documents\": 0}}}" }] } }
```

**Notas:** llamada **síncrona** (espera a que complete la ingesta antes de
responder). Reingerir el mismo `filename`+contenido con el mismo
`title + content_type` produce `created: false` (reemplaza la versión
anterior en vez de duplicarla).

---

### 4.8 `ingest_files_json_async`

**Cuerpo:** idéntico a `ingest_files_json` (`FilesIngestionJsonRequest`).

**Respuesta** (`dict[str, str]`, inmediata):

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `job_id` | `str` | ID del job encolado; usar con `get_job` para hacer polling. |
| `status` | `str` | `"queued"`. |
| `message` | `str` | Describe el modo de ejecución (RQ distribuido o worker local en thread). |

**Errores:**

| HTTP | Body | Causa |
| --- | --- | --- |
| `422` | `{"error": "DOCS_VALIDATION", "message": "<detalle>", "retryable": false}` | Payload inválido. |
| `500` | `{"error": "DOCS_UNAVAILABLE", "message": "<detalle>", "retryable": true}` | Fallo al encolar el job. |

**Ejemplo `tools/call`:**

```json
{ "jsonrpc": "2.0", "id": 17, "method": "tools/call",
  "params": { "name": "ingest_files_json_async", "arguments": {
    "files": [{ "filename": "reporte.md", "content_base64": "IyBSZXBvcnRl" }] } } }
```

```json
{ "jsonrpc": "2.0", "id": 17, "result": { "content": [{ "type": "text",
  "text": "{\"job_id\": \"7c2e...\", \"status\": \"queued\", \"message\": \"Job encolado en RQ.\"}" }] } }
```

**Notas:** si `USE_RQ=true` pero Redis no está disponible, cae
automáticamente a un worker local en thread sin intervención del llamante.
El archivo decodificado se persiste temporalmente en Postgres
(`Tbl_Ingestion_Artifacts_Uploaded`) para rehidratación sin filesystem
compartido.

---

### 4.9 `get_job`

**Parámetros:** `job_id: str` (requerido, path param).

**Respuesta** (`dict[str, Any]`):

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `job_id` | `str` | Eco del identificador. |
| `status` | `"queued" \| "running" \| "completed" \| "failed"` | Estado actual. |
| `message` | `str` | Último mensaje de progreso. |
| `created_at` | `datetime` | Timestamp de creación. |
| `updated_at` | `datetime` | Timestamp de última actualización. |
| `steps` | `list[dict]` | Breadcrumbs de progreso (si aplica). |
| `progress_pct` | `float` | Porcentaje de avance (si aplica). |

**Errores:**

| HTTP | Body | Causa |
| --- | --- | --- |
| `404` | `{"error": "DOCS_NOT_FOUND", "message": "Job not found", "retryable": false}` | El `job_id` no existe (ni localmente ni en RQ). |

**Ejemplo `tools/call`:**

```json
{ "jsonrpc": "2.0", "id": 18, "method": "tools/call",
  "params": { "name": "get_job", "arguments": { "job_id": "7c2e..." } } }
```

```json
{ "jsonrpc": "2.0", "id": 18, "result": { "content": [{ "type": "text",
  "text": "{\"job_id\": \"7c2e...\", \"status\": \"completed\", \"message\": \"Indexed 1 docs and 1 chunks\", \"created_at\": \"2026-01-01T00:00:00+00:00\", \"updated_at\": \"2026-01-01T00:00:05+00:00\", \"steps\": [...], \"progress_pct\": 100}" }] } }
```

**Notas:** si `USE_RQ=true`, primero intenta resolver el estado desde Redis;
si la conexión falla, continúa con el estado local persistido (merge
automático de campos como `steps`/`progress_pct`).

---

### 4.10 `query`

**Cuerpo** (`QueryRequest`):

| Campo | Tipo | Default | Descripción |
| --- | --- | --- | --- |
| `question` | `str` | requerido | Pregunta en lenguaje natural. |
| `source_id` | `str \| null` | `null` | Acota la búsqueda a una fuente de ingesta. |
| `document_ids` | `list[str]` | `[]` | Acota la búsqueda a documentos específicos. |
| `hops` | `int \| null` | `null` (usa default runtime, típicamente `2`) | Profundidad de expansión de grafo. |
| `llm_provider` | `str \| null` | `null` (usa default runtime) | `"local"` \| `"openai"` \| `"gemini"` \| `"vertex"`/`"vertex_ai"`. **Anthropic no es provider activo.** |
| `force_fallback` | `bool` | `false` | Fuerza modo degradado (diagnóstico). |
| `include_llm_answer` | `bool` | `true` | `false` retorna solo evidencia recuperada, sin síntesis LLM. |

**Respuesta** (`QueryResponse`):

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `answer` | `str` | Respuesta sintetizada (o extractiva si `include_llm_answer=false`). |
| `citations` | `list[Evidence]` | Fragmentos recuperados con trazabilidad. |
| `graph_paths` | `list[GraphPath]` | Rutas multi-hop (si Neo4j habilitado). |
| `diagnostics` | `dict[str, Any]` | Flags efectivos, proveedor/modelo usados, `llm_error`, `timestamp`. |

`Evidence`: `chunk_id: str`, `document_id: str`, `score: float`,
`snippet: str`, `path_or_url: str`, `section_name: str`, `start_ref: int`,
`end_ref: int`.

`GraphPath`: `nodes: list[str]`, `relationships: list[str]`.

**Errores:**

| HTTP | Body | Causa |
| --- | --- | --- |
| `503` | `{"error": "DOCS_UNAVAILABLE", "message": "<detalle>", "retryable": true}` | Fallo runtime estricto (provider LLM/embeddings, refresh de índices). |

**Ejemplo `tools/call`:**

```json
{ "jsonrpc": "2.0", "id": 19, "method": "tools/call",
  "params": { "name": "query", "arguments": {
    "question": "¿Quién aprueba la política de finanzas?", "hops": 2 } } }
```

```json
{ "jsonrpc": "2.0", "id": 19, "result": { "content": [{ "type": "text",
  "text": "{\"answer\": \"...\", \"citations\": [{\"chunk_id\": \"c1\", \"document_id\": \"7f0a1c2b\", \"score\": 0.91, \"snippet\": \"...\", \"path_or_url\": \"sample_data/policy_finance.md\", \"section_name\": \"Aprobaciones\", \"start_ref\": 0, \"end_ref\": 120}], \"graph_paths\": [], \"diagnostics\": {\"retrieval_candidates\": 12, \"reranked\": 5, \"llm_invoked\": true, \"llm_provider_effective\": \"openai\"}}" }] } }
```

**Política anti-alucinación:** si no hay evidencia suficiente, `answer` es
exactamente `"No se encontro informacion en las fuentes indexadas."` — un
integrador nunca debe recibir contenido inventado.

---

### 4.11 `retrieval_only`

**Cuerpo y respuesta:** idénticos a `query` (mismo `QueryRequest` /
`QueryResponse`, mismos errores). Es un alias funcional publicado para
compatibilidad y diagnóstico — no aporta un shape distinto.

## 5. Prompts MCP (3)

Registrados vía `register_mcp_prompts()` (`src/coderag/api/mcp_prompts.py`),
antes de montar `/mcp`. Se invocan con `prompts/get`.

| Prompt | Argumentos | Propósito |
| --- | --- | --- |
| `query_guide` | `pregunta` (requerido) | Cómo usar `query`/`retrieval_only` para Hybrid RAG. |
| `ingest_workflow_guide` | ninguno | Flujo end-to-end para ingerir documentos vía MCP. |
| `document_catalog_guide` | ninguno | Flujo para administrar el catálogo ya ingerido (listar, leer, tags, borrar). |

### 5.1 `query_guide`

Enseña: cómo invocar `query`/`retrieval_only`, que ambas retornan `answer` +
`citations` + `graph_paths` + `diagnostics`, cómo acotar con `source_id`/
`document_ids`, los parámetros `include_llm_answer`/`force_fallback`/
`llm_provider`/`hops`, y refuerza la política anti-alucinación: sin evidencia
suficiente la respuesta debe ser exactamente
`"No se encontro informacion en las fuentes indexadas."`.

**Ejemplo `prompts/get`:**

```json
{ "jsonrpc": "2.0", "id": 20, "method": "prompts/get",
  "params": { "name": "query_guide", "arguments": { "pregunta": "¿Qué documentos hablan de gobernanza?" } } }
```

```json
{ "jsonrpc": "2.0", "id": 20, "result": { "description": "Guía para responder '¿Qué documentos hablan de gobernanza?' con las tools query/retrieval_only.",
  "messages": [{ "role": "user", "content": { "type": "text",
    "text": "Para responder la pregunta usa la tool `query` (Hybrid RAG con síntesis LLM) o `retrieval_only` (evidencia cruda sin LLM)... [contenido completo en src/coderag/api/mcp_prompts.py]" } }] } }
```

### 5.2 `ingest_workflow_guide`

Flujo en 6 pasos: (1) consultar `ingest_readiness` (o el resource
`rag://ingest/readiness`) antes de ingestas grandes; (2) codificar archivos en
base64 e invocar `ingest_files_json` (síncrono) o `ingest_files_json_async`;
(3) si es async, sondear `get_job` hasta `status` sea `completed`/`failed`;
(4) verificar con `list_documents` (o resource `rag://documents`); (5) leer
texto completo con `get_document_content`; (6) recordar que la deduplicación
por `title + content_type` hace que reingerir el mismo documento no cree
duplicados (`created: false`).

### 5.3 `document_catalog_guide`

Flujo en 6 pasos para administrar el catálogo: (1) listar con
`list_documents`/resource `rag://documents`, filtrando por `source_id`; (2)
revisar tags existentes con `list_document_tags` para reutilizar
convenciones; (3) leer contenido completo con `get_document_content`; (4)
reemplazar tags con `replace_document_tags` (idempotente); (5) eliminar con
`delete_document` (destructivo, confirmar antes); (6) fundamentar siempre en
el contenido devuelto, sin asumir documentos no vistos.

## 6. Resources MCP (8)

Registrados vía `register_mcp_resources()`
(`src/coderag/api/mcp_resources.py`), antes de montar `/mcp`. Se listan con
`resources/list` (+ `resources/templates/list` para el template) y se leen
con `resources/read`.

| URI / template | Tipo | mimeType | Contenido |
| --- | --- | --- | --- |
| `rag://guide/tools-overview` | estático | `text/markdown` | Las 11 tools y cuándo usar cada una. |
| `rag://guide/query-cookbook` | estático | `text/markdown` | Recetas de fraseo para acotar búsquedas, uso de `hops`/grafo, política anti-alucinación. |
| `rag://guide/parameters` | estático | `text/markdown` | Parámetros de `QueryRequest`/`FilesIngestionJsonRequest` con defaults. |
| `rag://guide/capabilities` | estático | `text/markdown` | Capacidades reales: retrieval híbrido, storage, dedup, proveedores LLM soportados (**sin Anthropic**). |
| `rag://guide/errors` | estático | `text/markdown` | Tabla de errores 404/422/503 y cómo recuperarse. |
| `rag://documents` | dinámico | `application/json` | Resultado en vivo de `GET /sources/documents` (mismo shape que `list_documents`). |
| `rag://ingest/readiness` | dinámico | `application/json` | Resultado en vivo de `GET /sources/ingest/readiness` (mismo shape que `ingest_readiness`). |
| `rag://documents/{document_id}` | template dinámico | `application/json` | Resultado en vivo de `GET /sources/documents/{document_id}/content` (mismo shape que `get_document_content`). |

Los resources dinámicos reutilizan el cliente HTTP ASGI interno de
`FastApiMCP` (mismas rutas REST, mismo proceso); si la llamada interna falla,
retornan un JSON de error legible (`{"error": "...", ...}`) en vez de
propagar una excepción de protocolo — siempre con HTTP `200` a nivel de
transporte MCP.

**Ejemplo `resources/read` (dinámico):**

```json
{ "jsonrpc": "2.0", "id": 21, "method": "resources/read",
  "params": { "uri": "rag://documents/7f0a1c2b" } }
```

```json
{ "jsonrpc": "2.0", "id": 21, "result": { "contents": [{
  "uri": "rag://documents/7f0a1c2b", "mimeType": "application/json",
  "text": "{\"document_id\": \"7f0a1c2b\", \"content\": \"# Política de finanzas...\", \"title\": \"policy_finance\", ...}" }] } }
```

**Ejemplo `resources/read` (estático):**

```json
{ "jsonrpc": "2.0", "id": 22, "method": "resources/read",
  "params": { "uri": "rag://guide/errors" } }
```

```json
{ "jsonrpc": "2.0", "id": 22, "result": { "contents": [{
  "uri": "rag://guide/errors", "mimeType": "text/markdown",
  "text": "# Contrato de errores\n\n| Código | HTTP | ... |\n..." }] } }
```

## 7. Códigos de error consolidados

### 7.1 Errores de autenticación (endpoint `/mcp` completo, no por tool)

| Código | HTTP | Body | Causa |
| --- | --- | --- | --- |
| `mcp_disabled` | `404` | `{"message": "El servidor MCP está deshabilitado.", "code": "mcp_disabled"}` | `MCP_ENABLED=false`. |
| `invalid_mcp_token` | `401` | `{"message": "Token inválido para el endpoint MCP.", "code": "invalid_mcp_token"}` | `MCP_API_TOKEN` configurado y el Bearer recibido no coincide (o falta). |

### 7.2 Errores de tools (`DOCS_*`)

Shape estándar: `{"error": "DOCS_{CODE}", "message": "<descripción>", "retryable": <bool>}`.

| Código | HTTP | Retryable | Causa | Tools donde aplica |
| --- | --- | --- | --- | --- |
| `DOCS_NOT_FOUND` | `404` | `false` | El recurso (documento o job) no existe. | `get_document_content`, `delete_document`, `replace_document_tags`, `get_job` |
| `DOCS_VALIDATION` | `422` | `false` | Payload inválido (archivos vacíos, base64 corrupto). | `ingest_files_json`, `ingest_files_json_async` |
| `DOCS_UNAVAILABLE` | `503` / `500` | `true` | Fallo de runtime: provider LLM/embeddings, storage, refresh de índices. | `query`, `retrieval_only`, `ingest_files_json`, `ingest_files_json_async` |
| `DOCS_CONFLICT` | — | — | Reservado, sin uso actual. | — |
| `DOCS_RATE_LIMITED` | — | — | Reservado, sin uso actual. | — |
| `DOCS_AUTH_FAILED` | — | — | Reservado, sin uso actual (la auth de `/mcp` usa `invalid_mcp_token`, no este código). | — |

> Nota de transporte MCP: `fastapi-mcp==0.4.0` no implementa `isError`
> estricto por tool; el `status_code` HTTP original se conserva y el body de
> error se serializa como texto JSON dentro de `content`/`result`. Un cliente
> integrador debe parsear el texto y verificar el campo `error` para detectar
> fallos, no solo el código de transporte.

## 8. Ejemplo de sesión MCP completa

Secuencia mínima para un cliente nuevo (ver script ejecutable equivalente en
[scripts/mcp_smoke.sh](../scripts/mcp_smoke.sh)):

1. `POST /mcp` `initialize` → responde con `mcp-session-id` en headers y
   `capabilities: {tools, prompts, resources}`.
2. `POST /mcp` `notifications/initialized` (con header `mcp-session-id`).
3. `POST /mcp` `tools/list` → devuelve las 11 tools con sus JSON Schemas de
   entrada derivados del OpenAPI.
4. `POST /mcp` `tools/call` con `name` + `arguments` de la tool elegida (ver
   Sección 4 para el shape exacto de cada una).

```bash
./scripts/mcp_smoke.sh http://127.0.0.1:8000 "$MCP_API_TOKEN"
```

El script verifica además `GET /health` y `GET /info` antes del handshake MCP.

## 9. Configuración relevante

| Env var | Default | Descripción |
| --- | --- | --- |
| `MCP_ENABLED` | `true` | Habilita el montaje de `/mcp`. |
| `MCP_API_TOKEN` | `""` (vacío) | Token Bearer (`Authorization: Bearer {MCP_API_TOKEN}`); si vacío, sin protección adicional. |
| `MCP_MOUNT_PATH` | `/mcp` | Ruta de montaje del servidor MCP. |
| `MCP_SERVER_NAME` | `documents-kdb-mcp` (código) / `docrag-mcp` (`.env.example`) | Nombre publicado en `/health` e `/info`. |
| `MCP_SERVER_DESCRIPTION` | Descripción genérica del servicio | Publicada sin autenticación en `/info`. |

Detalle completo de variables en [CONFIGURATION.md](CONFIGURATION.md).

## 10. Versionado

- `fastapi-mcp==0.4.0`, `mcp==1.28.1` (`requirements-runtime.txt`).
- Cambios rompientes de este contrato (nuevas tools, cambios de shape,
  cambios de auth) se documentan en [CHANGELOG.md](../CHANGELOG.md) bajo
  `[Unreleased]` con la marca **BREAKING** cuando corresponda.
