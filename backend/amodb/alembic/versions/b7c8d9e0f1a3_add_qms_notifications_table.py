"""add qms notifications table

Revision ID: b7c8d9e0f1a3
Revises: a4d6f8b0c2e1
Create Date: 2026-02-12 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a3"
down_revision: Union[str, Sequence[str], None] = "a4d6f8b0c2e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEVERITY_VALUES: tuple[str, ...] = (
    "INFO",
    "WARNING",
    "ACTION_REQUIRED",
)


def _ensure_severity_enum() -> None:
    op.execute(
        sa.text(
            """
DO $$
DECLARE
    v text;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'qms_notification_severity'
          AND n.nspname = current_schema()
    ) THEN
        CREATE TYPE qms_notification_severity AS ENUM ('INFO', 'WARNING', 'ACTION_REQUIRED');
    END IF;

    FOREACH v IN ARRAY ARRAY['INFO', 'WARNING', 'ACTION_REQUIRED'] LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t2 ON t2.oid = e.enumtypid
            JOIN pg_namespace n2 ON n2.oid = t2.typnamespace
            WHERE t2.typname = 'qms_notification_severity'
              AND n2.nspname = current_schema()
              AND e.enumlabel = v
        ) THEN
            EXECUTE format('ALTER TYPE qms_notification_severity ADD VALUE %L', v);
        END IF;
    END LOOP;
END $$;
"""
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    _ensure_severity_enum()

    if not insp.has_table("qms_notifications"):
        severity_enum = postgresql.ENUM(*SEVERITY_VALUES, name="qms_notification_severity", create_type=False)
        op.create_table(
            "qms_notifications",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("severity", severity_enum, nullable=False),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_qms_notifications_created_by_user_id_users"), ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_qms_notifications_user_id_users"), ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_qms_notifications")),
        )
        op.create_index(op.f("ix_qms_notifications_user_id"), "qms_notifications", ["user_id"], unique=False)
        op.create_index(op.f("ix_qms_notifications_severity"), "qms_notifications", ["severity"], unique=False)
        op.create_index(op.f("ix_qms_notifications_created_by_user_id"), "qms_notifications", ["created_by_user_id"], unique=False)
        op.create_index(op.f("ix_qms_notifications_read_at"), "qms_notifications", ["read_at"], unique=False)
        op.create_index("ix_qms_notifications_user_created", "qms_notifications", ["user_id", "created_at"], unique=False)
        op.create_index("ix_qms_notifications_user_unread", "qms_notifications", ["user_id", "read_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("qms_notifications"):
        op.drop_index("ix_qms_notifications_user_unread", table_name="qms_notifications")
        op.drop_index("ix_qms_notifications_user_created", table_name="qms_notifications")
        op.drop_index(op.f("ix_qms_notifications_read_at"), table_name="qms_notifications")
        op.drop_index(op.f("ix_qms_notifications_created_by_user_id"), table_name="qms_notifications")
        op.drop_index(op.f("ix_qms_notifications_severity"), table_name="qms_notifications")
        op.drop_index(op.f("ix_qms_notifications_user_id"), table_name="qms_notifications")
        op.drop_table("qms_notifications")
