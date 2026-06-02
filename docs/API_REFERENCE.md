# API Reference

## Contract Note

Esta referencia documenta la API actual del proyecto. Durante el cutover pueden convivir aquí detalles
del comportamiento implementado hoy con el contrato objetivo aprobado para la arquitectura final.

Para decisiones de target runtime y alcance del cutover, la referencia autoritativa es
[docs/DESIGN_DECISIONS.md](DESIGN_DECISIONS.md).

En particular, el target aprobado establece que:

- El runtime final usa Postgres + Chroma remoto + Neo4j.
- La ingesta async de archivos locales debe terminar usando artifacts temporales en Postgres.
- El flujo multipart async ya persiste upload artifacts temporales en Postgres al momento de encolar, y los workers materializan esos archivos sólo al ejecutar el job sin depender de un shared staging volume.
- `path_or_url` ya se publica como origen logico estable para fuentes `folder`
  y multipart; no debe interpretarse como path absoluto o temporal del host.

## API docs entrypoints

Con el backend levantado con [src/main.py](../src/main.py), la API local expone:

- Base URL local: `http://127.0.0.1:8000`
- Base URL alternativa: `http://localhost:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

Nota: el proceso escucha en `0.0.0.0:8000`, por lo que desde otras maquinas
de la red puede consumirse usando la IP del host.

## Fuente principal de implementacion

- Capa HTTP (paths, metodos, codigos HTTP):
  [src/coderag/api/server.py](../src/coderag/api/server.py)
- Orquestacion de negocio de endpoints:
  [src/coderag/core/service.py](../src/coderag/core/service.py)
- Esquemas request/response (Pydantic):
  [src/coderag/core/models.py](../src/coderag/core/models.py)

## Resumen rapido de servicios

| Servicio HTTP | Metodo | Path | Handler FastAPI | Servicio interno | Schema request | Schema response |
| --- | --- | --- | --- | --- | --- | --- |
| Health | GET | `/health` | `health` | N/A | N/A | `{"status": "ok"}` |
| Readiness | GET | `/readiness` | `readiness` | checks runtime store + Chroma crítico | N/A | `{"status": "ready"}` |
| Ingestion sync | POST | `/sources/ingest` | `ingest_source` | `SERVICE.ingest` | `IngestionRequest` | `dict` (estado de job + metricas) |
| Ingestion uploads batch sync | POST | `/sources/ingest/files` | `ingest_source_files` | `UploadIngestionAdapter` + `SERVICE.ingest` | `multipart/form-data` (`files`, `source_type?`, `filters?`, `tags?`) | `dict` (estado de job + metricas) |
| Ingestion uploads batch async | POST | `/sources/ingest/files/async` | `ingest_source_files_async` | `UploadIngestionAdapter` + `enqueue_ingest_job/enqueue_local_ingest_job` | `multipart/form-data` (`files`, `source_type?`, `filters?`, `tags?`) | `{"job_id", "status", "message"}` |
| Ingestion async | POST | `/sources/ingest/async` | `ingest_source_async` | `enqueue_ingest_job` o `enqueue_local_ingest_job` | `IngestionRequest` | `{"job_id", "status", "message"}` |
| Ingestion readiness | GET | `/sources/ingest/readiness` | `ingest_readiness` | checks runtime + Chroma + Neo4j + Redis + RQ worker | N/A | `{"ready", "recommendation", "checks"}` |
| Documents catalog | GET | `/sources/documents` | `list_documents` | `SERVICE.list_documents` | `source_id?`, `tags?` | `{"source_id", "tags", "count", "documents"}` |
| Document content | GET | `/sources/documents/{document_id}/content` | `get_document_content` | `SERVICE.get_document_content` | `document_id` en path | `DocumentContentResponse` |
| Document tags catalog | GET | `/sources/tags` | `list_document_tags` | `SERVICE.list_document_tags` | `source_id?` | `ListDocumentTagsResponse` |
| Replace document tags | PUT | `/sources/documents/{document_id}/tags` | `replace_document_tags` | `SERVICE.replace_document_tags` | `document_id` en path + `ReplaceDocumentTagsRequest` | `ReplaceDocumentTagsResponse` |
| Delete document | DELETE | `/sources/documents/{document_id}` | `delete_document` | `SERVICE.delete_document` | `document_id` en path | `DeleteDocumentResponse` |
| Job status | GET | `/jobs/{job_id}` | `get_job` | `SERVICE.get_job` y fallback `get_rq_job_status` | `job_id` en path | `dict` (estado + timeline) |
| Full reset | POST | `/admin/reset` | `reset_sources` | `SERVICE.reset_all` | `X-Admin-Reset-Token` header + `AdminResetRequest` | `ResetAllResponse` |
| Query | POST | `/query` | `query` | `SERVICE.query` | `QueryRequest` | `QueryResponse` |
| Retrieval alias | POST | `/query/retrieval` | `retrieval_only` | `SERVICE.query` | `QueryRequest` | `QueryResponse` |
| TDM ingest | POST | `/tdm/ingest` | `ingest_tdm` | `SERVICE.ingest_tdm_assets` | `IngestionRequest` | `dict` (resumen TDM) |
| TDM query | POST | `/tdm/query` | `query_tdm` | `SERVICE.query_tdm` | `TdmQueryRequest` | `TdmQueryResponse` |
| TDM service catalog | GET | `/tdm/catalog/services/{service_name}` | `tdm_service_catalog` | `SERVICE.get_tdm_service_catalog` | `service_name` + `source_id?` | `dict` |
| TDM table catalog | GET | `/tdm/catalog/tables/{table_name}` | `tdm_table_catalog` | `SERVICE.get_tdm_table_catalog` | `table_name` + `source_id?` | `dict` |
| TDM virtualization preview | POST | `/tdm/virtualization/preview` | `preview_tdm_virtualization` | `SERVICE.preview_tdm_virtualization` | `TdmQueryRequest` | `dict` |
| TDM synthetic profile | GET | `/tdm/synthetic/profile/{table_name}` | `tdm_synthetic_profile` | `SERVICE.get_tdm_synthetic_profile` | `table_name` + `source_id?` + `target_rows?` | `dict` |

## Esquemas principales

### IngestionRequest

```json
{
  "source": {
    "source_type": "folder",
    "source_url": null,
    "base_url": null,
    "token": null,
    "local_path": "sample_data",
    "artifact_id": null,
    "filters": {},
    "tags": ["finance", "urgent"]
  }
}
```

Notas de contrato:

- `source.artifact_id` es opcional y hoy se usa para enlazar uploads async con artifacts temporales persistidos en Postgres durante el cutover.
- Los clientes JSON existentes no necesitan enviarlo; cuando aplica, el backend lo inyecta en los flujos multipart async.

### QueryRequest

```json
{
  "question": "Who works on Project Atlas?",
  "source_id": null,
  "document_ids": [],
  "hops": 2,
  "llm_provider": "openai",
  "force_fallback": false,
  "include_llm_answer": true
}
```

### QueryResponse (shape)

```json
{
  "answer": "...",
  "citations": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "score": 0.0,
      "snippet": "...",
      "path_or_url": "...",
      "section_name": "...",
      "start_ref": 0,
      "end_ref": 0
    }
  ],
  "graph_paths": [
    {
      "nodes": ["..."],
      "relationships": ["RELATES_TO"]
    }
  ],
  "diagnostics": {
    "retrieval_candidates": 0,
    "reranked": 0,
    "retrieval_unique_documents": 0,
    "reranked_unique_documents": 0,
    "graph_paths": 0,
    "requested_mode": "with_llm",
    "effective_mode": "with_llm",
    "llm_invoked": true,
    "llm_provider": "openai",
    "llm_provider_effective": "openai",
    "llm_model_effective": "gpt-4.1-mini",
    "llm_error": null,
    "llm_context_includes_graph": true,
    "embedding_provider": "openai",
    "embedding_model": "text-embedding-3-small",
    "llm_fallback_forced": false,
    "timestamp": "2026-01-01T00:00:00+00:00"
  }
}
```

## Endpoints en detalle

## POST /admin/reset

Ruta canonica para reset destructivo del estado de ingesta.

Request:

- Header obligatorio: `X-Admin-Reset-Token`
- Body obligatorio: `AdminResetRequest`

```json
{
  "confirm": true,
  "confirmation_phrase": "RESET ALL DATA"
}
```

Comportamiento:

- Borra documentos, chunks y jobs persistidos.
- Limpia el mirror de staging local y reinicia indices runtime.
- Elimina relaciones gestionadas de grafo y metadatos TDM persistidos.

Codigos comunes:

- `200`: reset completado.
- `403`: token administrativo faltante o invalido.
- `404`: endpoint administrativo deshabilitado.
- `422`: payload de confirmacion invalido.

## GET /health

Valida que el servicio este en ejecucion.

Response:

```json
{
  "status": "ok"
}
```

Codigos comunes:

- `200`: servicio disponible.

## GET /readiness

Valida que el proceso este listo para recibir trafico y que el estado de
runtime principal sea accesible.

Cuando Chroma corre en remoto, el detalle operativo del fallo incluye al
menos `target`, `auth`, `signal` y una `hint` corta para diagnostico.

Response:

```json
{
  "status": "ready"
}
```

Codigos comunes:

- `200`: servicio listo para trafico.
- `503`: servicio levantado pero no listo para atender peticiones.

## POST /sources/ingest

Ejecuta pipeline de ingesta e indexacion en modo sincrono.

Notas de contrato:

- `source.tags` es opcional y acepta una lista simple de strings.
- Las tags se persisten por documento dentro del lote ingerido.
- Este cambio no modifica el request schema de `/query` ni `/query/retrieval`.

## DELETE /sources/documents/{document_id}

Elimina un documento persistido puntual sin ejecutar una nueva ingesta.

Comportamiento:

- Elimina la fila de documento y sus chunks en SQLite.
- Elimina los vectores asociados en Chroma usando `document_id`.
- Si el archivo persistido apuntaba al mirror de staging bajo `DATA_DIR`,
  intenta borrar tambien la copia fisica y podar carpetas vacias.
- Resincroniza el grafo gestionado para el `source_id` afectado.
- Tras la resincronizacion, elimina nodos `Entity` huerfanos en Neo4j para
  evitar residuos de documentos ya borrados.
- Reconstruye el corpus lexico para que la consulta refleje el borrado inmediatamente.

Response (ejemplo exitoso):

```json
{
  "status": "completed",
  "message": "Document was deleted from persisted metadata, vector index, managed staging mirror, and Neo4j orphan cleanup.",
  "document_id": "abc123",
  "source_id": "f0e1d2c3b4a5",
  "deleted_documents": 1,
  "deleted_chunks": 3,
  "deleted_staging_files": 1,
  "reindexed_sources": 1,
  "neo4j_nodes_deleted": 2
}
```

Codigos comunes:

- `200`: documento eliminado.
- `404`: no existe documento persistido con ese `document_id`.

Comportamiento adicional:

- Antes de persistir cada lote, el servicio busca documentos ya ingestados que
  coincidan globalmente por `title + content_type`.
- Si el lote actual contiene duplicados con esa misma clave, conserva solo una
  version antes de tocar almacenamiento persistente.
- Si encuentra coincidencias, elimina la version previa de SQLite, Chroma y del
  mirror local legacy en `storage/ingestion_staging` cuando el archivo
  reemplazado provenia de un path staged antiguo.
- Si la coincidencia pertenecia a otro `source_id`, el grafo gestionado de esa
  fuente se reconstruye para evitar duplicados residuales.

Request:

```json
{
  "source": {
    "source_type": "folder",
    "local_path": "sample_data"
  }
}
```

Response (ejemplo exitoso):

```json
{
  "job_id": "abc123",
  "status": "completed",
  "source_id": "f0e1d2c3b4a5",
  "documents": "2",
  "chunks": "5",
  "progress_pct": 100,
  "steps": [
    {
      "name": "load_documents",
      "status": "ok",
      "elapsed_hhmmss": "00:00:01",
      "progress_pct": 30,
      "details": {
        "discovered_files": 2,
        "parsed_documents": 2
      }
    }
  ],
  "metrics": {
    "elapsed_hhmmss": "00:00:34",
    "discovered_files": 2,
    "parsed_documents": 2,
    "skipped_empty": 0,
    "incoming_duplicates_skipped": 0,
    "existing_duplicates_replaced": 1,
    "staging_files_deleted": 1
  },
  "deduplication": {
    "incoming_batch": {
      "input_documents": 2,
      "kept_documents": 2,
      "skipped_documents": 0,
      "resolution": "keep_last_by_sorted_path"
    },
    "replaced_existing": {
      "matched_documents": 1,
      "deleted_documents": 1,
      "deleted_chunks": 3,
      "deleted_staging_files": 1,
      "reindexed_sources": 1
    }
  }
}
```

Codigos comunes:

- `200`: ingesta terminada (tambien puede retornar `status=failed` de negocio).
- `503`: runtime estricto no disponible (por ejemplo, Chroma/provider).

## POST /sources/ingest/files

Ejecuta ingesta sincrona a partir de varios archivos subidos por
`multipart/form-data` en un solo lote.

Campos del formulario:

- `files` (requerido): una o mas partes de archivo con el mismo nombre de campo.
- `source_type` (opcional): actualmente solo acepta `folder`.
- `filters` (opcional): texto JSON con objeto de filtros.
- `tags` (opcional): CSV (`finance,urgent`) o JSON array (`["finance","urgent"]`).

Comportamiento:

- El backend stagea todos los archivos en un solo directorio temporal.
- La ingesta usa el mismo pipeline `folder` sobre ese staging de lote.
- Para un solo archivo, tambien se usa esta misma ruta con el campo `files`.

Extensiones soportadas en `files`:

- `.md`, `.txt`, `.html`, `.htm`, `.pdf`, `.docx`, `.doc`, `.pptx`, `.xlsx`

Ejemplo `curl` para un solo archivo:

```bash
curl -X POST http://127.0.0.1:8000/sources/ingest/files \
  -F "files=@sample_data/engineering.md" \
  -F "source_type=folder" \
  -F 'filters={"domain":"qa"}' \
  -F "tags=finance,urgent"
