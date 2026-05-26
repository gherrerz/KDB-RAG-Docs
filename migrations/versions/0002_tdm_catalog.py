# pyright: reportMissingImports=false

"""Create the TDM catalog schema slice for Docs PostgreSQL."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from coderag.storage.postgres_schema import (
    POSTGRES_TDM_COLUMNS_TABLE_NAME,
    POSTGRES_TDM_MASKING_RULES_TABLE_NAME,
    POSTGRES_TDM_SCHEMAS_TABLE_NAME,
    POSTGRES_TDM_SERVICE_MAPPINGS_TABLE_NAME,
    POSTGRES_TDM_SYNTHETIC_PROFILES_TABLE_NAME,
    POSTGRES_TDM_TABLES_TABLE_NAME,
    POSTGRES_TDM_VIRTUALIZATION_ARTIFACTS_TABLE_NAME,
)


revision = "0002_tdm_catalog"
down_revision = "0001_core_documents_jobs_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the TDM catalog schema slice."""
    op.create_table(
        POSTGRES_TDM_SCHEMAS_TABLE_NAME,
        sa.Column("schema_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("database_name", sa.Text(), nullable=False),
        sa.Column("schema_name", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "schema_id",
            name="pk_tbl_documents_tdmschemas",
        ),
        sa.UniqueConstraint(
            "source_id",
            "database_name",
            "schema_name",
            name="uq_tdm_schemas_source_database_schema",
        ),
    )
    op.create_index(
        "idx_tdm_schemas_source_id",
        POSTGRES_TDM_SCHEMAS_TABLE_NAME,
        ["source_id"],
        unique=False,
    )

    op.create_table(
        POSTGRES_TDM_TABLES_TABLE_NAME,
        sa.Column("table_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("schema_id", sa.Text(), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column(
            "table_type",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'table'"),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["schema_id"],
            [f"{POSTGRES_TDM_SCHEMAS_TABLE_NAME}.schema_id"],
            name="fk_tdm_tables_schema_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "table_id",
            name="pk_tbl_documents_tdmtables",
        ),
        sa.UniqueConstraint(
            "source_id",
            "schema_id",
            "table_name",
            name="uq_tdm_tables_source_schema_table",
        ),
    )
    op.create_index(
        "idx_tdm_tables_source_id",
        POSTGRES_TDM_TABLES_TABLE_NAME,
        ["source_id"],
        unique=False,
    )
    op.create_index(
        "idx_tdm_tables_schema_id",
        POSTGRES_TDM_TABLES_TABLE_NAME,
        ["schema_id"],
        unique=False,
    )

    op.create_table(
        POSTGRES_TDM_COLUMNS_TABLE_NAME,
        sa.Column("column_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("table_id", sa.Text(), nullable=False),
        sa.Column("column_name", sa.Text(), nullable=False),
        sa.Column("data_type", sa.Text(), nullable=False),
        sa.Column(
            "nullable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("pii_class", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["table_id"],
            [f"{POSTGRES_TDM_TABLES_TABLE_NAME}.table_id"],
            name="fk_tdm_columns_table_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "column_id",
            name="pk_tbl_documents_tdmcolumns",
        ),
        sa.UniqueConstraint(
            "source_id",
            "table_id",
            "column_name",
            name="uq_tdm_columns_source_table_column",
        ),
    )
    op.create_index(
        "idx_tdm_columns_source_id",
        POSTGRES_TDM_COLUMNS_TABLE_NAME,
        ["source_id"],
        unique=False,
    )
    op.create_index(
        "idx_tdm_columns_table_id",
        POSTGRES_TDM_COLUMNS_TABLE_NAME,
        ["table_id"],
        unique=False,
    )
    op.create_index(
        "idx_tdm_columns_pii_class",
        POSTGRES_TDM_COLUMNS_TABLE_NAME,
        ["pii_class"],
        unique=False,
        postgresql_where=sa.text("pii_class IS NOT NULL"),
    )

    op.create_table(
        POSTGRES_TDM_SERVICE_MAPPINGS_TABLE_NAME,
        sa.Column("mapping_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("service_name", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("table_id", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["table_id"],
            [f"{POSTGRES_TDM_TABLES_TABLE_NAME}.table_id"],
            name="fk_tdm_service_mappings_table_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "mapping_id",
            name="pk_tbl_documents_tdmservicemappings",
        ),
        sa.UniqueConstraint(
            "source_id",
            "service_name",
            "endpoint",
            "method",
            name="uq_tdm_service_mappings_source_service_endpoint_method",
        ),
    )
    op.create_index(
        "idx_tdm_service_mappings_source_id",
        POSTGRES_TDM_SERVICE_MAPPINGS_TABLE_NAME,
        ["source_id"],
        unique=False,
    )

    op.create_table(
        POSTGRES_TDM_MASKING_RULES_TABLE_NAME,
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("rule_name", sa.Text(), nullable=False),
        sa.Column("policy_type", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("table_id", sa.Text(), nullable=True),
        sa.Column("column_id", sa.Text(), nullable=True),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["table_id"],
            [f"{POSTGRES_TDM_TABLES_TABLE_NAME}.table_id"],
            name="fk_tdm_masking_rules_table_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["column_id"],
            [f"{POSTGRES_TDM_COLUMNS_TABLE_NAME}.column_id"],
            name="fk_tdm_masking_rules_column_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "rule_id",
            name="pk_tbl_documents_tdmmaskingrules",
        ),
    )
    op.create_index(
        "idx_tdm_masking_rules_source_id",
        POSTGRES_TDM_MASKING_RULES_TABLE_NAME,
        ["source_id"],
        unique=False,
    )
    op.create_index(
        "idx_tdm_masking_rules_priority",
        POSTGRES_TDM_MASKING_RULES_TABLE_NAME,
        ["priority"],
        unique=False,
    )

    op.create_table(
        POSTGRES_TDM_VIRTUALIZATION_ARTIFACTS_TABLE_NAME,
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("service_name", sa.Text(), nullable=False),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column(
            "content_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "artifact_id",
            name="pk_tbl_documents_tdmvirtualizationartifacts",
        ),
    )
    op.create_index(
        "idx_tdm_virtualization_artifacts_source_id",
        POSTGRES_TDM_VIRTUALIZATION_ARTIFACTS_TABLE_NAME,
        ["source_id"],
        unique=False,
    )

    op.create_table(
        POSTGRES_TDM_SYNTHETIC_PROFILES_TABLE_NAME,
        sa.Column("profile_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("profile_name", sa.Text(), nullable=False),
        sa.Column("target_table_id", sa.Text(), nullable=True),
        sa.Column(
            "strategy",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'template'"),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["target_table_id"],
            [f"{POSTGRES_TDM_TABLES_TABLE_NAME}.table_id"],
            name="fk_tdm_synthetic_profiles_target_table_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "profile_id",
            name="pk_tbl_documents_tdmsyntheticprofiles",
        ),
    )
    op.create_index(
        "idx_tdm_synthetic_profiles_source_id",
        POSTGRES_TDM_SYNTHETIC_PROFILES_TABLE_NAME,
        ["source_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the TDM catalog schema slice."""
    op.drop_index(
        "idx_tdm_synthetic_profiles_source_id",
        table_name=POSTGRES_TDM_SYNTHETIC_PROFILES_TABLE_NAME,
    )
    op.drop_table(POSTGRES_TDM_SYNTHETIC_PROFILES_TABLE_NAME)

    op.drop_index(
        "idx_tdm_virtualization_artifacts_source_id",
        table_name=POSTGRES_TDM_VIRTUALIZATION_ARTIFACTS_TABLE_NAME,
    )
    op.drop_table(POSTGRES_TDM_VIRTUALIZATION_ARTIFACTS_TABLE_NAME)

    op.drop_index(
        "idx_tdm_masking_rules_priority",
        table_name=POSTGRES_TDM_MASKING_RULES_TABLE_NAME,
    )
    op.drop_index(
        "idx_tdm_masking_rules_source_id",
        table_name=POSTGRES_TDM_MASKING_RULES_TABLE_NAME,
    )
    op.drop_table(POSTGRES_TDM_MASKING_RULES_TABLE_NAME)

    op.drop_index(
        "idx_tdm_service_mappings_source_id",
        table_name=POSTGRES_TDM_SERVICE_MAPPINGS_TABLE_NAME,
    )
    op.drop_table(POSTGRES_TDM_SERVICE_MAPPINGS_TABLE_NAME)

    op.drop_index(
        "idx_tdm_columns_pii_class",
        table_name=POSTGRES_TDM_COLUMNS_TABLE_NAME,
    )
    op.drop_index(
        "idx_tdm_columns_table_id",
        table_name=POSTGRES_TDM_COLUMNS_TABLE_NAME,
    )
    op.drop_index(
        "idx_tdm_columns_source_id",
        table_name=POSTGRES_TDM_COLUMNS_TABLE_NAME,
    )
    op.drop_table(POSTGRES_TDM_COLUMNS_TABLE_NAME)

    op.drop_index(
        "idx_tdm_tables_schema_id",
        table_name=POSTGRES_TDM_TABLES_TABLE_NAME,
    )
    op.drop_index(
        "idx_tdm_tables_source_id",
        table_name=POSTGRES_TDM_TABLES_TABLE_NAME,
    )
    op.drop_table(POSTGRES_TDM_TABLES_TABLE_NAME)

    op.drop_index(
        "idx_tdm_schemas_source_id",
        table_name=POSTGRES_TDM_SCHEMAS_TABLE_NAME,
    )
    op.drop_table(POSTGRES_TDM_SCHEMAS_TABLE_NAME)