# MIGRATION: UI Phase 3 Presenter + Api Client Split

## Objetivo

Separar transporte HTTP, validaciones y transformaciones de datos fuera de los widgets Qt para reducir acoplamiento y facilitar pruebas unitarias.

## Cambios aplicados

- Se extrae cliente HTTP reusable en src/coderag/ui/api_client.py.
- MainWindow pasa a delegar operaciones API/TDM en UiApiClient.
- IngestionView delega validacion/payload en src/coderag/ui/ingestion_presenter.py.
- IngestionView delega render tecnico/resumen en src/coderag/ui/ingestion_formatters.py.
- QueryView delega validacion/payload en src/coderag/ui/query_presenter.py.
- QueryView delega normalizacion/seleccion de catalogo en src/coderag/ui/document_catalog_controller.py.
- TdmView delega payload builders, hints y normalizacion de filas en src/coderag/ui/tdm_presenter.py.

## Compatibilidad

- Contrato de callbacks de las vistas se mantiene sin cambios.
- Endpoints invocados por la UI no cambian.
- Helpers estaticos legacy en views se mantienen como wrappers para compatibilidad de tests existentes.

## Impacto en pruebas

- Se reorientan pruebas de MainWindow para validar delegacion a UiApiClient.
- Se agregan pruebas unitarias para UiApiClient y presenters.
- Se agrega prueba de composicion de dependencias core en tests/test_composition.py.

## Checklist post-migracion

- Ejecutar pytest focalizado en UI y presenters.
- Verificar que Ingestion/Query/TDM responden igual desde la UI.
- Confirmar que no quedan llamados HTTP directos en MainWindow.
