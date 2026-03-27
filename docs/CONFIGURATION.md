# Configuration

La configuracion principal se define en `coderag/core/settings.py`.

## Parameters

- `workspace_dir`: carpeta de trabajo
- `data_dir`: carpeta donde se guarda `metadata.db`
- `max_context_chars`: limite de contexto ensamblado
- `graph_hops`: cantidad de saltos para expansion en grafo
- `retrieval_top_n`: candidatos iniciales del retrieval hibrido
- `rerank_top_k`: resultados finales para respuesta y evidencia
- `embedding_size`: dimension esperada para compatibilidad de pipeline

## Vector store actual

- `USE_CHROMA`: debe estar en `true` para habilitar runtime vectorial.
- `CHROMA_PERSIST_DIR`: directorio de persistencia local de ChromaDB.
- `CHROMA_COLLECTION`: coleccion activa donde se guardan chunks+embeddings.
- Los chunks se persisten en SQLite y tambien se indexan en Chroma con
  embeddings reales durante ingesta.
- Las consultas generan el embedding del query con el mismo provider/modelo
  configurado y buscan vecinos similares en Chroma.
- No existe fallback a embeddings locales cuando faltan credenciales o falla
  el proveedor de embedding.

## LLM providers

- `LLM_PROVIDER`: `openai`, `gemini`, `vertex`
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

## Graph and async integration

La aplicacion carga automaticamente variables desde `.env` en runtime.

- `USE_NEO4J`: habilita escritura/lectura de paths multi-hop en Neo4j
- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `USE_RQ`: habilita endpoint de ingesta asincrona
- `REDIS_URL`: conexion para cola RQ

Ejemplo rapido Neo4j local:

```dotenv
USE_NEO4J=true
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

## Source payload

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

## Query payload

```json
{
  "question": "Who works on Project Atlas?",
  "source_id": null,
  "hops": 2,
  "llm_provider": "local",
  "force_fallback": false
}
```

## Security notes

- No persistas tokens en texto plano.
- Usa variables de entorno o keyring para integraciones reales.
