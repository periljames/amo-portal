"""add email logs

Revision ID: s1t2u3v4w5x6
Revises: r1s2t3u4v5w6
Create Date: 2026-03-05 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "s1t2u3v4w5x6"
down_revision = "r1s2t3u4v5w6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    email_status_enum = sa.Enum(
        "QUEUED",
        "SENT",
        "FAILED",
        "SKIPPED_NO_PROVIDER",
        name="email_status_enum",
        native_enum=False,
    )
    op.create_table(
        "email_logs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("template_key", sa.String(length=128), nullable=False),
        sa.Column("status", email_status_enum, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_email_logs_amo_created", "email_logs", ["amo_id", "created_at"], unique=False)
    op.create_index("ix_email_logs_amo_status", "email_logs", ["amo_id", "status"], unique=False)
    op.create_index("ix_email_logs_amo_template", "email_logs", ["amo_id", "template_key"], unique=False)
    op.create_index("ix_email_logs_amo_recipient", "email_logs", ["amo_id", "recipient"], unique=False)
    op.create_index("ix_email_logs_created_at", "email_logs", ["created_at"], unique=False)
    op.create_index("ix_email_logs_status", "email_logs", ["status"], unique=False)


def downgrade() -> None:
    email_status_enum = sa.Enum(
        "QUEUED",
        "SENT",
        "FAILED",
        "SKIPPED_NO_PROVIDER",
        name="email_status_enum",
        native_enum=False,
    )
    op.drop_index("ix_email_logs_status", table_name="email_logs")
    op.drop_index("ix_email_logs_created_at", table_name="email_logs")
    op.drop_index("ix_email_logs_amo_recipient", table_name="email_logs")
    op.drop_index("ix_email_logs_amo_template", table_name="email_logs")
    op.drop_index("ix_email_logs_amo_status", table_name="email_logs")
    op.drop_index("ix_email_logs_amo_created", table_name="email_logs")
    op.drop_table("email_logs")
    email_status_enum.drop(op.get_bind(), checkfirst=True)
