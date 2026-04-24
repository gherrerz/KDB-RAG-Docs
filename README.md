# RAG Hybrid Response Validator

Aplicacion Python para ingesta documental y consulta con RAG hibrido
(vector + BM25 + grafo) con UI de escritorio (PySide6) y API (FastAPI).

## Features

- Ingesta de documentos locales (`.md`, `.txt`, `.html`, `.htm`, `.pdf`, `.docx`,
  `.doc`, `.pptx`, `.xlsx`) y Confluence (`source_type=confluence`)
- Pipeline de chunking semantico por secciones
- Recuperacion hibrida: vectorial + BM25
- Expansion por grafo multi-hop
- Respuesta con evidencia y trazabilidad
- Citas textuales de respuesta LLM priorizan nombre de documento/archivo
  con extension cuando esta disponible
  (los `chunk_id` se mantienen en `citations` para trazabilidad tecnica)
- Soporte de proveedores LLM: OpenAI, Gemini y Vertex AI
- Seleccion de provider por entorno (`LLM_PROVIDER`) con soporte para
  `local`, `openai`, `gemini` y `vertex` (`vertex_ai` como alias)
- Modelo de embedding configurable por provider y override global por
  `LLM_EMBEDDING`
- ChromaDB activo en runtime para persistencia y busqueda vectorial
- Embeddings reales por proveedor durante ingesta y consulta
- UI para operacion de ingesta y consultas
- UI renovada con tema visual editorial-industrial y mejor jerarquia
- Validacion anticipada de formularios en Ingestion/Query con ayudas contextuales
- Seguimiento de ingesta con estado visual, barra de progreso y resumen ejecutivo
- Vista de evidencia mejorada: tabla ordenable, detalle por fila y paths mas legibles
- Paneles tecnicos colapsables (diagnostics/raw JSON) y atajos de teclado para operacion rapida
- Microcopy unificado en espanol y errores accionables en Ingestion/Query
- UI de ingesta con polling async en vivo (RQ o worker local sin Redis)
- API REST para integracion externa
- Ingesta asincrona opcional con Redis + RQ
- Ingesta asincrona local sin Redis cuando `USE_RQ=false`
- Trazabilidad de ingesta en UI con timeline en vivo, pasos y metricas
- Boton `BORRAR TODO` en Ingestion para reset completo de BM25, vector,
  grafo y jobs antes de una nueva primera ingesta
- Persistencia de eventos por job para diagnosticar cuellos de botella
- Optimización de ingesta: embeddings en paralelo y upsert vectorial por lotes

## Arquitectura

- UI: PySide6
- API: FastAPI
- Vector index: `ChromaVectorIndex` persistente en `CHROMA_PERSIST_DIR`
- BM25: `rank-bm25`
- Grafo: Neo4j opcional para persistencia y expansion de paths
- Storage metadata: SQLite en `storage/metadata.db`

### Estado del vector store

- El runtime requiere `USE_CHROMA=true`.
- `USE_NEO4J=true` habilita persistencia y expansion por grafo.
- `USE_NEO4J=false` mantiene operativos ingest/query core con
  `graph_paths=[]` y sin persistencia de aristas en Neo4j.
- Los embeddings se calculan con el proveedor configurado (`openai`,
  `gemini` o `vertex`) y se guardan en ChromaDB.
- No existe fallback a embeddings locales en memoria cuando falta
  configuracion/credenciales.

## TDM (opt-in)

- Extension TDM aditiva para catalogo esquema-servicio, grafo tipado,
  masking preview, virtualizacion preview y planificacion sintetica.
- Los endpoints `/tdm/*` requieren `ENABLE_TDM=true`.
- Los endpoints `/tdm/*` tambien requieren `USE_NEO4J=true`; si
  `USE_NEO4J=false`, responden `HTTP 200` en modo degradado con mensaje
  explicito de indisponibilidad.
- Endpoints disponibles:
  - `POST /tdm/ingest`
  - `POST /tdm/query`
  - `GET /tdm/catalog/services/{service_name}`
  - `GET /tdm/catalog/tables/{table_name}`
  - `POST /tdm/virtualization/preview` (requiere `TDM_ENABLE_VIRTUALIZATION=true`)
  - `GET /tdm/synthetic/profile/{table_name}` (requiere `TDM_ENABLE_SYNTHETIC=true`)
