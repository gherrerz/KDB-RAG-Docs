"""Shared SQLAlchemy metadata for the Docs PostgreSQL schema."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Identity,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, TIMESTAMP, TSVECTOR
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.schema import (
    Column,
    ForeignKey,
    PrimaryKeyConstraint,
    UniqueConstraint,
)


POSTGRES_DOCUMENTS_TABLE_NAME = "Tbl_Documents_Documents"
POSTGRES_CHUNKS_TABLE_NAME = "Tbl_Documents_Chunks"
POSTGRES_LEXICAL_CORPUS_TABLE_NAME = "Tbl_Documents_LexicalCorpus"
POSTGRES_GRAPH_EDGES_TABLE_NAME = "Tbl_Documents_GraphEdges"
POSTGRES_JOBS_TABLE_NAME = "Tbl_Documents_Jobs"
POSTGRES_JOB_EVENTS_TABLE_NAME = "Tbl_Documents_JobEvents"
POSTGRES_RUNTIME_STATE_TABLE_NAME = "Tbl_Documents_RuntimeState"
POSTGRES_TDM_SCHEMAS_TABLE_NAME = "Tbl_Documents_TdmSchemas"
POSTGRES_TDM_TABLES_TABLE_NAME = "Tbl_Documents_TdmTables"
POSTGRES_TDM_COLUMNS_TABLE_NAME = "Tbl_Documents_TdmColumns"
POSTGRES_TDM_SERVICE_MAPPINGS_TABLE_NAME = (
    "Tbl_Documents_TdmServiceMappings"
)
POSTGRES_TDM_MASKING_RULES_TABLE_NAME = "Tbl_Documents_TdmMaskingRules"
POSTGRES_TDM_VIRTUALIZATION_ARTIFACTS_TABLE_NAME = (
    "Tbl_Documents_TdmVirtualizationArtifacts"
)
POSTGRES_TDM_SYNTHETIC_PROFILES_TABLE_NAME = (
    "Tbl_Documents_TdmSyntheticProfiles"
)
POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME = (
    "Tbl_Documents_IngestionArtifacts"
)
POSTGRES_INGESTION_ARTIFACT_FILES_TABLE_NAME = (
    "Tbl_Documents_IngestionArtifactFiles"
)


POSTGRES_SCHEMA_METADATA = MetaData()


class PostgresDeclarativeBase(DeclarativeBase):
    """Declarative base shared by future PostgreSQL ORM models."""

    metadata = POSTGRES_SCHEMA_METADATA


documents_table = Table(
    POSTGRES_DOCUMENTS_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("document_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("path_or_url", Text, nullable=False),
    Column("content_type", Text, nullable=False),
    Column(
        "tags_json",
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    ),
    Column(
        "metadata_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint("document_id", name="pk_tbl_documents_documents"),
    Index("idx_documents_source_id", "source_id"),
)


chunks_table = Table(
    POSTGRES_CHUNKS_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("chunk_id", Text, nullable=False),
    Column(
        "document_id",
        Text,
        ForeignKey(
            f'{POSTGRES_DOCUMENTS_TABLE_NAME}.document_id',
            ondelete="CASCADE",
            name="fk_chunks_document_id",
        ),
        nullable=False,
    ),
    Column("source_id", Text, nullable=False),
    Column("section_name", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("start_ref", BigInteger, nullable=False),
    Column("end_ref", BigInteger, nullable=False),
    Column("entity_name", Text, nullable=True),
    Column("entity_type", Text, nullable=True),
    Column(
        "metadata_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint("chunk_id", name="pk_tbl_documents_chunks"),
    Index("idx_chunks_document_id", "document_id"),
    Index("idx_chunks_source_id", "source_id"),
)


lexical_corpus_table = Table(
    POSTGRES_LEXICAL_CORPUS_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("chunk_id", Text, nullable=False),
    Column("document_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("path_or_url", Text, nullable=False),
    Column("section_name", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column(
        "metadata_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column("fts_vector", TSVECTOR, nullable=True),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint(
        "chunk_id",
        name="pk_tbl_documents_lexicalcorpus",
    ),
    Index("idx_lexical_corpus_source_id", "source_id"),
    Index("idx_lexical_corpus_document_id", "document_id"),
    Index(
        "idx_lexical_corpus_fts",
        "fts_vector",
        postgresql_using="gin",
    ),
)


graph_edges_table = Table(
    POSTGRES_GRAPH_EDGES_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("edge_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("source_node", Text, nullable=False),
    Column("relation", Text, nullable=False),
    Column("target_node", Text, nullable=False),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint("edge_id", name="pk_tbl_documents_graphedges"),
    Index("idx_graph_edges_source_id", "source_id"),
    Index("idx_graph_edges_source_node", "source_node"),
    Index("idx_graph_edges_target_node", "target_node"),
)


jobs_table = Table(
    POSTGRES_JOBS_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("job_id", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("message", Text, nullable=False),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint("job_id", name="pk_tbl_documents_jobs"),
    Index("idx_jobs_status", "status"),
    Index("idx_jobs_created_at", "created_at"),
)


job_events_table = Table(
    POSTGRES_JOB_EVENTS_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column(
        "event_id",
        BigInteger,
        Identity(),
        nullable=False,
    ),
    Column(
        "job_id",
        Text,
        ForeignKey(
            f'{POSTGRES_JOBS_TABLE_NAME}.job_id',
            ondelete="CASCADE",
            name="fk_job_events_job_id",
        ),
        nullable=False,
    ),
    Column("ordinal", BigInteger, nullable=False),
    Column("name", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("elapsed_ms", BigInteger, nullable=False),
    Column(
        "details_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint("event_id", name="pk_tbl_documents_jobevents"),
    UniqueConstraint(
        "job_id",
        "ordinal",
        name="uq_job_events_job_id_ordinal",
    ),
    Index("idx_job_events_job_id", "job_id"),
    Index("idx_job_events_job_id_ordinal", "job_id", "ordinal"),
)


runtime_state_table = Table(
    POSTGRES_RUNTIME_STATE_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("state_key", Text, nullable=False),
    Column("state_value", Text, nullable=False),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint(
        "state_key",
        name="pk_tbl_documents_runtimestate",
    ),
)


tdm_schemas_table = Table(
    POSTGRES_TDM_SCHEMAS_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("schema_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("database_name", Text, nullable=False),
    Column("schema_name", Text, nullable=False),
    Column(
        "metadata_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint("schema_id", name="pk_tbl_documents_tdmschemas"),
    Index("idx_tdm_schemas_source_id", "source_id"),
    UniqueConstraint(
        "source_id",
        "database_name",
        "schema_name",
        name="uq_tdm_schemas_source_database_schema",
    ),
)


tdm_tables_table = Table(
    POSTGRES_TDM_TABLES_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("table_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column(
        "schema_id",
        Text,
        ForeignKey(
            f'{POSTGRES_TDM_SCHEMAS_TABLE_NAME}.schema_id',
            ondelete="CASCADE",
            name="fk_tdm_tables_schema_id",
        ),
        nullable=False,
    ),
    Column("table_name", Text, nullable=False),
    Column(
        "table_type",
        Text,
        nullable=False,
        server_default=text("'table'"),
    ),
    Column(
        "metadata_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint("table_id", name="pk_tbl_documents_tdmtables"),
    Index("idx_tdm_tables_source_id", "source_id"),
    Index("idx_tdm_tables_schema_id", "schema_id"),
    UniqueConstraint(
        "source_id",
        "schema_id",
        "table_name",
        name="uq_tdm_tables_source_schema_table",
    ),
)


tdm_columns_table = Table(
    POSTGRES_TDM_COLUMNS_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("column_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column(
        "table_id",
        Text,
        ForeignKey(
            f'{POSTGRES_TDM_TABLES_TABLE_NAME}.table_id',
            ondelete="CASCADE",
            name="fk_tdm_columns_table_id",
        ),
        nullable=False,
    ),
    Column("column_name", Text, nullable=False),
    Column("data_type", Text, nullable=False),
    Column(
        "nullable",
        Boolean,
        nullable=False,
        server_default=text("true"),
    ),
    Column("pii_class", Text, nullable=True),
    Column(
        "metadata_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint("column_id", name="pk_tbl_documents_tdmcolumns"),
    Index("idx_tdm_columns_source_id", "source_id"),
    Index("idx_tdm_columns_table_id", "table_id"),
    UniqueConstraint(
        "source_id",
        "table_id",
        "column_name",
        name="uq_tdm_columns_source_table_column",
    ),
    Index(
        "idx_tdm_columns_pii_class",
        "pii_class",
        postgresql_where=text('pii_class IS NOT NULL'),
    ),
)


tdm_service_mappings_table = Table(
    POSTGRES_TDM_SERVICE_MAPPINGS_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("mapping_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("service_name", Text, nullable=False),
    Column("endpoint", Text, nullable=False),
    Column("method", Text, nullable=False),
    Column(
        "table_id",
        Text,
        ForeignKey(
            f'{POSTGRES_TDM_TABLES_TABLE_NAME}.table_id',
            ondelete="CASCADE",
            name="fk_tdm_service_mappings_table_id",
        ),
        nullable=False,
    ),
    Column(
        "metadata_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint(
        "mapping_id",
        name="pk_tbl_documents_tdmservicemappings",
    ),
    Index("idx_tdm_service_mappings_source_id", "source_id"),
    UniqueConstraint(
        "source_id",
        "service_name",
        "endpoint",
        "method",
        name="uq_tdm_service_mappings_source_service_endpoint_method",
    ),
)


tdm_masking_rules_table = Table(
    POSTGRES_TDM_MASKING_RULES_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("rule_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("rule_name", Text, nullable=False),
    Column("policy_type", Text, nullable=False),
    Column("scope", Text, nullable=False),
    Column(
        "table_id",
        Text,
        ForeignKey(
            f'{POSTGRES_TDM_TABLES_TABLE_NAME}.table_id',
            ondelete="SET NULL",
            name="fk_tdm_masking_rules_table_id",
        ),
        nullable=True,
    ),
    Column(
        "column_id",
        Text,
        ForeignKey(
            f'{POSTGRES_TDM_COLUMNS_TABLE_NAME}.column_id',
            ondelete="SET NULL",
            name="fk_tdm_masking_rules_column_id",
        ),
        nullable=True,
    ),
    Column(
        "priority",
        Integer,
        nullable=False,
        server_default=text("100"),
    ),
    Column(
        "metadata_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint(
        "rule_id",
        name="pk_tbl_documents_tdmmaskingrules",
    ),
    Index("idx_tdm_masking_rules_source_id", "source_id"),
    Index("idx_tdm_masking_rules_priority", "priority"),
)


tdm_virtualization_artifacts_table = Table(
    POSTGRES_TDM_VIRTUALIZATION_ARTIFACTS_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("artifact_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("service_name", Text, nullable=False),
    Column("artifact_type", Text, nullable=False),
    Column(
        "content_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "metadata_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint(
        "artifact_id",
        name="pk_tbl_documents_tdmvirtualizationartifacts",
    ),
    Index("idx_tdm_virtualization_artifacts_source_id", "source_id"),
)


tdm_synthetic_profiles_table = Table(
    POSTGRES_TDM_SYNTHETIC_PROFILES_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("profile_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("profile_name", Text, nullable=False),
    Column(
        "target_table_id",
        Text,
        ForeignKey(
            f'{POSTGRES_TDM_TABLES_TABLE_NAME}.table_id',
            ondelete="SET NULL",
            name="fk_tdm_synthetic_profiles_target_table_id",
        ),
        nullable=True,
    ),
    Column(
        "strategy",
        Text,
        nullable=False,
        server_default=text("'template'"),
    ),
    Column(
        "metadata_json",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint(
        "profile_id",
        name="pk_tbl_documents_tdmsyntheticprofiles",
    ),
    Index("idx_tdm_synthetic_profiles_source_id", "source_id"),
)


ingestion_artifacts_table = Table(
    POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column("artifact_id", Text, nullable=False),
    Column(
        "job_id",
        Text,
        ForeignKey(
            f'{POSTGRES_JOBS_TABLE_NAME}.job_id',
            ondelete="SET NULL",
            name="fk_ingestion_artifacts_job_id",
        ),
        nullable=True,
    ),
    Column("source_type", Text, nullable=False),
    Column("artifact_type", Text, nullable=False),
    Column("origin_path_or_url", Text, nullable=True),
    Column(
        "file_manifest",
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    ),
    Column(
        "file_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "total_size_bytes",
        BigInteger,
        nullable=False,
        server_default=text("0"),
    ),
    Column("processing_status", Text, nullable=False),
    Column("error_message", Text, nullable=True),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "processing_started_at",
        TIMESTAMP(timezone=True),
        nullable=True,
    ),
    Column(
        "processing_completed_at",
        TIMESTAMP(timezone=True),
        nullable=True,
    ),
    Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
    Column("cleanup_at", TIMESTAMP(timezone=True), nullable=True),
    PrimaryKeyConstraint(
        "artifact_id",
        name="pk_tbl_documents_ingestionartifacts",
    ),
    Index("idx_ingestion_artifacts_job_id", "job_id"),
    Index("idx_ingestion_artifacts_status", "processing_status"),
    Index("idx_ingestion_artifacts_expires_at", "expires_at"),
)


ingestion_artifact_files_table = Table(
    POSTGRES_INGESTION_ARTIFACT_FILES_TABLE_NAME,
    POSTGRES_SCHEMA_METADATA,
    Column(
        "artifact_file_id",
        BigInteger,
        Identity(),
        nullable=False,
    ),
    Column(
        "artifact_id",
        Text,
        ForeignKey(
            f'{POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME}.artifact_id',
            ondelete="CASCADE",
            name="fk_ingestion_artifact_files_artifact_id",
        ),
        nullable=False,
    ),
    Column("ordinal", Integer, nullable=False),
    Column("original_filename", Text, nullable=False),
    Column("media_type", Text, nullable=True),
    Column("size_bytes", BigInteger, nullable=False),
    Column("content_hash", Text, nullable=True),
    Column("payload", BYTEA, nullable=False),
    Column(
        "created_at",
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    PrimaryKeyConstraint(
        "artifact_file_id",
        name="pk_tbl_documents_ingestionartifactfiles",
    ),
    UniqueConstraint(
        "artifact_id",
        "ordinal",
        name="uq_ingestion_artifact_files_artifact_id_ordinal",
    ),
    Index("idx_ingestion_artifact_files_artifact_id", "artifact_id"),
)