"""Bind Admin Profile elevation to an authentication session.

Revision ID: accounts_20260803_auth_session
Revises: accounts_20260803_admin_profile
Create Date: 2026-08-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "accounts_20260803_auth_session"
down_revision = "accounts_20260803_admin_profile"
branch_labels = None
depends_on = None


_INDEX = "ix_admin_profile_sessions_auth_session"


def upgrade() -> None:
    # Add nullable first so databases that already contain a short-lived profile
    # row can migrate without a table rewrite failure. Existing rows receive an
    # unmatchable migration id and therefore fail closed until reactivation.
    op.add_column(
        "admin_profile_sessions",
        sa.Column("auth_session_id", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE admin_profile_sessions
        SET auth_session_id = 'migrated-' || id
        WHERE auth_session_id IS NULL
        """
    )
    with op.batch_alter_table("admin_profile_sessions") as batch:
        batch.alter_column(
            "auth_session_id",
            existing_type=sa.String(length=64),
            nullable=False,
        )
    op.create_index(
        _INDEX,
        "admin_profile_sessions",
        ["amo_id", "user_id", "auth_session_id", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="admin_profile_sessions")
    with op.batch_alter_table("admin_profile_sessions") as batch:
        batch.drop_column("auth_session_id")