- Feature flags:
  - `ENABLE_TDM`
  - `TDM_ENABLE_MASKING`
  - `TDM_ENABLE_VIRTUALIZATION`
  - `TDM_ENABLE_SYNTHETIC`
  - `TDM_ADMIN_ENDPOINTS`
- Referencias:
  - [docs/TDM_ROLLOUT_CHECKLIST.md](docs/TDM_ROLLOUT_CHECKLIST.md)
  - [docs/migration-guides/MIGRATION_0_2_TDM.md](docs/migration-guides/MIGRATION_0_2_TDM.md)
  - [docs/TDM_UI_OPERATIONS.md](docs/TDM_UI_OPERATIONS.md)

## Requisitos

- Python 3.11+
- Windows, Linux o macOS

## Instalacion

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Opciones de instalacion:

- `requirements.txt`: baseline API/worker para levantar el backend con foco runtime.
- `requirements-runtime.txt`: alias explicito del perfil liviano de API/worker.
- `requirements-desktop.txt`: runtime + UI de escritorio.
- `requirements-full.txt`: entorno completo para desarrollo local (API + UI + tests).

## Ejecucion

1. Iniciar API:

```bash
python src/main.py
```

2. Iniciar UI en otra terminal:

```bash
python src/run_ui.py
```

3. En la UI, pestaña Ingestion:
- `Source Type`: `folder`
- `Modo de ejecucion`: `Asincrono (cola + jobs)` o `Sincrono (directo)`
- `Local Path`: [sample_data](sample_data/)
- Click en `Ingest`
- Si modo async no esta listo, la UI recomienda/usa modo sync para evitar bloqueo.
- Antes de persistir, la ingesta elimina versiones previas ya ingestadas que
  coincidan por `title + content_type`, incluyendo borrado logico y limpieza
  fisica del mirror en `storage/ingestion_staging` cuando aplica.
- Si el mismo lote trae varias copias con igual `title + content_type`, se
  conserva una sola version de forma determinista y se descartan las demas
  antes de indexar.

4. En la pestaña Query, preguntar por ejemplo:
- `Who works on Project Atlas?`
- `Which procedure depends on Policy FIN-001?`
- `Source ID` sigue siendo opcional para acotar por una ingesta concreta.
- `Documentos (opcional)` permite seleccionar uno o varios documentos ya
  ingestados para limitar la consulta a ese subconjunto.

5. En la pestaña TDM (nueva):
- Usar `Ingerir TDM` para invocar `POST /tdm/ingest`.
- Usar `Consultar TDM` para invocar `POST /tdm/query`.
- Usar `Catalogo por servicio` y `Catalogo por tabla` para consultar
  `GET /tdm/catalog/services/{service_name}` y
  `GET /tdm/catalog/tables/{table_name}`.
- Usar `Preview de virtualizacion` para `POST /tdm/virtualization/preview`.
- Usar `Perfil sintetico` para
  `GET /tdm/synthetic/profile/{table_name}`.
- Si `ENABLE_TDM=false`, la UI mostrara mensaje explicito de TDM deshabilitado.
- Si `USE_NEO4J=false`, la UI recibira respuestas degradadas para TDM y debe
  tratarlas como capacidad no disponible.
- Si una capacidad esta deshabilitada por flag (virtualization/synthetic),
  la UI mostrara el hint correspondiente para activar el flag correcto.
- Si el backend devuelve `503`, la UI mostrara estado de indisponibilidad
  temporal para facilitar diagnostico operativo.
- La pestaña TDM muestra resultados en una tabla estructurada con panel de
  detalle JSON por fila, ademas del panel de JSON crudo completo.
- La vista TDM usa paneles por seccion (tipo acordeon) y scroll para mejorar
  legibilidad en ventanas pequenas o con escalado alto.
- Puedes filtrar filas de resultados por texto y exportar las filas visibles
  a JSON crudo con `Exportar filas visibles`.
