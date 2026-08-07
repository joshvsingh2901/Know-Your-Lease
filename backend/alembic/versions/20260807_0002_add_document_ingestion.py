"""Add document ingestion state and vector chunks.

Revision ID: 20260807_0002
Revises: 20260806_0001
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "20260807_0002"
down_revision: str | None = "20260806_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'processing'")
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'ready'")
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'failed'")

    op.add_column("documents", sa.Column("storage_key", sa.String(length=512), nullable=True))
    op.add_column("documents", sa.Column("error_message", sa.String(length=500), nullable=True))

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("paragraph_index", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(length=255), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(dim=1024), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_chunk_index",
        ),
    )
    op.create_index(
        "ix_document_chunks_document_id",
        "document_chunks",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_chunks_document_page",
        "document_chunks",
        ["document_id", "page_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_document_page", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_column("documents", "error_message")
    op.drop_column("documents", "storage_key")
    # PostgreSQL enum values are intentionally retained; removing enum values requires
    # recreating the type and is unsafe when older rows may use those statuses.
