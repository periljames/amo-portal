"""Harden tenant messaging, receipts and in-app notifications.

Revision ID: saas_20260722_messaging
Revises: saas_20260722_qms_read_idx
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "saas_20260722_messaging"
down_revision = "saas_20260722_qms_read_idx"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _columns(name: str) -> set[str]:
    if not _has_table(name):
        return set()
    return {str(column["name"]) for column in _inspector().get_columns(name)}


def _add_column(table: str, column: sa.Column) -> None:
    if _has_table(table) and column.name not in _columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    if not _has_table("chat_threads"):
        raise RuntimeError("Messaging hardening requires the realtime chat schema")

    _add_column("chat_threads", sa.Column("kind", sa.String(length=32), nullable=False, server_default="GROUP"))
    _add_column("chat_threads", sa.Column("scope_key", sa.String(length=255), nullable=True))
    _add_column("chat_threads", sa.Column("department_id", sa.String(length=36), nullable=True))
    _add_column("chat_threads", sa.Column("user_group_id", sa.String(length=36), nullable=True))
    _add_column("chat_threads", sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True))
    _add_column("chat_threads", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    _add_column("chat_threads", sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    _add_column("chat_thread_members", sa.Column("notification_level", sa.String(length=32), nullable=False, server_default="ALL"))
    _add_column("chat_thread_members", sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True))
    _add_column("chat_thread_members", sa.Column("muted_until", sa.DateTime(timezone=True), nullable=True))
    _add_column("chat_thread_members", sa.Column("left_at", sa.DateTime(timezone=True), nullable=True))
    _add_column("chat_thread_members", sa.Column("added_by_user_id", sa.String(length=36), nullable=True))

    _add_column("chat_messages", sa.Column("message_type", sa.String(length=32), nullable=False, server_default="TEXT"))
    _add_column("chat_messages", sa.Column("reply_to_message_id", sa.String(length=36), nullable=True))
    _add_column("chat_messages", sa.Column("metadata", sa.JSON(), nullable=True))

    bind = op.get_bind()
    if _has_table("departments"):
        foreign_keys = _inspector().get_foreign_keys("chat_threads")
        has_department_fk = any(
            tuple(item.get("constrained_columns") or ()) == ("department_id",)
            and item.get("referred_table") == "departments"
            for item in foreign_keys
        )
        if not has_department_fk:
            op.create_foreign_key(
                "fk_chat_threads_department_id_departments",
                "chat_threads",
                "departments",
                ["department_id"],
                ["id"],
                ondelete="SET NULL",
            )

    message_fks = _inspector().get_foreign_keys("chat_messages")
    has_reply_fk = any(
        tuple(item.get("constrained_columns") or ()) == ("reply_to_message_id",)
        and item.get("referred_table") == "chat_messages"
        for item in message_fks
    )
    if not has_reply_fk:
        op.create_foreign_key(
            "fk_chat_messages_reply_to_message_id_chat_messages",
            "chat_messages",
            "chat_messages",
            ["reply_to_message_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if not _has_table("portal_notifications"):
        op.create_table(
            "portal_notifications",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=True),
            sa.Column("entity_id", sa.String(length=64), nullable=True),
            sa.Column("action_url", sa.String(length=512), nullable=True),
            sa.Column("dedupe_key", sa.String(length=255), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _has_table("notification_preferences"):
        op.create_table(
            "notification_preferences",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("desktop_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("sound_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("chat_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("quiet_hours_start", sa.String(length=5), nullable=True),
            sa.Column("quiet_hours_end", sa.String(length=5), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("amo_id", "user_id", name="uq_notification_preferences_amo_user"),
        )

    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_threads_amo_scope_key ON chat_threads (amo_id, scope_key) WHERE scope_key IS NOT NULL"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_threads_amo_kind_updated ON chat_threads (amo_id, kind, updated_at DESC)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_threads_department ON chat_threads (amo_id, department_id) WHERE department_id IS NOT NULL"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_threads_user_group ON chat_threads (amo_id, user_group_id) WHERE user_group_id IS NOT NULL"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_thread_members_user_active ON chat_thread_members (user_id, thread_id) WHERE left_at IS NULL"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_messages_thread_created_id ON chat_messages (thread_id, created_at DESC, id DESC)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_message_receipts_user_unread ON message_receipts (amo_id, user_id, message_id) WHERE read_at IS NULL"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_portal_notifications_user_created ON portal_notifications (amo_id, user_id, created_at DESC, id DESC)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_portal_notifications_user_unread ON portal_notifications (amo_id, user_id, created_at DESC) WHERE read_at IS NULL AND archived_at IS NULL"))
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS uq_portal_notifications_user_dedupe ON portal_notifications (amo_id, user_id, dedupe_key) WHERE dedupe_key IS NOT NULL"))

    # Existing rows predate explicit thread kinds. Preserve them as ad-hoc groups.
    bind.execute(sa.text("UPDATE chat_threads SET kind = COALESCE(NULLIF(kind, ''), 'GROUP'), updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"))


def downgrade() -> None:
    for index_name in (
        "uq_portal_notifications_user_dedupe",
        "ix_portal_notifications_user_unread",
        "ix_portal_notifications_user_created",
        "ix_message_receipts_user_unread",
        "ix_chat_messages_thread_created_id",
        "ix_chat_thread_members_user_active",
        "ix_chat_threads_user_group",
        "ix_chat_threads_department",
        "ix_chat_threads_amo_kind_updated",
        "uq_chat_threads_amo_scope_key",
    ):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))

    if _has_table("notification_preferences"):
        op.drop_table("notification_preferences")
    if _has_table("portal_notifications"):
        op.drop_table("portal_notifications")

    for table_name, columns in (
        ("chat_messages", ("metadata", "reply_to_message_id", "message_type")),
        ("chat_thread_members", ("added_by_user_id", "left_at", "muted_until", "last_read_at", "notification_level")),
        ("chat_threads", ("is_archived", "updated_at", "last_message_at", "user_group_id", "department_id", "scope_key", "kind")),
    ):
        for column in columns:
            if column in _columns(table_name):
                op.drop_column(table_name, column)