```

Ejemplo `curl`:

```bash
curl -X POST http://127.0.0.1:8000/sources/ingest/files \
  -F "files=@sample_data/engineering.md" \
  -F "files=@sample_data/policy_finance.md" \
  -F "source_type=folder" \
  -F 'filters={"domain":"qa"}' \
  -F "tags=finance,urgent"
```

Codigos comunes:

- `200`: ingesta terminada (tambien puede retornar `status=failed` de negocio).
- `422`: formulario invalido, extension no soportada o `filters` no parseable.
- `500`: excepcion no controlada con payload de diagnostico estructurado.
- `503`: runtime estricto no disponible (por ejemplo, Chroma/provider).

## POST /sources/ingest/files/async

Encola una ingesta asincrona a partir de varios archivos subidos por
`multipart/form-data` en un solo lote.

Campos del formulario:

- `files` (requerido): una o mas partes de archivo con el mismo nombre de campo.
- `source_type` (opcional): actualmente solo acepta `folder`.
- `filters` (opcional): texto JSON con objeto de filtros.
- `tags` (opcional): CSV (`finance,urgent`) o JSON array (`["finance","urgent"]`).

Comportamiento segun modo async:

- Con `USE_RQ=false`: crea worker local en background y encola el job del lote.
- Con `USE_RQ=true`: persiste artifacts temporales en Postgres y el worker
  rehidrata el lote sin requerir staging compartido.

Para un solo archivo, tambien se usa esta misma ruta con el campo `files`.

Ejemplo `curl` para un solo archivo:

```bash
curl -X POST http://127.0.0.1:8000/sources/ingest/files/async \
  -F "files=@sample_data/engineering.md" \
  -F "source_type=folder" \
  -F 'filters={"domain":"qa"}' \
  -F "tags=finance,urgent"
