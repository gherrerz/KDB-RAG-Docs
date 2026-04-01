# Multi-hop Benchmark Report

- Benchmark file: `C:/Users/gherr/Documents/Personal/KDB-RAG-Docs/docs/benchmarks/complex_queries_release_gobierno_datos_es.json`
- Total cases: 5
- Passed: 1
- Failed: 4
- Pass rate: 20.0%

## Summary by type

| Type | Total | Passed | Failed | Pass rate |
|---|---:|---:|---:|---:|
| gobierno_datos_multihop | 4 | 0 | 4 | 0.0% |
| single_doc_control | 1 | 1 | 0 | 100.0% |

## Case results

| Case | Type | Pass | Retrieval docs | Reranked docs | Citation docs | Graph paths | Terms hit |
|---|---|---|---:|---:|---:|---:|---:|
| gd_estrategia_vs_gobierno | gobierno_datos_multihop | no | 2 | 1 | 1 | 6 | 2/3 |
  - Failure reasons: reranked_unique_documents 1 < 2; citation_unique_documents 1 < 2
| gd_roles_y_responsabilidades | gobierno_datos_multihop | no | 2 | 1 | 1 | 6 | 1/3 |
  - Failure reasons: reranked_unique_documents 1 < 2; citation_unique_documents 1 < 2; required_answer_terms_hit 1 < 2
| gd_iniciativas_prioritarias | gobierno_datos_multihop | no | 2 | 1 | 1 | 6 | 1/3 |
  - Failure reasons: reranked_unique_documents 1 < 2; citation_unique_documents 1 < 2; required_answer_terms_hit 1 < 2
| gd_trazabilidad_integridad | gobierno_datos_multihop | no | 1 | 1 | 1 | 6 | 3/3 |
  - Failure reasons: retrieval_unique_documents 1 < 2; reranked_unique_documents 1 < 2; citation_unique_documents 1 < 2
| gd_control_politica | single_doc_control | yes | 2 | 2 | 2 | 6 | 1/1 |
