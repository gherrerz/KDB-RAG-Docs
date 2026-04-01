# Migration Guide 0.2.x -> 0.3.0 (TDM Additive)

## Objetivo

Habilitar capacidades TDM (catalogo de esquemas, masking, virtualizacion y
planificacion sintetica) sin romper los servicios existentes.

Este upgrade es **aditivo**:
- Las rutas legacy (`/sources/*`, `/query*`) mantienen contrato.
- Las rutas TDM (`/tdm/*`) son opt-in y dependen de feature flags.

## Cambios incluidos

- Nuevas tablas SQLite de catalogo TDM:
  - `tdm_schemas`
  - `tdm_tables`
  - `tdm_columns`
  - `tdm_service_mappings`
  - `tdm_masking_rules`
  - `tdm_virtualization_artifacts`
  - `tdm_synthetic_profiles`
- Nuevas rutas API TDM:
  - `POST /tdm/ingest`
  - `POST /tdm/query`
  - `GET /tdm/catalog/services/{service_name}`
  - `GET /tdm/catalog/tables/{table_name}`
  - `POST /tdm/virtualization/preview`
  - `GET /tdm/synthetic/profile/{table_name}`
- Grafo tipado TDM en Neo4j para relaciones de catalogo.

## Feature Flags

Todos en `false` por default para compatibilidad estricta.

```dotenv
ENABLE_TDM=false
TDM_ENABLE_MASKING=false
TDM_ENABLE_VIRTUALIZATION=false
TDM_ENABLE_SYNTHETIC=false
TDM_ADMIN_ENDPOINTS=false
```

## Rollout recomendado

1. Deploy de codigo con todos los flags en `false`.
2. Smoke de compatibilidad legacy:
   - `GET /health`
   - `POST /sources/ingest`
   - `POST /query`
3. Activar solo `ENABLE_TDM=true` en staging.
4. Ejecutar ingesta TDM inicial:
   - `POST /tdm/ingest` con `source_type=tdm_folder`.
5. Activar flags por capacidad de forma progresiva:
   - `TDM_ENABLE_MASKING=true`
   - `TDM_ENABLE_VIRTUALIZATION=true`
   - `TDM_ENABLE_SYNTHETIC=true`
6. Validar rutas TDM y mantener monitoreo de rutas legacy.

## Rollback

Si se requiere rollback rapido:

1. Volver todos los flags TDM a `false`.
2. Reiniciar proceso API/UI.

Resultado esperado:
- `/tdm/*` deja de estar disponible (404).
- `/sources/*` y `/query*` siguen operando con contrato previo.

No se pierde informacion legacy de documentos/chunks/jobs.

## Validacion post-migracion

Ejecutar en Windows:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_tdm_api_routes.py tests/test_tdm_ingestion_pipeline.py tests/test_api_async_toggle.py
```

## Riesgos conocidos

- El grafo TDM depende de Neo4j habilitado y accesible.
- El preview de virtualizacion requiere `TDM_ENABLE_VIRTUALIZATION=true`.
- El perfil sintetico requiere `TDM_ENABLE_SYNTHETIC=true`.
- El masking preview requiere `TDM_ENABLE_MASKING=true`.

## Referencias

- [docs/API_REFERENCE.md](../API_REFERENCE.md)
- [docs/CONFIGURATION.md](../CONFIGURATION.md)
- [docs/ARCHITECTURE.md](../ARCHITECTURE.md)
