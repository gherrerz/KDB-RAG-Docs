"""Tests for typed TDM graph edge builder."""

from __future__ import annotations

from coderag.ingestion.tdm_graph_builder import build_tdm_typed_edges


def test_build_tdm_typed_edges_creates_expected_relations() -> None:
    """Generate typed graph edges from TDM catalog rows."""
    edges = build_tdm_typed_edges(
        source_id="src-1",
        schemas=[
            {
                "schema_id": "schema-1",
                "schema_name": "billing",
            }
        ],
        tables=[
            {
                "table_id": "table-1",
                "schema_id": "schema-1",
                "table_name": "invoices",
            }
        ],
        columns=[
            {
                "column_id": "col-1",
                "table_id": "table-1",
                "column_name": "customer_email",
                "pii_class": "email",
            }
        ],
        mappings=[
            {
                "service_name": "billing-api",
                "endpoint": "/v1/invoices",
                "method": "GET",
                "table_id": "table-1",
            }
        ],
        masking_rules=[
            {
                "rule_name": "mask-email",
                "table_id": "table-1",
            }
        ],
    )

    edge_set = set(edges)
    assert ("billing-api", "USES_TABLE", "invoices", "src-1") in edge_set
    assert ("invoices", "HAS_COLUMN", "customer_email", "src-1") in edge_set
    assert ("customer_email", "HAS_PII_CLASS", "email", "src-1") in edge_set
    assert ("invoices", "MASKED_BY", "mask-email", "src-1") in edge_set
    assert (
        "billing-api",
        "EXPOSES_ENDPOINT",
        "/v1/invoices",
        "src-1",
    ) in edge_set
