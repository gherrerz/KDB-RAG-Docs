# Changelog

<!-- markdownlint-disable MD024 -->

## [Unreleased]

### Added

- Nuevo documento `docs/MCP_CONTRACT.md`: contrato de integración MCP
  autocontenido para consumidores externos (payloads de entrada/salida de las
  11 tools, los 3 prompts y los 8 resources, tabla consolidada de códigos de
  error `DOCS_*`, ejemplos JSON-RPC de `tools/call`/`prompts/get`/
  `resources/read`, y una sesión completa de handshake). Enlazado desde
  `docs/API_REFERENCE.md` en la sección `POST/GET /mcp`.
- Resolución de URLs y credenciales de infraestructura (Chroma, Postgres, Neo4j)
  diferenciada por entorno mediante variables con sufijo `_DEV`/`_TEST`/`_PROD`,
  gobernadas por `RUNTIME_ENVIRONMENT`. Precedencia por variable:
  `{VAR}_{SUFIJO}` → `{VAR}` (base, fallback) → default. Implementado en el
  `model_validator(mode="before")` de `settings.py`; documentado en
  `docs/CONFIGURATION.md` y `.env.example`. Sin breaking change: si solo existe
  la variable base, el comportamiento es idéntico al previo.

### Security

- Se corrigen vulnerabilidades reportadas por Trivy en dependencias de runtime
  (`requirements-runtime.txt`):
  - `python-multipart` 0.0.20 → 0.0.27 (CVE-2026-24486 path traversal,
    CVE-2026-42561 DoS de parsing de headers).
  - `fastapi` 0.116.1 → 0.120.1 y pin explícito `starlette==0.49.1`
    (CVE-2025-62727 DoS por header Range de tiempo cuadrático).
  - Se reemplaza el paquete `chromadb` por el cliente delgado
    `chromadb-client==1.5.9` (CVE-2026-45829 "ChromaToast", RCE pre-auth en el
    **servidor** Chroma). El app solo usa `chromadb.HttpClient`, por lo que el
    cliente delgado elimina el código del servidor vulnerable de la imagen y
    reduce su tamaño. El servidor Chroma sigue siendo la superficie RCE: se
    habilita autenticación por token en `docker-compose.yml` y se cablea
    `CHROMA_TOKEN`/`CHROMA_USERNAME`/`CHROMA_PASSWORD` en los manifiestos k8s;
    debe mantenerse sin exposición pública y migrarse a una imagen parcheada o
    al servidor Rust cuando esté disponible.
- Segunda tanda de CVEs reportadas por Trivy en `requirements-runtime.txt`:
  - `python-multipart` 0.0.27 → 0.0.30 (CVE-2026-53539 DoS por complejidad
    cuadrática en `QuerystringParser`).
  - `starlette` 0.49.1 → 1.3.1 (CVE-2026-48818 SSRF + robo de credenciales NTLM
    vía rutas UNC en `StaticFiles`; CVE-2026-54283 DoS por límites de
    `request.form()` ignorados en `application/x-www-form-urlencoded`). El bump a
    starlette 1.x exige `fastapi` 0.120.1 → 0.137.1 (primera línea estable que
    admite starlette 1.x; `pydantic==2.11.7` permanece compatible). Barre además
    otras CVEs recientes de starlette (CVE-2026-48710 "BadHost", CVE-2026-48817).

### Changed

- Bump de dependencias `mcp` 1.23.0 → 1.28.1 y `pypdf` 5.4.0 → 6.14.2 en
  `requirements-runtime.txt`. Sin cambios de código: `mcp==1.28.1` sigue en la
  línea estable v1.x (misma API `Server`/`mcp.types` usada por
  `mcp_prompts.py`/`mcp_resources.py`) y satisface los mínimos ya pineados de
  `pydantic`/`uvicorn`/`starlette`/`httpx`; `pypdf==6.14.2` solo eliminó
  soporte a Python 3.8 (el runtime usa 3.12) y preserva la API
  `PdfReader`/`.pages`/`.extract_text()` usada en `pdf_parser.py`. Referencias
  actualizadas en `docs/MCP_CONTRACT.md`.
- **BREAKING** el servidor MCP (`/mcp`) migra su autenticación del header
  `X-MCP-Token` a `Authorization: Bearer {MCP_API_TOKEN}` (contrato de
  integración Hexa). Falta o incompatibilidad de token responde `401` con
  `{message, code:"invalid_mcp_token"}`; `MCP_ENABLED=false` sigue respondiendo
  `404`. Clientes existentes deben actualizar el header enviado.
- **BREAKING** `GET /health` cambia de forma: en lugar de `{"status":"ok"}`
  ahora retorna `{status: healthy|degraded|unhealthy, name, version,
  uptime_s, dependencies}` (modelo `McpHealthResponse`/`McpDependencyStatus`),
  reutilizando los checks ya existentes de `runtime_store`, `lexical`, `chroma`,
  `neo4j` y `redis` con latencia medida por dependencia. Sigue sin
  autenticación.
- Los endpoints publicados como tools MCP (`get_document_content`,
  `delete_document`, `replace_document_tags`, `ingest_files_json[/async]`,
  `get_job`, `query`, `retrieval_only`) devuelven cuerpos de error
  estandarizados `{error: "DOCS_*", message, retryable}` (`DOCS_NOT_FOUND`,
  `DOCS_VALIDATION`, `DOCS_UNAVAILABLE`) manteniendo el `status_code` HTTP
  previo. Los endpoints multipart (`ingest_source_files[/async]`) no cambian.
- **BREAKING** el reset global deja de usar `DELETE /sources/reset?confirm=true`
  y converge a `POST /admin/reset` con `ADMIN_RESET_ENABLED`,
  `ADMIN_RESET_TOKEN`, header `X-Admin-Reset-Token` y body explicito de
  confirmacion (`confirm=true`, `confirmation_phrase="RESET ALL DATA"`).
