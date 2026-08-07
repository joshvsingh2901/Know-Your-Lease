"""Add persistent verified grounded-answer cache.

Revision ID: 20260807_0003
Revises: 20260807_0002
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260807_0003"
down_revision: str | None = "20260807_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "grounded_answer_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_question", sa.String(length=1000), nullable=False),
        sa.Column("generation_version", sa.String(length=64), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "normalized_question",
            "generation_version",
            name="uq_grounded_answer_cache_document_question_version",
        ),
    )
    op.create_index(
        "ix_grounded_answer_cache_document_id",
        "grounded_answer_cache",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_grounded_answer_cache_document_id", table_name="grounded_answer_cache")
    op.drop_table("grounded_answer_cache")
