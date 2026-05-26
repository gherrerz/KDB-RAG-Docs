# pyright: reportMissingImports=false

"""Create the async ingestion artifacts schema slice for Docs PostgreSQL."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from coderag.storage.postgres_schema import (
    POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
    POSTGRES_INGESTION_ARTIFACT_FILES_TABLE_NAME,
    POSTGRES_JOBS_TABLE_NAME,
)


revision = "0003_async_artifacts"
down_revision = "0002_tdm_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the async rehydratable artifact schema slice."""
    op.create_table(
        POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("origin_path_or_url", sa.Text(), nullable=True),
        sa.Column(
            "file_manifest",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "file_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_size_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("processing_status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "processing_started_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "processing_completed_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "expires_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "cleanup_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            [f"{POSTGRES_JOBS_TABLE_NAME}.job_id"],
            name="fk_ingestion_artifacts_job_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "artifact_id",
            name="pk_tbl_documents_ingestionartifacts",
        ),
    )
    op.create_index(
        "idx_ingestion_artifacts_job_id",
        POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
        ["job_id"],
        unique=False,
    )
    op.create_index(
        "idx_ingestion_artifacts_status",
        POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
        ["processing_status"],
        unique=False,
    )
    op.create_index(
        "idx_ingestion_artifacts_expires_at",
        POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        POSTGRES_INGESTION_ARTIFACT_FILES_TABLE_NAME,
        sa.Column(
            "artifact_file_id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.BYTEA(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            [f"{POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME}.artifact_id"],
            name="fk_ingestion_artifact_files_artifact_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "artifact_file_id",
            name="pk_tbl_documents_ingestionartifactfiles",
        ),
        sa.UniqueConstraint(
            "artifact_id",
            "ordinal",
            name="uq_ingestion_artifact_files_artifact_id_ordinal",
        ),
    )
    op.create_index(
        "idx_ingestion_artifact_files_artifact_id",
        POSTGRES_INGESTION_ARTIFACT_FILES_TABLE_NAME,
        ["artifact_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the async rehydratable artifact schema slice."""
    op.drop_index(
        "idx_ingestion_artifact_files_artifact_id",
        table_name=POSTGRES_INGESTION_ARTIFACT_FILES_TABLE_NAME,
    )
    op.drop_table(POSTGRES_INGESTION_ARTIFACT_FILES_TABLE_NAME)

    op.drop_index(
        "idx_ingestion_artifacts_expires_at",
        table_name=POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
    )
    op.drop_index(
        "idx_ingestion_artifacts_status",
        table_name=POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
    )
    op.drop_index(
        "idx_ingestion_artifacts_job_id",
        table_name=POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
    )
    op.drop_table(POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME)