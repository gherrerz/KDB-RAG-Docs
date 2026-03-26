# RAG Hybrid Response Validator

Aplicacion Python para ingesta documental y consulta con RAG hibrido
(vector + BM25 + grafo) con UI de escritorio (PySide6) y API (FastAPI).

## Features

- Ingesta de documentos locales (`.md`, `.txt`, `.html`)
- Pipeline de chunking semantico por secciones
- Recuperacion hibrida: vectorial + BM25
- Expansion por grafo multi-hop
- Respuesta con evidencia y trazabilidad
- Soporte de proveedores LLM: local, OpenAI, Gemini y Vertex AI
- UI para operacion de ingesta y consultas
- API REST para integracion externa
- Ingesta asincrona opcional con Redis + RQ

## Arquitectura

- UI: PySide6
- API: FastAPI
- Vector index: `LocalVectorIndex` (compatible con evolucion a ChromaDB)
- BM25: `rank-bm25`
- Grafo: `networkx` (compatible con evolucion a Neo4j)
- Storage metadata: SQLite en `storage/metadata.db`

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

Ejemplo `POST /query`:

```json
{
  "question": "Who works on Project Atlas?",
  "hops": 2,
  "llm_provider": "local",
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

## Configuracion

Ver:
- `docs/INSTALLATION.md`
- `docs/CONFIGURATION.md`
- `docs/API_REFERENCE.md`

## Estado y roadmap

Este MVP es funcional end-to-end sin dependencias externas obligatorias.
El diseño de modulos permite reemplazar componentes locales por:
- ChromaDB para vectores
- Neo4j para grafo (opcional habilitado por `USE_NEO4J=true`)
- Redis + RQ para jobs asincronos (opcional con `USE_RQ=true`)
- Proveedores LLM (OpenAI, Gemini, Vertex AI)
