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
  "chunks": "5"
}
```

## GET /jobs/{id}

Consulta el estado de un job de ingesta.

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
  "llm_provider": "local",
  "force_fallback": false
}
```

Response keys:

- `answer`
- `citations`
- `graph_paths`
- `diagnostics`

## POST /query/retrieval

Alias funcional de `/query` para diagnostico y compatibilidad.
