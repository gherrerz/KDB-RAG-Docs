# pyright: reportMissingImports=false

"""Add supporting indexes for Docs PostgreSQL schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from coderag.storage.postgres_schema import (
    POSTGRES_DOCUMENTS_TABLE_NAME,
    POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
)


revision = "0004_supporting_indexes"
down_revision = "0003_async_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create low-risk supporting indexes for the initial schema."""
    op.create_index(
        "gin_documents_tags_json",
        POSTGRES_DOCUMENTS_TABLE_NAME,
        ["tags_json"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_ingestion_artifacts_status_expires_at",
        POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
        ["processing_status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "idx_ingestion_artifacts_job_id_status",
        POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
        ["job_id", "processing_status"],
        unique=False,
    )
    op.create_index(
        "idx_documents_updated_at",
        POSTGRES_DOCUMENTS_TABLE_NAME,
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the low-risk supporting indexes for the initial schema."""
    op.drop_index(
        "idx_documents_updated_at",
        table_name=POSTGRES_DOCUMENTS_TABLE_NAME,
    )
    op.drop_index(
        "idx_ingestion_artifacts_job_id_status",
        table_name=POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
    )
    op.drop_index(
        "idx_ingestion_artifacts_status_expires_at",
        table_name=POSTGRES_INGESTION_ARTIFACTS_TABLE_NAME,
    )
    op.drop_index(
        "gin_documents_tags_json",
        table_name=POSTGRES_DOCUMENTS_TABLE_NAME,
    )