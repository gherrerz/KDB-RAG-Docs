# Configuration

La configuracion principal se define en `src/coderag/core/settings.py`.

## Target Contract Approved For Cutover

La configuración final aprobada para este proyecto está orientada a:

- Postgres como backend obligatorio de metadata operacional.
- Chroma remoto como backend obligatorio de vectores.
- Neo4j como backend de grafo y TDM.

Durante el cutover todavía pueden aparecer en esta página parámetros que describen el runtime actual.
Cuando haya conflicto entre parámetros legacy y contrato objetivo, prevalece [docs/DESIGN_DECISIONS.md](DESIGN_DECISIONS.md).

Decisiones cerradas relevantes para configuración:

- `workspace_dir` no forma parte del contrato final como dependencia operativa persistente.
- `CHROMA_PERSIST_DIR` no forma parte del contrato final como storage vectorial objetivo.
- La ingesta async de archivos locales no debe depender de `UPLOAD_STAGING_SHARED` como requisito final del runtime; el target es rehidratación desde artifacts temporales en Postgres.

## Bootstrap Actual Del Cutover

El runtime ya acepta el contrato nuevo de configuración para preparar el cutover,
y opera con Postgres como store efectivo de metadata documental.

- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD` ya están soportados por `settings.py`.
- `POSTGRES_POOL_SIZE`, `POSTGRES_POOL_TIMEOUT` y `RUNTIME_ENVIRONMENT` ya controlan el bootstrap y la policy de startup de Alembic/Postgres.
- `CHROMA_MODE`, `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_TOKEN`, `CHROMA_USERNAME` y `CHROMA_PASSWORD` ya están soportados por el contrato de settings.
- Estado actual: el arranque requiere DSN de Postgres válido, valida heads de Alembic y falla explícitamente cuando `POSTGRES_*` está ausente. Jobs, job_events, runtime_state/index_version, documents, chunks, catálogo TDM y upload artifacts async se enrutan a Postgres. Los edges documentales se resuelven en Neo4j y ya no se persisten en Postgres. El endpoint multipart async persiste artifacts directamente en Postgres al encolar y los workers rehidratan batches desde esos artifacts, por lo que `UPLOAD_STAGING_SHARED` deja de ser un requisito funcional; el staging temporal en filesystem queda sólo para flujos locales legacy fuera de ese path async. La capa vectorial operativa final usa cliente remoto; `embedded` queda sólo como valor legacy no soportado operativamente.
- En base compartida con KDB-RAG-Repo, Alembic debe quedar aislado por aplicacion: Docs usa `alembic_version_docs` y Repo usa `alembic_version_repo`; no se debe usar `alembic_version` por defecto.
- Runbook operativo de Fase 6:
  [migration-guides/alembic-shared-db-cutover.md](migration-guides/alembic-shared-db-cutover.md).

## Parameters

## Controles administrativos

- `ADMIN_RESET_ENABLED`: expone `POST /admin/reset` solo cuando vale `true`.
- `ADMIN_RESET_TOKEN`: token obligatorio para autorizar el reset global cuando
  `ADMIN_RESET_ENABLED=true`.
- Si `ADMIN_RESET_ENABLED=true` y `ADMIN_RESET_TOKEN` esta vacio, el runtime
  considera la configuracion invalida y falla al construir settings.
- La UI desktop y cualquier script operador que invoque `POST /admin/reset`
  deben usar el mismo `ADMIN_RESET_TOKEN` configurado en la API protegida.

- `data_dir`: carpeta de trabajo local para staging legacy puntual,
  uploads transitorios y artefactos no-relacionales; no se usa como
  backend de metadata runtime
- `max_context_chars`: limite de contexto ensamblado
- `graph_hops`: cantidad de saltos para expansion en grafo
- `retrieval_top_n`: candidatos iniciales del retrieval hibrido
- `rerank_top_k`: resultados finales para respuesta y evidencia
- `embedding_size`: dimension esperada para compatibilidad de pipeline
- `ingest_embed_workers`: concurrencia para embeddings durante ingesta
- `chroma_upsert_batch_size`: lote de escritura para upserts en Chroma

## Docker Compose local

- `CHROMA_IMAGE`: override opcional solo para `docker-compose.yml`; si no se
  define, el compose usa `chromadb/chroma:0.5.5`.
- `NEO4J_IMAGE`: override opcional solo para `docker-compose.yml`; si no se
  define, el compose usa `neo4j:5`.
- `REDIS_IMAGE`: override opcional solo para `docker-compose.yml`; si no se
  define, el compose usa `redis:7.2.4-alpine`.
- `USE_RQ`: en `docker-compose.yml` controla el modo async de la API; para el
  profile `async`, exportarlo como `true` para que `/sources/ingest/async`
  use Redis RQ en vez del worker local en proceso.
- `API_HOST` y `API_PORT`: bind host/port usados por `python src/main.py`
  fuera de Docker Compose; `PORT` funciona como fallback si `API_PORT` no
  esta definido.
- `API_BASE_URL`: URL base que usa `python src/run_ui.py` para hablar con la
  API; si no esta definido, la UI deriva la URL desde `API_HOST` y
  `API_PORT`, normalizando `0.0.0.0` a `127.0.0.1`.
- `UI_API_HOST` y `UI_API_PORT`: overrides opcionales para la UI cuando debe
  hablar con una API distinta al bind compartido.
- `CHROMA_HOST_PORT`, `POSTGRES_HOST_PORT`, `NEO4J_HTTP_HOST_PORT`,
  `NEO4J_BOLT_HOST_PORT`, `API_HOST_PORT` y `REDIS_HOST_PORT` permiten mover
  bindings host para convivencia con otros stacks locales como KDB-RAG-Repo.

### Resolucion de rutas de almacenamiento

- `data_dir` y `CHROMA_PERSIST_DIR` aceptan rutas relativas o absolutas.
- Si son relativas, el runtime las normaliza contra el root del repositorio
  para evitar drift al iniciar API/UI desde directorios distintos.
- Recomendacion operativa: en ambientes multi-servicio o scripts externos,
  usar rutas absolutas explicitas en `.env`.

## Vector store actual

- `USE_CHROMA`: debe estar en `true` para habilitar runtime vectorial.
- `CHROMA_MODE`: el runtime final soporta `remote`; si recibe `embedded`, readiness y operaciones fallan de forma explicita para forzar el cutover.
- `CHROMA_PERSIST_DIR`: ruta legacy de compatibilidad; ya no se usa como backend vectorial operativo.
- `CHROMA_HOST` y `CHROMA_PORT`: destino del servicio Chroma cuando `CHROMA_MODE=remote`.
- `CHROMA_TOKEN` o `CHROMA_USERNAME` + `CHROMA_PASSWORD`: autenticación para
  Chroma remoto. **Recomendado habilitarla** como mitigación de CVE-2026-45829
  ("ChromaToast", RCE pre-auth en el servidor Chroma): el servidor debe rechazar
  peticiones no autenticadas y no exponerse públicamente. El runtime usa el
  cliente delgado `chromadb-client` (no incluye el código del servidor
  vulnerable). `CHROMA_TOKEN` se envía como `Authorization: Bearer <token>`.
- `CHROMA_COLLECTION`: coleccion activa donde se guardan chunks+embeddings.
- `INGEST_EMBED_WORKERS`: numero de workers para generar embeddings en
  paralelo durante `rebuild` de indice vectorial.
- `CHROMA_UPSERT_BATCH_SIZE`: cantidad de chunks por lote en cada upsert a
  Chroma.
- Los chunks se persisten en Postgres y tambien se indexan en Chroma con
  embeddings reales durante ingesta.
- Las consultas generan el embedding del query con el mismo provider/modelo
  configurado y buscan vecinos similares en Chroma.
- No existe fallback a embeddings locales cuando faltan credenciales o falla
  el proveedor de embedding.

## LLM providers

- `LLM_PROVIDER`: `local`, `openai`, `gemini`, `vertex`
  - Compatibilidad: `vertex_ai` tambien es aceptado como alias.
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL` (default `https://api.openai.com/v1`)
- `OPENAI_ANSWER_MODEL`
- `OPENAI_EMBEDDING_MODEL` (default `text-embedding-3-small`)
- `GEMINI_API_KEY`
- `GEMINI_ANSWER_MODEL`
- `GEMINI_EMBEDDING_MODEL` (default `text-embedding-004`)
- `VERTEX_SERVICE_ACCOUNT_JSON_B64` (JSON de service account en base64)
- `VERTEX_PROJECT_ID`
- `VERTEX_LOCATION`
- `VERTEX_AUTH_TOKEN_URL` (default `https://oauth2.googleapis.com/token`)
- `VERTEX_API_BASE_URL` (default `aiplatform.googleapis.com`)
- `VERTEX_ANSWER_MODEL`
- `VERTEX_EMBEDDING_MODEL` (default `text-embedding-005`)
- `VERTEX_LABEL_SERVICE` (default `webspec-coipo`)
- `VERTEX_LABEL_SERVICE_ACCOUNT` (default `qa-anthos`)
- `VERTEX_LABEL_MODEL_NAME` (fallback opcional; se infiere dinamicamente)
- `VERTEX_LABEL_USE_CASE_ID` (default `tbd`)
- `LLM_EMBEDDING` (override global opcional para el modelo de embedding)
- `LLM_REQUEST_TIMEOUT_SEC` (default `120`): timeout en segundos de las llamadas
  HTTP a los proveedores de respuesta (OpenAI/Gemini/Vertex). Subirlo evita que
  respuestas fundamentadas largas excedan el límite y caigan en `503` strict.
