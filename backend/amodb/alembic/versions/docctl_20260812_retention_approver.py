"""Add assigned approver to Document Control retention disposition.

Revision ID: docctl_20260812_retention_approver
Revises: docctl_20260812_retention_disposition
Create Date: 2026-08-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "docctl_20260812_retention_approver"
down_revision = "docctl_20260812_retention_disposition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_retention_dispositions",
        sa.Column("approver_user_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_document_retention_approver_user",
        "document_retention_dispositions",
        "users",
        ["approver_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_document_retention_approver",
        "document_retention_dispositions",
        ["tenant_id", "approver_user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_retention_approver", table_name="document_retention_dispositions")
    op.drop_constraint(
        "fk_document_retention_approver_user",
        "document_retention_dispositions",
        type_="foreignkey",
    )
    op.drop_column("document_retention_dispositions", "approver_user_id")
