# RAG Hybrid Response Validator

Aplicacion Python para ingesta documental y consulta con RAG hibrido
(vector + lexical + grafo) con UI de escritorio (PySide6) y API (FastAPI).

## Estado Del Cutover

La arquitectura objetivo aprobada para este repositorio es Postgres + Chroma remoto + Neo4j.
Ese es el contrato final de runtime que guiará la implementación del cutover.

Mientras el trabajo de migración siga en curso, algunas secciones de este README y de la documentación
todavía describen la implementación actual. Cuando haya conflicto entre estado actual y arquitectura
objetivo, la referencia autoritativa para el target del cutover es [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md).

Decisiones cerradas para la implementación:

- Las tablas nuevas de Docs en Postgres deben usar el prefijo `Tbl_Documents_`.
- `path_or_url` debe conservar el origen original del documento.
- La deduplicación mantiene la regla actual basada en `title + content_type`.
- No habrá migración histórica desde SQLite; la ruta acordada es reset + reingesta.
- No habrá dual-write prolongado entre storage legacy y storage objetivo.
- La ingesta async con archivos locales persiste artifacts temporales en Postgres al encolar y rehidrata desde ahí durante la ejecución, sin depender de filesystem compartido.

## Features

- Ingesta de documentos locales (`.md`, `.txt`, `.html`, `.htm`, `.pdf`, `.docx`,
  `.doc`, `.pptx`, `.xlsx`) y Confluence (`source_type=confluence`)
- Pipeline de chunking semantico por secciones
- Recuperacion hibrida: vectorial + lexical Postgres
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
- Tags opcionales por documento durante ingesta y filtro de catalogo por tags
- Trazabilidad de ingesta en UI con timeline en vivo, pasos y metricas
- Boton `BORRAR TODO` en Ingestion para reset completo de indice lexico, vector,
  grafo y jobs antes de una nueva primera ingesta
- Persistencia de eventos por job para diagnosticar cuellos de botella
- Optimización de ingesta: embeddings en paralelo y upsert vectorial por lotes

## Arquitectura

Nota de contrato: la arquitectura listada debajo todavía refleja en parte el estado actual de implementación.
El contrato objetivo aprobado para el cutover es Postgres + Chroma remoto + Neo4j; ver [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md).

- UI: PySide6
- API: FastAPI
- Vector index: `ChromaVectorIndex` solo en modo `remote`
- Lexical index: Postgres FTS sobre `Tbl_Documents_LexicalCorpus`
- Grafo: Neo4j opcional para persistencia y expansion de paths
- Storage metadata: Postgres como runtime objetivo; `storage/metadata.db`
  ya no es backend operativo cuando `POSTGRES_*` esta configurado.

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

Variables opcionales para el bind local del entrypoint:

- `API_HOST`: host de escucha para `src/main.py` (default `0.0.0.0`).
- `API_PORT`: puerto de escucha para `src/main.py` (default `8000`).
- `PORT`: fallback compatible con plataformas que inyectan solo `PORT`.

1. Iniciar UI en otra terminal:

```bash
python src/run_ui.py
```

Variables opcionales para apuntar la UI a una API distinta:

- `API_BASE_URL`: override explicito completo, por ejemplo
  `http://127.0.0.1:8010`.
- Si no defines `API_BASE_URL`, `src/run_ui.py` reutiliza `API_HOST` y
  `API_PORT`; cuando `API_HOST=0.0.0.0`, la UI lo normaliza a
  `127.0.0.1` para conectarse localmente.
- `UI_API_HOST` y `UI_API_PORT`: overrides opcionales cuando la UI debe
  hablar con una API distinta al bind compartido.
- Si no defines nada, `src/run_ui.py` usa `http://127.0.0.1:8000`.

1. En la UI, pestaña Ingestion:

- `Source Type`: `folder`
- `Canal de envio`: `Carpeta (multipart recursivo)` o `Archivo (multipart upload)`
- `Modo de ejecucion`: `Asincrono (cola + jobs)` o `Sincrono (directo)`
- `Local Path`: carpeta cuando usas `Carpeta (multipart recursivo)` o uno/multiples
  archivos cuando usas `Archivo (multipart upload)` (separados por `;`).
- `Origen persistido`: `path_or_url` queda en formato logico estable. Para
  carpetas locales usa el nombre de la raiz ingresada; para multipart
  recursivo la UI preserva la ruta relativa enviada al backend en lugar de
  persistir paths temporales o absolutos del runtime.
