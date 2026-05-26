# Decommission de Graph Edges en Postgres

## Fase 3 - Contratos internos y pruebas

Fecha: 2026-05-26
Repositorio: KDB-RAG-Docs

## Objetivo

Conservar compatibilidad interna durante la transición, dejar explícito el estado
legacy de APIs de graph edges en RuntimeStore y blindar con pruebas que la
persistencia documental en Postgres ya no se usa.

## Cambios aplicados

### 1) Contrato interno legacy explicitado

- Se documentó `replace_graph_edges` como hook legacy de compatibilidad:
  [src/coderag/core/protocols.py](../../src/coderag/core/protocols.py#L84)
- Se documentó `list_graph_edges` como hook legacy de compatibilidad:
  [src/coderag/core/protocols.py](../../src/coderag/core/protocols.py#L91)

### 2) Store híbrido alineado a contrato de reset

- `clear_all_data` fija `deleted_graph_edges` en `0` para no propagar valores
  legacy de backends internos:
  [src/coderag/storage/hybrid_metadata_store.py](../../src/coderag/storage/hybrid_metadata_store.py#L405)
- Métodos de graph edges del híbrido quedaron marcados como compatibilidad
  transitoria:
  [src/coderag/storage/hybrid_metadata_store.py](../../src/coderag/storage/hybrid_metadata_store.py#L131)

### 3) Implementaciones legacy marcadas

- SQLite MetadataStore mantiene métodos de graph edges con docstring legacy:
  [src/coderag/storage/metadata_store.py](../../src/coderag/storage/metadata_store.py#L460)
- Postgres DocumentChunkStore ya opera en no-op/read-empty para graph edges:
  [src/coderag/storage/postgres_document_chunk_store.py](../../src/coderag/storage/postgres_document_chunk_store.py#L421)

### 4) Pruebas nuevas y ajustadas

- Se ajustó contrato del híbrido para esperar `deleted_graph_edges=0`:
  [tests/test_hybrid_metadata_store.py](../../tests/test_hybrid_metadata_store.py#L213)
- Se agregó test unitario que valida no-op/list-empty y ausencia de delete sobre
  tabla de graph edges en el store Postgres:
  [tests/test_postgres_document_chunk_store_graph_edges_legacy.py](../../tests/test_postgres_document_chunk_store_graph_edges_legacy.py#L1)

## Evidencia de validación

Comando:

.venv\Scripts\python.exe -m pytest tests/test_hybrid_metadata_store.py tests/test_ingestion_application_service.py tests/test_postgres_document_chunk_store_graph_edges_legacy.py tests/test_runtime_store_selection.py tests/test_tdm_compat_contract.py -q

Resultado:

- 22 passed
- 0 failed

## Estado de fase

Fase 3 completada.

Gate recomendado para siguiente fase:

- Avanzar a Fase 4 de cleanup estructural/migración de esquema cuando se
  confirme ventana de release para drop físico de la tabla legacy.