- La UI desktop y los checks operativos de Docs ahora usan el nuevo contrato
  administrativo de reset y requieren compartir `ADMIN_RESET_TOKEN` cuando
  apuntan a una API protegida.
- El versionado Alembic queda aislado por aplicacion cuando KDB-RAG-Docs y
  KDB-RAG-Repo comparten la misma base Postgres: Docs usa
  `alembic_version_docs` y Repo usa `alembic_version_repo`, evitando
  colisiones en `alembic_version`.
- Se agregan guardrails de CI para bloquear regresiones hacia
  `alembic_version` default en rutas criticas de migracion y bootstrap
  (`tests/test_alembic_version_contract.py`).

### Added

- Nuevo endpoint público `GET /info` (sin autenticación) para el contrato de
  integración Hexa: expone `{name, version, server_type: "tools", description,
  sensitive_fields}` (modelo `McpInfoResponse`). `sensitive_fields` declara los
  campos con contenido libre de usuario (`query`, `question`, `content`,
  `title`, `tags`, `answer`) para que Hexa configure su Dual-LLM Sanitizer.
- Prompts y resources MCP (paridad con `KDB-RAG-Repo`): nuevo módulo
  `src/coderag/api/mcp_prompts.py` con 3 prompts (`query_guide`,
  `ingest_workflow_guide`, `document_catalog_guide`) y
  `src/coderag/api/mcp_resources.py` con 5 guías estáticas más los recursos
  dinámicos `rag://documents`, `rag://ingest/readiness` y el template
  `rag://documents/{document_id}`, registrados antes de montar `/mcp` para que
  el handshake `initialize` anuncie las capabilities `tools`+`prompts`+
  `resources`. Nuevos tests `tests/test_mcp_prompts.py` y
  `tests/test_mcp_resources.py`.
- Campo `created: bool` en las respuestas de las tools de escritura
  (contrato Hexa de idempotencia): `ingest_files_json[/async]` (`true` si el
  lote ingerido era completamente nuevo, `false` si la deduplicación por
  `title+content_type` reemplazó al menos un documento existente),
  `delete_document` y `replace_document_tags` (siempre `false`, mutaciones
  idempotentes sobre un documento ya persistido).
- Guia operativa de Fase 6 para ejecutar backup, upgrade y validacion de
  tablas Alembic aisladas en base Postgres compartida:
  `docs/migration-guides/alembic-shared-db-cutover.md`.
- Politica de retiro controlado para la tabla `alembic_version` legacy,
  con ventana minima de observacion, validaciones previas y estrategia
  reversible rename-then-drop en la guia de cutover compartido.
- Nuevo endpoint `GET /sources/documents/{document_id}/content` para
  recuperar el contenido textual completo persistido de un documento
  ingestado sin reconstruirlo desde chunks.
- Soporte MCP (Model Context Protocol) coexistiendo con la API REST: nuevo
  endpoint `POST/GET /mcp` (envoltura `fastapi-mcp` montada sobre la misma app
  FastAPI, transporte HTTP streamable) que permite a agentes de IA descubrir
  (`tools/list`) y ejecutar (`tools/call`) un subconjunto de operaciones derivado
  del OpenAPI (nombre de tool = `operation_id`). Se publican vía
  `include_operations` (default-deny): `list_documents`, `list_document_tags`,
  `get_document_content`, `delete_document`, `replace_document_tags`,
  `ingest_readiness`, `ingest_source_files`, `ingest_source_files_async`,
  `get_job`, `query` y `retrieval_only`; quedan fuera `/admin/reset`, la ingesta
  por payload (`/sources/ingest[/async]`) y los endpoints `/tdm/*`. Configurable
  con `MCP_ENABLED`, `MCP_API_TOKEN` (header `X-MCP-Token`), `MCP_MOUNT_PATH` y
  `MCP_SERVER_NAME`. Se añaden `fastapi-mcp==0.4.0` y `mcp==1.23.0`. Nuevo módulo
  `src/coderag/api/mcp_server.py`, tests `tests/test_mcp.py` y smoke
  `scripts/mcp_smoke.sh`.
- Nuevos endpoints de ingesta por archivos vía JSON base64
  `POST /sources/ingest/files/json` y `POST /sources/ingest/files/json/async`
  (modelos `UploadedFilePayload`/`FilesIngestionJsonRequest`): alternativa
  MCP-friendly a los endpoints multipart que recibe el contenido como base64 en el
  cuerpo, reutilizando el mismo pipeline de staging/ingesta. El servidor MCP pasa a
  exponer estas variantes (`ingest_files_json[/async]`) en lugar de las multipart
  (`ingest_source_files[/async]`), que quedan como REST-only para la UI porque el
  binario `multipart/form-data` no mapea a argumentos JSON de una tool MCP. Nuevo
  test `tests/test_upload_ingestion_json.py`.
- Headers de identidad opcionales en los servicios MCP: `x-role-id`, `x-user-id` y
  `x-country-id` se reenvían (pass-through) desde la conexión `/mcp` hacia cada tool
  vía el allowlist de `fastapi-mcp` y se declaran en el OpenAPI de los 11 endpoints
  expuestos. Nuevo módulo `src/coderag/api/identity_headers.py` (dependencia
  `identity_headers` + `IDENTITY_HEADER_NAMES`).

### Fixed

- Swagger UI volvia a mostrar el campo `files` de `POST /sources/ingest/files`
  (y su variante `/async`) como caja de texto en vez de selector de archivos:
  regresion del salto a OpenAPI 3.1 con FastAPI 0.137, que describe los binarios
  de `UploadFile` con `contentMediaType` en lugar de `format: binary`. El
  post-procesador de OpenAPI (`custom_openapi`) ahora restaura `format: binary`
  en los schemas de upload sin alterar el parsing multipart.
