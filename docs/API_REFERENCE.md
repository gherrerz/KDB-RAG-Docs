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
  "steps": [
    {
      "name": "folder_scan_completed",
      "status": "ok",
      "details": {
        "path": "sample_data",
        "discovered_files": 2
      }
    }
  ],
  "metrics": {
    "elapsed_ms": 34.72,
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
  "created_at": "2026-03-27T20:06:53.082744+00:00",
  "updated_at": "2026-03-27T20:06:54.122108+00:00"
}
```

Response (async/RQ completado):

```json
{
  "job_id": "rq-job-id",
  "status": "finished",
  "message": "completed",
  "source_id": "f0e1d2c3b4a5",
  "documents": "2",
  "chunks": "5"
}
```

## POST /sources/ingest/async

Encola una ingesta en Redis + RQ cuando `USE_RQ=true`.

Response:

```json
{
  "job_id": "rq-job-id",
  "status": "queued",
  "message": "Ingestion job enqueued"
}
```

Si `USE_RQ=false`, retorna `400` con `detail: "Async ingestion disabled. Set USE_RQ=true."`.

## POST /sources/reset

Borra completamente los repositorios de ingesta y deja el sistema listo para
una primera ingesta.

Alcance del borrado:

- metadata de documentos en SQLite
- chunks indexados para retrieval BM25/vector
- aristas de grafo en SQLite
- historial de jobs
- relaciones `RELATES_TO` en Neo4j (si `USE_NEO4J=true`)

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
  "force_fallback": false
}
```

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
- `embedding_provider`
- `embedding_model`
- `llm_fallback_forced`
- `timestamp`

## POST /query/retrieval

Alias funcional de `/query` para diagnostico y compatibilidad.
