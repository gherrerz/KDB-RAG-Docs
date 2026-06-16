# CLAUDE.md — RAG Hybrid Response Validator (KDB-RAG-Docs)

Guía de contexto para agentes que trabajen en este repositorio. Adaptada desde
`.github/` (instructions, agents, skills) al formato de Claude Code. Trata este
documento como **contrato de la implementación actual**, no como visión futura.

## 1. Qué es el proyecto

Aplicación Python para ingesta documental empresarial y consulta con **RAG
híbrido** (vector + lexical + grafo), con UI de escritorio (PySide6) y API HTTP
(FastAPI). Permite ingestar documentos (carpeta local y multipart), construir
retrieval híbrido y responder preguntas con trazabilidad y evidencias verificables.

Arquitectura conceptual: **Hybrid Retrieval + Graph expansion + Multi-hop
reasoning + Diagnostics-driven grounding**.

### Estado del cutover (importante)
- Arquitectura objetivo aprobada: **Postgres + Chroma remoto + Neo4j**. Es el
  contrato final de runtime.
- Referencia autoritativa ante conflictos actual vs objetivo:
  [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md).
- Decisiones cerradas:
  - Tablas nuevas de Docs en Postgres usan prefijo `Tbl_Documents_`.
  - Si comparte base Postgres con KDB-RAG-Repo, cada app usa su tabla Alembic
    aislada (`alembic_version_docs` para Docs, `alembic_version_repo` para Repo).
  - `path_or_url` conserva el origen original del documento.
  - Deduplicación por `title + content_type`.
  - No hay migración histórica desde SQLite: ruta acordada es **reset + reingesta**.
  - No hay dual-write prolongado entre storage legacy y objetivo.
  - Ingesta async con archivos locales persiste artifacts temporales en Postgres
    al encolar y rehidrata desde ahí (sin filesystem compartido).

### Ajustes de realidad frente a la visión inicial
- **No** existe soporte Anthropic como capacidad implementada del LLM.
- Confluence existe en contrato, pero su cliente actual es **placeholder**.
- Chroma embebido **no** es modo operativo válido en runtime Docs (modo remoto obligatorio).

## 2. Componentes y stack

- UI de escritorio: **PySide6**
- Backend: **FastAPI**
- Vector store: **Chroma remoto** (HTTP, auth opcional por token o basic auth)
- Lexical index: **Postgres FTS** (lenguaje FTS parametrizable)
- Grafo: **Neo4j** (opcional, degradación controlada si `USE_NEO4J=false`)
- LLM providers soportados: `local`, `openai` (Responses API), `gemini`,
  `vertex`/`vertex_ai`
- Jobs async: **Redis + RQ** cuando `USE_RQ=true`; worker local en thread como
  fallback automático si Redis no está disponible.

## 3. Estructura modular (`src/coderag/`)

Reglas de ubicación por responsabilidad — respétalas en cambios nuevos:

- `ui/` — vistas, presenters y cliente HTTP. **Solo** UI/presentación aquí.
- `api/` — rutas FastAPI y adaptador de ingesta multipart. **Solo** endpoints HTTP.
- `core/` — modelos, settings, runtime, orquestación, servicios (casos de uso).
- `ingestion/` + `parsers/` — loader, scanner, chunker, embeddings, indexado
  vectorial, grafo y parseadores por formato.
- `retrieval/` — búsqueda híbrida, rerank, expansión de grafo, context assembly.
- `llm/` — cliente de proveedor y prompts.
- `storage/` — persistencia Postgres e interfaces de estado runtime.
- `jobs/` — cola RQ y worker (ejecución asíncrona).
- `tdm/` — capacidades TDM (opt-in, gobernadas por feature flags).

Entrypoints: `src/main.py`, `src/run_ui.py`.
Documentación funcional/operativa en `docs/`. Tests en `tests/` reflejando
contratos de API, core y UI.

### Convenciones de archivos
- Un archivo por responsabilidad concreta; nombres explícitos por módulo y flujo.
- No mezclar lógica de UI con lógica de dominio.
- Si agregas endpoint nuevo: agregar test y actualizar `docs/API_REFERENCE.md`.
- Si agregas flag nuevo: documentarlo en `docs/CONFIGURATION.md` y README.

## 4. Contratos clave de API

