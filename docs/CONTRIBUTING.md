# Contributing

## Workflow

1. Crea una rama de trabajo.
2. Implementa cambios con tests.
3. Ejecuta linters y pruebas.
4. Actualiza documentacion si cambias codigo.
5. Abre pull request.

Para cambios de UI desktop, prioriza este patron:

- Widget Qt como shell de composicion y render.
- Transporte HTTP en `ui/api_client.py`.
- Validaciones/normalizacion en presenters o controladores puros.

## Quality checklist

- Tests verdes
- Sin regresiones funcionales
- Documentacion alineada con codigo
- Cambios de API documentados
- Cobertura para presenters/clientes extraidos cuando se mueve logica fuera de vistas

## Service and Runtime refactor guardrails

- Mantener `core/service.py` como fachada estable; mover logica nueva a
  servicios enfocados (`query_service`, `tdm_*`, `ingestion_service`, etc.).
- Si se agrega una dependencia al servicio, cablearla desde
  `core/composition.py` y evitar instanciar concretos en la logica de casos
  de uso.
- Si se cambia el comportamiento del runtime de storage, cubrir el ruteo en
  `tests/test_runtime_store_selection.py` y/o
  `tests/test_hybrid_metadata_store.py`.

## UI refactor guardrails

- Los widgets Qt deben actuar como shell de render/composicion.
- Transporte HTTP: `src/coderag/ui/api_client.py`.
- Validacion y normalizacion: presenters/controladores puros.
- Al agregar funcionalidad UI, priorizar pruebas unitarias del presenter o
  controlador antes de pruebas de vista.

## Recommended focused test run

```bash
pytest -q tests/test_composition.py tests/test_runtime_store_selection.py tests/test_hybrid_metadata_store.py
pytest -q tests/test_ui_api_client.py tests/test_ingestion_presenter.py tests/test_query_presenter.py tests/test_tdm_presenter.py tests/test_main_window_ingestion_mode.py
```
