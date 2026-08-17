"""Add device-scoped auth refresh and presence sessions.

Revision ID: resilience_260816_sessions
Revises: workforce_260815_hire_dates
Create Date: 2026-08-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "resilience_260816_sessions"
down_revision = "workforce_260815_hire_dates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portal_auth_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=True),
        sa.Column("refresh_family_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent_hash", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portal_auth_sessions_user_id", "portal_auth_sessions", ["user_id"])
    op.create_index("ix_portal_auth_sessions_amo_id", "portal_auth_sessions", ["amo_id"])
    op.create_index("ix_portal_auth_sessions_expires_at", "portal_auth_sessions", ["expires_at"])
    op.create_index("ix_portal_auth_sessions_revoked_at", "portal_auth_sessions", ["revoked_at"])
    op.create_index(
        "ix_portal_auth_sessions_refresh_family_id",
        "portal_auth_sessions",
        ["refresh_family_id"],
        unique=True,
    )
    op.create_index(
        "ix_portal_auth_sessions_user_active",
        "portal_auth_sessions",
        ["user_id", "revoked_at", "expires_at"],
    )
    op.create_index(
        "ix_portal_auth_sessions_amo_active",
        "portal_auth_sessions",
        ["amo_id", "revoked_at", "expires_at"],
    )

    op.create_table(
        "refresh_session_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("replaced_by_id", sa.String(length=36), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["refresh_session_tokens.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["refresh_session_tokens.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["portal_auth_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_session_tokens_session_id", "refresh_session_tokens", ["session_id"])
    op.create_index("ix_refresh_session_tokens_family_id", "refresh_session_tokens", ["family_id"])
    op.create_index(
        "ix_refresh_session_tokens_token_hash",
        "refresh_session_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index("ix_refresh_session_tokens_status", "refresh_session_tokens", ["status"])
    op.create_index("ix_refresh_session_tokens_expires_at", "refresh_session_tokens", ["expires_at"])
    op.create_index(
        "ix_refresh_session_tokens_session_status",
        "refresh_session_tokens",
        ["session_id", "status", "expires_at"],
    )
    op.create_index(
        "ix_refresh_session_tokens_family",
        "refresh_session_tokens",
        ["family_id", "issued_at"],
    )

    op.create_table(
        "presence_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=7), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "amo_id",
            "user_id",
            "session_id",
            name="uq_presence_sessions_amo_user_session",
        ),
    )
    op.create_index("ix_presence_sessions_amo_id", "presence_sessions", ["amo_id"])
    op.create_index("ix_presence_sessions_user_id", "presence_sessions", ["user_id"])
    op.create_index(
        "ix_presence_sessions_amo_fresh",
        "presence_sessions",
        ["amo_id", "last_seen_at"],
    )
    op.create_index(
        "ix_presence_sessions_user_fresh",
        "presence_sessions",
        ["amo_id", "user_id", "last_seen_at"],
    )


def downgrade() -> None:
    op.drop_table("presence_sessions")
    op.drop_table("refresh_session_tokens")
    op.drop_table("portal_auth_sessions")
