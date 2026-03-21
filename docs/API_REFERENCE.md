# API Reference

Fuente de verdad de la API HTTP.

- Implementacion base: coderag/api/server.py
- Modelos: coderag/core/models.py
- Servicios de consulta: coderag/api/query_service.py

## Base URL y OpenAPI

- Base URL local: http://127.0.0.1:8000
- OpenAPI JSON: GET /openapi.json
- Swagger UI: GET /docs
- ReDoc: GET /redoc

## Endpoints por journey

### Journey 1: Setup e ingesta

#### POST /repos/ingest

Inicia una ingesta asincrona de repositorio.

Request:

- provider (default: github)
- repo_url (required)
- token (optional)
- branch (default: main)
- commit (optional)
- embedding_provider (optional)
- embedding_model (optional)

Response:

- JobInfo con id, status, progress, logs, repo_id y error.

Errores:

- 503 preflight de storage fallido.

#### GET /jobs/{job_id}

Consulta estado y logs de ingesta.

Path params:

- job_id

Query params:

- logs_tail (default: 200, min: 0, max: 2000)

Response:

- JobInfo con logs acotados por logs_tail.

Errores:

- 404 job no encontrado.

#### GET /repos

Lista repo_id disponibles.

Response:

- RepoCatalogResponse { repo_ids: list[str] }

#### GET /repos/{repo_id}/status

Readiness por repositorio para consultas.

Path params:

- repo_id

Query params:

- requested_embedding_provider (optional)
- requested_embedding_model (optional)

Campos relevantes de respuesta:

- query_ready
- chroma_counts
- bm25_loaded
- graph_available
- embedding_compatible
- last_embedding_provider
- last_embedding_model
- warnings

### Journey 2: Query con LLM

#### POST /query

Ejecuta retrieval hibrido y sintetiza respuesta con LLM cuando aplica.

Request:

- repo_id (required)
- query (required)
- top_n (default: 60)
- top_k (default: 15)
- embedding_provider (optional)
- embedding_model (optional)
- llm_provider (optional)
- answer_model (optional)
- verifier_model (optional)

Response:

- QueryResponse { answer, citations, diagnostics }

Errores:

- 422 repo_not_ready o embedding_incompatible
- 503 preflight de storage fallido

### Journey 3: Query retrieval-only

#### POST /query/retrieval

Ejecuta retrieval hibrido sin sintesis LLM.

Request:

- repo_id (required)
- query (required)
- top_n (default: 60)
- top_k (default: 15)
- embedding_provider (optional)
- embedding_model (optional)
- include_context (default: false)

Response:

- RetrievalQueryResponse
  - mode
  - answer
  - chunks
  - citations
  - statistics
  - diagnostics
  - context (cuando include_context=true)

Notas:

- Puede entrar en modo literal deterministico para consultas de codigo exacto.
- En modo ambiguo, retorna salida segura sin chunks/citations.

#### POST /inventory/query

Consulta de inventario paginada y orientada a listados amplios.

Request:

- repo_id (required)
- query (required)
- page (default: 1)
- page_size (default: 80)

Response:

- InventoryQueryResponse con items, citations y diagnostics.

Errores:

- 503 preflight de storage fallido.

### Journey 4: Operaciones y administracion

#### GET /providers/models

Catalogo de modelos por provider.

Query params:

- provider (required): openai, anthropic, gemini, vertex_ai
- kind (required): embedding o llm
- force_refresh (optional, default: false)

Notas:

- source puede ser remote, cache o fallback.
- warning informa fallback de catalogo sin devolver error HTTP.

#### GET /health/storage

Reporte consolidado de salud de storage.

Response:

- StorageHealthResponse con ok, failed_components e items.

#### DELETE /repos/{repo_id}

Elimina un repositorio de todas las capas de almacenamiento.

Path params:

- repo_id

Response:

- RepoDeleteResponse con cleared, deleted_counts y warnings.

Errores:

- 404 repo inexistente
- 409 jobs activos del mismo repo
- 422 repo_id vacio
- 500 error inesperado

#### POST /admin/reset

Limpieza total de estado indexado.

Response:

- ResetResponse con recursos limpiados y warnings.

Errores:

- 409 hay jobs en ejecucion
- 500 error inesperado

## Tabla de mapping interno

