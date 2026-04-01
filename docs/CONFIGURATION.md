# Configuration

La configuracion principal se define en `src/coderag/core/settings.py`.

## Parameters

- `workspace_dir`: carpeta de trabajo
- `data_dir`: carpeta donde se guarda `metadata.db`
- `max_context_chars`: limite de contexto ensamblado
- `graph_hops`: cantidad de saltos para expansion en grafo
- `retrieval_top_n`: candidatos iniciales del retrieval hibrido
- `rerank_top_k`: resultados finales para respuesta y evidencia
- `embedding_size`: dimension esperada para compatibilidad de pipeline
- `ingest_embed_workers`: concurrencia para embeddings durante ingesta
- `chroma_upsert_batch_size`: lote de escritura para upserts en Chroma

### Resolucion de rutas de almacenamiento

- `workspace_dir`, `data_dir` y `CHROMA_PERSIST_DIR` aceptan rutas relativas
  o absolutas.
- Si son relativas, el runtime las normaliza contra el root del repositorio
  para evitar drift al iniciar API/UI desde directorios distintos.
- Recomendacion operativa: en ambientes multi-servicio o scripts externos,
  usar rutas absolutas explicitas en `.env`.

## Vector store actual

- `USE_CHROMA`: debe estar en `true` para habilitar runtime vectorial.
- `CHROMA_PERSIST_DIR`: directorio de persistencia local de ChromaDB.
- `CHROMA_COLLECTION`: coleccion activa donde se guardan chunks+embeddings.
- `INGEST_EMBED_WORKERS`: numero de workers para generar embeddings en
  paralelo durante `rebuild` de indice vectorial.
- `CHROMA_UPSERT_BATCH_SIZE`: cantidad de chunks por lote en cada upsert a
  Chroma.
- Los chunks se persisten en SQLite y tambien se indexan en Chroma con
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
- `VERTEX_AI_API_KEY`
- `VERTEX_PROJECT_ID`
- `VERTEX_LOCATION`
- `VERTEX_ANSWER_MODEL`
- `VERTEX_EMBEDDING_MODEL` (default `text-embedding-005`)
- `LLM_EMBEDDING` (override global opcional para el modelo de embedding)

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

### Fallback de respuesta LLM

- Para la fase de embeddings: no existe fallback local; si falla el provider,
  la operacion falla con error explicito.
- Para la fase de respuesta final: existe fallback extractivo local en
  `ProviderLlmClient` cuando el provider remoto falla o cuando
  `force_fallback=true`.

## Graph and async integration

La aplicacion carga automaticamente variables desde `.env` en runtime.

- `USE_NEO4J`: debe estar en `true` (Neo4j es obligatorio en runtime)
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

Para ingesta `folder`, la UI hace staging automatico del directorio elegido
por el usuario hacia `storage/ingestion_staging` dentro del repositorio.
El backend consume esa ruta staged, visible tanto para `api` como `worker`
en Docker Compose por el montaje del repo (`./:/app`).

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
