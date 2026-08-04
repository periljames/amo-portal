"""Store user-scoped portal appearance and accessibility preferences.

Revision ID: accounts_260804_portal_prefs
Revises: accounts_20260803_auth_session
Create Date: 2026-08-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "accounts_260804_portal_prefs"
down_revision = "accounts_20260803_auth_session"
branch_labels = None
depends_on = None


_TABLE = "user_portal_preferences"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=True),
        sa.Column("text_scale", sa.String(length=24), nullable=False, server_default="standard"),
        sa.Column("density", sa.String(length=24), nullable=False, server_default="comfortable"),
        sa.Column("motion", sa.String(length=24), nullable=False, server_default="system"),
        sa.Column("color_scheme", sa.String(length=24), nullable=False, server_default="system"),
        sa.Column("accent", sa.String(length=24), nullable=False, server_default="tenant"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_user_portal_preferences_user"),
        sa.CheckConstraint(
            "text_scale IN ('standard', 'large', 'extra-large')",
            name="ck_user_portal_preferences_text_scale",
        ),
        sa.CheckConstraint(
            "density IN ('comfortable', 'compact')",
            name="ck_user_portal_preferences_density",
        ),
        sa.CheckConstraint(
            "motion IN ('system', 'full', 'reduced')",
            name="ck_user_portal_preferences_motion",
        ),
        sa.CheckConstraint(
            "color_scheme IN ('system', 'light', 'dark')",
            name="ck_user_portal_preferences_color_scheme",
        ),
        sa.CheckConstraint(
            "accent IN ('tenant', 'blue', 'teal', 'green', 'amber', 'violet')",
            name="ck_user_portal_preferences_accent",
        ),
    )
    op.create_index(
        "ix_user_portal_preferences_amo_user",
        _TABLE,
        ["amo_id", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_portal_preferences_amo_user", table_name=_TABLE)
    op.drop_table(_TABLE)