| Metodo | Ruta | Servicio interno | Request | Response |
|---|---|---|---|---|
| POST | /repos/ingest | JobManager.create_ingest_job | RepoIngestRequest | JobInfo |
| GET | /jobs/{job_id} | JobManager.get_job | Path job_id + query logs_tail | JobInfo |
| POST | /query | run_query | QueryRequest | QueryResponse |
| POST | /query/retrieval | run_retrieval_query | RetrievalQueryRequest | RetrievalQueryResponse |
| POST | /inventory/query | run_inventory_query | InventoryQueryRequest | InventoryQueryResponse |
| GET | /repos | JobManager.list_repo_ids | N/A | RepoCatalogResponse |
| DELETE | /repos/{repo_id} | JobManager.delete_repo | Path repo_id | RepoDeleteResponse |
| GET | /providers/models | discover_models | Query provider/kind/force_refresh | ProviderModelCatalogResponse |
| GET | /repos/{repo_id}/status | get_repo_query_status | Path repo_id + query requested_embedding_* | RepoQueryStatusResponse |
| GET | /health/storage | run_storage_preflight | N/A | StorageHealthResponse |
| POST | /admin/reset | JobManager.reset_all_data | N/A | ResetResponse |

## Errores comunes

| Codigo | Endpoint | Causa |
|---|---|---|
| 404 | GET /jobs/{job_id} | Job inexistente |
| 404 | DELETE /repos/{repo_id} | Repo inexistente |
| 409 | DELETE /repos/{repo_id} | Jobs activos del repo |
| 409 | POST /admin/reset | Reset con jobs activos |
| 422 | POST /query | repo_not_ready o embedding_incompatible |
| 422 | POST /query/retrieval | repo_not_ready o embedding_incompatible |
| 422 | DELETE /repos/{repo_id} | repo_id vacio |
| 503 | /repos/ingest, /query, /query/retrieval, /inventory/query | preflight de storage |

## Ejemplos

Ejemplos ejecutables por journey:

- examples/python/ingest_and_poll.py
- examples/python/query_with_llm.py
- examples/python/query_retrieval_only.py
- examples/curl/
- examples/powershell/

## Ejemplos por endpoint

### POST /repos/ingest

Request:

```json
{
  "provider": "github",
  "repo_url": "https://github.com/macrozheng/mall.git",
  "branch": "main"
}
```

Response:

```json
{
  "id": "job-123",
  "status": "queued",
  "progress": 0.0,
  "logs": [],
  "repo_id": null,
  "error": null
}
```

### GET /jobs/{job_id}?logs_tail=200

Response:

```json
{
  "id": "job-123",
  "status": "running",
  "progress": 0.42,
  "logs": [
    "Clonando repositorio...",
    "Escaneando archivos..."
  ],
  "repo_id": null,
  "error": null
}
```

### POST /query

Request:

```json
{
  "repo_id": "mall",
  "query": "cuales son los controller del modulo mall-admin",
  "top_n": 60,
  "top_k": 15
}
```

Response:

```json
{
  "answer": "Se encontraron controllers en el modulo mall-admin...",
  "citations": [
    {
      "path": "mall-admin/src/main/java/.../AdminController.java",
      "start_line": 42,
      "end_line": 88,
      "score": 0.91,
      "reason": "hybrid_rag_match"
    }
  ],
  "diagnostics": {
    "retrieved": 60,
    "reranked": 15,
    "graph_nodes": 12,
    "fallback_reason": null
  }
}
```

### POST /query/retrieval

Request:

```json
{
  "repo_id": "mall",
  "query": "donde esta la configuracion de neo4j",
  "top_n": 60,
  "top_k": 15,
  "include_context": false
}
```

Response:

```json
{
  "mode": "retrieval_only",
  "answer": "Se encontraron archivos de configuracion de Neo4j...",
  "chunks": [
    {
      "id": "chunk-1",
      "path": "coderag/core/settings.py",
      "start_line": 10,
      "end_line": 40,
      "score": 0.88
    }
  ],
  "citations": [],
  "statistics": {
    "total_before_rerank": 60,
    "total_after_rerank": 15,
    "graph_nodes_count": 8
  },
  "diagnostics": {}
}
```

### GET /repos/{repo_id}/status

Response:

