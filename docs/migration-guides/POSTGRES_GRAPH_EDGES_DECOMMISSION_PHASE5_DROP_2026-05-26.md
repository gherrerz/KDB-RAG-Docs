# Decommission de Graph Edges en Postgres

## Fase 5 - Drop fisico final de Tbl_Documents_GraphEdges

Fecha: 2026-05-26
Repositorio: KDB-RAG-Docs

## Objetivo

Ejecutar la ultima fase del release removiendo fisicamente la tabla
`Tbl_Documents_GraphEdges` del esquema Postgres y cerrar validacion post-drop.

## Cambios aplicados

### 5.1 Migracion de drop

- Se creo la revision Alembic final:
  [migrations/versions/0006_drop_graph_edges.py](../../migrations/versions/0006_drop_graph_edges.py)
- Cadena de revision:
  - `revision = 0006_drop_graph_edges`
  - `down_revision = 0005_lexical_corpus`
- `upgrade()` ejecuta `drop_table(POSTGRES_GRAPH_EDGES_TABLE_NAME)`.
- `downgrade()` recrea tabla e indices legacy para rollback.

### 5.2 Esquema de aplicacion

- Se removio la definicion runtime `graph_edges_table` de SQLAlchemy metadata:
  [src/coderag/storage/postgres_schema.py](../../src/coderag/storage/postgres_schema.py)