- `Tags`: lista opcional separada por comas; se aplica a los documentos del lote.
- Click en `Ingest`
- `Borrado puntual`: si ya conoces un `document_id`, puedes eliminarlo desde
  el panel de Ingestion con `Eliminar documento`.
- Si modo async no esta listo, la UI recomienda/usa modo sync para evitar bloqueo
  y muestra senales estructuradas de Chroma como `signal`, `target`,
  `collection` y `hnsw_space` cuando existen.
- Antes de persistir, la ingesta elimina versiones previas ya ingestadas que
  coincidan por `title + content_type`, incluyendo borrado logico y limpieza
  fisica del mirror legacy en `storage/ingestion_staging` cuando aplica.
- Si el mismo lote trae varias copias con igual `title + content_type`, se
  conserva una sola version de forma determinista y se descartan las demas
  antes de indexar.

1. En la pestaña Query, preguntar por ejemplo:

- `Who works on Project Atlas?`
- `Which procedure depends on Policy FIN-001?`
- `Source ID` sigue siendo opcional para acotar por una ingesta concreta.
- `Documentos (opcional)` permite seleccionar uno o varios documentos ya
  ingestados para limitar la consulta a ese subconjunto.
- `Tags catalogo (opcional)` filtra el catalogo de documentos por una o mas tags.
- `Facetas de tags` muestra las tags agregadas con cantidad de documentos; al
  hacer click sobre una faceta se aplica ese filtro al catalogo.
- Tras seleccionar uno o varios documentos en Query, `Editar tags` permite
  reemplazar sus tags persistidas sin reingerir el contenido.
- Tras seleccionar documentos en Query, `Eliminar seleccionados` permite
  borrarlos de forma persistente desde la UI usando el endpoint publico
  `DELETE /sources/documents/{document_id}`.

1. En la pestaña TDM (nueva):

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
- `POST /sources/ingest/files`
- `POST /sources/ingest/files/async`
- `DELETE /sources/reset?confirm=true`
- `POST /sources/ingest/async`
- `GET /sources/ingest/readiness`
- `GET /sources/documents`
- `GET /sources/tags`
- `PUT /sources/documents/{document_id}/tags`
- `DELETE /sources/documents/{document_id}`
- `GET /jobs/{id}`
- `POST /query`
- `POST /query/retrieval`

`GET /sources/ingest/readiness` expone checks estructurados de Chroma y del
backend lexico Postgres para diagnostico operativo, incluyendo `signal`,
`mode`, `target`, `collection`, `hnsw_space`, `indexed` y `corpus_rows`
cuando corresponda.

Ejemplo `POST /sources/ingest`:

```json
{
  "source": {
    "source_type": "folder",
    "local_path": "sample_data",
    "tags": ["finance", "urgent"]
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

Ejemplo `POST /sources/ingest/files` (multipart upload sync, uno o mas archivos):

Para un solo archivo, usar igualmente el campo multipart `files`:

```bash
curl -X POST http://127.0.0.1:8000/sources/ingest/files \
  -F "files=@sample_data/engineering.md" \
  -F "source_type=folder" \
  -F 'filters={"domain":"qa"}' \
  -F "tags=finance,urgent"
```

Ejemplo `POST /sources/ingest/files` (multipart upload batch sync):

```bash
curl -X POST http://127.0.0.1:8000/sources/ingest/files \
  -F "files=@sample_data/engineering.md" \
  -F "files=@sample_data/policy_finance.md" \
  -F "source_type=folder" \
  -F 'filters={"domain":"qa"}' \
  -F "tags=finance,urgent"
```

Ejemplo `POST /sources/ingest/files/async` (multipart upload async, uno o mas archivos):

Para un solo archivo, usar igualmente el campo multipart `files`:

```bash
curl -X POST http://127.0.0.1:8000/sources/ingest/files/async \
  -F "files=@sample_data/engineering.md" \
  -F "source_type=folder" \
  -F 'filters={"domain":"qa"}' \
  -F "tags=finance,urgent"
```

Ejemplo `POST /sources/ingest/files/async` (multipart upload batch async):

```bash
curl -X POST http://127.0.0.1:8000/sources/ingest/files/async \
  -F "files=@sample_data/engineering.md" \
  -F "files=@sample_data/policy_finance.md" \
  -F "source_type=folder" \
  -F 'filters={"domain":"qa"}' \
  -F "tags=finance,urgent"
