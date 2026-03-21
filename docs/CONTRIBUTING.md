# Contributing

Guia para contribuir con cambios de codigo y documentacion.

## Regla principal

Todo cambio de comportamiento publico debe incluir actualizacion de
README y/o docs relevantes en el mismo cambio.

## Checklist de PR

- README actualizado si cambia onboarding o quick start.
- API_REFERENCE actualizado si cambian endpoints, parametros o payloads.
- CHANGELOG actualizado para cambios visibles al usuario.
- Ejemplos en examples/ actualizados si cambian contratos.
- Diagramas Mermaid actualizados si cambia el flujo de ingesta o query.
- Validacion de docs ejecutada localmente.

## Validacion local de docs

```powershell
.\.venv\Scripts\python scripts/docs/validate_docs.py
.\.venv\Scripts\python scripts/docs/validate_links.py
.\.venv\Scripts\python scripts/docs/validate_examples.py
```

## Estilo de documentacion

- Priorizar claridad y accionabilidad.
- Evitar duplicar tablas extensas entre README y docs.
- Usar README como portal corto y docs/ para detalle.
- Mantener consistencia de terminos entre UI, API y codigo.

## Plantilla para breaking changes

Si hay breaking change, agregar guia en docs/migration-guides/ y registrar en
CHANGELOG.md bajo Changed con prefijo BREAKING.