Salud/consulta: `GET /health`, `GET /readiness`, `POST /query`, `POST /query/retrieval`.
Ingesta/jobs: `POST /sources/ingest[/files][/async]`, `GET /sources/ingest/readiness`,
`GET /jobs/{job_id}`, `DELETE /sources/reset?confirm=true`.
Catálogo: `GET /sources/documents`, `GET /sources/tags`,
`PUT /sources/documents/{id}/tags`, `DELETE /sources/documents/{id}`.
TDM: `POST /tdm/ingest`, `POST /tdm/query`, `GET /tdm/catalog/...`,
`POST /tdm/virtualization/preview`, `GET /tdm/synthetic/profile/{table}`.

Shape de respuesta de consulta: `answer`, `citations`, `graph_paths`, `diagnostics`.

Defaults recomendados de retrieval: hybrid `top_n = 60`, rerank `top_k = 15`,
graph `hops = 2`, `max_context_chars = 16000`.

Al modificar el repo: preserva compatibilidad con endpoints y payloads usados por
UI y tests. Si agregas capacidad nueva, documenta su estado: `implemented`,
`partial` o `planned`.

## 5. Política anti-alucinación (obligatoria)

1. No inventar entidades, relaciones ni citas.
2. Toda afirmación de respuesta debe estar soportada por evidencia textual o path de grafo.
3. Sin evidencia suficiente, responder exactamente:
   `No se encontro informacion en las fuentes indexadas.`
4. En multi-hop, priorizar soporte con rutas de grafo.
5. Si una capacidad está deshabilitada por flags, informarlo en `diagnostics`.

## 6. Convenciones de código Python

Aplican a `**/*.py` (ver `.github/instructions/python.instructions.md`):

- PEP 8; 4 espacios; líneas ≤ 79 caracteres.
- Type hints modernos: `list[str]`, `dict[str, int]`; usa `Protocol`,
  `TypedDict`, `TypeAlias` cuando aporten claridad.
- Docstrings PEP 257 en funciones, clases y módulos públicos.
- SOLID: responsabilidad única; separar reglas de negocio de I/O, persistencia,
  serialización, framework y presentación.
- Composición sobre herencia salvo relación is-a real.
- Depender de abstracciones (inyectar colaboradores por constructor/parámetros);
  interfaces pequeñas con `Protocol`/ABC.
- Tests de contrato cuando varias implementaciones comparten una abstracción.
- Cubrir edge cases: inputs vacíos, tipos inválidos, datasets grandes; manejo de
  excepciones claro.

## 7. Docker / contenedores

Ver `.github/instructions/containerization-docker-best-practices.instructions.md`.
Esenciales: multi-stage builds, imágenes base mínimas y versionadas (`slim`/`alpine`/
distroless), optimizar capas y limpiar en el mismo `RUN`, `.dockerignore`
comprensivo, usuario **no-root**, `HEALTHCHECK`, configuración por variables de
entorno, **nunca** secretos en capas de imagen, escaneo SAST (hadolint/Trivy).

## 8. Documentación al cambiar código

Ver `.github/instructions/update-docs-on-code-change.instructions.md`. Mantén
sincronizadas README, `CHANGELOG.md` y `docs/` con los cambios de código **en el
mismo commit/PR**: nuevas features, cambios de API/CLI, nuevas variables de
entorno (añádelas a `.env.example`), breaking changes (con guía de migración).
Actualiza `CHANGELOG.md` con secciones Added/Changed/Fixed/Deprecated/Removed/Security.

## 9. Seguridad operativa

- No hardcodear credenciales: usar variables de entorno para secretos.
- Tratar Chroma y Postgres como dependencias críticas de readiness.
- Mantener aislamiento de base para el entorno Docs.
- Exponer errores operativos de forma estructurada y accionable.

## 10. Criterios de aceptación de un cambio

1. Ingesta y consulta funcionan en flujo folder y multipart.
2. Retrieval híbrido entrega evidencia trazable.
3. Diagnostics reportan modo efectivo y estado de dependencias.
4. Contratos API y UI permanecen compatibles.
5. TDM respeta feature flags y degradación controlada.
6. Tests relevantes pasan en verde.
7. Respeta la jerarquía de carpetas y la separación de responsabilidades.
8. Incluye actualización documental y cobertura de pruebas asociada.

## 11. Agents y skills disponibles

Subagentes en `.claude/agents/` (lánzalos con la tool Agent):
- **qa** — QA meticuloso: planes de prueba, caza de bugs, edge cases, verificación.
- **sast-sca-security-analyzer** — análisis SAST/SCA, CWE/CVE, reportes de seguridad.

Skills en `.claude/skills/`:
- **audit-integrity** — marco de integridad para análisis de seguridad/calidad.
- **frontend-design** — interfaces frontend distintivas y de alta calidad.

Fuente original (Copilot): `.github/agents/` y `.github/skills/`. Los archivos de
`.claude/` son la versión adaptada para este harness.
