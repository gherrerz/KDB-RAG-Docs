# RAG Hybrid Response Validator - Instrucciones de Construccion para Agentes LLM

## Prompt Maestro para Agente de IA Constructor

Este documento define instrucciones completas para que un agente LLM construya un sistema RAG hibrido de analisis documental empresarial, alineado a la implementacion real actual del proyecto.

La construccion objetivo debe permitir:

1. Ingestar documentos empresariales desde carpeta local y flujos multipart.
2. Construir retrieval hibrido con vector, lexical en Postgres y grafo.
3. Responder preguntas con trazabilidad y evidencias verificables.
4. Operar por UI de escritorio y API HTTP.
5. Extender capacidades TDM de forma opt-in y gobernada por feature flags.

---

## 1. Objetivo del sistema

Construir una aplicacion llamada RAG Hybrid Response Validator con interfaz grafica y API que habilite:

### Ingesta

- Carga de documentos desde carpeta local.
- Carga de documentos via multipart.
- Integracion Confluence existente como placeholder de arquitectura.
- Parseo de formatos soportados.
- Chunking semantico.
- Embeddings con proveedor configurable.
- Persistencia en Postgres, Chroma remoto y grafo opcional.

### Consulta

- Preguntas en lenguaje natural.
- Recuperacion hibrida lexical y vector.
- Expansion por grafo en consultas multi-hop.
- Respuesta con LLM remoto o fallback local.
- Evidencia trazable por citas y diagnosticos.

---

## 2. Arquitectura general

El sistema implementa:

Hybrid Retrieval + Graph expansion + Multi-hop reasoning + Diagnostics-driven grounding

Componentes principales:

- UI de escritorio en PySide6.
- Backend en FastAPI.
- Vector store en Chroma remoto.
- Lexical index en Postgres FTS.
- Grafo en Neo4j.
- Capa de LLM con proveedores local, OpenAI, Gemini y Vertex.

Ajustes de realidad frente a la vision inicial:

- No existe soporte Anthropic en la implementacion actual.
- Confluence existe en contrato, pero su cliente actual es placeholder.
- Chroma embebido no es modo operativo valido en runtime Docs.

---

## 3. Arquitectura de modulos Python

Estructura modular esperada:

- ui: vistas, presenters y cliente HTTP.
- api: rutas FastAPI y adaptador de ingesta multipart.
- core: modelos, settings, runtime, orquestacion, servicios extraidos.
- ingestion: loader, scanner, chunker, embeddings, indexado vectorial y grafo.
- retrieval: busqueda hibrida, rerank, expansion y assembly de contexto.
- llm: cliente de proveedor y prompts.
- parsers: parseadores por formato y parseadores TDM.
- storage: capa Postgres e interfaces de estado runtime.
- jobs: cola con RQ y fallback local.

Regla de construccion:

- Mantener separacion por contratos de aplicacion.
- Evitar acoplar UI con logica de dominio.
- Mantener API y modelos compatibles con contratos vigentes.

---

## 4. Flujo de ingesta

## Paso 1 - Conectar fuente documental

Entradas de contrato:

- source_type
- local_path o fuente multipart
- filtros opcionales
- tags opcionales
- artifact_id opcional para async multipart

Comportamiento real:

- source_type folder es el camino operativo principal.
- source_type confluence existe pero hoy no retorna contenido real.
- En multipart async, los artifacts se persisten temporalmente en Postgres para rehidratacion del worker.

---

## Paso 2 - Escaneo y parseo de contenido

El sistema detecta y parsea archivos soportados:

- md
- txt
- html
- htm
- pdf
- docx
- doc
- pptx
- xlsx

Comportamiento clave:

- Recorre carpeta de forma recursiva.
- Conserva origen logico en path_or_url.
- Reporta diagnosticos de escaneo y parseo.
- Omite contenido vacio.

---

## Paso 3 - Chunking y materializacion

Pipeline de materializacion:

1. Construccion de chunks semanticos.
2. Extraccion de relaciones para grafo documental.
3. Persistencia de documentos y chunks.
4. Rebuild de indices lexical y vector.
5. Sincronizacion de grafo gestionado por source_id.

Reglas operativas:

- Deduplicacion por title y content_type antes de persistir.
- Si hay reemplazos, limpiar residuos previos en metadata, vector y grafo.
- Mantener eventos y progreso de job para trazabilidad.

