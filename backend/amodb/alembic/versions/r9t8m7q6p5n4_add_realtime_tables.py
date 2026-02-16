"""add realtime tables

Revision ID: r9t8m7q6p5n4
Revises: c3d4e5f6a7b8, d6e7f8a9b0c1
Create Date: 2026-02-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "r9t8m7q6p5n4"
down_revision = ("c3d4e5f6a7b8", "d6e7f8a9b0c1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chat_thread_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "user_id", name="uq_chat_thread_members_thread_user"),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("sender_id", sa.String(length=36), nullable=True),
        sa.Column("body_bin", sa.LargeBinary(), nullable=False),
        sa.Column("body_mime", sa.String(length=64), nullable=False),
        sa.Column("client_msg_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sender_id", "client_msg_id", name="uq_chat_messages_sender_client_msg"),
    )
    op.create_table(
        "message_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_receipts_message_user"),
    )
    op.create_table(
        "prompts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("subject_ref", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "prompt_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("prompt_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("action_bin", sa.LargeBinary(), nullable=True),
        sa.Column("action_mime", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prompt_id", "user_id", name="uq_prompt_deliveries_prompt_user"),
    )
    op.create_table(
        "presence_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "user_id", name="uq_presence_state_amo_user"),
    )
    op.create_table(
        "realtime_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("payload_bin", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "realtime_connect_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )

    op.create_index("ix_chat_messages_amo_thread_created_at", "chat_messages", ["amo_id", "thread_id", "created_at"])
    op.create_index("ix_message_receipts_message_user", "message_receipts", ["message_id", "user_id"])
    op.create_index("ix_prompt_deliveries_prompt_user", "prompt_deliveries", ["prompt_id", "user_id"])
    op.create_index("ix_presence_state_amo_user", "presence_state", ["amo_id", "user_id"])
    op.create_index("ix_realtime_outbox_pending", "realtime_outbox", ["published_at", "created_at"])


def downgrade() -> None:
    for idx, table in [
        ("ix_realtime_outbox_pending", "realtime_outbox"),
        ("ix_presence_state_amo_user", "presence_state"),
        ("ix_prompt_deliveries_prompt_user", "prompt_deliveries"),
        ("ix_message_receipts_message_user", "message_receipts"),
        ("ix_chat_messages_amo_thread_created_at", "chat_messages"),
    ]:
        op.drop_index(idx, table_name=table)

    op.drop_table("realtime_connect_tokens")
    op.drop_table("realtime_outbox")
    op.drop_table("presence_state")
    op.drop_table("prompt_deliveries")
    op.drop_table("prompts")
    op.drop_table("message_receipts")
    op.drop_table("chat_messages")
    op.drop_table("chat_thread_members")
    op.drop_table("chat_threads")
