# Configuration

La configuracion principal se define en `coderag/core/settings.py`.

## Parameters

- `workspace_dir`: carpeta de trabajo
- `data_dir`: carpeta donde se guarda `metadata.db`
- `max_context_chars`: limite de contexto ensamblado
- `graph_hops`: cantidad de saltos para expansion en grafo
- `retrieval_top_n`: candidatos iniciales del retrieval hibrido
- `rerank_top_k`: resultados finales para respuesta y evidencia
- `embedding_size`: tamano del embedding local deterministico

## LLM providers

- `LLM_PROVIDER`: `local`, `openai`, `gemini`, `vertex_ai`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL` (default `https://api.openai.com/v1`)
- `OPENAI_ANSWER_MODEL`
- `GEMINI_API_KEY`
- `GEMINI_ANSWER_MODEL`
- `VERTEX_AI_API_KEY`
- `VERTEX_PROJECT_ID`
- `VERTEX_LOCATION`
- `VERTEX_ANSWER_MODEL`

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
