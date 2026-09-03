"""Add ingestion version and attempt metadata.

Revision ID: 20260903_0005
Revises: 20260902_0004
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_0005"
down_revision: str | None = "20260902_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "current_ingestion_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("completed_ingestion_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "ingestion_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("last_ingestion_error_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("last_ingestion_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("last_ingestion_failed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        "UPDATE documents SET completed_ingestion_version = 1 "
        "WHERE status = 'ready'"
    )

    op.create_check_constraint(
        "ck_documents_current_ingestion_version_positive",
        "documents",
        "current_ingestion_version > 0",
    )
    op.create_check_constraint(
        "ck_documents_completed_ingestion_version_positive",
        "documents",
        "completed_ingestion_version IS NULL OR completed_ingestion_version > 0",
    )
    op.create_check_constraint(
        "ck_documents_ingestion_attempts_nonnegative",
        "documents",
        "ingestion_attempts >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_documents_ingestion_attempts_nonnegative",
        "documents",
        type_="check",
    )
    op.drop_constraint(
        "ck_documents_completed_ingestion_version_positive",
        "documents",
        type_="check",
    )
    op.drop_constraint(
        "ck_documents_current_ingestion_version_positive",
        "documents",
        type_="check",
    )
    op.drop_column("documents", "last_ingestion_failed_at")
    op.drop_column("documents", "last_ingestion_started_at")
    op.drop_column("documents", "last_ingestion_error_code")
    op.drop_column("documents", "ingestion_attempts")
    op.drop_column("documents", "completed_ingestion_version")
    op.drop_column("documents", "current_ingestion_version")