- `POST /query` devolvia `503` intermitente
  (`LLM provider call failed in strict mode`) cuando la generacion de una
  respuesta fundamentada larga superaba el `timeout=30` fijo del POST al
  proveedor. El timeout ahora es configurable via `LLM_REQUEST_TIMEOUT_SEC`
  (default 120) y los payloads de OpenAI/Gemini/Vertex acotan la salida con
  `LLM_MAX_OUTPUT_TOKENS` (default 4096) para limitar latencia y costo.

## [0.3.10] - 2026-05-26

### Changed

- `path_or_url` ahora se normaliza a un origen logico estable para ingestas
  `folder` y multipart, evitando persistir paths absolutos o temporales del
  runtime.

- Uploads multipart recursivos preservan la ruta relativa enviada por el
  cliente y la limpieza legacy de `storage/ingestion_staging` sigue resolviendo
  esos documentos hacia el mirror administrado cuando corresponde.

- `GET /sources/ingest/readiness` ahora expone senales estructuradas de
  Chroma en `checks.chroma` (`signal`, `mode`, `target`/`persist_dir`,
  `collection`, `hnsw_space`, entre otras) sin depender solo del campo
  `detail`.

- `GET /sources/ingest/readiness` ahora expone tambien un snapshot
  estructurado del backend lexico Postgres en `checks.lexical`
  (`backend`, `fts_language`, `target`, `indexed`, `corpus_rows`,
  `document_count`, `source_count`) para distinguir corpus vacio de backend
  no alcanzable.

- La UI de Ingestion ahora renderiza esas senales estructuradas de Chroma en
  el diagnostico visible cuando degrada automaticamente de `async` a `sync`.

- La UI de Ingestion ahora renderiza tambien el snapshot del backend lexico
  en el diagnostico tecnico visible durante el fallback automatico de
  `async` a `sync`.

- `src/main.py` ahora respeta `API_HOST` y `API_PORT` con fallback a `PORT`
  para evitar colisiones locales de bind cuando el puerto `8000` ya esta en
  uso.

- `src/run_ui.py` ahora acepta `API_BASE_URL` o `UI_API_HOST`/
  `UI_API_PORT`, permitiendo validar la UI contra una API real levantada en
  un puerto alternativo como `8010`.
- `scripts/run_release_gates.py --mode full` ahora ejecuta por defecto solo
  el benchmark baseline de release; el perfil tematico de Gobierno de Datos
  queda opt-in via `--include-gobierno-datos-benchmark` cuando la fuente
  activa contiene ese corpus.

- Cuando `API_BASE_URL` no esta definido, `src/run_ui.py` ahora reutiliza
  `API_HOST`/`API_PORT` como contrato compartido con la API y normaliza
  `0.0.0.0` a `127.0.0.1`; `.env.example` deja `API_BASE_URL` y
  `UI_API_HOST`/`UI_API_PORT` solo como overrides opcionales.

- Los ingestion artifacts ahora purgan inmediatamente el payload binario al
  quedar `completed` o `failed`, y existe `scripts/purge_expired_ingestion_artifacts.py`
  para eliminar metadata expirada por TTL desde Postgres.

- Cuando `POSTGRES_*` esta configurado, `src/coderag/core/runtime.py` ya no
  instancia `MetadataStore` ni depende de `storage/metadata.db`; el fallback
  legacy a SQLite queda deshabilitado de forma explicita en ese path.

- `src/coderag/ingestion/index_chroma.py` ya no acepta `CHROMA_MODE=embedded`
  como modo operativo final: el runtime exige Chroma remoto, y readiness
  devuelve `signal=chroma_mode_unsupported` sin exponer `persist_dir` local.

- Se introdujo composicion tipada por contratos en `core/protocols.py` y
  `core/composition.py`; `RuntimeState` ahora declara store/artifacts con
  protocolos explicitos y `RagApplicationService` consume dependencias
  inyectables en lugar de construir concretos dentro de su constructor.

- Se extrajeron `core/ingestion_service.py` y `core/job_service.py` como
  primer paso de separacion del servicio monolitico; la fachada
  `RagApplicationService` delega reset/delete/estado de job y la cola async
  consume el servicio de ingestion delegado sin cambiar el contrato externo.

- La deduplicacion pre-ingesta y la materializacion de
  documentos/chunks/grafo por `source_id` quedaron encapsuladas en metodos
  atomicos de `IngestionApplicationService`, reduciendo complejidad en
  `_ingest_impl` y manteniendo el contrato de fachada `service.ingest(...)`
  para compatibilidad con workers y tests.

- La construccion de chunks con snapshots de progreso (`chunk_progress`)
  tambien se movio a `IngestionApplicationService`; la fachada principal
  conserva la emision del timeline publico y los mismos porcentajes de avance.

- El rebuild de indices posterior a la persistencia de ingesta tambien se
  delega a `IngestionApplicationService`, preservando el mismo paso publico
  `rebuild_indexes` y el contrato de salida del job.

- El armado del payload final de ingesta completada (metricas y resumen de
  deduplicacion) tambien se delega a `IngestionApplicationService`, dejando
  la fachada centrada en orquestacion y emision de eventos.

- La logica de timeline/progreso de ingesta (`append_job_event`, transiciones
  `running`/`failed` y callback de progreso) se centraliza en
  `IngestionApplicationService.append_ingest_step()`, reduciendo complejidad
  de `_ingest_impl` sin alterar el contrato de pasos publicado.

- La construccion del mensaje de error cuando una fuente no produce
  documentos, junto con el payload final `failed` de ingesta, se delega a
  `IngestionApplicationService` para mantener `_ingest_impl` orientado a
  orquestacion.

- El calculo de progreso del loader de documentos tambien se delega a
  `IngestionApplicationService.build_loader_progress_step()`, preservando la
  misma banda de porcentaje y formato de step publicado.

- Se agregaron pruebas unitarias directas para helpers de
  `IngestionApplicationService` en
  `tests/test_ingestion_application_service.py`.

