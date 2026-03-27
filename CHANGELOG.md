# Changelog

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
