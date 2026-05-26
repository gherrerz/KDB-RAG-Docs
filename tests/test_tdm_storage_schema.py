"""Tests for Postgres-backed TDM metadata schema and repository APIs."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect

from coderag.core.models import ChunkRecord, DocumentRecord
from coderag.core.settings import SETTINGS
from coderag.storage.hybrid_metadata_store import HybridMetadataStore
from coderag.storage.postgres_schema import (
    POSTGRES_CHUNKS_TABLE_NAME,
    POSTGRES_DOCUMENTS_TABLE_NAME,
    POSTGRES_RUNTIME_STATE_TABLE_NAME,
    POSTGRES_TDM_COLUMNS_TABLE_NAME,
    POSTGRES_TDM_MASKING_RULES_TABLE_NAME,
    POSTGRES_TDM_SCHEMAS_TABLE_NAME,
    POSTGRES_TDM_SERVICE_MAPPINGS_TABLE_NAME,
    POSTGRES_TDM_SYNTHETIC_PROFILES_TABLE_NAME,
    POSTGRES_TDM_TABLES_TABLE_NAME,
    POSTGRES_TDM_VIRTUALIZATION_ARTIFACTS_TABLE_NAME,
)
from coderag.storage.postgres_session import (
    PostgresSessionFactory,
    resolve_postgres_dsn,
)
from coderag.storage.postgres_startup import ensure_postgres_schema_ready


pytest.importorskip("sqlalchemy")


EXPECTED_CORE_TABLES = {
    POSTGRES_DOCUMENTS_TABLE_NAME,
    POSTGRES_CHUNKS_TABLE_NAME,
    POSTGRES_RUNTIME_STATE_TABLE_NAME,
}

EXPECTED_TDM_TABLES = {
    POSTGRES_TDM_SCHEMAS_TABLE_NAME,
    POSTGRES_TDM_TABLES_TABLE_NAME,
    POSTGRES_TDM_COLUMNS_TABLE_NAME,
    POSTGRES_TDM_SERVICE_MAPPINGS_TABLE_NAME,
    POSTGRES_TDM_MASKING_RULES_TABLE_NAME,
    POSTGRES_TDM_VIRTUALIZATION_ARTIFACTS_TABLE_NAME,
    POSTGRES_TDM_SYNTHETIC_PROFILES_TABLE_NAME,
}


def _postgres_dsn_or_skip() -> str:
    """Return active Postgres DSN or skip when it is not configured."""
    postgres_dsn = resolve_postgres_dsn(SETTINGS)
    if not postgres_dsn:
        pytest.skip("Postgres DSN is required for TDM storage schema tests.")
    return postgres_dsn


def _build_store() -> HybridMetadataStore:
    """Build runtime store backed by the active Postgres connection."""
    ensure_postgres_schema_ready(SETTINGS, force=True)
    return HybridMetadataStore(postgres_dsn=_postgres_dsn_or_skip())


def _list_tables(postgres_dsn: str) -> set[str]:
    """Return all visible table names from active Postgres schema."""
    session_factory = PostgresSessionFactory(postgres_dsn)
    try:
        return set(inspect(session_factory.engine).get_table_names())
    finally:
        session_factory.engine.dispose()


def test_tdm_tables_are_created_with_core_runtime_tables() -> None:
    """Create store schema and verify core + additive TDM tables exist."""
    ensure_postgres_schema_ready(SETTINGS, force=True)
    tables = _list_tables(_postgres_dsn_or_skip())

    assert EXPECTED_CORE_TABLES.issubset(tables)
    assert EXPECTED_TDM_TABLES.issubset(tables)


def test_tdm_schema_creation_is_idempotent() -> None:
    """Re-initialize store twice without migration conflicts."""
    postgres_dsn = _postgres_dsn_or_skip()
    ensure_postgres_schema_ready(SETTINGS, force=True)
    ensure_postgres_schema_ready(SETTINGS, force=True)

    tables = _list_tables(postgres_dsn)
    assert EXPECTED_TDM_TABLES.issubset(tables)


def test_tdm_repository_upserts_and_lists() -> None:
    """Persist and read back TDM entities using additive APIs."""
    store = _build_store()
    suffix = uuid4().hex
    source_id = f"src-{suffix}"
    schema_id = f"schema-{suffix}"
    table_id = f"table-{suffix}"
    column_id = f"col-{suffix}"
    mapping_id = f"map-{suffix}"
    rule_id = f"rule-{suffix}"
    artifact_id = f"artifact-{suffix}"
    profile_id = f"profile-{suffix}"

    store.upsert_tdm_schema(
        schema_id=schema_id,
        source_id=source_id,
        database_name="billing",
        schema_name="public",
        metadata={"owner": "qa"},
    )
    store.upsert_tdm_table(
        table_id=table_id,
        source_id=source_id,
        schema_id=schema_id,
        table_name="invoices",
        metadata={"critical": True},
    )
    store.upsert_tdm_column(
        column_id=column_id,
        source_id=source_id,
        table_id=table_id,
        column_name="customer_email",
        data_type="varchar",
        nullable=False,
        pii_class="email",
    )
    store.upsert_tdm_service_mapping(
        mapping_id=mapping_id,
        source_id=source_id,
        service_name="billing-api",
        endpoint="/v1/invoices",
        method="GET",
        table_id=table_id,
    )
    store.upsert_tdm_masking_rule(
        rule_id=rule_id,
        source_id=source_id,
        rule_name="mask-email",
        policy_type="tokenize",
        scope="column",
        column_id=column_id,
        priority=10,
    )
    store.upsert_tdm_virtualization_artifact(
        artifact_id=artifact_id,
        source_id=source_id,
        service_name="billing-api",
        artifact_type="mock-template",
        content={"endpoint": "/v1/invoices"},
    )
    store.upsert_tdm_synthetic_profile(
        profile_id=profile_id,
        source_id=source_id,
        profile_name="billing-smoke",
        target_table_id=table_id,
        strategy="template",
    )

    assert len(store.list_tdm_schemas(source_id=source_id)) == 1
    assert len(store.list_tdm_tables(source_id=source_id)) == 1
    assert len(store.list_tdm_columns(source_id=source_id)) == 1
    assert len(store.list_tdm_service_mappings(source_id=source_id)) == 1
    assert len(store.list_tdm_masking_rules(source_id=source_id)) == 1
    assert len(store.list_tdm_virtualization_artifacts(source_id=source_id)) == 1
    assert len(store.list_tdm_synthetic_profiles(source_id=source_id)) == 1


def test_clear_all_data_removes_additive_tdm_rows() -> None:
    """Full reset should clear TDM rows alongside core ingestion tables."""
    store = _build_store()
    suffix = uuid4().hex
    source_id = f"src-{suffix}"
    document_id = f"doc-{suffix}"
    schema_id = f"schema-{suffix}"
    table_id = f"table-{suffix}"
    column_id = f"col-{suffix}"
    mapping_id = f"map-{suffix}"
    rule_id = f"rule-{suffix}"
    artifact_id = f"artifact-{suffix}"
    profile_id = f"profile-{suffix}"

    store.upsert_document(
        DocumentRecord(
            document_id=document_id,
            source_id=source_id,
            title="Billing",
            content="test payload",
            path_or_url=f"sample_data/{document_id}.md",
            content_type="md",
            updated_at=datetime.now(UTC),
            metadata={"origin": "test"},
        )
    )
    store.replace_chunks(
        source_id=source_id,
        chunks=[
            ChunkRecord(
                chunk_id=f"chunk-{suffix}",
                document_id=document_id,
                source_id=source_id,
                section_name="intro",
                text="hello",
                start_ref=0,
                end_ref=5,
                entity_name=None,
                entity_type=None,
                metadata={},
            )
        ],
    )

    store.upsert_tdm_schema(
        schema_id=schema_id,
        source_id=source_id,
        database_name="billing",
        schema_name="public",
        metadata={"owner": "qa"},
    )
    store.upsert_tdm_table(
        table_id=table_id,
        source_id=source_id,
        schema_id=schema_id,
        table_name="invoices",
        metadata={},
    )
    store.upsert_tdm_column(
        column_id=column_id,
        source_id=source_id,
        table_id=table_id,
        column_name="customer_email",
        data_type="varchar",
        nullable=False,
        pii_class="email",
    )
    store.upsert_tdm_service_mapping(
        mapping_id=mapping_id,
        source_id=source_id,
        service_name="billing-api",
        endpoint="/v1/invoices",
        method="GET",
        table_id=table_id,
    )
    store.upsert_tdm_masking_rule(
        rule_id=rule_id,
        source_id=source_id,
        rule_name="mask-email",
        policy_type="tokenize",
        scope="column",
        column_id=column_id,
        priority=10,
    )
    store.upsert_tdm_virtualization_artifact(
        artifact_id=artifact_id,
        source_id=source_id,
        service_name="billing-api",
        artifact_type="mock-template",
        content={"endpoint": "/v1/invoices"},
    )
    store.upsert_tdm_synthetic_profile(
        profile_id=profile_id,
        source_id=source_id,
        profile_name="billing-smoke",
        target_table_id=table_id,
        strategy="template",
    )

    deleted = store.clear_all_data()

    assert deleted["deleted_documents"] >= 1
    assert deleted["deleted_chunks"] >= 1
    assert deleted["deleted_jobs"] >= 0
    assert store.list_documents(source_id=source_id) == []
    assert store.list_chunks(source_id=source_id) == []
    assert store.list_tdm_schemas(source_id=source_id) == []
    assert store.list_tdm_tables(source_id=source_id) == []
    assert store.list_tdm_columns(source_id=source_id) == []
    assert store.list_tdm_service_mappings(source_id=source_id) == []
    assert store.list_tdm_masking_rules(source_id=source_id) == []
    assert store.list_tdm_virtualization_artifacts(source_id=source_id) == []
    assert store.list_tdm_synthetic_profiles(source_id=source_id) == []
