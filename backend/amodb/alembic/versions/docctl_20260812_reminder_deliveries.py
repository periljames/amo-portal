"""Add durable Document Control reminder delivery ledger.

Revision ID: docctl_20260812_reminder_deliveries
Revises: docctl_20260812_evidence_assets
Create Date: 2026-08-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "docctl_20260812_reminder_deliveries"
down_revision = "docctl_20260812_evidence_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_reminder_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("obligation_type", sa.String(length=48), nullable=False),
        sa.Column("obligation_id", sa.String(length=36), nullable=False),
        sa.Column("recipient_user_id", sa.String(length=36), nullable=False),
        sa.Column("reminder_stage", sa.String(length=64), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("action_url", sa.String(length=512), nullable=False),
        sa.Column("delivery_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "obligation_type",
            "obligation_id",
            "recipient_user_id",
            "reminder_stage",
            name="uq_document_reminder_obligation_recipient_stage",
        ),
    )
    op.create_index("ix_document_reminders_tenant_created", "document_reminder_deliveries", ["tenant_id", "created_at"], unique=False)
    op.create_index("ix_document_reminders_obligation", "document_reminder_deliveries", ["tenant_id", "obligation_type", "obligation_id"], unique=False)
    op.create_index("ix_document_reminders_recipient", "document_reminder_deliveries", ["tenant_id", "recipient_user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_document_reminders_recipient", table_name="document_reminder_deliveries")
    op.drop_index("ix_document_reminders_obligation", table_name="document_reminder_deliveries")
    op.drop_index("ix_document_reminders_tenant_created", table_name="document_reminder_deliveries")
    op.drop_table("document_reminder_deliveries")