- Se agregaron pruebas unitarias directas para los servicios extraidos de
  consulta (`tests/test_query_application_service.py`) y TDM
  (`tests/test_tdm_query_application_service.py`), validando modos fallback,
  firmas legacy de expansion de grafo, filtros de catalogo y persistencia de
  artefactos de virtualizacion/perfiles sinteticos.

- Se introdujo `core/query_service.py` y la fachada `RagApplicationService`
  ahora delega la ejecucion de `query(...)` en `QueryApplicationService`
  despues del refresh de indices, manteniendo el mismo contrato de
  `QueryResponse`.

- Se introdujo `core/tdm_query_service.py` y la fachada `RagApplicationService`
  ahora delega `query_tdm`, catalogos TDM y previews de virtualizacion/
  sinteticos en `TdmQueryApplicationService`, manteniendo payloads y
  contratos existentes.

- Se introdujo `core/tdm_ingestion_service.py` y la fachada
  `RagApplicationService` ahora delega `ingest_tdm_assets(...)` en
  `TdmIngestionApplicationService`, encapsulando la sincronizacion de edges
  tipados TDM y el enriquecimiento de metricas de grafo sin cambiar el
  contrato publico del endpoint.

- Se agregaron pruebas unitarias directas para
  `TdmIngestionApplicationService` en
  `tests/test_tdm_ingestion_application_service.py`, cubriendo guardrails,
  persistencia de metricas de grafo y branch sin `source_id`.

- Se introdujo `core/tdm_policy_service.py` y la fachada
  `RagApplicationService` ahora delega en este servicio los guardrails TDM
  (`ENABLE_TDM` + disponibilidad de Neo4j) para evitar validaciones
  duplicadas entre metodos TDM.

- Se introdujo `core/index_coordinator_service.py` y la fachada delega la
  reconstruccion/sincronizacion de indices (`rebuild_indexes`, refresh
  lexical por cambios externos y chequeo de `index_version`) en
  `RetrievalIndexCoordinator`.

- Se agregaron pruebas unitarias directas para servicios extraidos de policy
  y coordinacion de indices en `tests/test_tdm_policy_service.py` y
  `tests/test_index_coordinator_service.py`.

- La UI desktop completa la Fase 3 de desacople: `MainWindow` ahora delega
  transporte/polling HTTP en `src/coderag/ui/api_client.py`, y las vistas
  de Ingestion/Query/TDM delegan validaciones y normalizacion en
  presenters/controladores dedicados.

- Se agregaron pruebas unitarias para los nuevos componentes UI extraidos:
  `tests/test_ui_api_client.py`, `tests/test_ingestion_presenter.py`,
  `tests/test_query_presenter.py`, `tests/test_tdm_presenter.py`, y se
  reoriento `tests/test_main_window_ingestion_mode.py` al contrato de
  delegacion por cliente.

- Se agrego `tests/test_composition.py` para validar el wiring de
  `core/composition.py` con dependencias inyectables.

- Se reforzo la cobertura contractual de runtime/composicion en Fase 5:
  `tests/test_runtime_store_selection.py` ahora valida seleccion de artifact
  store (null vs Postgres), `tests/test_hybrid_metadata_store.py` protege
  delegacion legacy por `__getattr__`, y `tests/test_composition.py` valida
  el guardrail `require_chroma_enabled()` durante wiring.

- Se inicio la migracion de anotaciones legacy `typing` hacia tipos built-in
  en componentes de fase 4 (`src/coderag/jobs/queue.py`,
  `src/coderag/core/graph_store.py`, `scripts/preflight_release.py`,
  `scripts/run_multihop_benchmark.py`).

- Se extendio la migracion de tipado moderno en Fase 4 a
  `src/coderag/core/service.py`, `src/coderag/core/settings.py`,
  `src/coderag/api/upload_ingestion.py` y
  `src/coderag/ingestion/index_chroma.py`, y se valido con pruebas
  focalizadas de core/API/ingestion.

- Se continuo Fase 4 con migracion de anotaciones legacy en retrieval y
  query (`src/coderag/retrieval/*`, `src/coderag/core/query_service.py`),
  ingestion/parsers (`src/coderag/ingestion/chunker.py`,
  `src/coderag/ingestion/embedding.py`,
  `src/coderag/ingestion/confluence_client.py`,
  `src/coderag/ingestion/repo_scanner.py`,
  `src/coderag/ingestion/graph_builder.py`,
  `src/coderag/ingestion/tdm_graph_builder.py`, `src/coderag/parsers/*`) y
  utilitarios/store acotados (`src/coderag/core/vertex_auth.py`,
  `src/coderag/tdm/*`, `src/coderag/ui/evidence_view.py`,
  `src/coderag/storage/postgres_job_state_store.py`,
  `src/coderag/storage/postgres_ingestion_artifact_store.py`).

- Esta continuidad de Fase 4 se valido con pruebas focalizadas en query,
  pipeline, TDM, parsers, UI evidence, auth Vertex y stores Postgres.

- Se completo el cierre tecnico de Fase 4 para migracion de typing legacy en
  `src/` y `scripts/`, incluyendo los modulos remanentes
  `src/coderag/storage/metadata_store.py`,
  `src/coderag/storage/postgres_document_chunk_store.py`,
  `src/coderag/storage/postgres_tdm_store.py`,
  `src/coderag/llm/providerlmm_client.py`,
  `src/coderag/ingestion/document_loader.py`,
  `src/coderag/ingestion/tdm_ingestion.py` y
  `src/coderag/core/models.py`.

- Se validaron los ultimos cambios de cierre de Fase 4 con bateria focalizada
  de pipeline, fallback LLM, auth Vertex y stores metadata/Postgres/TDM.

- Se agrego la guia de migracion
  `docs/migration-guides/MIGRATION_UI_PHASE3_PRESENTERS.md` con el detalle
  operativo del split UI por capas.

