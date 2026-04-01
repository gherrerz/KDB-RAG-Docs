# Changelog

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
- `run_api.py` y `run_ui.py` fijan CWD al root del repositorio al iniciar,
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