```

Ejemplo `curl`:

```bash
curl -X POST http://127.0.0.1:8000/sources/ingest/files/async \
  -F "files=@sample_data/engineering.md" \
  -F "files=@sample_data/policy_finance.md" \
  -F "source_type=folder" \
  -F 'filters={"domain":"qa"}' \
  -F "tags=finance,urgent"
```

Response (shape):

```json
{
  "job_id": "job-id",
  "status": "queued",
  "message": "Upload ingestion job enqueued"
}
```

Codigos comunes:

- `200`: job aceptado.
- `422`: formulario invalido, extension no soportada o `filters` no parseable.
- `500`: error al encolar o iniciar worker.

## POST /sources/ingest/async

Encola una ingesta asincrona y retorna `job_id` para polling.

- Con `USE_RQ=true`: encola en Redis + RQ.
- Con `USE_RQ=false`: crea worker local en background dentro de API.

Response:

```json
{
  "job_id": "job-id",
  "status": "queued",
  "message": "Ingestion job enqueued"
}
```

Variaciones de `message`:

- `Ingestion job enqueued` (modo RQ)
- `Ingestion job started (local async worker)` (modo local async)

Codigos comunes:

- `200`: job aceptado.
- `500`: error al encolar o iniciar worker.

## GET /jobs/{job_id}

Consulta el estado de un job de ingesta.

Response (shape):

```json
{
  "job_id": "abc123",
  "status": "running",
  "message": "65% | persist_chunks",
  "progress_pct": 65,
  "steps": [],
  "created_at": "2026-03-27T20:06:53.082744+00:00",
  "updated_at": "2026-03-27T20:06:54.122108+00:00"
}
```

Codigos comunes:

- `200`: job encontrado.
- `404`: job inexistente.

## GET /sources/ingest/readiness

Expone readiness operativo para decidir entre ingesta `async` o `sync`.

El check de `chroma` informa el destino remoto, modo de auth, coleccion
gestionada, espacio HNSW detectado cuando existe, y una senal operativa
como `chroma_auth_failed`, `chroma_timeout`, `chroma_dns_failed` o
`chroma_hnsw_space_mismatch`.

El check de `lexical` informa el destino Postgres configurado, el backend
activo, el idioma FTS y un snapshot ligero del corpus (`indexed`,
`corpus_rows`, `document_count`, `source_count`) para distinguir entre un
backend reachable y un corpus aun vacio durante cutover o reindexacion.

Ademas de `detail`, el payload de `checks.chroma` expone campos
estructurados como `signal`, `mode`, `target`,
`auth_mode`, `collection`, `collections_count`, `heartbeat_ok`,
`hnsw_space` y `expected_hnsw_space` cuando aplican.

Ademas de `detail`, el payload de `checks.lexical` expone campos
estructurados como `signal`, `backend`, `fts_language`, `target`,
`indexed`, `corpus_rows`, `document_count` y `source_count`.

Response (shape):

```json
{
  "ready": true,
  "recommendation": "async",
  "use_rq": true,
  "use_neo4j": true,
  "checks": {
    "runtime_store": {
      "required": true,
      "ok": true,
      "detail": "metadata store reachable"
    },
    "lexical": {
      "required": true,
      "ok": true,
      "detail": "lexical backend reachable backend=lexical fts_language=english target=127.0.0.1:5432/coderag_docs indexed=true corpus_rows=7 documents=3 sources=2",
      "signal": "lexical_ready",
      "backend": "lexical",
      "fts_language": "english",
      "target": "127.0.0.1:5432/coderag_docs",
      "indexed": true,
      "corpus_rows": 7,
      "document_count": 3,
      "source_count": 2
    },
    "chroma": {
      "required": true,
      "ok": true,
      "detail": "remote chroma reachable target=chroma.internal:9000 auth=bearer collections=2 collection=coderag_chunks hnsw=cosine",
      "signal": "chroma_ready",
      "mode": "remote",
      "target": "chroma.internal:9000",
      "auth_mode": "bearer",
      "collections_count": 2,
      "collection": "coderag_chunks",
      "heartbeat_ok": true,
      "hnsw_space": "cosine",
      "expected_hnsw_space": "cosine"
    },
    "neo4j": {
      "required": true,
      "ok": true,
      "detail": "neo4j reachable"
    },
    "redis": {
      "required": true,
      "ok": true,
      "detail": "redis reachable"
    },
    "rq_worker": {
      "required": true,
      "ok": true,
      "detail": "workers=1"
    }
  }
}
```

## POST /admin/reset Details

Borra repositorios de ingesta y deja el sistema listo para primera ingesta.

Incluye:

- documentos/chunks/jobs en SQLite
- metadatos TDM aditivos en SQLite
- reset de indices en memoria
- limpieza condicional de staging espejo local legacy en
  `DATA_DIR/ingestion_staging` cuando existen documentos historicos staged
- limpieza de relaciones administradas y nodos huerfanos en Neo4j

Request:

- Header obligatorio: `X-Admin-Reset-Token`
- Body obligatorio:

```json
{
  "confirm": true,
  "confirmation_phrase": "RESET ALL DATA"
}
```

Response:

```json
{
  "status": "completed",
  "message": "All repositories were cleared, indexes were reset, and 3 staging mirror entries were removed.",
  "deleted_documents": 19,
  "deleted_chunks": 961,
  "deleted_jobs": 10,
  "neo4j_enabled": true,
  "neo4j_edges_deleted": 204
}
```

Codigos comunes:

- `200`: reset ejecutado.
- `403`: token administrativo faltante o invalido.
- `404`: endpoint administrativo deshabilitado.
- `422`: payload de confirmacion invalido.

## POST /query

Ejecuta retrieval hibrido, expansion de grafo y respuesta con evidencia.

Request:

```json
{
  "question": "Who works on Project Atlas?",
  "source_id": null,
  "document_ids": [],
  "hops": 2,
  "llm_provider": "openai",
  "force_fallback": false,
  "include_llm_answer": true
}
```

Notas operativas:

- `llm_provider` acepta `local`, `openai`, `gemini`, `vertex` y alias `vertex_ai`.
- Para `llm_provider=vertex`, el runtime exige
  `VERTEX_SERVICE_ACCOUNT_JSON_B64` y `VERTEX_PROJECT_ID`.
- Las llamadas Vertex incluyen labels de trazabilidad configurados por
  `VERTEX_LABEL_*`.
- `include_llm_answer=false` ejecuta retrieval+grafo sin invocar LLM.
- `force_fallback=true` fuerza respuesta extractiva local.
- Si `source_id` existe, retrieval y expansion de grafo se restringen a esa fuente.
- Si `document_ids` contiene uno o mas ids, retrieval se restringe a esos
  documentos; puede combinarse con `source_id` para acotar a una ingesta y un
  subconjunto de archivos concretos.

## GET /sources/documents

Retorna metadata liviana de documentos ya ingestados para poblar selectores UI
o diagnostico operativo.

Query params opcionales:

- `source_id`: limita el catalogo a una fuente/lote de ingesta.
- `tags`: filtra por una o mas tags usando CSV con semantica OR.

Response shape:

```json
{
  "source_id": "abc123def456",
  "tags": ["finance"],
  "count": 2,
  "documents": [
    {
      "document_id": "7f0a...",
      "source_id": "abc123def456",
      "title": "engineering",
      "path_or_url": "sample_data/engineering.md",
      "content_type": "md",
      "updated_at": "2026-04-23T15:00:00+00:00",
      "tags": ["finance", "urgent"]
    }
  ]
}
```

Nota: `path_or_url` representa el origen logico estable que se usa en catalogo,
evidencias y deduplicacion visible. Para carpetas locales se deriva desde la
raiz configurada; para uploads multipart se preserva la ruta relativa enviada
por el cliente cuando aplica.

Ejemplo:

```bash
curl "http://127.0.0.1:8000/sources/documents?source_id=abc123def456&tags=finance,urgent"
```

Codigos comunes:

- `200`: respuesta generada.
- `503`: falla de runtime estricto (provider/embedding/index refresh).

## GET /sources/documents/{document_id}/content

Retorna el contenido textual completo persistido para un documento ya
ingestado.

Path params:

- `document_id`: identificador persistido del documento.

Response shape:

```json
{
  "document_id": "7f0a...",
  "source_id": "abc123def456",
  "title": "engineering",
  "content": "# Engineering\n\nProject Atlas uses Budget FY26-Platform.",
  "path_or_url": "sample_data/engineering.md",
  "content_type": "md",
  "updated_at": "2026-04-23T15:00:00+00:00",
  "tags": ["finance", "urgent"]
}
```

Notas operativas:

- La fuente de verdad de este endpoint es el contenido textual persistido en
  Postgres (`documents.content`).
- Este endpoint no reconstruye el documento desde chunks.
- Este endpoint no devuelve el archivo fuente raw byte a byte; devuelve el
  texto que quedo persistido por la ingesta.

Ejemplo:

```bash
curl http://127.0.0.1:8000/sources/documents/7f0a/content
```

Codigos comunes:

- `200`: documento encontrado.
- `404`: no existe documento persistido con ese `document_id`.

## GET /sources/tags

Retorna la lista unica de tags actualmente presentes en documentos ya
persistidos.

Query params opcionales:

- `source_id`: limita la agregacion a una fuente/lote de ingesta.

Response shape:

```json
{
  "source_id": "abc123def456",
  "count": 2,
  "tags": ["finance", "urgent"],
  "items": [
    {"tag": "finance", "document_count": 3},
    {"tag": "urgent", "document_count": 1}
  ]
}
```

`tags` mantiene la lista unica ordenada para compatibilidad. `items` expone
las facetas visibles con el total de documentos persistidos por tag.

Ejemplo:

```bash
curl "http://127.0.0.1:8000/sources/tags?source_id=abc123def456"
```

Codigos comunes:

- `200`: respuesta generada.

## PUT /sources/documents/{document_id}/tags

Reemplaza completamente las tags persistidas para un documento dado.

Request:

```json
{
  "tags": ["legal", "approved"]
}
```

Response shape:

```json
{
  "status": "updated",
  "message": "Tags replaced for document.",
  "document_id": "7f0a...",
  "source_id": "abc123def456",
  "old_tags": ["finance", "urgent"],
  "new_tags": ["legal", "approved"]
}
```

Ejemplo:

```bash
curl -X PUT http://127.0.0.1:8000/sources/documents/7f0a/tags \
  -H "Content-Type: application/json" \
  -d '{"tags": ["legal", "approved"]}'
