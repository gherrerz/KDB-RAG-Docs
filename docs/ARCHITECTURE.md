# Arquitectura Tecnica

## Resena de arquitectura

RAG Hybrid Response Validator implementa una arquitectura modular orientada a
servicios para resolver dos capacidades principales:

- Ingesta de conocimiento documental (carpeta local o Confluence) hacia
  estructuras consultables.
- Consulta con RAG hibrido (vector + BM25 + grafo) con trazabilidad de
  evidencia.

El sistema esta disenado para operar con ChromaDB activo en runtime para la
capa vectorial y Neo4j obligatorio para capa de grafo. Componentes opcionales
adicionales de produccion:

- Redis + RQ para ingesta asincrona.
- Proveedores de embedding/answer externos (OpenAI, Gemini, Vertex AI).

## Descripcion general

### Runtime principal

- UI de escritorio en PySide6 (`src/coderag/ui/*`) para operar ingesta y consulta.
- Capa UI con tema centralizado, validaciones en cliente y estados visuales de
  operacion (progreso, resumen y diagnostico tecnico desacoplado).
- API FastAPI (`src/coderag/api/server.py`) como fachada de operaciones.
- Orquestador de negocio (`src/coderag/core/service.py`) con flujo end-to-end.
- Persistencia SQLite (`src/coderag/storage/metadata_store.py`) para documentos,
  chunks, aristas, jobs, eventos de timeline por job (`job_events`) y estado
  de runtime (`runtime_state`).
- Persistencia vectorial en Chroma (`src/coderag/ingestion/index_chroma.py`) para
  embeddings de chunks y busqueda de similitud.
- Retrieval hibrido (`src/coderag/retrieval/*`) con ranking y expansion por grafo.
- Integracion de LLM (`src/coderag/llm/providerlmm_client.py`) para respuesta.

### Principios de diseno actuales

- Chroma-first: la capa vectorial requiere Chroma (`USE_CHROMA=true`).
- Neo4j obligatorio: la capa de grafo requiere `USE_NEO4J=true` y credenciales.
- Evolutivo: interfaces internas permiten reemplazar componentes por equivalentes
  gestionados sin romper contratos API/UI.
- Explicable: cada respuesta expone evidencias (`citations`) y rutas de grafo
  (`graph_paths`) con diagnosticos de pipeline.
- Observable: la ingesta persiste eventos con progreso y tiempos acumulados,
  reutilizados por UI/API para seguimiento en vivo.
- Performante por lotes: documentos, Chroma y Neo4j se procesan con estrategias
  de batching para reducir latencia total en ingestas medianas/grandes.
- Consistencia cross-process: en modo async con RQ, la API detecta cambios
  de `index_version` en SQLite y refresca indices en query sin reinicio.

## Diagrama de infraestructura por capas

```mermaid
flowchart TB
    subgraph L5[CAPA 5 - Cliente]
        UI[Desktop UI\nPySide6]
        APIClient[Cliente HTTP externo]
    end

    subgraph L4[CAPA 4 - Exposicion]
        FastAPI[FastAPI\nEndpoints REST]
    end

    subgraph L3[CAPA 3 - Aplicacion y Dominio]
        Service[RagApplicationService\nOrquestacion]
        Jobs[RQ Queue Helpers\nworker opcional]
    end

    subgraph L2[CAPA 2 - Recuperacion e Ingesta]
        Loader[Document Loader + Parsers]
        Chunker[Chunker + Graph Builder]
        Retrieval[Hybrid Search + Rerank]
        GraphExpand[Graph Expand + Context Assembler]
        LLM[ProviderLlmClient]
    end

    subgraph L1[CAPA 1 - Datos]
        SQLite[(SQLite metadata.db)]
      Chroma[(Chroma vector store)]
        Neo4j[(Neo4j obligatorio)]
        Redis[(Redis opcional)]
    end

    UI --> FastAPI
    APIClient --> FastAPI
    FastAPI --> Service
    Service --> Loader
    Service --> Chunker
    Service --> Retrieval
    Service --> GraphExpand
    Service --> LLM
    Service --> SQLite
    Service --> Chroma
    Service --> Neo4j
    Jobs --> Redis
    FastAPI --> Jobs
```

