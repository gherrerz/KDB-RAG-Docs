# Migration Guide: Service + UI Refactor

## Scope

This guide consolidates the refactor delivered across phases 2 to 5:

- Service decomposition from `RagApplicationService` into focused application services.
- Dependency composition through contracts/protocols.
- UI split between Qt widgets (shell), HTTP transport, and presenters/controllers.
- Runtime/store cutover guardrails validated with contract tests.

## What changed

### Service layer

- `src/coderag/core/service.py` remains the stable facade.
- Query/TDM/index/policy/ingestion responsibilities moved into focused services:
  - `src/coderag/core/query_service.py`
  - `src/coderag/core/tdm_query_service.py`
  - `src/coderag/core/tdm_ingestion_service.py`
  - `src/coderag/core/index_coordinator_service.py`
  - `src/coderag/core/tdm_policy_service.py`
  - `src/coderag/core/ingestion_service.py`
  - `src/coderag/core/job_service.py`

### Dependency composition

- `src/coderag/core/protocols.py` defines runtime contracts.
- `src/coderag/core/composition.py` centralizes dependency wiring.
- Runtime singleton wiring is done in `src/coderag/core/runtime.py`.

### UI layer

- `src/coderag/ui/main_window.py` acts as shell/composition root.
- HTTP transport moved to `src/coderag/ui/api_client.py`.
- Input validation and payload building moved to:
  - `src/coderag/ui/ingestion_presenter.py`
  - `src/coderag/ui/query_presenter.py`
  - `src/coderag/ui/tdm_presenter.py`
  - `src/coderag/ui/document_catalog_controller.py`

## Migration actions for contributors

1. If you add a new use case, extend a focused service first and keep facade methods thin.
2. If you add a dependency, wire it in `core/composition.py` and test the wiring contract.
3. If you change UI behavior, prefer presenter/controller updates over widget business logic.
4. Add or update focused tests for runtime routing and composition contracts.

## Test suites to run

Run at least:

```bash
pytest -q tests/test_composition.py tests/test_runtime_store_selection.py tests/test_hybrid_metadata_store.py
pytest -q tests/test_ui_api_client.py tests/test_ingestion_presenter.py tests/test_query_presenter.py tests/test_tdm_presenter.py tests/test_main_window_ingestion_mode.py
```

## Related guides

- `docs/migration-guides/MIGRATION_UI_PHASE3_PRESENTERS.md`
