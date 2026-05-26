# Decommission de Graph Edges en Postgres

## Fase 1 - Alineacion de alcance y baseline

Fecha: 2026-05-26
Repositorio: KDB-RAG-Docs

## Objetivo

Confirmar alcance tecnico y compatibilidad de contrato antes de modificar comportamiento de persistencia de edges en Postgres, y dejar evidencia base reproducible para comparar en Fase 2.

## Alcance confirmado con evidencia

### 1) El query graph-path usa Neo4j en runtime

- La capa de query delega expansion de paths a GraphStore: [src/coderag/core/query_service.py](../../src/coderag/core/query_service.py#L179), [src/coderag/core/query_service.py](../../src/coderag/core/query_service.py#L186).
- GraphStore es adaptador Neo4j y expande con RELATES_TO: [src/coderag/core/graph_store.py](../../src/coderag/core/graph_store.py#L1), [src/coderag/core/graph_store.py](../../src/coderag/core/graph_store.py#L456), [src/coderag/core/graph_store.py](../../src/coderag/core/graph_store.py#L486).

Conclusion: el consumo operativo de paths no depende de la tabla Tbl_Documents_GraphEdges en Postgres.

### 2) La ingesta y sync todavia escriben edges en Postgres

- En ingesta de contenido se construyen edges y se llama replace_graph_edges: [src/coderag/core/ingestion_service.py](../../src/coderag/core/ingestion_service.py#L197), [src/coderag/core/ingestion_service.py](../../src/coderag/core/ingestion_service.py#L201).
- En resincronizacion por source se repite la escritura: [src/coderag/core/service.py](../../src/coderag/core/service.py#L385), [src/coderag/core/service.py](../../src/coderag/core/service.py#L386).
- El store Postgres ejecuta insert masivo sobre graph_edges_table: [src/coderag/storage/postgres_document_chunk_store.py](../../src/coderag/storage/postgres_document_chunk_store.py#L422), [src/coderag/storage/postgres_document_chunk_store.py](../../src/coderag/storage/postgres_document_chunk_store.py#L445).
- La tabla sigue definida en esquema: [src/coderag/storage/postgres_schema.py](../../src/coderag/storage/postgres_schema.py#L29), [src/coderag/storage/postgres_schema.py](../../src/coderag/storage/postgres_schema.py#L178).

Conclusion: existe acoplamiento de escritura que debemos eliminar en Fase 2.

### 3) Contrato de compatibilidad de reset con deleted_graph_edges

- Protocolo interno mantiene operaciones legacy de graph edges: [src/coderag/core/protocols.py](../../src/coderag/core/protocols.py#L17), [src/coderag/core/protocols.py](../../src/coderag/core/protocols.py#L84), [src/coderag/core/protocols.py](../../src/coderag/core/protocols.py#L91).
- Tests de contrato esperan deleted_graph_edges en respuesta: [tests/test_reset_all_staging.py](../../tests/test_reset_all_staging.py#L104), [tests/test_runtime_store_selection.py](../../tests/test_runtime_store_selection.py#L61), [tests/test_hybrid_metadata_store.py](../../tests/test_hybrid_metadata_store.py#L22).
- Documentacion publica hoy expone valor no-cero de ejemplo: [README.md](../../README.md#L441), [docs/API_REFERENCE.md](../API_REFERENCE.md#L596).

Conclusion: en Fase 2 se conserva deleted_graph_edges por compatibilidad, fijado en 0.

### 4) TDM se trata como alcance separado

- TDM usa campo tdm_graph_edges (distinto de deleted_graph_edges): [tests/test_tdm_ingestion_application_service.py](../../tests/test_tdm_ingestion_application_service.py#L107), [tests/test_tdm_ingestion_application_service.py](../../tests/test_tdm_ingestion_application_service.py#L149).

Conclusion: no mezclar cambios de decommission documental con contrato TDM en esta fase.

## Baseline operativo y de pruebas

### Readiness

Comando ejecutado:

curl -s http://localhost:8000/sources/ingest/readiness

Resultado relevante:

- ready: true
- use_neo4j: true
- checks.runtime_store.ok: true
- checks.chroma.ok: true
- checks.lexical.ok: true

### Logs API

Comando ejecutado:

docker compose logs --since=24h api | Select-String -Pattern 65535|Tbl_Documents_GraphEdges|/sources/ingest/files HTTP/1.1" 503

Resultado relevante:

- Se observa al menos un evento 503 en POST /sources/ingest/files.
- Evidencia causal previa de sesion confirma error de limite de parametros: number of parameters must be between 0 and 65535 durante INSERT de Tbl_Documents_GraphEdges.

### Baseline de tests

Comando ejecutado:

.venv\Scripts\python.exe -m pytest tests/test_hybrid_metadata_store.py tests/test_runtime_store_selection.py tests/test_reset_all_staging.py -q

Resultado:

- 14 passed
- 1 failed

Fallo detectado (preexistente a esta fase):

- Test: test_reset_all_skips_legacy_staging_cleanup_without_staged_docs
- Archivo: [tests/test_reset_all_staging.py](../../tests/test_reset_all_staging.py#L95)
- Error: AttributeError: module coderag.core.service has no attribute datetime

Interpretacion:

- La falla pertenece al baseline previo y no fue introducida por cambios de Fase 1.
- Se registra para trazabilidad y para no confundir con el objetivo de decommission.

## Criterios de aceptacion de Fase 1

| Criterio | Estado | Evidencia |
| --- | --- | --- |
| Confirmar backend de graph-path en query | Cumplido | [src/coderag/core/query_service.py](../../src/coderag/core/query_service.py#L179), [src/coderag/core/graph_store.py](../../src/coderag/core/graph_store.py#L456) |
| Identificar puntos de escritura de edges en Postgres | Cumplido | [src/coderag/core/ingestion_service.py](../../src/coderag/core/ingestion_service.py#L201), [src/coderag/core/service.py](../../src/coderag/core/service.py#L386), [src/coderag/storage/postgres_document_chunk_store.py](../../src/coderag/storage/postgres_document_chunk_store.py#L445) |
| Confirmar impacto de contrato deleted_graph_edges | Cumplido | [tests/test_reset_all_staging.py](../../tests/test_reset_all_staging.py#L104), [README.md](../../README.md#L441), [docs/API_REFERENCE.md](../API_REFERENCE.md#L596) |
| Confirmar separacion de alcance TDM | Cumplido | [tests/test_tdm_ingestion_application_service.py](../../tests/test_tdm_ingestion_application_service.py#L107) |
| Registrar baseline de readiness y pruebas | Cumplido con observacion | Readiness OK, 14 passed, 1 failed preexistente |

## Entregables de Fase 1

- Documento de alcance y baseline: este archivo.
- Snapshot de estado operativo y de pruebas antes de cambios funcionales.
- Lista de evidencias para gate de entrada a Fase 2.

## Decision de gate

Fase 1 queda completada y documentada.

Recomendacion para inicio de Fase 2:

- Proceder con corte funcional de persistencia de edges en Postgres manteniendo compatibilidad del campo deleted_graph_edges en 0.
- Tratar la falla baseline de test como item paralelo no bloqueante, salvo que se decida exigir suite limpia como politica de gate.