- `LLM_MAX_OUTPUT_TOKENS` (default `4096`): cota de tokens de salida aplicada al
  payload de los tres proveedores; acota latencia y costo por llamada.

### Plantillas .env por provider

El repositorio incluye plantillas listas para copiar segun provider:

- `.env.openai.example`
- `.env.gemini.example`
- `.env.vertex.example`

Uso sugerido en Windows PowerShell:

```powershell
Copy-Item .env.openai.example .env
```

Reemplaza `openai` por `gemini` o `vertex` segun el caso, luego completa
las credenciales necesarias.

### Resolucion de modelo de embedding

Precedencia:

1. `LLM_EMBEDDING` (si esta definido)
2. Modelo por proveedor segun `LLM_PROVIDER`
   (`OPENAI_EMBEDDING_MODEL`, `GEMINI_EMBEDDING_MODEL`,
   `VERTEX_EMBEDDING_MODEL`)
3. Sin fallback local: si no hay credenciales/provider valido, la operacion
  falla con error explicito.

### Credenciales Vertex (sin API key)

- El provider `vertex` usa autenticacion OAuth con service account.
- `VERTEX_SERVICE_ACCOUNT_JSON_B64` debe contener el JSON completo de la
  cuenta de servicio codificado en base64.
- En el arranque de la app, el runtime decodifica ese valor y deja el JSON
  disponible en memoria para uso interno de autenticacion.
