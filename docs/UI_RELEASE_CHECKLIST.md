# UI Release Checklist

Checklist operativo para validar la experiencia UI antes de publicar una version.

## 1. Consistencia visual

- Verificar tema cargado en toda la aplicacion (tabs, formularios, botones, tablas).
- Confirmar contraste de estados visuales: `inactivo`, `en curso`, `ok`, `error`.
- Revisar espaciado en ventana normal y maximizada (sin solapamientos ni cortes).

## 2. Usabilidad y accesibilidad

- Confirmar orden de tabulacion en Ingestion y Query.
- Verificar atajos:
  - Ingestion: `Ctrl+I` (ingerir), `Ctrl+T` (mostrar/ocultar tecnico).
  - Query: `Ctrl+Enter`/`Ctrl+Return` (consultar), `Ctrl+D` (diagnosticos), `Ctrl+J` (JSON crudo).
- Validar foco inicial en campo de pregunta al abrir Query.
- Confirmar que Query permite abrir el selector de documentos, seleccionar
  multiples documentos y limpiar el filtro sin perder el `source_id` opcional.
- Confirmar mensajes de validacion en espanol y accion sugerida en errores.

## 3. Flujo funcional

- Ingestion folder valida ruta local obligatoria.
- Ingestion confluence valida URL base y token obligatorios.
- Filtros JSON invalidos se bloquean antes de enviar request.
- Query valida pregunta obligatoria y hops entre 1 y 6.
- Query mantiene `Source ID` como filtro opcional de ingesta y permite sumar
  filtro multi-documento con documentos ya ingestados.
- Evidencia ordena por `score` descendente y muestra detalle al seleccionar fila.

## 4. Diagnostico tecnico

- Confirmar toggles de panel tecnico funcionan sin perder informacion:
  - Ingestion: timeline + JSON crudo.
  - Query: diagnosticos + JSON crudo.
- Verificar que los errores muestren detalle y accion sugerida.

## 5. Regresion minima recomendada

- Ejecutar gate smoke unificado:
  - `.venv\Scripts\python.exe scripts\run_release_gates.py --mode smoke`
- Ejecutar pruebas UI:
  - `.venv\Scripts\python.exe -m pytest -q tests/test_query_view.py tests/test_ingestion_view.py tests/test_evidence_view.py`
- Ejecutar regresion completa:
  - `.venv\Scripts\python.exe -m pytest -q`

## 6. Evidencia para release

- Capturas recomendadas:
  - Ingestion: estado `en curso` con barra de progreso y resumen.
  - Query: resultado exitoso con evidencia y paths.
  - Query: error accionable mostrado en panel de respuesta.
- Confirmar `README.md` y `CHANGELOG.md` actualizados.
