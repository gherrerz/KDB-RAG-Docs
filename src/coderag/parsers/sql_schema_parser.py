"""Parse SQL DDL snippets into structured TDM schema assets."""

from __future__ import annotations

import re
from typing import Any, Dict, List

CREATE_TABLE_PATTERN = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>[\w\.\"`\[\]]+)\s*\((?P<body>.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
COLUMN_PATTERN = re.compile(
    r"^\s*(?P<name>[\w\"`\[\]]+)\s+"
    r"(?P<dtype>[A-Z][A-Z0-9_]*(?:\s*\([^\)]*\))?)",
    re.IGNORECASE,
)

PII_HINTS = {
    "email": "email",
    "phone": "phone",
    "telefono": "phone",
    "ssn": "national_id",
    "dni": "national_id",
    "passport": "passport",
    "tarjeta": "payment_card",
    "card": "payment_card",
    "iban": "iban",
}


def _normalize_identifier(value: str) -> str:
    """Remove common SQL identifier wrappers and normalize whitespace."""
    cleaned = value.strip().strip('"`[]')
    return cleaned


def _split_table_name(full_name: str) -> tuple[str, str]:
    """Split a SQL table reference into schema and table names."""
    normalized = _normalize_identifier(full_name)
    if "." not in normalized:
        return "public", normalized
    schema, table = normalized.split(".", 1)
    return _normalize_identifier(schema), _normalize_identifier(table)


def _guess_pii_class(column_name: str) -> str | None:
    """Infer a coarse PII class from a column name using lexical hints."""
    lowered = column_name.casefold()
    for hint, pii_class in PII_HINTS.items():
        if hint in lowered:
            return pii_class
    return None


def _parse_columns(table_body: str) -> List[Dict[str, Any]]:
    """Parse column definitions from one CREATE TABLE body block."""
    columns: List[Dict[str, Any]] = []
    for raw_line in table_body.splitlines():
        line = raw_line.strip().rstrip(",")
        if not line:
            continue
        # Skip table-level constraints and indexes for this lightweight pass.
        if re.match(
            r"^(PRIMARY|FOREIGN|UNIQUE|CONSTRAINT|CHECK|INDEX)\b",
            line,
            flags=re.IGNORECASE,
        ):
            continue

        match = COLUMN_PATTERN.match(line)
        if match is None:
            continue

        column_name = _normalize_identifier(match.group("name"))
        data_type = match.group("dtype").strip()
        nullable = "NOT NULL" not in line.upper()
        columns.append(
            {
                "column_name": column_name,
                "data_type": data_type,
                "nullable": nullable,
                "pii_class": _guess_pii_class(column_name),
            }
        )
    return columns


def parse_sql_schema(sql_text: str) -> Dict[str, Any]:
    """Extract schema, table, and column metadata from SQL DDL text."""
    schemas: Dict[str, Dict[str, Any]] = {}
    tables: List[Dict[str, Any]] = []
    columns: List[Dict[str, Any]] = []

    for table_match in CREATE_TABLE_PATTERN.finditer(sql_text):
        full_name = table_match.group("name")
        table_body = table_match.group("body")
        schema_name, table_name = _split_table_name(full_name)

        if schema_name not in schemas:
            schemas[schema_name] = {
                "database_name": "default",
                "schema_name": schema_name,
            }

        table_entry = {
            "schema_name": schema_name,
            "table_name": table_name,
            "table_type": "table",
        }
        tables.append(table_entry)

        for column in _parse_columns(table_body):
            columns.append(
                {
                    "schema_name": schema_name,
                    "table_name": table_name,
                    **column,
                }
            )

    return {
        "schemas": list(schemas.values()),
        "tables": tables,
        "columns": columns,
    }