- El filtro de resultados combina selector por tipo (`finding`,
  `service_mapping`, `table`, `column`, etc.) y busqueda por texto.
- Acciones rapidas por fila: copiar JSON de la fila, copiar
  `endpoint/metodo`, y cargar la fila seleccionada al panel JSON crudo.
- Atajos de teclado en TDM: `Ctrl+Shift+C` (copiar fila JSON),
  `Ctrl+Shift+E` (copiar endpoint/metodo), `Ctrl+Shift+L`
  (cargar fila en raw), `Ctrl+Shift+X` (exportar filas visibles).
- Guia operativa detallada: [docs/TDM_UI_OPERATIONS.md](docs/TDM_UI_OPERATIONS.md).

## API Endpoints

- `GET /health`
- `POST /sources/ingest`
- `POST /sources/reset`
- `POST /sources/ingest/async`
- `GET /sources/ingest/readiness`
- `GET /sources/documents`
- `GET /jobs/{id}`
- `POST /query`
- `POST /query/retrieval`

Ejemplo `POST /sources/ingest`:

```json
{
  "source": {
    "source_type": "folder",
    "local_path": "sample_data"
  }
}
```

Ejemplo `POST /sources/ingest` para Confluence:

```json
{
  "source": {
    "source_type": "confluence",
    "base_url": "https://your-domain.atlassian.net/wiki",
    "token": "your-api-token",
    "filters": {}
  }
}
```

Ejemplo `POST /query`:

```json
{
  "question": "Who works on Project Atlas?",
  "hops": 2,
  "llm_provider": "openai",
  "force_fallback": false,
  "include_llm_answer": true
}
```

Para modo retrieval-only (sin invocar LLM):

```json
{
  "question": "Who works on Project Atlas?",
  "hops": 2,
  "include_llm_answer": false
}
```

Ejemplo `POST /sources/ingest/async`:

```json
{
  "source": {
    "source_type": "folder",
    "local_path": "sample_data"
  }
}
```

Respuesta:

```json
{
  "job_id": "rq-job-id",
  "status": "queued",
  "message": "Ingestion job enqueued"
}
```

Nota: si `USE_RQ=false`, el backend devuelve
`"message": "Ingestion job started (local async worker)"`.

Ejemplo `POST /sources/reset`:

```json
{
  "confirm": true
}
```

Respuesta:

```json
{
  "status": "completed",
  "message": "All repositories were cleared, indexes were reset, and 3 staging mirror entries were removed.",
  "deleted_documents": 19,
  "deleted_chunks": 961,
  "deleted_graph_edges": 204,
  "deleted_jobs": 10,
  "neo4j_enabled": true,
  "neo4j_edges_deleted": 204
}
```

## Testing

En Windows (recomendado en este repo):

```bash
.venv\Scripts\python.exe -m pytest -q
```

Gate unificado de release (preflight + regresion smoke):

```bash
.venv\Scripts\python.exe scripts\run_release_gates.py --mode smoke
```

Gate full (incluye regresion completa y benchmarks de release):

```bash
.venv\Scripts\python.exe scripts\run_release_gates.py --mode full
```

Preflight de release (compatibilidad legacy + readiness TDM):

```bash
.venv\Scripts\python.exe scripts\preflight_release.py --skip-http
```

Con API levantada, validar tambien contrato OpenAPI:

```bash
.venv\Scripts\python.exe scripts\preflight_release.py --base-url http://127.0.0.1:8000
```

Benchmark E2E de consultas complejas (multi-hop y multi-documento):

```bash
.venv\Scripts\python.exe scripts\run_multihop_benchmark.py --fail-on-threshold
```

Benchmark de release en espanol con umbrales por tipo de pregunta:

```bash
.venv\Scripts\python.exe scripts\run_multihop_benchmark.py --benchmark-file docs/benchmarks/complex_queries_release_es.json --output-json docs/benchmarks/last_run_release_es.json --output-md docs/benchmarks/last_run_release_es.md --fail-on-threshold
```

Benchmark de release para Gobierno de Datos (preguntas reales + patrones
minimos en respuesta/evidencia):

