# API Reference

## GET /health

Valida que el servicio este en ejecucion.

Response:

```json
{
  "status": "ok"
}
```

## POST /sources/ingest

Ejecuta pipeline de ingesta e indexacion.

Request:

```json
{
  "source": {
    "source_type": "folder",
    "local_path": "sample_data"
  }
}
```

Response:

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
      "name": "folder_scan_completed",
      "status": "ok",
      "elapsed_hhmmss": "00:00:00",
      "progress_pct": 12,
      "details": {
        "path": "sample_data",
        "discovered_files": 2
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

Nota: si no se encuentran documentos soportados, retorna `status=failed` con
detalle en `message` y trazas en `steps`.

Error estricto de runtime:

- Retorna `503` cuando `USE_CHROMA=false`, faltan credenciales del provider
  de embedding o falla la llamada al proveedor.

## GET /jobs/{id}

Consulta el estado de un job de ingesta.

Response (sync/local):

```json
{
  "job_id": "abc123",
  "status": "completed",
  "message": "Indexed 2 docs and 5 chunks",
  "progress_pct": 100,
  "steps": [
    {
      "ordinal": 1,
      "name": "folder_scan_completed",
      "status": "ok",
      "elapsed_hhmmss": "00:00:00",
      "details": {
        "path": "sample_data",
        "discovered_files": 2,
        "progress_pct": 10
      },
      "created_at": "2026-03-27T20:06:53.582744+00:00"
    }
  ],
  "created_at": "2026-03-27T20:06:53.082744+00:00",
  "updated_at": "2026-03-27T20:06:54.122108+00:00"
}
```

Notas:

- Mientras el job esta en `running`, `steps` va creciendo durante el polling.
- Cada paso contiene `elapsed_hhmmss` acumulado en formato `hh:mm:ss`.
- Tras `status=completed`, el siguiente `/query` refresca retrieval en API
  automaticamente (sin restart) cuando la ingesta corrio en worker RQ.
  El refresh recompone BM25 en memoria y reutiliza vectores persistidos en
  Chroma (sin reindexacion vectorial global en el proceso API).

Response (async/RQ completado):

```json
{
  "job_id": "rq-job-id",
  "status": "finished",
  "message": "completed",
  "source_id": "f0e1d2c3b4a5",
  "documents": "2",
  "chunks": "5",
  "progress_pct": 100,
  "steps": []
}
```

## POST /sources/ingest/async

Encola una ingesta asincrona y retorna `job_id` para polling.

- Si `USE_RQ=true`: usa Redis + RQ.
- Si `USE_RQ=false`: usa worker local en background dentro del API.

Response:

```json
{
  "job_id": "job-id",
  "status": "queued",
  "message": "Ingestion job enqueued"
}
```

## POST /sources/reset

Borra completamente los repositorios de ingesta y deja el sistema listo para
una primera ingesta.

Alcance del borrado:

- metadata de documentos en SQLite
- chunks indexados para retrieval BM25/vector
- aristas de grafo en SQLite
- historial de jobs
- relaciones `RELATES_TO` en Neo4j

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
  "message": "All repositories were cleared and indexes were reset.",
  "deleted_documents": 19,
  "deleted_chunks": 961,
  "deleted_graph_edges": 204,
  "deleted_jobs": 10,
  "neo4j_enabled": true,
  "neo4j_edges_deleted": 204
}
```

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

Notas:

- `llm_provider` acepta `local`, `openai`, `gemini` o `vertex`
  (`vertex_ai` tambien es valido como alias).
- `include_llm_answer=true` ejecuta retrieval+grafo y luego respuesta LLM.
- `include_llm_answer=false` ejecuta retrieval+grafo sin invocar LLM y retorna
  `answer=""`.
- En modo estricto (`include_llm_answer=true` y `force_fallback=false`), si
  falla el provider remoto de respuesta, el endpoint retorna `503`.

Error estricto de runtime:

- Retorna `503` cuando Chroma no esta disponible o cuando falla la generacion
  de embeddings con el proveedor configurado.

Response keys:

- `answer`
- `citations`
- `graph_paths`
- `diagnostics`

Campos relevantes en `diagnostics`:

- `retrieval_candidates`
- `reranked`
- `graph_paths`
- `llm_provider`
- `requested_mode`
- `effective_mode`
- `llm_invoked`
- `llm_provider_effective`
- `llm_model_effective`
- `llm_error`
- `embedding_provider`
- `embedding_model`
- `llm_fallback_forced`
- `timestamp`

Notas:

- `source_id` filtra retrieval BM25/vector a la fuente indicada.
- Si `source_id` no existe, `citations` puede ser vacio.

## POST /query/retrieval

Alias funcional de `/query` para diagnostico y compatibilidad.