```json
{
  "repo_id": "mall",
  "listed_in_catalog": true,
  "query_ready": true,
  "chroma_counts": {
    "code_symbols": 1200,
    "code_files": 350,
    "code_modules": 18
  },
  "bm25_loaded": true,
  "graph_available": true,
  "warnings": []
}
```

### DELETE /repos/{repo_id}

Response:

```json
{
  "message": "Repositorio 'mall' eliminado",
  "repo_id": "mall",
  "cleared": ["chroma", "bm25", "neo4j", "workspace", "metadata"],
  "deleted_counts": {
    "chroma": 1568,
    "neo4j": 923
  },
  "warnings": []
}
```

## Ejemplos de errores operativos

### GET /jobs/{job_id} - 404

```json
{
  "detail": "Job no encontrado"
}
```

### POST /query - 422 (repo_not_ready)

```json
{
  "detail": {
    "message": "El repositorio no está listo para consultas. Reingesta el repositorio o revisa el estado de índices.",
    "code": "repo_not_ready",
    "repo_status": {
      "repo_id": "mall",
      "listed_in_catalog": true,
      "query_ready": false,
      "chroma_counts": {
        "code_symbols": 0,
        "code_files": 0,
        "code_modules": 0
      },
      "bm25_loaded": false,
      "graph_available": null,
      "warnings": [
        "No hay indice BM25 en memoria para repo 'mall'."
      ]
    }
  }
}
```

### POST /query - 422 (embedding_incompatible)

```json
{
  "detail": {
    "message": "El embedding seleccionado para consulta no es compatible con la última ingesta del repositorio. Reingesta con el mismo modelo/provider o limpia índices antes de consultar.",
    "code": "embedding_incompatible",
    "repo_status": {
      "repo_id": "mall",
      "query_ready": false,
      "embedding_compatible": false,
      "last_embedding_provider": "openai",
      "last_embedding_model": "text-embedding-3-large"
    }
  }
}
```

### POST /query - 503 (preflight)

```json
{
  "detail": {
    "message": "Preflight de storage falló antes de consulta.",
    "health": {
      "ok": false,
      "strict": true,
      "context": "query",
      "failed_components": ["neo4j"],
      "items": [
        {
          "name": "neo4j",
          "ok": false,
          "critical": true,
          "code": "neo4j_unreachable",
          "message": "No se pudo conectar a Neo4j"
        }
      ]
    }
  }
}
```

### DELETE /repos/{repo_id} - 409

```json
{
  "detail": "No se puede eliminar el repo 'mall' porque tiene jobs en ejecución"
}
```

### DELETE /repos/{repo_id} - 422

```json
{
  "detail": "repo_id no puede estar vacío"
}
```

### POST /admin/reset - 409

```json
{
  "detail": "No se puede limpiar mientras hay jobs en ejecución"
}
```

## Matriz de accion recomendada

| Error | Endpoint | Que significa | Accion recomendada |
|---|---|---|---|
| 404 | GET /jobs/{job_id} | El identificador de job no existe o expiró del contexto esperado. | Verifica el job_id devuelto por POST /repos/ingest y relanza la ingesta si fue descartado. |
| 422 repo_not_ready | POST /query | El repositorio no tiene indices listos para consulta. | Ejecuta GET /repos/{repo_id}/status, valida query_ready y reingesta el repo. |
| 422 embedding_incompatible | POST /query, POST /query/retrieval | El embedding de consulta no coincide con la ultima ingesta. | Usa provider/modelo de embedding compatible o limpia y reingesta con la configuracion deseada. |
| 503 preflight | POST /repos/ingest, POST /query, POST /query/retrieval, POST /inventory/query | Fallo de componentes criticos de storage (por ejemplo Neo4j/Chroma). | Revisa GET /health/storage, corrige el componente fallido y reintenta. |
| 409 | DELETE /repos/{repo_id} | Hay jobs activos para el mismo repositorio. | Espera a que terminen los jobs o cancela flujo operativo antes de eliminar. |
| 422 | DELETE /repos/{repo_id} | repo_id vacio tras normalizacion. | Envia un repo_id no vacio y sin espacios laterales. |
| 409 | POST /admin/reset | Hay jobs en ejecucion y no se permite limpieza total. | Espera fin de jobs activos y vuelve a ejecutar reset. |

Notas:

- Para diagnostico detallado de readiness: GET /repos/{repo_id}/status.
- Para diagnostico detallado de infraestructura: GET /health/storage.