```

Nota: los endpoints multipart persisten `path_or_url` como origen logico
estable. En cargas recursivas desde la UI se conserva el nombre de la carpeta
seleccionada y la ruta relativa interna, sin exponer directorios temporales
del servidor o del worker.

Ejemplo `GET /sources/documents` filtrando por tags del catalogo:

```bash
curl "http://127.0.0.1:8000/sources/documents?source_id=abc123&tags=finance,urgent"
```

Ejemplo `GET /sources/tags` para listar las tags actualmente presentes:

```bash
curl "http://127.0.0.1:8000/sources/tags?source_id=abc123"
```

Respuesta esperada:

```json
{
  "source_id": "abc123",
  "count": 2,
  "tags": ["finance", "urgent"],
  "items": [
    {"tag": "finance", "document_count": 3},
    {"tag": "urgent", "document_count": 1}
  ]
}
```

Ejemplo `PUT /sources/documents/{document_id}/tags` para reemplazar tags de un documento:

```bash
curl -X PUT http://127.0.0.1:8000/sources/documents/7f0a/tags \
  -H "Content-Type: application/json" \
  -d '{"tags": ["legal", "approved"]}'
```

El filtro de `tags` usa semantica OR sobre el catalogo de documentos y no cambia
el contrato de `POST /query` ni de `POST /query/retrieval`.

Nota: si `USE_RQ=true`, los uploads async se rehidratan desde artifacts
temporales en Postgres y ya no requieren `UPLOAD_STAGING_SHARED`.

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

Ejemplo `DELETE /sources/reset?confirm=true`:

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

Gate full (incluye regresion completa y benchmark de release baseline):

```bash
.venv\Scripts\python.exe scripts\run_release_gates.py --mode full
```

Para incluir ademas el benchmark tematico de Gobierno de Datos:

```bash
.venv\Scripts\python.exe scripts\run_release_gates.py --mode full --include-gobierno-datos-benchmark
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
Datos en la fuente activa. [sample_data](sample_data/) ya incluye los
documentos [sample_data/governance_strategy.md](sample_data/governance_strategy.md)
y [sample_data/governance_operating_model.md](sample_data/governance_operating_model.md),
pero debes reingerir `sample_data` despues de actualizar el workspace para que
la fuente activa refleje ese corpus tematico. Si el `source_id` activo no
incluye esos documentos o un corpus equivalente, el benchmark tematico puede
fallar por `required_answer_terms_hit`, por eso no forma parte del gate `full`
baseline salvo que se pida explicitamente con
`--include-gobierno-datos-benchmark`.

Si necesitas correr solo regresion + benchmark baseline sin perfiles
tematicos adicionales:

```bash
.venv\Scripts\python.exe scripts\run_release_gates.py --mode full
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

Para purgar metadata de ingestion artifacts ya expirados en Postgres:

```bash
.venv\Scripts\python.exe scripts/purge_expired_ingestion_artifacts.py
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
- `LEXICAL_FTS_LANGUAGE`: configuracion del diccionario FTS de Postgres para
  retrieval lexico (`english` por defecto)
- Nota: para embeddings el runtime requiere provider externo
  (`openai`/`gemini`/`vertex`); `local` aplica a respuesta extractiva.
- Para `vertex`, el runtime usa `VERTEX_SERVICE_ACCOUNT_JSON_B64` +
  `VERTEX_PROJECT_ID` (sin API keys).
- `VERTEX_AUTH_TOKEN_URL`: endpoint OAuth para obtener bearer token
  (default `https://oauth2.googleapis.com/token`).
- `VERTEX_API_BASE_URL`: dominio base para llamadas Vertex
  (default `aiplatform.googleapis.com`; se combina con `VERTEX_LOCATION`).
- `LLM_EMBEDDING`: override global opcional para modelo de embedding
- `INGEST_EMBED_WORKERS`: workers para generar embeddings en paralelo
- `CHROMA_UPSERT_BATCH_SIZE`: tamano de lote por escritura en Chroma
- `USE_CHROMA`: debe estar en `true` para habilitar vector store runtime
- `CHROMA_PERSIST_DIR`: ruta legacy solo para compatibilidad documental;
  no forma parte del runtime vectorial operativo final
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

Para ingesta `folder`, la UI enumera recursivamente los archivos soportados de
la carpeta seleccionada y los envia por multipart al backend.
El mirror en `DATA_DIR/ingestion_staging` queda solo como compatibilidad para
limpieza condicional de documentos legacy ya staged o para flujos locales
antiguos.

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
  servicios (reconstruye el corpus lexico en Postgres y reutiliza vectores ya persistidos
  en Chroma).
- El resumen visual de progreso permite detectar rapidamente etapas lentas
  (parseo, chunking, grafo o indexacion).

## Consistencia de consulta

- `source_id` en `/query` aplica filtro real sobre retrieval lexical/vector.
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