---

## 5. Vector Database (Chroma)

Contrato de runtime actual:

- Chroma obligatorio para retrieval vectorial.
- Modo remoto obligatorio.
- Coleccion configurable por entorno.
- Embeddings segun proveedor configurado.

Comportamiento esperado:

- Inicializar cliente HTTP con auth opcional por token o basic auth.
- Validar coleccion y compatibilidad de espacio HNSW.
- Exponer diagnosticos de disponibilidad y causa de error.

---

## 6. Grafo de conocimiento (Neo4j)

Modelo real documental:

- Nodo principal: Entity
- Relacion principal: RELATES_TO

Modelo TDM tipado:

- Relacion base: TDM_REL
- Tipos permitidos:
- USES_TABLE
- HAS_COLUMN
- HAS_PII_CLASS
- MASKED_BY
- EXPOSES_ENDPOINT
- BACKED_BY_SCHEMA

Regla de operacion:

- Si USE_NEO4J es false, la consulta central sigue operativa sin expansion.
- TDM sin Neo4j opera en modo degradado con diagnostico explicito.

---

## 7. Indice lexical

Se utiliza Postgres FTS para retrieval lexical.

Principios:

- Postgres es backend objetivo de runtime.
- El indice lexical participa en hybrid retrieval.
- La salud lexical debe entrar en readiness operativo.
- La configuracion de lenguaje FTS debe ser parametrizable.

---

## 8. Pipeline de consultas

Pipeline completo esperado:

1. Normalizacion de consulta.
2. Hybrid retrieval lexical y vector.
3. Reranking.
4. Expansion de grafo opcional.
5. Assembly de contexto.
6. Llamada al LLM si include_llm_answer es true.
7. Entrega de respuesta con citations, graph_paths y diagnostics.

---

## 9. Hybrid Retrieval

Combinacion esperada:

- Vector search en Chroma remoto.
- Lexical search en Postgres FTS.
- Fusion de candidatos.

Valor inicial recomendado:

- top_n = 60

---

## 10. Reranking

Objetivo:

- Ordenar por relevancia final de evidencia.

Valor inicial recomendado:

- top_k = 15

---

## 11. Expansion por grafo

Objetivo:

- Recuperar caminos semanticos de soporte para preguntas multi-hop.

Valor inicial recomendado:

- hops = 2

Regla de degradacion:

- Sin Neo4j, graph_paths debe quedar vacio sin romper contrato de respuesta.

---

## 12. Context Assembly

El contexto final debe incluir:

- snippets relevantes
- referencias de origen
- seccion y offsets cuando aplique
- paths de grafo cuando existan

Tamano maximo recomendado:

- max_context_chars = 16000

---

## 13. Uso de proveedores LLM

Proveedores soportados actualmente:

- local
- openai
- gemini
- vertex y vertex_ai

Comportamiento esperado:

- Resolver proveedor efectivo por configuracion o request.
- Permitir fallback local controlado.
- Exponer proveedor y modelo efectivo en diagnostics.
- En modo strict, elevar error de proveedor si falla invocacion remota.

Nota de alineacion:

- OpenAI usa Responses API.
- No incluir Anthropic como capacidad implementada.

---

## 14. Politica anti-alucinacion

Reglas obligatorias:

1. No inventar entidades, relaciones ni citas.
2. Toda afirmacion debe estar soportada por evidencia textual o path de grafo.
3. Si no hay evidencia suficiente, responder exactamente:
No se encontro informacion en las fuentes indexadas.
4. En preguntas multi-hop, priorizar soporte con rutas de grafo.
5. Si una capacidad esta deshabilitada por flags, informarlo en diagnostics.

---

## 15. Interfaz grafica

Framework:

- PySide6

Subvistas operativas:

- Ingestion
- Query
- Evidence
- TDM

### Ingesta UI

Debe permitir:

- source type
- ruta local o seleccion de archivos
- modo sync o async
- filtros y tags opcionales
- seguimiento de progreso y estado de job

### Consulta UI

Debe permitir:

- pregunta
- filtros por source_id o document_ids
- proveedor llm opcional
- lectura de respuesta, citas y rutas de grafo

### TDM UI

Debe permitir:

