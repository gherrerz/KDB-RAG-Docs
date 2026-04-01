"""Unit tests for SQL DDL parser used by TDM ingestion."""

from __future__ import annotations

from coderag.parsers.sql_schema_parser import parse_sql_schema


def test_parse_sql_schema_extracts_tables_and_columns() -> None:
    """Parse CREATE TABLE statements into schema/table/column assets."""
    sql = """
    CREATE TABLE public.customers (
        id BIGINT NOT NULL,
        customer_email VARCHAR(255),
        created_at TIMESTAMP,
        PRIMARY KEY (id)
    );

    CREATE TABLE billing.invoices (
        invoice_id BIGINT NOT NULL,
        customer_id BIGINT,
        total_amount DECIMAL(10,2)
    );
    """

    parsed = parse_sql_schema(sql)

    assert len(parsed["schemas"]) == 2
    assert len(parsed["tables"]) == 2
    assert any(t["table_name"] == "customers" for t in parsed["tables"])
    assert any(t["table_name"] == "invoices" for t in parsed["tables"])

    columns = parsed["columns"]
    assert any(c["column_name"] == "id" and c["nullable"] is False for c in columns)
    assert any(
        c["column_name"] == "customer_email"
        and c["pii_class"] == "email"
        for c in columns
    )