- Se agrego `docs/migration-guides/service-ui-refactor.md` para consolidar
  el estado final del refactor de servicios/UI, el contrato de composicion,
  y la matriz de pruebas focalizadas para regresion de Fase 5.

- La documentacion operativa y de API ahora refleja el snapshot lexico de
  readiness y su uso en UI, incluyendo `README.md`,
  `docs/API_REFERENCE.md` y `docs/UI_RELEASE_CHECKLIST.md`.

- [sample_data](sample_data/) ahora incluye un corpus minimo de Gobierno de
  Datos para poder reingerir y ejecutar el benchmark tematico de release sin
  depender de un dataset externo.

### Fixed

- `alembic.ini` ahora define `path_separator = os`, eliminando el warning de
  configuracion legacy durante startup y pytest.

- Se agrego cobertura de integracion para validar que el snapshot de
  `checks.lexical` pasa de corpus vacio a corpus poblado despues de una
  ingesta real.

## [0.3.9] - 2026-05-25

### Changed

- La UI desktop ahora enruta `source_type=folder` a upload multipart
  recursivo en lugar de copiar la carpeta a `storage/ingestion_staging`
  antes de llamar al backend.

- Se elimino la utilidad `src/coderag/ui/staging.py`; el staging espejo en
  `DATA_DIR/ingestion_staging` queda solo como compatibilidad legacy para
  limpieza de documentos historicos ya staged.

## [0.3.8] - 2026-05-08

### Changed

- Se eliminaron los endpoints `POST /sources/ingest/file` y
  `POST /sources/ingest/file/async` para consolidar el upload multipart en
  `POST /sources/ingest/files` y `POST /sources/ingest/files/async`.

- La migracion requerida para clientes no es solo de path: incluso para un
  solo archivo, el nombre del campo multipart ahora debe ser `files` en lugar
  de `file`.

## [0.3.7] - 2026-05-07

### Fixed

- `DELETE /sources/documents/{document_id}` ahora limpia nodos `Entity`
  huerfanos en Neo4j despues de resincronizar el grafo del `source_id`
  afectado, evitando residuos de documentos borrados.

### Changed

- `DeleteDocumentResponse` expone la metrica `neo4j_nodes_deleted` para
  reportar cuantos nodos huerfanos fueron eliminados durante el borrado.

## [0.3.6] - 2026-04-28

### Changed

- Invocaciones Vertex ya no dependen de dominios hardcodeados:
  - `VERTEX_AUTH_TOKEN_URL` controla el endpoint OAuth de token
    (default `https://oauth2.googleapis.com/token`).
  - `VERTEX_API_BASE_URL` controla el dominio base API de Vertex
    (default `aiplatform.googleapis.com`, combinado con `VERTEX_LOCATION`).

- Capa de autenticacion Vertex fuerza `token_uri` desde configuracion para
  evitar dependencia del valor embebido en credenciales.

## [0.3.5] - 2026-04-27

### Added

- Nuevo endpoint `POST /sources/ingest/file` para ingesta sincrona por
  `multipart/form-data` con archivo adjunto (`file`) y soporte opcional de
  `filters` JSON en formulario.

- Nuevo endpoint `POST /sources/ingest/file/async` para ingesta asincrona por
  `multipart/form-data` con soporte de encolado local o RQ.

- Capa dedicada `UploadIngestionAdapter` en
  `src/coderag/api/upload_ingestion.py` para staging, validacion y limpieza de
  uploads.

- Cobertura de pruebas para upload endpoint en
  `tests/test_ingest_upload_endpoint.py`.

### Changed

- Dependencias runtime actualizadas para incluir `python-multipart` como
  requisito de FastAPI para endpoints `File/Form`.

- Configuracion extendida con `UPLOAD_STAGING_SHARED` y
  `UPLOAD_MAX_BYTES` para controlar uploads async y limites de tamano.

- Cola async (`src/coderag/jobs/queue.py`) ahora soporta limpieza best-effort
  de staging de uploads al finalizar jobs locales o RQ.

- UI de Ingestion ahora permite seleccionar canal de envio
  `Carpeta (JSON)` o `Archivo (multipart upload)` para probar desde
  interfaz los endpoints `/sources/ingest/file*`.

## [0.3.4] - 2026-04-10

### Added

- Archivos de dependencias separados para runtime headless, desktop y desarrollo:
  `requirements-runtime.txt`, `requirements-desktop.txt` y
  `requirements-dev.txt`.

- `requirements-full.txt` como entrada explicita para entorno local completo.

### Changed

- `requirements.txt` pasa a representar el baseline API/worker.
- `Dockerfile` ahora construye la imagen API/worker con `requirements.txt`
  alineado al contrato API-first para excluir PySide6 y pytest del runtime.

- Documentacion de instalacion y Kubernetes actualizada para reflejar los
  nuevos perfiles de dependencias y el entrypoint estable del worker.

## [0.3.3] - 2026-04-09

### Added

- Nueva capa de autenticacion Vertex en
  `src/coderag/core/vertex_auth.py` con OAuth bearer token basado en
  `VERTEX_SERVICE_ACCOUNT_JSON_B64`.

- Soporte de labels configurables para requests Vertex (answer + embeddings)
  via `VERTEX_LABEL_SERVICE`, `VERTEX_LABEL_SERVICE_ACCOUNT`,
  `VERTEX_LABEL_MODEL_NAME` y `VERTEX_LABEL_USE_CASE_ID`.

- Cobertura de pruebas para auth/labels Vertex en
  `tests/test_vertex_auth_and_labels.py` y casos nuevos en
  `tests/test_embedding_settings.py`.

### Changed

- Migracion de llamadas Vertex para eliminar API key en query params y usar
  `Authorization: Bearer <token>` en:
  - `src/coderag/llm/providerlmm_client.py`
  - `src/coderag/ingestion/embedding.py`
- Contrato de configuracion Vertex actualizado para requerir
  `VERTEX_SERVICE_ACCOUNT_JSON_B64` + `VERTEX_PROJECT_ID`.

