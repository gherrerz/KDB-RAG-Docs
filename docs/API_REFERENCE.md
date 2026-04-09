# API Reference

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
| Readiness | GET | `/readiness` | `readiness` | `SERVICE.store.get_index_version` | N/A | `{"status": "ready"}` |
| Ingestion sync | POST | `/sources/ingest` | `ingest_source` | `SERVICE.ingest` | `IngestionRequest` | `dict` (estado de job + metricas) |
| Ingestion async | POST | `/sources/ingest/async` | `ingest_source_async` | `enqueue_ingest_job` o `enqueue_local_ingest_job` | `IngestionRequest` | `{"job_id", "status", "message"}` |
| Ingestion readiness | GET | `/sources/ingest/readiness` | `ingest_readiness` | checks runtime + Neo4j + Redis + RQ worker | N/A | `{"ready", "recommendation", "checks"}` |
| Job status | GET | `/jobs/{job_id}` | `get_job` | `SERVICE.get_job` y fallback `get_rq_job_status` | `job_id` en path | `dict` (estado + timeline) |
| Full reset | POST | `/sources/reset` | `reset_sources` | `SERVICE.reset_all` | `ResetAllRequest` | `ResetAllResponse` |
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
    "filters": {}
  }
}
```

### ResetAllRequest

```json
{
  "confirm": true
}
```

### QueryRequest

```json
{
  "question": "Who works on Project Atlas?",
  "source_id": null,
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
    "skipped_empty": 0
  }
}
```

Codigos comunes:

- `200`: ingesta terminada (tambien puede retornar `status=failed` de negocio).
- `503`: runtime estricto no disponible (por ejemplo, Chroma/provider).

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

## POST /sources/reset

Borra repositorios de ingesta y deja el sistema listo para primera ingesta.

Incluye:

- documentos/chunks/aristas/jobs en SQLite
- reset de indices en memoria
- limpieza de staging espejo local en `storage/ingestion_staging`
- limpieza de relaciones de grafo en Neo4j

Request:

```json
{
  "confirm": true
}
```

Response:

```json
{
  "status": "completed",
  "message": "All repositories were cleared, indexes were reset, and 3 staging mirror entries were removed.",
  "deleted_documents": 19,
  "deleted_chunks": 961,
  "deleted_graph_edges": 204,
  "deleted_jobs": 10,
  "neo4j_enabled": true,
  "neo4j_edges_deleted": 204
}
```

Codigos comunes:

- `200`: reset ejecutado.
- `400`: falta confirmacion (`confirm=false`).

## POST /query

Ejecuta retrieval hibrido, expansion de grafo y respuesta con evidencia.

Request:

```json
{
  "question": "Who works on Project Atlas?",
  "source_id": null,
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

Codigos comunes:

- `200`: respuesta generada.
- `503`: falla de runtime estricto (provider/embedding/index refresh).

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
