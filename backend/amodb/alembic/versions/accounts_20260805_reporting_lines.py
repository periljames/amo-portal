"""Add governed display-title preferences and reporting-line support.

Revision ID: accounts_20260805_reporting_lines
Revises: accounts_20260805_corporate_structure
Create Date: 2026-08-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "accounts_20260805_reporting_lines"
down_revision = "accounts_20260805_corporate_structure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personnel_title_preferences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "amo_id",
            sa.String(36),
            sa.ForeignKey("amos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assignment_id",
            sa.String(36),
            sa.ForeignKey("position_assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_title", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="SELF_SERVICE"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column(
            "requested_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "decided_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_personnel_title_preferences_amo_user_status",
        "personnel_title_preferences",
        ["amo_id", "user_id", "status"],
    )
    op.create_index(
        "ix_personnel_title_preferences_assignment_status",
        "personnel_title_preferences",
        ["assignment_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_personnel_title_preferences_assignment_status",
        table_name="personnel_title_preferences",
    )
    op.drop_index(
        "ix_personnel_title_preferences_amo_user_status",
        table_name="personnel_title_preferences",
    )
    op.drop_table("personnel_title_preferences")