- Credencial Vertex ahora soporta `VERTEX_SERVICE_ACCOUNT_JSON_B64`
  (como formato recomendado) con decodificacion en runtime al iniciar app;
  `VERTEX_SERVICE_ACCOUNT_JSON` se mantiene como fallback legacy.

- Plantillas `.env`, manifests Kubernetes y documentacion (`README`,
  `docs/CONFIGURATION.md`, `docs/INSTALLATION.md`,
  `docs/KUBERNETES.md`, `docs/API_REFERENCE.md`) alineadas al nuevo esquema.

- `gcp_credentials_vertex.json` (y variantes) agregado a `.gitignore` para
  uso local de ejemplo sin versionar secretos.

## [0.3.2] - 2026-04-05

### Added

- `HEALTHCHECK` en imagen API (`Dockerfile`) para validar `GET /health`.
- Healthchecks, politicas `restart`, y rotacion de logs en
  `docker-compose.yml` para `api`, `worker`, `redis` y `neo4j`.

- Probes y recursos para Redis/Neo4j en `k8s/overlays/dev`.
- Startup/readiness/liveness probe para `coderag-worker` en Kubernetes.
- `k8s/base/networkpolicy.yaml` con politicas de red para `api`, `worker`,
  `redis` y `neo4j`.

### Changed

- `docker-compose.yml` ahora usa `NEO4J_PASSWORD` por variable de entorno
  en lugar de password fija en texto plano.

- Puertos de infraestructura en compose (`redis`, `neo4j`) ahora quedan
  bind a `127.0.0.1` por defecto para reducir exposicion en dev.

- Pinning de imagenes en runtime:
  - `python:3.12.3-slim` en `Dockerfile`
  - `redis:7.2.4-alpine` en compose/dev overlay
  - `neo4j:5.24.0` en compose/dev overlay
- Plantilla `k8s/base/secret-app.example.yaml` reemplaza password por
  placeholder `REPLACE_ME`.

- Ingress base ahora incluye TLS (`coderag-api-tls`) y redireccion HTTPS.
- Documentacion de instalacion y Kubernetes actualizada para nuevos
  requisitos de seguridad/operacion.

- Dependencia `chromadb` actualizada a `1.5.5` y capa de compatibilidad
  de excepciones en `index_chroma` para soportar API 0.x/1.x sin warnings
  deprecados de Pydantic en tests/runtime.

## [0.3.1] - 2026-04-03

### Added

- Endpoint operativo `GET /sources/ingest/readiness` para diagnosticar
  dependencias de ingesta y recomendar modo `async`/`sync`.

- Selector explicito de modo de ejecucion en Ingestion UI
  (`Asincrono`/`Sincrono`) con precheck de readiness antes de despachar jobs.

- Cobertura de regresion para routing de modo de ingesta en UI/API:
  `tests/test_main_window_ingestion_mode.py` y casos nuevos en
  `tests/test_api_async_toggle.py` y `tests/test_ingestion_view.py`.

- Script unificado `scripts/run_release_gates.py` para ejecutar gates
  `smoke`/`full` de release con preflight, tests y benchmarks.

### Changed

- `MainWindow.ingest` ahora enruta por `_ingestion_mode`: usa
  `/sources/ingest` en `sync` y `/sources/ingest/async` en `async`.

- `IngestionView` cambia automaticamente a `sync` cuando el readiness reporta
  dependencias async no listas, mostrando detalle tecnico de checks.

- Documentacion sincronizada en `README.md` y `docs/API_REFERENCE.md` para
  nuevo endpoint y flujo de modo de ejecucion.

### Fixed

- `GET /jobs/{job_id}` ya no retorna `500` cuando Redis/RQ no es alcanzable
  durante polling; ahora preserva estado local para jobs en fallback async.

## [0.3.0] - 2026-04-01

### Added

- Extension TDM aditiva y opt-in por feature flags:
  `ENABLE_TDM`, `TDM_ENABLE_MASKING`, `TDM_ENABLE_VIRTUALIZATION`,
  `TDM_ENABLE_SYNTHETIC`, `TDM_ADMIN_ENDPOINTS`.

- Nuevas tablas SQLite de catalogo TDM:
  `tdm_schemas`, `tdm_tables`, `tdm_columns`, `tdm_service_mappings`,
  `tdm_masking_rules`, `tdm_virtualization_artifacts`,
  `tdm_synthetic_profiles`.

- Parsers TDM para SQL DDL, OpenAPI y diccionarios de datos.
- Grafo tipado TDM con relaciones:
  `USES_TABLE`, `HAS_COLUMN`, `HAS_PII_CLASS`, `MASKED_BY`,
  `EXPOSES_ENDPOINT`, `BACKED_BY_SCHEMA`.

- Endpoints TDM nuevos:
  - `POST /tdm/ingest`
  - `POST /tdm/query`
  - `GET /tdm/catalog/services/{service_name}`
  - `GET /tdm/catalog/tables/{table_name}`
  - `POST /tdm/virtualization/preview`
  - `GET /tdm/synthetic/profile/{table_name}`
- Modulos de dominio TDM:
  - `src/coderag/tdm/masking_engine.py`
  - `src/coderag/tdm/synthetic_planner.py`
  - `src/coderag/tdm/virtualization_export.py`
- Guia de migracion y checklist de rollout:
  - `docs/migration-guides/MIGRATION_0_2_TDM.md`
  - `docs/TDM_ROLLOUT_CHECKLIST.md`
- Script de preflight de release `scripts/preflight_release.py` para validar
  compatibilidad legacy, dependencias de flags TDM y contrato OpenAPI.

### Changed

- `RagApplicationService.ingest_tdm_assets` ahora sincroniza aristas tipadas
  TDM a Neo4j.

- `RagApplicationService.query_tdm` agrega `masking_preview` cuando
  `TDM_ENABLE_MASKING=true`.

