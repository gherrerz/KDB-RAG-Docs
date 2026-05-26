"""Tests for final PostgreSQL schema state after graph-edges drop."""

from __future__ import annotations

from coderag.storage.postgres_schema import (
    POSTGRES_CHUNKS_TABLE_NAME,
    POSTGRES_DOCUMENTS_TABLE_NAME,
    POSTGRES_GRAPH_EDGES_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
)


def test_postgres_schema_metadata_excludes_graph_edges_table() -> None:
    """Runtime schema metadata should no longer include GraphEdges table."""
    table_names = set(POSTGRES_SCHEMA_METADATA.tables.keys())

    assert POSTGRES_GRAPH_EDGES_TABLE_NAME not in table_names
    assert POSTGRES_DOCUMENTS_TABLE_NAME in table_names
    assert POSTGRES_CHUNKS_TABLE_NAME in table_names
