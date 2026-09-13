"""Persist governed tenant access-profile elevation requests.

Revision ID: accounts_260913_access_requests
Revises: quality_260913_control_trace
Create Date: 2026-09-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "accounts_260913_access_requests"
down_revision = "quality_260913_control_trace"
branch_labels = None
depends_on = None


_STATUSES = "'PENDING', 'APPROVED', 'DENIED', 'CANCELLED'"


def upgrade() -> None:
    op.create_table(
        "user_access_profile_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("current_profile_id", sa.String(length=36), nullable=True),
        sa.Column("requested_profile_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_profile_id"], ["auth_role_definitions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_profile_id"], ["auth_role_definitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_user_access_profile_request_status"),
    )
    op.create_index(
        "ix_user_access_profile_requests_tenant_status",
        "user_access_profile_requests",
        ["amo_id", "status", "created_at"],
    )
    op.create_index(
        "ix_user_access_profile_requests_user_status",
        "user_access_profile_requests",
        ["user_id", "status", "created_at"],
    )
    pending_only = sa.text("status = 'PENDING'")
    op.create_index(
        "uq_user_access_profile_pending",
        "user_access_profile_requests",
        ["amo_id", "user_id"],
        unique=True,
        postgresql_where=pending_only,
        sqlite_where=pending_only,
    )


def downgrade() -> None:
    op.drop_index("uq_user_access_profile_pending", table_name="user_access_profile_requests")
    op.drop_index("ix_user_access_profile_requests_user_status", table_name="user_access_profile_requests")
    op.drop_index("ix_user_access_profile_requests_tenant_status", table_name="user_access_profile_requests")
    op.drop_table("user_access_profile_requests")
