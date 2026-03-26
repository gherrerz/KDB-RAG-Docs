# Changelog

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
