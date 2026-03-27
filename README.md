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
- Soporte de proveedores LLM: OpenAI, Gemini y Vertex AI
- Seleccion de provider por entorno (`LLM_PROVIDER`) con soporte para
  `local`, `openai`, `gemini` y `vertex` (`vertex_ai` como alias)
- Modelo de embedding configurable por provider y override global por
  `LLM_EMBEDDING`
- ChromaDB activo en runtime para persistencia y busqueda vectorial
- Embeddings reales por proveedor durante ingesta y consulta
- UI para operacion de ingesta y consultas
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
- Grafo: Neo4j obligatorio para persistencia y expansion de paths
- Storage metadata: SQLite en `storage/metadata.db`

### Estado del vector store

- El runtime requiere `USE_CHROMA=true`.
- El runtime requiere `USE_NEO4J=true`.
- Los embeddings se calculan con el proveedor configurado (`openai`,
  `gemini` o `vertex`) y se guardan en ChromaDB.
- No existe fallback a embeddings locales en memoria cuando falta
  configuracion/credenciales.

## Requisitos

- Python 3.11+
- Windows, Linux o macOS

## Instalacion

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Ejecucion

1. Iniciar API:

```bash
python run_api.py
```

2. Iniciar UI en otra terminal:

```bash
python run_ui.py
```

3. En la UI, pestaña Ingestion:
- `Source Type`: `folder`
- `Local Path`: `sample_data`
- Click en `Ingest`

4. En la pestaña Query, preguntar por ejemplo:
- `Who works on Project Atlas?`
- `Which procedure depends on Policy FIN-001?`

## API Endpoints

- `GET /health`
- `POST /sources/ingest`
- `POST /sources/reset`
- `POST /sources/ingest/async`
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
  "force_fallback": false
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
  "message": "All repositories were cleared and indexes were reset.",
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
limpia aristas Neo4j y vuelve a levantar API/UI):

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
- `docs/INSTALLATION.md`
- `docs/CONFIGURATION.md`
- `docs/API_REFERENCE.md`
- `docs/ARCHITECTURE.md`

Variables relevantes de entorno:
- `LLM_PROVIDER`: provider para consulta y embeddings (`local`, `openai`,
  `gemini`, `vertex`)
- Nota: para embeddings el runtime requiere provider externo
  (`openai`/`gemini`/`vertex`); `local` aplica a respuesta extractiva.
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
- `RQ_INGEST_JOB_TIMEOUT_SEC`: timeout en segundos para ingestas async con
  RQ (`USE_RQ=true`). Default: `900`.

Plantillas listas para copiar:
- `.env.openai.example`
- `.env.gemini.example`
- `.env.vertex.example`

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
