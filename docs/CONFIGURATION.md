# Configuration

Guia de configuracion de entorno y providers.

## Variables clave

### LLM

- LLM_PROVIDER: openai, anthropic, gemini, vertex_ai
- LLM_ANSWER_MODEL
- LLM_VERIFIER_MODEL
- LLM_VERIFY_ENABLED

### Embeddings

- EMBEDDING_PROVIDER: openai, anthropic, gemini, vertex_ai
- EMBEDDING_MODEL

### Chroma y retrieval

- CHROMA_PATH
- CHROMA_HNSW_SPACE: cosine o l2
- MAX_CONTEXT_TOKENS
- GRAPH_HOPS
- QUERY_MAX_SECONDS

### Storage y workspace

- NEO4J_URI
- NEO4J_USER
- NEO4J_PASSWORD
- WORKSPACE_PATH

### Escaneo de ingesta (obligatorias)

- SCAN_MAX_FILE_SIZE_BYTES
- SCAN_EXCLUDED_DIRS
- SCAN_EXCLUDED_EXTENSIONS
- SCAN_EXCLUDED_FILES (opcional)

## Ejemplo minimo recomendado

```dotenv
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=your_key
NEO4J_URI=bolt://127.0.0.1:17687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4jpassword
SCAN_MAX_FILE_SIZE_BYTES=200000
SCAN_EXCLUDED_DIRS=.git,node_modules,dist,build,.venv,__pycache__
SCAN_EXCLUDED_EXTENSIONS=.png,.jpg,.jpeg,.gif,.pdf,.zip,.jar,.class,.dll,.exe
```

## Notas operativas

- Si cambias CHROMA_HNSW_SPACE, haz reset y reingesta.
- Si cambias provider/modelo de embedding, valida compatibilidad del repo con
  GET /repos/{repo_id}/status antes de consultar.
- Para provider catalog, usa GET /providers/models.

## Referencias

- Flujos de consulta y fallback: docs/ARCHITECTURE.md.
- Contratos API: docs/API_REFERENCE.md.
