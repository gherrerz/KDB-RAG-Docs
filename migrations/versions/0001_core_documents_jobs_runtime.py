# pyright: reportMissingImports=false

"""Create the core Docs PostgreSQL schema for documents and jobs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from coderag.storage.postgres_schema import (
    POSTGRES_CHUNKS_TABLE_NAME,
    POSTGRES_DOCUMENTS_TABLE_NAME,
    POSTGRES_GRAPH_EDGES_TABLE_NAME,
    POSTGRES_JOB_EVENTS_TABLE_NAME,
    POSTGRES_JOBS_TABLE_NAME,
    POSTGRES_RUNTIME_STATE_TABLE_NAME,
)


revision = "0001_core_documents_jobs_runtime"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the first PostgreSQL schema slice for Docs."""
    op.create_table(
        POSTGRES_DOCUMENTS_TABLE_NAME,
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("path_or_url", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column(
            "tags_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "document_id",
            name="pk_tbl_documents_documents",
        ),
    )
    op.create_index(
        "idx_documents_source_id",
        POSTGRES_DOCUMENTS_TABLE_NAME,
        ["source_id"],
        unique=False,
    )

    op.create_table(
        POSTGRES_CHUNKS_TABLE_NAME,
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("section_name", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_ref", sa.BigInteger(), nullable=False),
        sa.Column("end_ref", sa.BigInteger(), nullable=False),
        sa.Column("entity_name", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.Text(), nullable=True),
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
            ["document_id"],
            [f"{POSTGRES_DOCUMENTS_TABLE_NAME}.document_id"],
            name="fk_chunks_document_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "chunk_id",
            name="pk_tbl_documents_chunks",
        ),
    )
    op.create_index(
        "idx_chunks_document_id",
        POSTGRES_CHUNKS_TABLE_NAME,
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "idx_chunks_source_id",
        POSTGRES_CHUNKS_TABLE_NAME,
        ["source_id"],
        unique=False,
    )

    op.create_table(
        POSTGRES_GRAPH_EDGES_TABLE_NAME,
        sa.Column("edge_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_node", sa.Text(), nullable=False),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column("target_node", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "edge_id",
            name="pk_tbl_documents_graphedges",
        ),
    )
    op.create_index(
        "idx_graph_edges_source_id",
        POSTGRES_GRAPH_EDGES_TABLE_NAME,
        ["source_id"],
        unique=False,
    )
    op.create_index(
        "idx_graph_edges_source_node",
        POSTGRES_GRAPH_EDGES_TABLE_NAME,
        ["source_node"],
        unique=False,
    )
    op.create_index(
        "idx_graph_edges_target_node",
        POSTGRES_GRAPH_EDGES_TABLE_NAME,
        ["target_node"],
        unique=False,
    )

    op.create_table(
        POSTGRES_JOBS_TABLE_NAME,
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
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
            "job_id",
            name="pk_tbl_documents_jobs",
        ),
    )
    op.create_index(
        "idx_jobs_status",
        POSTGRES_JOBS_TABLE_NAME,
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_jobs_created_at",
        POSTGRES_JOBS_TABLE_NAME,
        ["created_at"],
        unique=False,
    )

    op.create_table(
        POSTGRES_JOB_EVENTS_TABLE_NAME,
        sa.Column("event_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("elapsed_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "details_json",
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
        sa.ForeignKeyConstraint(
            ["job_id"],
            [f"{POSTGRES_JOBS_TABLE_NAME}.job_id"],
            name="fk_job_events_job_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "event_id",
            name="pk_tbl_documents_jobevents",
        ),
        sa.UniqueConstraint(
            "job_id",
            "ordinal",
            name="uq_job_events_job_id_ordinal",
        ),
    )
    op.create_index(
        "idx_job_events_job_id",
        POSTGRES_JOB_EVENTS_TABLE_NAME,
        ["job_id"],
        unique=False,
    )
    op.create_index(
        "idx_job_events_job_id_ordinal",
        POSTGRES_JOB_EVENTS_TABLE_NAME,
        ["job_id", "ordinal"],
        unique=False,
    )

    op.create_table(
        POSTGRES_RUNTIME_STATE_TABLE_NAME,
        sa.Column("state_key", sa.Text(), nullable=False),
        sa.Column("state_value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "state_key",
            name="pk_tbl_documents_runtimestate",
        ),
    )


def downgrade() -> None:
    """Drop the initial Docs PostgreSQL schema slice."""
    op.drop_table(POSTGRES_RUNTIME_STATE_TABLE_NAME)

    op.drop_index(
        "idx_job_events_job_id_ordinal",
        table_name=POSTGRES_JOB_EVENTS_TABLE_NAME,
    )
    op.drop_index(
        "idx_job_events_job_id",
        table_name=POSTGRES_JOB_EVENTS_TABLE_NAME,
    )
    op.drop_table(POSTGRES_JOB_EVENTS_TABLE_NAME)

    op.drop_index("idx_jobs_created_at", table_name=POSTGRES_JOBS_TABLE_NAME)
    op.drop_index("idx_jobs_status", table_name=POSTGRES_JOBS_TABLE_NAME)
    op.drop_table(POSTGRES_JOBS_TABLE_NAME)

    op.drop_index(
        "idx_graph_edges_target_node",
        table_name=POSTGRES_GRAPH_EDGES_TABLE_NAME,
    )
    op.drop_index(
        "idx_graph_edges_source_node",
        table_name=POSTGRES_GRAPH_EDGES_TABLE_NAME,
    )
    op.drop_index(
        "idx_graph_edges_source_id",
        table_name=POSTGRES_GRAPH_EDGES_TABLE_NAME,
    )
    op.drop_table(POSTGRES_GRAPH_EDGES_TABLE_NAME)

    op.drop_index(
        "idx_chunks_source_id",
        table_name=POSTGRES_CHUNKS_TABLE_NAME,
    )
    op.drop_index(
        "idx_chunks_document_id",
        table_name=POSTGRES_CHUNKS_TABLE_NAME,
    )
    op.drop_table(POSTGRES_CHUNKS_TABLE_NAME)

    op.drop_index(
        "idx_documents_source_id",
        table_name=POSTGRES_DOCUMENTS_TABLE_NAME,
    )
    op.drop_table(POSTGRES_DOCUMENTS_TABLE_NAME)