- ingesta TDM
- query TDM
- catalogo por servicio y tabla
- preview de virtualizacion
- perfil sintetico

---

## 16. API Backend (FastAPI)

Endpoints principales de salud y consulta:

- GET /health
- GET /readiness
- POST /query
- POST /query/retrieval

Endpoints de ingesta y jobs:

- POST /sources/ingest
- POST /sources/ingest/files
- POST /sources/ingest/async
- POST /sources/ingest/files/async
- GET /sources/ingest/readiness
- GET /jobs/{job_id}
- DELETE /sources/reset?confirm=true

Endpoints de catalogo y mantenimiento:

- GET /sources/documents
- GET /sources/tags
- PUT /sources/documents/{document_id}/tags
- DELETE /sources/documents/{document_id}

Endpoints TDM:

- POST /tdm/ingest
- POST /tdm/query
- GET /tdm/catalog/services/{service_name}
- GET /tdm/catalog/tables/{table_name}
- POST /tdm/virtualization/preview
- GET /tdm/synthetic/profile/{table_name}

Shape de respuesta de consulta:

- answer
- citations
- graph_paths
- diagnostics

---

## 17. Cola de trabajos

Modo async soportado:

- Redis y RQ cuando USE_RQ es true.
- Worker local en thread cuando USE_RQ es false.
- Fallback automatico a worker local si Redis no esta disponible.

Tipos de trabajo efectivos:

- ingesta de source
- ingesta multipart
- polling de estado por job
- rehidratacion de artifacts multipart en worker

---

## 18. Estrategia incremental

Lineamientos de estado actual:

- Existe deduplicacion por clave funcional de documento.
- Se reemplaza contenido previo equivalente antes de reindexar.
- Se reconstruyen indices para mantener consistencia de consulta.
- En reset, se limpia estado persistido y runtime asociado.

---

## 19. Seguridad

Reglas operativas:

- No hardcodear credenciales en codigo.
- Usar variables de entorno para secretos.
- Tratar Chroma y Postgres como dependencias criticas de readiness.
- Mantener aislamiento de base para entorno Docs.
- Exponer errores operativos de forma estructurada y accionable.

---

## 20. Criterios de aceptacion

El sistema se considera alineado cuando:

1. Ingesta y consulta funcionan en flujo folder y multipart.
2. Retrieval hibrido entrega evidencia trazable.
3. Diagnosticos reportan modo efectivo y estado de dependencias.
4. Contratos API y UI permanecen compatibles.
5. TDM respeta feature flags y degradacion controlada.
6. Tests relevantes pasan en verde.

---

## 21. Entregables

El repositorio construido debe incluir:

- Aplicacion Python funcional con UI y API.
- Configuracion por entorno para Postgres, Chroma remoto y Neo4j.
- Soporte async con RQ opcional y fallback local.
- Suite de pruebas con pytest.
- Documentacion consistente con comportamiento real.

---

## 22. Instrucciones para agentes de IA que modifiquen este repo

Al generar codigo en este proyecto:

1. Tratar este documento como contrato de implementacion actual, no como vision futura abstracta.
2. No proponer componentes no existentes como si ya estuvieran productivos.
3. Si agregas nueva capacidad, documentar si queda en estado implemented, partial o planned.
4. Preservar compatibilidad con endpoints existentes y payloads usados por UI y tests.
5. Mantener consistencia con README y docs/API_REFERENCE.

### 22.1 Formato propuesto de carpetas, subcarpetas y archivos

Raiz:

- src
- docs
- tests
- migrations
- scripts
- sample_data
- storage
- requirements.txt
- requirements-runtime.txt
- requirements-desktop.txt
- requirements-dev.txt
- requirements-full.txt
- Dockerfile
- docker-compose.yml
- README.md
- CHANGELOG.md

Entrypoints:

- src/main.py
- src/run_ui.py

API:

- src/coderag/api/server.py
- src/coderag/api/upload_ingestion.py

Core:

- src/coderag/core/models.py
- src/coderag/core/settings.py
- src/coderag/core/runtime.py
- src/coderag/core/service.py
- src/coderag/core/composition.py
- src/coderag/core/ingestion_service.py
- src/coderag/core/query_service.py
- src/coderag/core/tdm_policy_service.py
- src/coderag/core/tdm_ingestion_service.py
- src/coderag/core/tdm_query_service.py
- src/coderag/core/index_coordinator_service.py
- src/coderag/core/graph_store.py

