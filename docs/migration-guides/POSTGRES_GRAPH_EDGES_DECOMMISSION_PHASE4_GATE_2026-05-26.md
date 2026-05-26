# Decommission de Graph Edges en Postgres

## Fase 4 - Corte de Contrato y Gate de Regresion

Fecha: 2026-05-26
Repositorio: KDB-RAG-Docs

## Objetivo

Aplicar el cambio breaking del contrato de reset para remover
`deleted_graph_edges` del payload externo y cerrar el gate de regresion de la
fase.

## 4.1 Contrato funcional alineado

### Contrato de reset

- `deleted_graph_edges` fue removido del contrato de `DELETE /sources/reset`:
  [README.md](../../README.md#L441)
- API reference confirma el mismo contrato actualizado:
  [docs/API_REFERENCE.md](../API_REFERENCE.md#L596)

### Flujo de grafo en arquitectura

- Se removio la referencia a persistencia de edges en Postgres durante ingesta
  y se reemplazo por nota de no-persistencia documental:
  [docs/ARCHITECTURE.md](../ARCHITECTURE.md#L325)

## 4.2 Gate obligatorio de regresion

### Bateria ejecutada

Comando:

.venv\Scripts\python.exe -m pytest tests/test_hybrid_metadata_store.py tests/test_runtime_store_selection.py tests/test_reset_all_staging.py tests/test_ingestion_artifact_queue.py tests/test_tdm_compat_contract.py -q

.venv\Scripts\python.exe -m pytest tests/test_api_async_toggle.py::test_reset_clears_ingested_data -q

Resultado:

- 22 passed
- 0 failed

Cobertura funcional del gate:

- Agregacion de cleanup en runtime hibrido sin `deleted_graph_edges`:
  [tests/test_hybrid_metadata_store.py](../../tests/test_hybrid_metadata_store.py#L165)
- Runtime guard sin campo legado en fallback deshabilitado:
  [tests/test_runtime_store_selection.py](../../tests/test_runtime_store_selection.py#L58)
- Contrato de reset en API y servicio sin campo legado:
  [tests/test_reset_all_staging.py](../../tests/test_reset_all_staging.py#L95),
  [tests/test_api_async_toggle.py](../../tests/test_api_async_toggle.py#L207)
- Compatibilidad TDM estable tras cambio de contrato:
  [tests/test_tdm_compat_contract.py](../../tests/test_tdm_compat_contract.py#L56)

### Verificacion estatica de remocion del campo externo

Patron inspeccionado en codigo y tests:

- `deleted_graph_edges`

Resultado:

- Sin coincidencias en contratos activos (`src/`, `tests/`, `README.md`,
  `docs/API_REFERENCE.md`).
- Referencias historicas permanecen solo en documentos de migracion de fases
  anteriores.

## Criterios de aceptacion de Fase 4

| Criterio | Estado | Evidencia |
| --- | --- | --- |
| Contrato de reset sin campo legado | Cumplido | [src/coderag/core/models.py](../../src/coderag/core/models.py#L31), [src/coderag/core/ingestion_service.py](../../src/coderag/core/ingestion_service.py#L416) |
| Stores alineados al contrato | Cumplido | [src/coderag/storage/hybrid_metadata_store.py](../../src/coderag/storage/hybrid_metadata_store.py#L378), [src/coderag/storage/postgres_document_chunk_store.py](../../src/coderag/storage/postgres_document_chunk_store.py#L421), [src/coderag/storage/metadata_store.py](../../src/coderag/storage/metadata_store.py#L903) |
| Reset operativo en API | Cumplido | [tests/test_api_async_toggle.py](../../tests/test_api_async_toggle.py#L207) |
| Regresion de contratos y runtime en verde | Cumplido | [tests/test_hybrid_metadata_store.py](../../tests/test_hybrid_metadata_store.py#L165), [tests/test_runtime_store_selection.py](../../tests/test_runtime_store_selection.py#L58), [tests/test_tdm_compat_contract.py](../../tests/test_tdm_compat_contract.py#L56) |

## Decision Go/No-Go

GO.

La Fase 4 queda aprobada con cambio breaking aplicado en contrato externo de
reset. El release queda habilitado para continuar con limpieza final y drop
fisico de artefactos legacy de graph edges.