- `RagApplicationService.preview_tdm_virtualization` usa exportador dedicado
  y persiste artefactos en `tdm_virtualization_artifacts` cuando
  `TDM_ENABLE_VIRTUALIZATION=true`.

### Fixed

- Compatibilidad estricta preservada para rutas legacy:
  `/sources/*` y `/query*` se mantienen sin cambios de contrato.

- Rutas `/tdm/*` retornan `404` cuando `ENABLE_TDM=false` para evitar
  activaciones accidentales en despliegues existentes.

## [0.2.6] - 2026-03-31

### Added

- Nuevo perfil de benchmark de release para Gobierno de Datos en
  `docs/benchmarks/complex_queries_release_gobierno_datos_es.json`, con
  preguntas complejas y `required_answer_terms` por caso.

- Nuevos reportes dedicados para este perfil:
  `docs/benchmarks/last_run_release_gobierno_datos_es.json` y
  `docs/benchmarks/last_run_release_gobierno_datos_es.md`.

### Changed

- `scripts/run_multihop_benchmark.py` ahora soporta validacion opcional de
  cobertura semantica por terminos requeridos en respuesta/evidencia, mediante
  `required_answer_terms` y `min_required_answer_terms_hit` (por caso o por
  `thresholds_by_type`).

- Reportes JSON/Markdown/console del benchmark ahora incluyen `terms_hit` para
  facilitar gates de calidad semantica en consultas complejas.

## [0.2.5] - 2026-03-31

### Added

- Benchmark de release en espanol con casos complejos y umbrales por tipo de
  pregunta en `docs/benchmarks/complex_queries_release_es.json`.

- Reportes de benchmark de release en
  `docs/benchmarks/last_run_release_es.json` y
  `docs/benchmarks/last_run_release_es.md`.

### Changed

- `scripts/run_multihop_benchmark.py` ahora soporta dos formatos de entrada:
  lista legacy de casos y esquema extendido con `thresholds_by_type` +
  `cases`, manteniendo compatibilidad hacia atras.

- El benchmark ahora evalua umbrales por tipo de pregunta y publica
  `summary_by_type` en salida JSON/Markdown para gates de calidad por
  categoria.

## [0.2.4] - 2026-03-31

### Added

- Benchmark persistente de consultas complejas en
  `docs/benchmarks/complex_queries.json`.

- Script de evaluacion E2E `scripts/run_multihop_benchmark.py` con salida en
  JSON y Markdown para seguimiento de regresiones multi-hop.

### Changed

- Reranking para consultas complejas reforzado con seleccion tipo
  Maximal Marginal Relevance (MMR) para reducir redundancia y elevar cobertura
  cross-documento.

## [0.2.3] - 2026-03-31

### Added

- Nuevas metricas de diagnostico de diversidad documental en `/query`:
  `retrieval_unique_documents` y `reranked_unique_documents`.

- Pruebas de regresion para cobertura multi-documento en reranking,
  contexto y fallback local.

### Changed

- Reranking reforzado con normalizacion lexica (acentos/casefold),
  `token_overlap`, `phrase_overlap` y seleccion diversificada para
  consultas complejas.

- Ensamblado de contexto ahora intercala chunks por documento y reserva
  espacio para paths de grafo, reduciendo sesgo por truncado secuencial.

- Fallback local extractivo en LLM ahora sintetiza hallazgos desde varios
  documentos en lugar de depender de un unico chunk dominante.

- Deteccion de entidades en ingesta/grafo mejorada para textos en espanol
  con acentos y entidades multi-palabra.

### Fixed

- Expansion de grafo multi-hop ahora puede restringirse por `source_id`,
  evitando mezclar rutas de otras fuentes durante consulta filtrada.

## [0.2.2] - 2026-03-31

### Added

- Staging automatico en UI para fuentes `folder`: la carpeta seleccionada
  se copia a `storage/ingestion_staging` antes de enviar la ingesta.

- Nueva utilidad de staging en `src/coderag/ui/staging.py` con limpieza de
  directorios antiguos para controlar crecimiento en disco.

### Changed

- `MainWindow.ingest` ahora ejecuta un preflight de staging y envia al
  backend una ruta relativa al repo, compatible con runtime local y Docker.

- Documentacion (`README`, `docs/CONFIGURATION.md`) actualizada para reflejar
  que no se requieren mapeos manuales por carpeta.

### Fixed

- Ingesta de rutas arbitrarias seleccionadas por usuario (incluyendo rutas
  Windows fuera del repo) en despliegues Docker/Rancher sin configurar
  volumenes nuevos por cada carpeta.

## [0.2.1] - 2026-03-30

### Added

- Checklist operativo de release UI en `docs/UI_RELEASE_CHECKLIST.md` con
  validaciones de estilo, accesibilidad, atajos y regresion.

- Nuevas pruebas UI para `EvidenceView` (orden por score, detalle de fila,
  truncado de snippet y render de graph paths).

### Changed

- Pulido final de UX UI: microcopy unificado en espanol, mensajes de error
  accionables y ajustes de densidad visual para mejor legibilidad.

- Estados visuales de Query/Ingestion refinados para mostrar badge compacto
  y mensajes operativos consistentes en runtime.

### Fixed

- Cobertura de regresion UI ampliada y alineada a textos localizados en
  pruebas de Ingestion/Query.

## [0.2.0] - 2026-03-27

### Added

- Integracion activa de ChromaDB en runtime para persistencia y busqueda
  vectorial de chunks.

- Configuracion dedicada de Chroma por entorno: `USE_CHROMA`,
  `CHROMA_PERSIST_DIR`, `CHROMA_COLLECTION`.

- Script de operacion `scripts/cold_reset.ps1` para reset cold end-to-end:
  detiene API/UI, limpia Chroma completo, elimina metadata local, limpia
  aristas Neo4j y reinicia servicios.

