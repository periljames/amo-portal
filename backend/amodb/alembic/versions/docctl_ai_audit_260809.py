"""Create the controlled-document assistance audit table.

Revision ID: docctl_ai_audit_260809
Revises: plat_qms_260809_merge
Create Date: 2026-08-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "docctl_ai_audit_260809"
down_revision = "plat_qms_260809_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_ai_hook_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["manual_tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_manual_ai_hook_events_tenant_id"),
        "manual_ai_hook_events",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_manual_ai_hook_events_tenant_id"), table_name="manual_ai_hook_events")
    op.drop_table("manual_ai_hook_events")
