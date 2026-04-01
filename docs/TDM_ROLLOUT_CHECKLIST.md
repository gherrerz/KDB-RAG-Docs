# TDM Rollout Checklist

Checklist operativo para habilitar TDM de manera segura y gradual.

## 1. Pre-deploy

- Confirmar backup de `storage/metadata.db`.
- Confirmar conectividad a Neo4j (`USE_NEO4J=true`).
- Confirmar flags TDM en `false` antes del primer deploy.

## 2. Deploy compatible

- Deploy de version con codigo TDM y flags en `false`.
- Validar rutas legacy:
  - `GET /health`
  - `POST /sources/ingest`
  - `POST /query`
- Ejecutar preflight local:
  - `.venv\Scripts\python.exe scripts\preflight_release.py --skip-http`
- Revisar que no hay regresiones en UI.

## 3. Activacion TDM base

- Activar `ENABLE_TDM=true`.
- Ejecutar `POST /tdm/ingest` sobre carpeta tecnica (`tdm_folder`).
- Verificar catalogo:
  - `GET /tdm/catalog/services/{service_name}`
  - `GET /tdm/catalog/tables/{table_name}`

## 4. Activaciones por capacidad

- Masking preview:
  - Activar `TDM_ENABLE_MASKING=true`.
  - Probar `POST /tdm/query` y validar `masking_preview`.

- Virtualizacion:
  - Activar `TDM_ENABLE_VIRTUALIZATION=true`.
  - Probar `POST /tdm/virtualization/preview`.
  - Verificar persistencia en `tdm_virtualization_artifacts`.

- Synthetic planning:
  - Activar `TDM_ENABLE_SYNTHETIC=true`.
  - Probar `GET /tdm/synthetic/profile/{table_name}`.

## 5. Observabilidad

- Monitorear errores 5xx de `/tdm/*`.
- Monitorear latencia y tiempos de ingesta TDM.
- Confirmar estabilidad de rutas legacy.
- Con API levantada, ejecutar:
  - `.venv\Scripts\python.exe scripts\preflight_release.py --base-url http://127.0.0.1:8000`

## 6. Rollback rapido

- Volver flags TDM a `false`.
- Reiniciar API/UI.
- Verificar continuidad de `/sources/*` y `/query*`.
