"""Tests for additive TDM metadata schema and repository APIs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from coderag.storage.metadata_store import MetadataStore


EXPECTED_TDM_TABLES = {
    "tdm_schemas",
    "tdm_tables",
    "tdm_columns",
    "tdm_service_mappings",
    "tdm_masking_rules",
    "tdm_virtualization_artifacts",
    "tdm_synthetic_profiles",
}


def _list_tables(db_path: Path) -> set[str]:
    """Return all table names from one SQLite database file."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return {str(row[0]) for row in rows}
    finally:
        conn.close()


def test_tdm_tables_are_created_and_legacy_tables_remain(tmp_path: Path) -> None:
    """Create store schema and verify additive TDM tables exist."""
    db_path = tmp_path / "metadata.db"
    MetadataStore(db_path)

    tables = _list_tables(db_path)
    assert "documents" in tables
    assert "chunks" in tables
    assert "graph_edges" in tables
    assert "runtime_state" in tables

    for table_name in EXPECTED_TDM_TABLES:
        assert table_name in tables


def test_tdm_schema_creation_is_idempotent(tmp_path: Path) -> None:
    """Re-initialize store twice without migration conflicts."""
    db_path = tmp_path / "metadata.db"
    MetadataStore(db_path)
    MetadataStore(db_path)

    tables = _list_tables(db_path)
    for table_name in EXPECTED_TDM_TABLES:
        assert table_name in tables


def test_tdm_repository_upserts_and_lists(tmp_path: Path) -> None:
    """Persist and read back TDM entities using additive APIs."""
    db_path = tmp_path / "metadata.db"
    store = MetadataStore(db_path)

    store.upsert_tdm_schema(
        schema_id="schema-1",
        source_id="src-1",
        database_name="billing",
        schema_name="public",
        metadata={"owner": "qa"},
    )
    store.upsert_tdm_table(
        table_id="table-1",
        source_id="src-1",
        schema_id="schema-1",
        table_name="invoices",
        metadata={"critical": True},
    )
    store.upsert_tdm_column(
        column_id="col-1",
        source_id="src-1",
        table_id="table-1",
        column_name="customer_email",
        data_type="varchar",
        nullable=False,
        pii_class="email",
    )
    store.upsert_tdm_service_mapping(
        mapping_id="map-1",
        source_id="src-1",
        service_name="billing-api",
        endpoint="/v1/invoices",
        method="GET",
        table_id="table-1",
    )
    store.upsert_tdm_masking_rule(
        rule_id="rule-1",
        source_id="src-1",
        rule_name="mask-email",
        policy_type="tokenize",
        scope="column",
        column_id="col-1",
        priority=10,
    )
    store.upsert_tdm_virtualization_artifact(
        artifact_id="artifact-1",
        source_id="src-1",
        service_name="billing-api",
        artifact_type="mock-template",
        content={"endpoint": "/v1/invoices"},
    )
    store.upsert_tdm_synthetic_profile(
        profile_id="profile-1",
        source_id="src-1",
        profile_name="billing-smoke",
        target_table_id="table-1",
        strategy="template",
    )

    assert len(store.list_tdm_schemas(source_id="src-1")) == 1
    assert len(store.list_tdm_tables(source_id="src-1")) == 1
    assert len(store.list_tdm_columns(source_id="src-1")) == 1
    assert len(store.list_tdm_service_mappings(source_id="src-1")) == 1
    assert len(store.list_tdm_masking_rules(source_id="src-1")) == 1
    assert len(store.list_tdm_virtualization_artifacts(source_id="src-1")) == 1
    assert len(store.list_tdm_synthetic_profiles(source_id="src-1")) == 1


def test_clear_all_data_removes_additive_tdm_rows(tmp_path: Path) -> None:
    """Full reset should clear TDM rows alongside core ingestion tables."""
    db_path = tmp_path / "metadata.db"
    store = MetadataStore(db_path)

    store.upsert_tdm_schema(
        schema_id="schema-1",
        source_id="src-1",
        database_name="billing",
        schema_name="public",
        metadata={"owner": "qa"},
    )
    store.upsert_tdm_table(
        table_id="table-1",
        source_id="src-1",
        schema_id="schema-1",
        table_name="invoices",
        metadata={},
    )
    store.upsert_tdm_column(
        column_id="col-1",
        source_id="src-1",
        table_id="table-1",
        column_name="customer_email",
        data_type="varchar",
        nullable=False,
        pii_class="email",
    )
    store.upsert_tdm_service_mapping(
        mapping_id="map-1",
        source_id="src-1",
        service_name="billing-api",
        endpoint="/v1/invoices",
        method="GET",
        table_id="table-1",
    )
    store.upsert_tdm_masking_rule(
        rule_id="rule-1",
        source_id="src-1",
        rule_name="mask-email",
        policy_type="tokenize",
        scope="column",
        column_id="col-1",
        priority=10,
    )
    store.upsert_tdm_virtualization_artifact(
        artifact_id="artifact-1",
        source_id="src-1",
        service_name="billing-api",
        artifact_type="mock-template",
        content={"endpoint": "/v1/invoices"},
    )
    store.upsert_tdm_synthetic_profile(
        profile_id="profile-1",
        source_id="src-1",
        profile_name="billing-smoke",
        target_table_id="table-1",
        strategy="template",
    )

    store.clear_all_data()

    assert store.list_tdm_schemas(source_id="src-1") == []
    assert store.list_tdm_tables(source_id="src-1") == []
    assert store.list_tdm_columns(source_id="src-1") == []
    assert store.list_tdm_service_mappings(source_id="src-1") == []
    assert store.list_tdm_masking_rules(source_id="src-1") == []
    assert store.list_tdm_virtualization_artifacts(source_id="src-1") == []
    assert store.list_tdm_synthetic_profiles(source_id="src-1") == []
