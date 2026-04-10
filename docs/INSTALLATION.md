# Installation Guide

Esta guia deja el proyecto funcionando en local con API + UI y, cuando aplica,
con servicios de infraestructura en contenedores.

## 1. Prerequisites

- Python 3.11+
- pip
- Docker Desktop (recomendado para Neo4j y Redis)
- Git

Notas importantes de runtime:

- Neo4j es obligatorio en runtime (`USE_NEO4J=true`).
- Chroma debe estar habilitado (`USE_CHROMA=true`).
- Redis solo es obligatorio si se usa ingesta async con RQ (`USE_RQ=true`).
- Para embeddings se requiere provider externo (`openai`, `gemini` o `vertex`).

## 2. Clone and Python environment

Desde la raiz del repo:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Perfiles disponibles:

- `requirements.txt`: baseline API/worker para levantar la API con el menor set necesario.
- `requirements-runtime.txt`: alias explicito de solo API/worker para entornos headless.
- `requirements-desktop.txt`: API/worker + PySide6 para usar la UI.
- `requirements-full.txt`: instalacion completa para desarrollo local, UI y tests.

## 3. Configure environment (.env)

Usa una plantilla base y completa credenciales:

```powershell
Copy-Item .env.openai.example .env
```

Alternativas:

- `.env.gemini.example`
- `.env.vertex.example`

Variables minimas para un arranque funcional:

- `LLM_PROVIDER` en `openai`, `gemini` o `vertex`
- credenciales del provider elegido (`OPENAI_API_KEY`, `GEMINI_API_KEY` o
    `VERTEX_SERVICE_ACCOUNT_JSON_B64` + `VERTEX_PROJECT_ID`)
- `USE_CHROMA=true`
- `USE_NEO4J=true`
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`

Si usas `LLM_PROVIDER=vertex`:

- Define labels de trazabilidad (opcional) via `VERTEX_LABEL_*`.
- Defaults incluidos en plantillas:
    - `VERTEX_LABEL_SERVICE=webspec-coipo`
    - `VERTEX_LABEL_SERVICE_ACCOUNT=qa-anthos`
    - `VERTEX_LABEL_MODEL_NAME=gemini-2.5-flash`
    - `VERTEX_LABEL_USE_CASE_ID=tbd`

Para usar un archivo local de ejemplo de service account durante pruebas
manuales (sin commitearlo):

```powershell
$env:VERTEX_SERVICE_ACCOUNT_JSON_B64 = (Get-Content gcp_credentials_vertex.base64.txt -Raw)
```

Si usas Redis + RQ:

- `USE_RQ=true`
- `REDIS_URL=redis://localhost:6379/0` (o `redis://redis:6379/0` en Docker)

## 4. Start infrastructure services (containers)

Para ejecutar API/UI locales, levanta primero la infraestructura.

Imagenes usadas por `docker-compose.yml`:

- `neo4j:5.24.0` (obligatorio)
- `redis:7.2.4-alpine` (opcional, solo async con RQ)

Antes de levantar compose, define password de Neo4j (evita defaults inseguros):

```powershell
$env:NEO4J_PASSWORD="<neo4j-password-seguro>"
```

Descarga recomendada previa de imagenes:

```powershell
docker compose pull neo4j redis
```

Arranque recomendado minimo:

```powershell
docker compose up -d neo4j
```

Si vas a usar async con RQ:

```powershell
docker compose up -d neo4j redis
```

Puertos esperados:

- Neo4j Browser: `http://127.0.0.1:7474`
- Neo4j Bolt: `127.0.0.1:7687`
- Redis: `127.0.0.1:6379`

Nota: Redis y Neo4j quedan bind a localhost por defecto en compose para
reducir exposicion de red en desarrollo.

Credenciales por defecto en compose:

- Neo4j user: `neo4j`
- Neo4j password: valor de `NEO4J_PASSWORD`

## 5. Run API

```powershell
python src/main.py
```

Verificacion rapida:

- Health: `http://127.0.0.1:8000/health`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## 6. Run desktop UI

En otra terminal (con `.venv` activa):

Si el entorno fue creado solo con `requirements.txt`, instala antes soporte UI:

```powershell
pip install -r requirements-desktop.txt
```

Luego ejecuta:

```powershell
python src/run_ui.py
```

## 7. Optional async worker

Si `USE_RQ=true`, inicia worker en otra terminal:

```powershell
python -m coderag.jobs.worker
```

En Windows, el worker usa `SimpleWorker` para evitar problemas de `os.fork`.

## 8. Optional full stack with Docker Compose

Si prefieres API/worker tambien en contenedores:

```powershell
docker compose up -d --build api worker redis neo4j
```

Servicios definidos en [docker-compose.yml](../docker-compose.yml):

- `api` (build local, expone `8000`)
- `worker` (RQ worker)
- `redis` (`redis:7-alpine`)
- `neo4j` (`neo4j:5`)

La imagen de contenedor usa el baseline de `requirements.txt` (alineado a
runtime API/worker), por lo que no instala dependencias de escritorio ni
tooling de test.

## 9. First functional check

1. Abrir UI.
2. Ingestion:
3. Source Type: `folder`
4. Local Path: `sample_data`
5. Ejecutar ingest.
6. Query: ejecutar una pregunta simple y validar `citations`.

## 10. Run tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## 11. Supported ingestion file types

- Supported: `.md`, `.txt`, `.html`, `.htm`, `.pdf`, `.docx`, `.doc`,
    `.pptx`, `.xlsx`
- Not supported in this version: `.ppt`, `.xls`

## 12. Troubleshooting rapido

- Error de Neo4j al iniciar API: verificar que `neo4j` este levantado en
    `localhost:7687` y credenciales correctas en `.env`.
- Error de embeddings/provider: revisar `LLM_PROVIDER` y credenciales del
    proveedor elegido.
- Async jobs no avanzan: si `USE_RQ=true`, confirmar `redis` activo y worker
    ejecutandose.
- `pytest` no encontrado en PATH: usar
    `.venv\Scripts\python.exe -m pytest -q`.

## 13. Cleanup local artifacts

En sesiones con politica que bloquea `Remove-Item`, usa:

```powershell
.venv\Scripts\python.exe scripts/clean_artifacts.py --remove-metadata-db
```

## 14. Related documentation

- Configuracion avanzada: [docs/CONFIGURATION.md](CONFIGURATION.md)
- Referencia de endpoints y contratos: [docs/API_REFERENCE.md](API_REFERENCE.md)
- Arquitectura tecnica: [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- Despliegue en Kubernetes: [docs/KUBERNETES.md](KUBERNETES.md)
