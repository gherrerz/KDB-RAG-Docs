# pyright: reportMissingImports=false

"""Drop legacy PostgreSQL graph edges table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from coderag.storage.postgres_schema import (
    POSTGRES_GRAPH_EDGES_TABLE_NAME,
)


revision = "0006_drop_graph_edges"
down_revision = "0005_lexical_corpus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop legacy document graph edges table now unused by runtime."""
    op.drop_table(POSTGRES_GRAPH_EDGES_TABLE_NAME)


def downgrade() -> None:
    """Recreate legacy graph edges table for backward compatibility."""
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
