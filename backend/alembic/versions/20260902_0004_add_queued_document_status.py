"""Add queued document status.

Revision ID: 20260902_0004
Revises: 20260807_0003
Create Date: 2026-09-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260902_0004"
down_revision: str | None = "20260807_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'queued'")


def downgrade() -> None:
    # PostgreSQL enum values are intentionally retained. Removing a value requires
    # replacing the enum type and is unsafe if a document still uses that status.
    pass