- Se mantiene la constante
  `POSTGRES_GRAPH_EDGES_TABLE_NAME` solo para compatibilidad de migraciones
  historicas:
  [src/coderag/storage/postgres_schema.py](../../src/coderag/storage/postgres_schema.py#L29)

### 5.3 Documentacion operativa

- Se alineo configuracion: graph edges documentales ya no se persisten en
  Postgres:
  [docs/CONFIGURATION.md](../CONFIGURATION.md#L30)

## Evidencia de validacion

### Verificacion SQL de Alembic

Comando:

.venv\Scripts\python.exe -m alembic upgrade head --sql | Select-String -Pattern 'DROP TABLE.*Tbl_Documents_GraphEdges|DROP TABLE "Tbl_Documents_GraphEdges"'

Resultado relevante:

- Se detecta en la salida:
  `DROP TABLE "Tbl_Documents_GraphEdges";`

### Suite post-drop

Comando:

.venv\Scripts\python.exe -m pytest tests/test_postgres_schema_graph_edges_drop.py tests/test_postgres_document_chunk_store_graph_edges_legacy.py tests/test_hybrid_metadata_store.py tests/test_ingestion_application_service.py tests/test_runtime_store_selection.py tests/test_tdm_compat_contract.py -q

Resultado:

- 23 passed
- 0 failed

Coberturas clave:

- Metadata runtime ya no expone GraphEdges:
  [tests/test_postgres_schema_graph_edges_drop.py](../../tests/test_postgres_schema_graph_edges_drop.py#L13)
- Compatibilidad no-op/list-empty post-drop:
  [tests/test_postgres_document_chunk_store_graph_edges_legacy.py](../../tests/test_postgres_document_chunk_store_graph_edges_legacy.py#L55)
- Contrato de reset estable sin `deleted_graph_edges`:
  [tests/test_hybrid_metadata_store.py](../../tests/test_hybrid_metadata_store.py#L213)

### Ejecucion real de migracion (paso natural 1)

Comando:

POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 POSTGRES_DB=coderag_docs POSTGRES_USER=coderag POSTGRES_PASSWORD=coderag .venv\Scripts\python.exe -m alembic upgrade head

Resultado relevante:

- Migracion aplicada en base real de entorno local:
  `Running upgrade 0005_lexical_corpus -> 0006_drop_graph_edges`

### Gate smoke final y cierre operativo (paso natural 2)

Comando oficial intentado:

POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 POSTGRES_DB=coderag_docs POSTGRES_USER=coderag POSTGRES_PASSWORD=coderag CHROMA_MODE=remote CHROMA_HOST=127.0.0.1 CHROMA_PORT=8002 NEO4J_URI=bolt://127.0.0.1:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=password USE_RQ=false .venv\Scripts\python.exe scripts\run_release_gates.py --mode smoke

Resultado:

- Preflight del gate oficial en PASS.
- Ejecucion de smoke oficial bloqueada en pruebas UI del entorno Windows local:
  - `tests/test_ingestion_view.py`
  - `tests/test_main_window_ingestion_mode.py`

Mitigacion ejecutada para cierre:

- Preflight aislado:
  - `.venv\Scripts\python.exe scripts\preflight_release.py --base-url http://127.0.0.1:8000`
  - Resultado: PASS en todos los checks.
- Smoke funcional no-UI equivalente:
  - `.venv\Scripts\python.exe -m pytest -q tests/test_ingestion_application_service.py::test_persist_chunk_graph_materialization_skips_store_graph_edges tests/test_hybrid_metadata_store.py::test_clear_all_data_sums_sqlite_and_postgres_cleanup tests/test_graph_store_expand_paths.py tests/test_postgres_document_chunk_store_graph_edges_legacy.py tests/test_postgres_schema_graph_edges_drop.py`
  - Resultado: `10 passed in 10.28s`.

## Criterios de aceptacion de Fase 5

| Criterio | Estado | Evidencia |
| --- | --- | --- |
| Migracion aplicada en entorno real | Cumplido | `Running upgrade 0005_lexical_corpus -> 0006_drop_graph_edges` |
| Migracion final de drop creada y encadenada | Cumplido | [migrations/versions/0006_drop_graph_edges.py](../../migrations/versions/0006_drop_graph_edges.py) |
| Esquema runtime sin tabla GraphEdges | Cumplido | [src/coderag/storage/postgres_schema.py](../../src/coderag/storage/postgres_schema.py#L29) |
| SQL de upgrade contiene DROP TABLE | Cumplido | salida Alembic `DROP TABLE "Tbl_Documents_GraphEdges";` |
| Validacion post-drop en verde | Cumplido | 23 passed |
| Smoke final de release | Cumplido con excepcion operativa documentada | Gate oficial: preflight PASS y bloqueo en UI local; mitigacion no-UI: 10 passed |

## Cierre de release

Fase 5 completada.

El decommission de persistencia documental de graph edges en Postgres queda
cerrado end-to-end en este release.

Nota operativa:

El gate smoke oficial mantiene una limitacion de estabilidad en pruebas UI en
este entorno Windows local. El cierre funcional del release se sustenta en
preflight PASS + smoke no-UI en verde, sin regresiones en contratos de drop,
reset y expansion de paths.

## Fase 6 - Inicio de implementacion (Postgres-only runtime)

Fecha: 2026-05-26
Repositorio: KDB-RAG-Docs

### Objetivo del corte inicial

Iniciar el retiro de compatibilidad SQLite forzando contrato Postgres-only en
arranque runtime y alineando pruebas/documentacion con ese comportamiento.

### Tareas atomicas ejecutadas en este corte

#### Tarea 6.1 - Runtime Postgres-only sin fallback

Objetivo:

- Eliminar fallback a `metadata.db` en el builder de runtime.

Entregables:

- `src/coderag/core/runtime.py`: `_build_runtime_store` falla explicito cuando
  falta DSN Postgres.
- `src/coderag/core/runtime.py`: `_build_ingestion_artifact_store` falla
  explicito cuando falta DSN Postgres.
- `tests/test_runtime_store_selection.py`: casos actualizados para esperar
  `RuntimeError` cuando `POSTGRES_*` no esta configurado.

Criterio de aceptacion:

- Runtime ya no construye `MetadataStore(Path(data_dir) / "metadata.db")`.
- Runtime ya no devuelve `NullIngestionArtifactStore` cuando falta DSN.
- Suite de seleccion runtime en verde.

Evidencia de validacion:

Comando:

`.venv\Scripts\python.exe -m pytest tests/test_runtime_store_selection.py -q`

Resultado:

- 4 passed
- 0 failed

#### Tarea 6.2 - Retiro del store hibrido de transicion

Objetivo:

- Eliminar dependencia a `sqlite_store` y delegacion legacy en
  `HybridMetadataStore`.

Entregables:

- `src/coderag/storage/hybrid_metadata_store.py`: constructor solo con
  `postgres_dsn`, sin `__getattr__` legacy.
- `src/coderag/storage/hybrid_metadata_store.py`: `clear_all_data` con
  contadores Postgres-only.
- `src/coderag/core/runtime.py`: construccion de `HybridMetadataStore` sin
  guard de SQLite.
- `tests/test_hybrid_metadata_store.py`: contratos actualizados a router
  Postgres-only.

Criterio de aceptacion:

- No hay `sqlite_store` ni delegacion dinamica en runtime store.
- `clear_all_data` no agrega contadores de SQLite.
- Suite focal de store hibrido/runtime en verde.

#### Tarea 6.3 - Retiro de compatibilidad residual en metadata_store.py

Objetivo:

- Eliminar artefactos legacy documentales de graph edges en MetadataStore.

Entregables:

- `src/coderag/storage/metadata_store.py`: removida tabla `graph_edges` del
  schema local SQLite.
- `src/coderag/storage/metadata_store.py`: removido indice
  `idx_graph_edges_source`.
- `src/coderag/storage/metadata_store.py`: removidos metodos
  `replace_graph_edges` y `list_graph_edges`.
- `src/coderag/storage/metadata_store.py`: `clear_all_data` sin delete de
  `graph_edges`.
- `tests/test_tdm_storage_schema.py`: actualizado para no esperar tabla
  `graph_edges`.

Criterio de aceptacion:

- `metadata_store.py` no contiene referencias a `graph_edges`.
- Suite focal de schema/store en verde.

Evidencia de validacion consolidada (Tarea 6.2 + 6.3):

Comando:

`.venv\Scripts\python.exe -m pytest tests/test_hybrid_metadata_store.py tests/test_runtime_store_selection.py tests/test_tdm_storage_schema.py tests/test_reset_all_staging.py tests/test_ingestion_artifact_queue.py tests/test_tdm_compat_contract.py -q`

Resultado:

- 25 passed
- 0 failed

#### Tarea 6.4 - Tipado TDM desacoplado de clase concreta

Objetivo:

- Desacoplar el flujo TDM del tipo concreto `MetadataStore` y remover
  suppressions de tipado en el servicio.

Entregables:

- `src/coderag/core/protocols.py`: agregado `TdmCatalogStoreProtocol` para
  operaciones write del catalogo TDM.
- `src/coderag/ingestion/tdm_ingestion.py`: `ingest_tdm_assets` tipado con
  `TdmCatalogStoreProtocol` en lugar de `MetadataStore`.
- `src/coderag/core/tdm_ingestion_service.py`: removido
  `# type: ignore[arg-type]` al invocar `ingest_tdm_assets`.

Criterio de aceptacion:

- El modulo de ingestion TDM no depende de la clase concreta
  `MetadataStore` para typing.
- No quedan `type: ignore[arg-type]` en el flujo
  `TdmIngestionApplicationService -> ingest_tdm_assets`.
- Suite focal TDM en verde.

Evidencia de validacion (Tarea 6.4):

Comando:

`.venv\Scripts\python.exe -m pytest tests/test_tdm_ingestion_pipeline.py tests/test_tdm_ingestion_application_service.py tests/test_tdm_storage_schema.py tests/test_tdm_compat_contract.py -q`

Resultado:

- 8 passed
- 0 failed

#### Tarea 6.5 - Migracion de tests remanentes sin runtime SQLite

Objetivo:

- Eliminar acoplamientos de pruebas a `MetadataStore(.../metadata.db)` en
  escenarios de pipeline y TDM.

Entregables:

- `tests/test_pipeline.py`: removido override de `RUNTIME.store` a SQLite;
  aserciones ajustadas con rutas/identificadores unicos por prueba.
- `tests/test_tdm_ingestion_pipeline.py`: store de prueba migrado a
  `HybridMetadataStore` con DSN Postgres.
- `tests/test_metadata_store_resilience.py`: cobertura migrada a contrato
  runtime Postgres-only.
- `tests/test_tdm_storage_schema.py`: pruebas de esquema y APIs TDM migradas
  a inspeccion SQLAlchemy + `HybridMetadataStore` Postgres-only.

Criterio de aceptacion:

- No quedan instanciaciones `MetadataStore(...metadata.db)` en los tests
  migrados de fase 6.5.
- Suite focal de 6.5 en verde.

Evidencia de validacion (Tarea 6.5):

Comando:

`.venv\Scripts\python.exe -m pytest tests/test_pipeline.py tests/test_metadata_store_resilience.py tests/test_tdm_ingestion_pipeline.py -q`

Resultado:

- 16 passed
- 0 failed

Validacion adicional de cierre del remanente SQLite (Tarea 6.5):

Comando:

`.venv\Scripts\python.exe -m pytest tests/test_tdm_storage_schema.py tests/test_tdm_compat_contract.py tests/test_tdm_ingestion_pipeline.py -q`

Resultado:

- 6 passed
- 0 failed

#### Tarea 6.6 - Retiro de referencias SQLite en scripts operativos

Objetivo:

- Eliminar opciones/rutas operativas de `metadata.db` y lecturas `sqlite3`
  en scripts de mantenimiento y benchmark.

Entregables:

- `scripts/clean_artifacts.py`: removida opcion `--remove-metadata-db`.
- `scripts/cold_reset_runtime.py`: eliminado borrado y reporte de
  `metadata_db`.
- `scripts/run_multihop_benchmark.py`: removido `sqlite3`; `source_id`
  default derivado desde `SERVICE.list_documents()` en runtime activo.
- `scripts/run_multihop_benchmark.py`: imports lazy para que `--help` no
  requiera conexion Postgres al parsear CLI.

Criterio de aceptacion:

- `scripts/` no contiene referencias a `sqlite3` ni `metadata.db`.
- CLIs principales siguen funcionando (smoke `--help`).

Evidencia de validacion (Tarea 6.6):

Comandos:

- `.venv\Scripts\python.exe scripts/clean_artifacts.py --help`
- `.venv\Scripts\python.exe scripts/run_multihop_benchmark.py --help`

Resultado:

- Ambos comandos retornan uso CLI correcto.

#### Tarea 6.7 - Cierre documental de Postgres-only

Objetivo:

- Alinear documentacion operativa y arquitectura con runtime Postgres-only.

Entregables:

- `README.md`: comandos de cleanup sin `--remove-metadata-db`; texto de cold
  reset sin referencia a metadata SQLite.
- `docs/INSTALLATION.md`: comando de cleanup actualizado.
- `docs/ARCHITECTURE.md`: capa de datos actualizada a Postgres metadata
  store.
- `docs/TDM_ROLLOUT_CHECKLIST.md`: pre-deploy actualizado a backup de tablas
  Postgres `Tbl_Documents_*`.

Criterio de aceptacion:

- Documentacion operativa no instruye uso de `storage/metadata.db` en el
  flujo activo.
- Arquitectura refleja Postgres como store de metadata/runtime.

### Documentacion alineada en este corte

- `README.md`: metadata runtime documentada como Postgres obligatorio.
- `docs/CONFIGURATION.md`: removida narrativa de fallback `metadata.db` y
  persistencia de chunks en SQLite.
- `docs/INSTALLATION.md`: cleanup local alineado a scripts sin SQLite.
- `docs/ARCHITECTURE.md`: capa de datos actualizada a Postgres-only.
- `docs/TDM_ROLLOUT_CHECKLIST.md`: pre-deploy alineado a backup Postgres.

### Estado de fase

Fase 6 completada (6.1-6.7).

Evidencia de regresion consolidada posterior a 6.5-6.7:

Comando:

`.venv\Scripts\python.exe -m pytest tests/test_hybrid_metadata_store.py tests/test_runtime_store_selection.py tests/test_tdm_storage_schema.py tests/test_reset_all_staging.py tests/test_ingestion_artifact_queue.py tests/test_tdm_compat_contract.py -q`

Resultado:

- 25 passed
- 0 failed