- En pruebas locales puedes cargarlo desde archivo con PowerShell:
  `$env:VERTEX_SERVICE_ACCOUNT_JSON_B64 = (Get-Content gcp_credentials_vertex.base64.txt -Raw)`.
- `VERTEX_PROJECT_ID` es obligatorio para llamadas de answer y embeddings.
- `VERTEX_AUTH_TOKEN_URL` permite configurar el endpoint OAuth para emitir
  bearer tokens de Vertex (default `https://oauth2.googleapis.com/token`).
- `VERTEX_API_BASE_URL` define el dominio base para invocaciones Vertex y se
  combina con `VERTEX_LOCATION` para formar hosts como
  `https://us-central1-aiplatform.googleapis.com`.
- Compatibilidad: `VERTEX_SERVICE_ACCOUNT_JSON` (raw JSON) se mantiene como
  fallback legacy, pero el formato recomendado es base64.
- No se usa `VERTEX_AI_API_KEY` en este runtime.

### Labels Vertex

- Todas las llamadas Vertex (answer y embeddings) adjuntan labels para
  trazabilidad.
- `model_name` se ajusta automaticamente al modelo real de cada operacion:
  `VERTEX_ANSWER_MODEL` para respuestas y el modelo efectivo de embedding
  para vectorizacion.
- Los labels se resuelven desde `VERTEX_LABEL_*` y se normalizan a formato
  seguro (`lowercase`, espacios a `-`, sin caracteres invalidos).

### Fallback de respuesta LLM

- Para la fase de embeddings: no existe fallback local; si falla el provider,
  la operacion falla con error explicito.
- Para la fase de respuesta final: existe fallback extractivo local en
  `ProviderLlmClient` cuando el provider remoto falla o cuando
  `force_fallback=true`.

## Graph and async integration

La aplicacion carga automaticamente variables desde `.env` en runtime.

- `USE_NEO4J`: habilita la capa de grafo cuando vale `true`.
- Con `USE_NEO4J=false`, la API core sigue operativa sin expansion por grafo,
  pero TDM queda deshabilitado en modo degradado.
- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `NEO4J_INGEST_BATCH_SIZE`: tamano de bloque para escrituras `UNWIND`
  durante persistencia de relaciones.
  Valor recomendado inicial: `500` para optimizar tiempo total de ingesta
  en cargas medianas/grandes.
- `NEO4J_INGEST_MAX_RETRIES`: reintentos maximos por bloque cuando hay
  fallas transitorias de red/lock.
- `NEO4J_INGEST_RETRY_DELAY_MS`: espera base (ms) entre reintentos.
- `USE_RQ`: habilita endpoint de ingesta asincrona
- `REDIS_URL`: conexion para cola RQ
- `RQ_INGEST_JOB_TIMEOUT_SEC`: timeout (segundos) para jobs de ingesta en
  RQ. Default `900`. Aumentar en ingestas largas para evitar errores por
  timeout de worker.
- `UPLOAD_MAX_BYTES`: limite maximo por archivo para endpoints de upload
  multipart (`/sources/ingest/files*`). Default `26214400` (25 MB).

Para ingesta `folder`, la UI enumera recursivamente los archivos soportados del
directorio elegido y los envia por multipart al backend.
`DATA_DIR/ingestion_staging` queda solo como compatibilidad para limpieza de
documentos legacy ya staged o para flujos locales que aun usen rutas staged.
El reset solo toca ese mirror cuando existen documentos historicos bajo esa
ruta.

Para upload async (`POST /sources/ingest/files/async`) con `USE_RQ=true`,
el API persiste artifacts temporales en Postgres y el worker rehidrata esos
archivos sin requerir staging compartido por filesystem.

Ejemplo rapido Neo4j local:

```dotenv
USE_NEO4J=true
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_INGEST_BATCH_SIZE=500
NEO4J_INGEST_MAX_RETRIES=2
NEO4J_INGEST_RETRY_DELAY_MS=150
```

Ejemplo sin Neo4j:

```dotenv
USE_NEO4J=false
```

En este modo la ingesta y query core siguen disponibles, pero los endpoints
`/tdm/*` responden en modo degradado y no realizan operaciones TDM.

## Source payload

Ejemplo `folder`:

```json
{
  "source": {
    "source_type": "folder",
    "local_path": "sample_data",
    "base_url": null,
    "token": null,
    "filters": {}
  }
}
```

Ejemplo `confluence`:

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

Ejemplo `tdm_folder` (catalogo de esquemas/servicios):

```json
{
  "source": {
    "source_type": "tdm_folder",
    "local_path": "sample_data",
    "filters": {}
  }
}
```

## Query payload

```json
{
  "question": "Who works on Project Atlas?",
  "source_id": null,
  "hops": 2,
  "llm_provider": "local",
  "force_fallback": false,
  "include_llm_answer": true
}
```

## Security notes

- No persistas tokens en texto plano.
- Usa variables de entorno o keyring para integraciones reales.

## TDM feature flags (opt-in)

Los siguientes flags habilitan capacidades TDM de forma aditiva.
Todos default en `false` para preservar compatibilidad estricta con
la funcionalidad y servicios actuales.

- `ENABLE_TDM`: activa rutas y flujos TDM nuevos cuando existan.
- `TDM_ENABLE_MASKING`: habilita capacidades de politicas de enmascaramiento.
- `TDM_ENABLE_VIRTUALIZATION`: habilita capacidades de virtualizacion.
- `TDM_ENABLE_SYNTHETIC`: habilita capacidades de perfiles sinteticos.
- `TDM_ADMIN_ENDPOINTS`: habilita endpoints administrativos TDM.

Notas operativas:

- `ENABLE_TDM=true` habilita los endpoints `/tdm/*`.
- `TDM_ENABLE_VIRTUALIZATION=true` habilita la generacion/persistencia de
  templates en `/tdm/virtualization/preview`.
- `TDM_ENABLE_SYNTHETIC=true` habilita la planificacion sintetica en
  `/tdm/synthetic/profile/{table_name}`.
- `TDM_ENABLE_MASKING=true` habilita previews de enmascaramiento en
  respuestas de consulta TDM.

Ejemplo:

```dotenv
ENABLE_TDM=false
TDM_ENABLE_MASKING=false
TDM_ENABLE_VIRTUALIZATION=false
TDM_ENABLE_SYNTHETIC=false
TDM_ADMIN_ENDPOINTS=false
```