### Notas de capas

- Capa 5 (Cliente): UI de operacion y clientes de integracion via HTTP.
- Capa 4 (Exposicion): contratos estables de API (`/sources/*`, `/query*`).
- Capa 3 (Aplicacion y Dominio): coordina casos de uso y politicas del flujo.
- Capa 2 (Recuperacion e Ingesta): contiene logica de parseo, chunking,
  indexacion, retrieval y grounding para respuesta.
- Capa 1 (Datos): almacenamiento local obligatorio y servicios externos
  opcionales para escalar capacidades.

## Diagrama de componentes

```mermaid
graph LR
    UI[ui/main_window.py\nIngestionView + QueryView]
    API[api/server.py\nFastAPI controllers]
    Service[core/service.py\nRagApplicationService]

    Loader[ingestion/document_loader.py]
    Parsers[parsers/*]
    Chunker[ingestion/chunker.py]
    GraphBuilder[ingestion/graph_builder.py]
    BM25[ingestion/index_bm25.py]
    Vector[ingestion/index_chroma.py\nChromaVectorIndex]
    Embedding[ingestion/embedding.py\nProvider Embeddings API]

    Retrieval[retrieval/hybrid_search.py]
    Reranker[retrieval/reranker.py]
    GraphLocal[retrieval/graph_expand.py]
    Context[retrieval/context_assembler.py]

    GraphStore[core/graph_store.py]
    LLM[llm/providerlmm_client.py]
    Store[storage/metadata_store.py]

    RQ[jobs/queue.py + jobs/worker.py]

    UI --> API
    API --> Service

    Service --> Loader
    Loader --> Parsers
    Service --> Chunker
    Service --> GraphBuilder
    Service --> Store

    Service --> BM25
    Service --> Vector
    Vector --> Embedding
    Service --> Retrieval
    Service --> Reranker

    Service --> GraphStore
    Service --> GraphLocal
    Service --> Context
    Service --> LLM

    API --> RQ
    RQ --> Service
```

## Secuencia principal: ingesta

```mermaid
sequenceDiagram
    autonumber
    participant User as Usuario/UI
    participant API as FastAPI
    participant SVC as RagApplicationService
    participant DL as DocumentLoader
    participant PRS as Parsers
    participant DB as SQLite MetadataStore
    participant EMB as Embedding Provider API
    participant GS as GraphStore (Neo4j obligatorio)
    participant IDX as BM25 + ChromaVectorIndex

    User->>API: POST /sources/ingest o /sources/ingest/async
    API->>SVC: ingest(request)
    SVC->>DB: touch_job(running)
    SVC->>DB: append_job_event(...)

    SVC->>DL: load_documents(source)
    DL->>PRS: parse_by_extension(...)
    PRS-->>DL: texto normalizado
    DL-->>SVC: documentos + estadisticas

    alt Sin documentos soportados
        SVC->>DB: touch_job(failed)
        SVC-->>API: status=failed + steps
    else Con documentos
        loop por documento
            SVC->>SVC: build_chunks(doc)
        end
        SVC->>DB: upsert_documents(docs) en lote
        SVC->>DB: replace_chunks(source_id, chunks)
        SVC->>SVC: build_graph_edges(chunks)
        SVC->>DB: replace_graph_edges(source_id, edges)
        SVC->>GS: replace_edges(source_id, edges)
        Note over SVC,GS: UNWIND por bloques + transaccion por lote + retry acotado
        SVC->>IDX: rebuild indexes
        IDX->>EMB: embeddings en paralelo por lote
        EMB-->>IDX: vectors
        IDX->>IDX: upsert por lotes en Chroma
        SVC->>DB: append_job_event(...)
        SVC->>DB: touch_job(completed)
        SVC-->>API: status=completed + metrics + steps
    end

    API-->>User: JSON de estado de ingesta
```