- Timeline de ingesta persistido por job (`job_events`) con pasos,
  progreso y tiempos acumulados.

- UI de ingesta con visualizacion en vivo del progreso (`progress_pct`) y
  resumen temporal por etapa.

- Nuevos parametros de performance de ingesta:
  `INGEST_EMBED_WORKERS`, `CHROMA_UPSERT_BATCH_SIZE`.

- Parametros de tuning Neo4j para ingesta:
  `NEO4J_INGEST_BATCH_SIZE`, `NEO4J_INGEST_MAX_RETRIES`,
  `NEO4J_INGEST_RETRY_DELAY_MS`.

- Parametro de consulta `include_llm_answer` para seleccionar entre
  `retrieval_only` (hybrid+grafo sin LLM) y `with_llm` (hybrid+grafo+LLM).

- Selector en UI de consulta para enviar el modo de respuesta al endpoint
  `/query`.

### Changed

- Pipeline de embeddings migrado a proveedores reales (OpenAI, Gemini,
  Vertex) para ingesta y consulta.

- Eliminado fallback operativo a embeddings locales en memoria para el flujo
  de retrieval vectorial.

- Documentacion (`README`, `CONFIGURATION`, `API_REFERENCE`,
  `ARCHITECTURE`) alineada con el nuevo runtime vectorial.

- Persistencia de documentos en lote en SQLite para reducir commits por
  documento.

- Escritura de aristas a Neo4j optimizada con `UNWIND` en lote.
- Indexacion vectorial optimizada con embeddings en paralelo y upsert por
  lotes.

- Persistencia Neo4j ahora usa transacciones por bloque con reintentos
  acotados para fallas transitorias.

- Default recomendado ajustado para `NEO4J_INGEST_BATCH_SIZE=500` en
  optimizacion orientada a tiempo total de ingesta.

- **BREAKING**: payload publico de ingesta/jobs reemplaza `elapsed_ms` por
  `elapsed_hhmmss` (`hh:mm:ss`) en `steps` y `metrics`.

- `/query` ahora expone diagnosticos operativos de modo y LLM:
  `requested_mode`, `effective_mode`, `llm_invoked`,
  `llm_provider_effective`, `llm_model_effective`, `llm_error`.

### Fixed

- `reset_all` ahora limpia tambien la coleccion vectorial activa de Chroma.
- Ingestion UI ahora muestra progreso y timeline en vivo tambien con
  `USE_RQ=false` usando worker async local (sin fallback bloqueante sync).

- Worker RQ compatible con Windows (`SimpleWorker` + `TimerDeathPenalty`)
  para evitar fallas por `SIGALRM`.

- Timeout de ingesta RQ ahora configurable via
  `RQ_INGEST_JOB_TIMEOUT_SEC` (default `900`) para evitar fallas por
  limite default de `180s` en cargas largas.

- La primera consulta tras ingesta async ya no reindexa vectores completos en
  el proceso API: el refresh por version reconstruye solo BM25 para reducir
  latencia y evitar timeouts iniciales.

- Timeout de consulta desde UI aumentado de 60s a 180s para reducir errores
  transitorios en primer query posterior a ingestas grandes.

- Jobs RQ ahora se marcan como `failed` en metadata local si el worker lanza
  excepcion, evitando estados `queued` permanentes.

- Consistencia de consulta tras ingesta async: `/query` ahora detecta cambios
  en indices persistidos y refresca retrieval automaticamente en el proceso
  API sin requerir reinicio.

- `source_id` en `/query` ahora filtra retrieval BM25/vector de forma real,
  evitando resultados mezclados de otras fuentes.

- Modo LLM estricto en consulta (`include_llm_answer=true` y
  `force_fallback=false`): si falla el provider remoto, se evita fallback
  silencioso y se retorna error explicito.

- Robustez de persistencia post-restart: rutas relativas de `workspace_dir`,
  `data_dir` y `CHROMA_PERSIST_DIR` ahora se normalizan a absolutas contra el
  root del repositorio para evitar drift entre procesos API/UI.

- `src/main.py` y `src/run_ui.py` fijan CWD al root del repositorio al iniciar,
  reduciendo inconsistencias cuando se ejecutan desde otras carpetas.

- Diagnostico de ingesta por carpeta reforzado: ahora diferencia entre ruta
  no encontrada, ruta no directorio y carpeta sin extensiones soportadas,
  incluyendo conteo real de archivos escaneados y sugerencias de rutas cercanas.

- Expansion de paths de grafo reforzada para consultas en minusculas: cuando
  no se detectan entidades por patron capitalizado, se resuelven semillas de
  entidades en Neo4j a partir de tokens de la pregunta.

## [0.1.1] - 2026-03-27

### Added

- Documento tecnico de arquitectura con resumen, descripcion general y
  diagramas Mermaid de capas, componentes y secuencias para ingesta y consulta.

### Changed

- `README.md` actualizado con endpoint `POST /sources/reset`, soporte `.htm`
  y referencia a `docs/ARCHITECTURE.md`.

- `docs/API_REFERENCE.md` actualizado con ejemplos de respuesta real para
  ingesta, jobs y diagnosticos de consulta.

## [0.1.0] - 2026-03-26

### Added

- Estructura completa del proyecto `coderag/`.
- API FastAPI con endpoints de salud, ingesta, estado de job y query.
- Endpoint `POST /sources/ingest/async` con Redis + RQ opcional.
- UI PySide6 con vistas de ingesta, consulta y evidencias.
- Pipeline RAG hibrido funcional (vector + BM25 + grafo).
- Persistencia local en SQLite para documentos, chunks, grafo y jobs.
- Integracion opcional Neo4j para expansion de paths multi-hop.
- Cliente LLM con soporte configurable para local, OpenAI, Gemini y Vertex AI.
- Datos de ejemplo en `sample_data/`.
- Tests de flujo end-to-end y nuevos tests para fallback/async.

### Changed

- N/A

### Fixed

- N/A
