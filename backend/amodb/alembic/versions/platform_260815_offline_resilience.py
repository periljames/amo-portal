"""Add revocable portal refresh sessions for outage recovery.

Revision ID: platform_260815_offline_resilience
Revises: accounts_260815_role_aliases
Create Date: 2026-08-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "platform_260815_offline_resilience"
down_revision = "accounts_260815_role_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portal_refresh_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=True),
        sa.Column("auth_session_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_portal_refresh_session_token_hash"),
    )
    op.create_index(
        "ix_portal_refresh_session_user_expiry",
        "portal_refresh_sessions",
        ["user_id", "expires_at"],
    )
    op.create_index(
        "ix_portal_refresh_session_auth_session",
        "portal_refresh_sessions",
        ["auth_session_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_portal_refresh_session_auth_session", table_name="portal_refresh_sessions")
    op.drop_index("ix_portal_refresh_session_user_expiry", table_name="portal_refresh_sessions")
    op.drop_table("portal_refresh_sessions")