## Secuencia principal: consulta

```mermaid
sequenceDiagram
    autonumber
    participant User as Usuario/UI
    participant API as FastAPI
    participant SVC as RagApplicationService
    participant BM25 as BM25Index
    participant VEC as ChromaVectorIndex
    participant EMB as Embedding Provider API
    participant RET as hybrid_search_reranker
    participant GS as GraphStore Neo4j obligatorio
    participant DB as SQLite MetadataStore
    participant LLM as ProviderLlmClient

    User->>API: POST /query
    API->>SVC: query(request)
    SVC->>DB: get_index_version()
    alt Version cambio por ingesta async
        SVC->>DB: list_chunks()
        SVC->>BM25: rebuild(chunks)
        Note over SVC,VEC: Chroma ya persistio vectores en worker
        Note over SVC,VEC: API evita reindexacion vectorial global
    end

    SVC->>RET: hybrid_search(question)
    RET->>BM25: search(top_n)
    RET->>VEC: search(top_n)
    VEC->>EMB: embed(question)
    EMB-->>VEC: query vector
    RET-->>SVC: candidatos fusionados

    SVC->>RET: rerank_results(question, hits, top_k)
    RET-->>SVC: chunks rerankeados

    SVC->>GS: expand_paths(question, hops)
    GS-->>SVC: graph_paths

    alt include_llm_answer=true
      SVC->>LLM: answer(question, context, provider)
      LLM-->>SVC: respuesta markdown
    else include_llm_answer=false
      Note over SVC: omite llamada LLM y retorna answer vacio
    end

    SVC->>DB: get_document_map(source_id)
    SVC->>SVC: construir citations y diagnostics
    SVC-->>API: QueryResponse
    API-->>User: answer y citations y graph_paths y diagnostics
```

## Consideraciones de despliegue

- Modo local (default): API + UI + SQLite + Chroma persistente.
- Modo expandido: activar `USE_RQ=true` para procesamiento asincrono.
- Docker Compose incluye servicios `redis` y `neo4j`; la capa vectorial usa
  Chroma embebido en disco dentro de la API (`CHROMA_PERSIST_DIR`).

## Consistencia post-ingesta async

- El worker de ingesta (RQ) persiste chunks en SQLite y vectores en Chroma,
  luego incrementa `index_version` en `runtime_state`.
- La API mantiene un `loaded_index_version` en memoria por proceso.
- En el siguiente `/query`, si detecta mismatch de version:
  - reconstruye BM25 desde SQLite,
  - reutiliza vectores ya persistidos en Chroma,
  - actualiza su version cargada y continua el retrieval.
- Este enfoque evita reinicio manual de API y reduce el riesgo de timeout en
  la primera consulta posterior a ingesta async.

## Optimizaciones recientes de ingesta

- Persistencia de documentos en SQLite en lote (`upsert_documents`) para
  reducir commits por documento.
- Persistencia de relaciones en Neo4j con UNWIND por bloques configurables,
  transaccion por lote y reintentos acotados para fallas transitorias.
- Generacion de embeddings de chunks con concurrencia configurable y escritura
  a Chroma por lotes para mejorar throughput.
- Timeline de ingesta persistido en `job_events` con progreso (`progress_pct`)
  y `elapsed_hhmmss` acumulado para visualizacion en UI y polling de jobs.

Parametros de tuning relevantes:

- `INGEST_EMBED_WORKERS`
- `CHROMA_UPSERT_BATCH_SIZE`
- `NEO4J_INGEST_BATCH_SIZE`
- `NEO4J_INGEST_MAX_RETRIES`
- `NEO4J_INGEST_RETRY_DELAY_MS`
