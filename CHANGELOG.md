# Changelog

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
