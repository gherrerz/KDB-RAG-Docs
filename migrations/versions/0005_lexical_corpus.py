# pyright: reportMissingImports=false

"""Create PostgreSQL lexical corpus storage for Docs retrieval."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from coderag.storage.postgres_schema import (
    POSTGRES_LEXICAL_CORPUS_TABLE_NAME,
)


revision = "0005_lexical_corpus"
down_revision = "0004_supporting_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create one dedicated lexical corpus table backed by PostgreSQL FTS."""
    op.create_table(
        POSTGRES_LEXICAL_CORPUS_TABLE_NAME,
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("path_or_url", sa.Text(), nullable=False),
        sa.Column("section_name", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("fts_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "chunk_id",
            name="pk_tbl_documents_lexicalcorpus",
        ),
    )
    op.create_index(
        "idx_lexical_corpus_source_id",
        POSTGRES_LEXICAL_CORPUS_TABLE_NAME,
        ["source_id"],
        unique=False,
    )
    op.create_index(
        "idx_lexical_corpus_document_id",
        POSTGRES_LEXICAL_CORPUS_TABLE_NAME,
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "idx_lexical_corpus_fts",
        POSTGRES_LEXICAL_CORPUS_TABLE_NAME,
        ["fts_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Drop the Docs lexical corpus table and supporting indexes."""
    op.drop_index(
        "idx_lexical_corpus_fts",
        table_name=POSTGRES_LEXICAL_CORPUS_TABLE_NAME,
    )
    op.drop_index(
        "idx_lexical_corpus_document_id",
        table_name=POSTGRES_LEXICAL_CORPUS_TABLE_NAME,
    )
    op.drop_index(
        "idx_lexical_corpus_source_id",
        table_name=POSTGRES_LEXICAL_CORPUS_TABLE_NAME,
    )
    op.drop_table(POSTGRES_LEXICAL_CORPUS_TABLE_NAME)