```bash
.venv\Scripts\python.exe scripts\run_multihop_benchmark.py --benchmark-file docs/benchmarks/complex_queries_release_gobierno_datos_es.json --output-json docs/benchmarks/last_run_release_gobierno_datos_es.json --output-md docs/benchmarks/last_run_release_gobierno_datos_es.md --fail-on-threshold
```

Nota: este perfil requiere tener previamente ingerido el corpus de Gobierno de
Datos en la fuente activa. Si el `source_id` activo solo contiene
[sample_data](sample_data/), el gate fallara por `required_answer_terms_hit`.

Tip: si ejecutas `--mode full` sobre `sample_data`, puedes evitar falsos
negativos en benchmark usando:

```bash
.venv\Scripts\python.exe scripts\run_release_gates.py --mode full --skip-benchmarks
```

Artefactos de salida del benchmark:
- [docs/benchmarks/complex_queries.json](docs/benchmarks/complex_queries.json) (casos)
- [docs/benchmarks/complex_queries_release_es.json](docs/benchmarks/complex_queries_release_es.json) (casos de release + `thresholds_by_type`)
- [docs/benchmarks/complex_queries_release_gobierno_datos_es.json](docs/benchmarks/complex_queries_release_gobierno_datos_es.json) (release Gobierno de Datos + `required_answer_terms`)
- [docs/benchmarks/last_run.json](docs/benchmarks/last_run.json) (resultado estructurado)
- [docs/benchmarks/last_run.md](docs/benchmarks/last_run.md) (reporte legible)
- [docs/benchmarks/last_run_release_es.json](docs/benchmarks/last_run_release_es.json) (resultado release)
- [docs/benchmarks/last_run_release_es.md](docs/benchmarks/last_run_release_es.md) (reporte release por tipo)
- [docs/benchmarks/last_run_release_gobierno_datos_es.json](docs/benchmarks/last_run_release_gobierno_datos_es.json) (resultado release Gobierno de Datos)
- [docs/benchmarks/last_run_release_gobierno_datos_es.md](docs/benchmarks/last_run_release_gobierno_datos_es.md) (reporte release Gobierno de Datos)

## Cleanup artifacts

Para limpiar artefactos locales sin usar `Remove-Item` (bloqueado en algunos
entornos):

```bash
.venv\Scripts\python.exe scripts/clean_artifacts.py --remove-metadata-db
```

Opcional para incluir caches dentro de `.venv`:

```bash
.venv\Scripts\python.exe scripts/clean_artifacts.py --include-venv --remove-metadata-db
```

