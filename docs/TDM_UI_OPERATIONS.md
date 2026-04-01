# TDM UI Operations Guide

Guia operativa para usar la pestana TDM en la UI sin afectar flujos legacy.

## Objetivo

La pestana TDM permite operar endpoints `/tdm/*` de forma aditiva:

- Ingesta de catalogo tecnico.
- Consultas TDM por pregunta, servicio o tabla.
- Catalogo por servicio y tabla.
- Preview de virtualizacion.
- Perfil sintetico.

Las rutas legacy (`/sources/*` y `/query*`) no cambian.

## Requisitos

- API y UI levantadas.
- `ENABLE_TDM=true` para habilitar rutas `/tdm/*`.
- Flags por capacidad segun caso:
  - `TDM_ENABLE_MASKING=true`
  - `TDM_ENABLE_VIRTUALIZATION=true`
  - `TDM_ENABLE_SYNTHETIC=true`

## Flujo recomendado

1. Ejecutar `Ingest TDM` con `source_type=tdm_folder` y ruta tecnica.
2. Ejecutar `Query TDM` para validar hallazgos iniciales.
3. Consultar `Service Catalog` para un servicio concreto.
4. Consultar `Table Catalog` para inspeccionar columnas.
5. Usar `Virtualization Preview` cuando esa capacidad este habilitada.
6. Usar `Synthetic Profile` cuando esa capacidad este habilitada.

## Operacion de resultados

La vista de resultados permite:

- Filtro por tipo (`finding`, `service_mapping`, `table`, `column`, etc.).
- Filtro por texto en columnas visibles.
- Export de filas visibles a JSON crudo.
- Panel de detalle por fila.
- Panel de JSON crudo completo.

### Quick Actions

- Copiar JSON de fila
- Copiar endpoint/metodo
- Cargar fila en raw
- Exportar filas visibles

### Atajos de teclado

- `Ctrl+Shift+C`: copiar fila JSON.
- `Ctrl+Shift+E`: copiar endpoint/metodo.
- `Ctrl+Shift+L`: cargar fila seleccionada en panel raw.
- `Ctrl+Shift+X`: exportar filas visibles.

## Troubleshooting rapido

- Mensaje TDM deshabilitado:
  - Verificar `ENABLE_TDM=true`.
- Mensaje de capacidad deshabilitada:
  - Verificar flag de capacidad correspondiente.
- Estado `503`:
  - Revisar disponibilidad del backend y dependencias.
- Resultado vacio:
  - Ajustar filtros, `source_id`, `service_name` o `table_name`.

## Limitaciones conocidas

- La calidad de hallazgos depende de la calidad de las fuentes tecnicas
  (DDL/OpenAPI/diccionario). Si faltan metadatos, la tabla puede quedar parcial.
- El parser OpenAPI en modo YAML-like es best-effort (sin dependencia externa),
  por lo que contratos muy complejos pueden requerir JSON u homogeneizar formato.
- El preview de virtualizacion y el perfil sintetico no reemplazan validaciones
  funcionales E2E; se usan como apoyo rapido para diseño y pruebas iniciales.
- En consultas TDM con filtros estrictos (servicio/tabla/source_id), un resultado
  vacio no implica error; puede requerir ampliar filtros o re-ejecutar ingesta.
- Los atajos de teclado de quick actions aplican en la pestana TDM y pueden no
  disparar si otro control global de teclado toma foco en el entorno de escritorio.

## Validacion sugerida

Para validar cambios de UI TDM:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_tdm_view.py tests/test_main_window_tdm_wiring.py -q
```

Para validar regresion amplia:

```powershell
.venv\Scripts\python.exe -m pytest -q
```