```

Codigos comunes:

- `200`: tags reemplazadas.
- `404`: no existe documento persistido con ese `document_id`.

## POST /query/retrieval

Alias funcional de `/query` para diagnostico y compatibilidad.

- Usa el mismo request schema (`QueryRequest`).
- Retorna el mismo response schema (`QueryResponse`).

## Referencias cruzadas utiles

- Arquitectura general: [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- Configuracion de providers y runtime: [docs/CONFIGURATION.md](CONFIGURATION.md)
- Arranque local: [docs/INSTALLATION.md](INSTALLATION.md)

## Endpoints TDM (aditivos)

Los endpoints `/tdm/*` son opt-in y se exponen solo con `ENABLE_TDM=true`.
Con `ENABLE_TDM=false` responden `404` por diseno para mantener
compatibilidad estricta en despliegues existentes.

### POST /tdm/ingest

Ingesta catalogo TDM desde fuentes tecnicas (`tdm_folder`).

Request (ejemplo):

```json
{
  "source": {
    "source_type": "tdm_folder",
    "local_path": "sample_data",
    "filters": {}
  }
}
```

### POST /tdm/query

Consulta catalogo TDM para agentes (impacto, mapeos, pistas de masking).

Request (ejemplo):

```json
{
  "question": "que tablas usa billing-api",
  "source_id": null,
  "service_name": "billing-api",
  "table_name": null,
  "include_virtualization_preview": false
}
```

### GET /tdm/catalog/services/{service_name}

Retorna mapeos servicio-endpoint-tabla desde el catalogo TDM.

### GET /tdm/catalog/tables/{table_name}

Retorna metadata de tabla y columnas asociadas en el catalogo TDM.

### POST /tdm/virtualization/preview

Genera plantillas ligeras de virtualizacion a partir de mapeos TDM.

### GET /tdm/synthetic/profile/{table_name}

Construye y persiste un plan de perfil sintetico basado en metadata de tabla.

Parametros opcionales:

- `source_id`
- `target_rows` (default `1000`)