Reset cold completo (detiene servicios, borra Chroma completo + metadata,
limpia staging espejo de ingesta, limpia aristas Neo4j y vuelve a levantar
API/UI):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\cold_reset.ps1 -Force
```

Opciones utiles:
- `-SkipStart`: no vuelve a levantar servicios.
- `-SkipUI`: levanta solo API.
- `-ApiPort 8000`: puerto usado para validar `/health`.
- Si `USE_RQ=true`, tambien inicia automaticamente un worker RQ para la cola
  `ingestion`.

## Configuracion

Ver:
- [docs/INSTALLATION.md](docs/INSTALLATION.md)
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/UI_RELEASE_CHECKLIST.md](docs/UI_RELEASE_CHECKLIST.md)

Variables relevantes de entorno:
- `LLM_PROVIDER`: provider para consulta y embeddings (`local`, `openai`,
  `gemini`, `vertex`)
- Nota: para embeddings el runtime requiere provider externo
  (`openai`/`gemini`/`vertex`); `local` aplica a respuesta extractiva.
- Para `vertex`, el runtime usa `VERTEX_SERVICE_ACCOUNT_JSON_B64` +
  `VERTEX_PROJECT_ID` (sin API keys).
- `LLM_EMBEDDING`: override global opcional para modelo de embedding
- `INGEST_EMBED_WORKERS`: workers para generar embeddings en paralelo
- `CHROMA_UPSERT_BATCH_SIZE`: tamano de lote por escritura en Chroma
- `USE_CHROMA`: debe estar en `true` para habilitar vector store runtime
- `CHROMA_PERSIST_DIR`: carpeta local de persistencia de Chroma
- `CHROMA_COLLECTION`: nombre de coleccion activa de vectores
- `NEO4J_INGEST_BATCH_SIZE`: tamano de bloque para `UNWIND` en persistencia
  de grafo
  recomendado inicial: `500` para priorizar tiempo total end-to-end
- `NEO4J_INGEST_MAX_RETRIES`: reintentos por bloque Neo4j ante fallas
  transitorias
- `NEO4J_INGEST_RETRY_DELAY_MS`: espera base en milisegundos para reintentos
- `OPENAI_EMBEDDING_MODEL`, `GEMINI_EMBEDDING_MODEL`,
  `VERTEX_EMBEDDING_MODEL`: modelos por provider
- `VERTEX_LABEL_SERVICE`, `VERTEX_LABEL_SERVICE_ACCOUNT`,
  `VERTEX_LABEL_MODEL_NAME`, `VERTEX_LABEL_USE_CASE_ID`: labels de
  trazabilidad para requests Vertex (defaults en `.env.vertex.example`).
- `RQ_INGEST_JOB_TIMEOUT_SEC`: timeout en segundos para ingestas async con
  RQ (`USE_RQ=true`). Default: `900`.

Para ingesta `folder`, la UI realiza staging automatico de la carpeta
seleccionada hacia `DATA_DIR/ingestion_staging`.
Luego envia esa ruta al backend (`api`/`worker`) para que funcione igual
en runtime local y en Docker/Rancher, sin configurar mapeos por carpeta.

Plantillas listas para copiar:
- [.env.openai.example](.env.openai.example)
- [.env.gemini.example](.env.gemini.example)
- [.env.vertex.example](.env.vertex.example)

## Estado y roadmap

Este MVP es funcional end-to-end con vector store persistente en ChromaDB.
El diseño de modulos permite evolucionar componentes opcionales como:
- Redis + RQ para jobs asincronos (opcional con `USE_RQ=true`)
- Proveedores LLM (OpenAI, Gemini, Vertex AI)

## Observabilidad de ingesta

- Durante la ingesta, la UI muestra progreso (`progress_pct`) y timeline de
  pasos con `elapsed_hhmmss` por paso (`hh:mm:ss`).
- `GET /jobs/{id}` devuelve `steps` persistidos por job para diagnostico,
  incluso en ejecuciones asincronas.
- Cuando una ingesta async (`USE_RQ=true`) termina en `completed`, el API
  refresca retrieval en el siguiente `/query` automaticamente sin reiniciar
  servicios (reconstruye BM25 en memoria y reutiliza vectores ya persistidos
  en Chroma).
- El resumen visual de progreso permite detectar rapidamente etapas lentas
  (parseo, chunking, grafo o indexacion).

## Consistencia de consulta

- `source_id` en `/query` aplica filtro real sobre retrieval BM25/vector.
- Si `source_id` no existe, `citations` retorna vacio en lugar de mezclar
  resultados de otras fuentes.
- En preguntas complejas, el reranking aplica diversidad documental para
  reducir colapso de resultados sobre un solo documento cuando existe
  evidencia relevante en multiples fuentes.
- El ensamblado de contexto ahora intercala chunks por documento antes de
  truncar por longitud para mejorar cobertura en consultas multi-hop.
- La expansion de grafo con `source_id` restringe paths a relaciones
  asociadas a la misma fuente consultada.
- `/query` soporta dos modos via `include_llm_answer`:
  - `true`: retrieval+grafo+respuesta LLM (markdown estructurado)
  - `false`: retrieval+grafo sin LLM (`answer=""` para consumo por otros
    agentes)
- En modo LLM estricto (`include_llm_answer=true` y `force_fallback=false`),
  fallas de provider remoto retornan error en lugar de fallback silencioso.
- En fallback local (`force_fallback=true` o `LLM_PROVIDER=local`), la
  respuesta extractiva sintetiza hallazgos desde varios documentos cuando
  existe evidencia multi-documento.
- El reranking para consultas complejas aplica una etapa adicional tipo
  Maximal Marginal Relevance (MMR) para reducir redundancia semantica entre
  chunks y mejorar cobertura cross-documento.
