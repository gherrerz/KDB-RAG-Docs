# Architecture and Customer Journeys

Documento de referencia para entender la interaccion entre usuario, UI,
API, pipeline de ingesta, retrieval y LLM.

## Vista ejecutiva de journeys

```mermaid
flowchart LR
    U[Usuario] --> J1[Journey 1: Ingesta]
    U --> J2[Journey 2: Query con LLM]
    U --> J3[Journey 3: Query retrieval-only]

    J1 --> O1[Outcome: repo listo para consulta]
    J2 --> O2[Outcome: respuesta sintetizada con citas]
    J3 --> O3[Outcome: evidencia estructurada sin LLM]

    O1 --> R[Readiness check]
    R --> J2
    R --> J3
```

## Journey 1: Ingesta

### Flujo

```mermaid
flowchart TB
    A[POST /repos/ingest] --> B[Job queued]
    B --> C[Job running]
    C --> D[Clone repo]
    D --> E[Scan files]
    E --> F[Extract symbols]
    F --> G[Index Chroma]
    F --> H[Index BM25]
    F --> I[Build graph Neo4j]
    G --> J[Persist metadata]
    H --> J
    I --> J
    J --> K{Readiness}
    K -->|ok| L[completed]
    K -->|warning| M[partial]
    C -->|exception| N[failed]
```

### Secuencia

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant UI
    participant API
    participant JobManager
    participant Pipeline
    participant Storage

    User->>UI: Inicia ingesta
    UI->>API: POST /repos/ingest
    API->>JobManager: create_ingest_job
    JobManager-->>UI: job_id, status=queued

    loop Polling
        UI->>API: GET /jobs/{job_id}?logs_tail=200
        API->>JobManager: get_job(job_id)
        JobManager-->>UI: status, progress, logs
    end

    JobManager->>Pipeline: run ingest pipeline
    Pipeline->>Storage: write Chroma/BM25/Neo4j/metadata
    Pipeline-->>JobManager: completed|partial|failed
    JobManager-->>API: final state
    API-->>UI: final job info
    UI-->>User: Estado final y repo_id
```

## Journey 2: Query con LLM

### Flujo

```mermaid
flowchart TB
    A[POST /query] --> B[Readiness and compatibility]
    B --> C{Intent inventory?}
    C -->|yes| D[Inventory graph-first]
    C -->|no| E[Hybrid search]
    E --> F[Rerank]
    F --> G[Graph expand]
    G --> H[Assemble context]
    D --> I[Build response]
    H --> J[LLM answer]
    J --> K{Verify valid?}
    K -->|yes| I
    K -->|no| L[Extractive fallback]
    L --> I
```

### Secuencia

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant UI
    participant API
    participant QueryService
    participant Retrieval
    participant LLM

    User->>UI: Pregunta de negocio
    UI->>API: POST /query
    API->>QueryService: run_query
    QueryService->>Retrieval: hybrid_search + rerank + graph_expand
    Retrieval-->>QueryService: chunks + context + citations
    QueryService->>LLM: answer(context)
    LLM-->>QueryService: draft answer
    QueryService->>LLM: verify(answer, context)

    alt verify ok
        QueryService-->>API: QueryResponse(answer, citations, diagnostics)
    else verify failed or llm error
        QueryService-->>API: fallback extractivo + diagnostics
    end

    API-->>UI: respuesta final
    UI-->>User: respuesta + evidencia
```

## Journey 3: Query retrieval-only

### Flujo

```mermaid
flowchart TB
    A[POST /query/retrieval] --> B[Readiness and compatibility]
    B --> C{Intent inventory?}
    C -->|yes| D[Inventory graph-first]
    C -->|no| E[Hybrid search]
    E --> F[Rerank]
    F --> G[Graph expand]
    G --> H[Assemble context]
    D --> I[Build retrieval response]
    H --> I
    I --> J[Return chunks and citations]
```

### Secuencia

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant UI
    participant API
    participant QueryService
    participant Retrieval

    User->>UI: Pregunta tecnica
    UI->>API: POST /query/retrieval
    API->>QueryService: run_retrieval_query
    QueryService->>Retrieval: hybrid_search + rerank + graph_expand
    Retrieval-->>QueryService: chunks + citations + stats
    QueryService-->>API: RetrievalQueryResponse
    API-->>UI: evidencia estructurada
    UI-->>User: chunks, citas y diagnostics
```

## Componentes principales

- UI PySide6: captura inputs de ingesta/consulta y presenta evidencias.
- API FastAPI: valida precondiciones y expone contratos HTTP.
- JobManager: orquesta estados de ingesta y persistencia de logs.
- Retrieval pipeline: fusion vectorial + BM25 + expansion de grafo.
- LLM clients: answer y verify en proveedores soportados.
- Storage: Chroma, BM25, Neo4j, SQLite metadata y workspace local.

## Referencias

- Endpoints y contratos: docs/API_REFERENCE.md
- Instalacion: docs/INSTALLATION.md
- Configuracion: docs/CONFIGURATION.md
- Troubleshooting: docs/TROUBLESHOOTING.md