Ingestion:

- src/coderag/ingestion/document_loader.py
- src/coderag/ingestion/repo_scanner.py
- src/coderag/ingestion/chunker.py
- src/coderag/ingestion/embedding.py
- src/coderag/ingestion/index_chroma.py
- src/coderag/ingestion/graph_builder.py
- src/coderag/ingestion/confluence_client.py
- src/coderag/ingestion/tdm_ingestion.py
- src/coderag/ingestion/tdm_graph_builder.py

Retrieval:

- src/coderag/retrieval/hybrid_search.py
- src/coderag/retrieval/reranker.py
- src/coderag/retrieval/graph_expand.py
- src/coderag/retrieval/context_assembler.py

LLM:

- src/coderag/llm/providerlmm_client.py
- src/coderag/llm/prompts.py

Parsers:

- src/coderag/parsers/generic_parser.py
- src/coderag/parsers/markdown_parser.py
- src/coderag/parsers/html_parser.py
- src/coderag/parsers/pdf_parser.py
- src/coderag/parsers/doc_parser.py
- src/coderag/parsers/docx_parser.py
- src/coderag/parsers/pptx_parser.py
- src/coderag/parsers/xlsx_parser.py
- src/coderag/parsers/sql_schema_parser.py
- src/coderag/parsers/data_dictionary_parser.py
- src/coderag/parsers/openapi_service_parser.py

Storage:

- src/coderag/storage/hybrid_metadata_store.py
- src/coderag/storage/metadata_store.py
- src/coderag/storage/lexical_store.py
- src/coderag/storage/postgres_session.py
- src/coderag/storage/postgres_schema.py
- src/coderag/storage/postgres_startup.py
- src/coderag/storage/postgres_document_chunk_store.py
- src/coderag/storage/postgres_job_state_store.py
- src/coderag/storage/postgres_ingestion_artifact_store.py
- src/coderag/storage/postgres_tdm_store.py

Jobs:

- src/coderag/jobs/queue.py
- src/coderag/jobs/worker.py

UI:

- src/coderag/ui/main_window.py
- src/coderag/ui/api_client.py
- src/coderag/ui/ingestion_view.py
- src/coderag/ui/ingestion_presenter.py
- src/coderag/ui/query_view.py
- src/coderag/ui/query_presenter.py
- src/coderag/ui/tdm_view.py
- src/coderag/ui/tdm_presenter.py
- src/coderag/ui/evidence_view.py
- src/coderag/ui/document_catalog_controller.py

Documentacion principal:

- docs/API_REFERENCE.md
- docs/ARCHITECTURE.md
- docs/CONFIGURATION.md
- docs/INSTALLATION.md
- docs/DESIGN_DECISIONS.md
- docs/TDM_UI_OPERATIONS.md
- docs/TDM_ROLLOUT_CHECKLIST.md

### 22.2 Reglas de ubicacion por responsabilidad

- UI y presentacion solo en src/coderag/ui.
- Endpoints HTTP solo en src/coderag/api.
- Casos de uso y orquestacion en src/coderag/core.
- Parseo e ingesta en src/coderag/ingestion y src/coderag/parsers.
- Recuperacion en src/coderag/retrieval.
- Persistencia e infraestructura de datos en src/coderag/storage.
- Jobs y ejecucion asincrona en src/coderag/jobs.
- Documentacion funcional y operativa en docs.
- Pruebas en tests reflejando contratos API, core y UI.

### 22.3 Convenciones para nuevos archivos

- Un archivo por responsabilidad concreta.
- Evitar mezclar logica de UI con logica de dominio.
- Mantener nombres explicitos por modulo y flujo.
- Si se agrega endpoint nuevo, agregar test y actualizar API reference.
- Si se agrega flag nuevo, documentarlo en configuracion y README.

### 22.4 Criterio de aceptacion estructural

Un cambio estructural se considera correcto si:

1. Respeta esta jerarquia de carpetas.
2. Mantiene separacion de responsabilidades.
3. No rompe importaciones ni entrypoints existentes.
4. Incluye actualizacion documental y cobertura de pruebas asociada.

---

## Fin del documento
