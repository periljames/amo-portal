"""Complete central email delivery policy and Resend event persistence.

Revision ID: notifications_20260729_delivery
Revises: document_control_20260724_domain
Create Date: 2026-07-29
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "notifications_20260729_delivery"
down_revision = "document_control_20260724_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_preferences",
        sa.Column("receipt_email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "notification_preferences",
        sa.Column("marketing_email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "notification_tenant_preferences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("routine_email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("receipt_email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("marketing_email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", name="uq_notification_tenant_preferences_amo"),
    )
    op.create_index(
        "ix_notification_tenant_preferences_amo_id",
        "notification_tenant_preferences",
        ["amo_id"],
        unique=False,
    )

    op.add_column("email_logs", sa.Column("provider", sa.String(length=32), nullable=True))
    op.add_column("email_logs", sa.Column("provider_message_id", sa.String(length=255), nullable=True))
    op.add_column("email_logs", sa.Column("delivery_status", sa.String(length=64), nullable=True))
    op.add_column("email_logs", sa.Column("last_delivery_event_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_email_logs_provider", "email_logs", ["provider"], unique=False)
    op.create_index("ix_email_logs_provider_message_id", "email_logs", ["provider_message_id"], unique=False)
    op.create_index("ix_email_logs_delivery_status", "email_logs", ["delivery_status"], unique=False)
    op.create_index(
        "ix_email_logs_provider_message",
        "email_logs",
        ["provider", "provider_message_id"],
        unique=False,
    )

    op.create_table(
        "email_delivery_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email_log_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="resend"),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["email_log_id"], ["email_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_email_delivery_provider_event"),
    )
    op.create_index(
        "ix_email_delivery_events_message",
        "email_delivery_events",
        ["provider", "provider_message_id"],
        unique=False,
    )
    op.create_index(
        "ix_email_delivery_events_log_created",
        "email_delivery_events",
        ["email_log_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_email_delivery_events_log_created", table_name="email_delivery_events")
    op.drop_index("ix_email_delivery_events_message", table_name="email_delivery_events")
    op.drop_table("email_delivery_events")
    op.drop_index("ix_email_logs_provider_message", table_name="email_logs")
    op.drop_index("ix_email_logs_delivery_status", table_name="email_logs")
    op.drop_index("ix_email_logs_provider_message_id", table_name="email_logs")
    op.drop_index("ix_email_logs_provider", table_name="email_logs")
    op.drop_column("email_logs", "last_delivery_event_at")
    op.drop_column("email_logs", "delivery_status")
    op.drop_column("email_logs", "provider_message_id")
    op.drop_column("email_logs", "provider")
    op.drop_index("ix_notification_tenant_preferences_amo_id", table_name="notification_tenant_preferences")
    op.drop_table("notification_tenant_preferences")
    op.drop_column("notification_preferences", "marketing_email_enabled")
    op.drop_column("notification_preferences", "receipt_email_enabled")
