"""Build typed TDM graph edges from structured catalog assets."""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


def build_tdm_typed_edges(
    source_id: str,
    schemas: Iterable[Dict[str, object]],
    tables: Iterable[Dict[str, object]],
    columns: Iterable[Dict[str, object]],
    mappings: Iterable[Dict[str, object]],
    masking_rules: Iterable[Dict[str, object]],
) -> List[Tuple[str, str, str, str]]:
    """Create typed graph edges from TDM catalog entities."""
    edges: List[Tuple[str, str, str, str]] = []

    table_name_by_id = {
        str(row.get("table_id")): str(row.get("table_name"))
        for row in tables
        if row.get("table_id") and row.get("table_name")
    }
    schema_name_by_id = {
        str(row.get("schema_id")): str(row.get("schema_name"))
        for row in schemas
        if row.get("schema_id") and row.get("schema_name")
    }

    for table in tables:
        table_id = str(table.get("table_id", ""))
        table_name = str(table.get("table_name", "")).strip()
        schema_id = str(table.get("schema_id", "")).strip()
        schema_name = schema_name_by_id.get(schema_id)
        if not table_name:
            continue
        if schema_name:
            edges.append((table_name, "BACKED_BY_SCHEMA", schema_name, source_id))

    for column in columns:
        table_id = str(column.get("table_id", "")).strip()
        table_name = table_name_by_id.get(table_id, "")
        column_name = str(column.get("column_name", "")).strip()
        pii_class = str(column.get("pii_class", "") or "").strip()
        if table_name and column_name:
            edges.append((table_name, "HAS_COLUMN", column_name, source_id))
        if column_name and pii_class:
            edges.append((column_name, "HAS_PII_CLASS", pii_class, source_id))

    for mapping in mappings:
        service_name = str(mapping.get("service_name", "")).strip()
        endpoint = str(mapping.get("endpoint", "")).strip()
        table_id = str(mapping.get("table_id", "")).strip()
        table_name = table_name_by_id.get(table_id, "")
        if service_name and endpoint:
            edges.append((service_name, "EXPOSES_ENDPOINT", endpoint, source_id))
        if service_name and table_name:
            edges.append((service_name, "USES_TABLE", table_name, source_id))

    for rule in masking_rules:
        rule_name = str(rule.get("rule_name", "")).strip()
        table_id = str(rule.get("table_id", "") or "").strip()
        column_id = str(rule.get("column_id", "") or "").strip()
        table_name = table_name_by_id.get(table_id, "")
        if table_name and rule_name:
            edges.append((table_name, "MASKED_BY", rule_name, source_id))

        if column_id and rule_name:
            # We do not keep a global lookup by column id in this lightweight pass,
            # so this relation is represented only when table scope is known.
            continue

    deduped = list(dict.fromkeys(edges))
    return deduped
