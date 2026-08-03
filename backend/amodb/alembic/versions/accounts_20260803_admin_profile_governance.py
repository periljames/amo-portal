"""Add governed tenant Admin Profile grants, sessions and audit events.

Revision ID: accounts_20260803_admin_profile
Revises: notifications_20260729_delivery
Create Date: 2026-08-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "accounts_20260803_admin_profile"
down_revision = "notifications_20260729_delivery"
branch_labels = None
depends_on = None


GRANT_TYPES = ("PERMANENT", "TEMPORARY")
GRANT_STATUSES = ("PENDING", "ACTIVE", "REVOKED", "REJECTED", "EXPIRED")
APPROVAL_DECISIONS = ("APPROVED", "REJECTED")


def upgrade() -> None:
    op.create_table(
        "admin_access_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("grant_type", sa.String(length=16), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "grant_type IN ('PERMANENT', 'TEMPORARY')",
            name="ck_admin_access_grants_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'REVOKED', 'REJECTED', 'EXPIRED')",
            name="ck_admin_access_grants_status",
        ),
        sa.CheckConstraint(
            "grant_type = 'PERMANENT' OR valid_until IS NOT NULL",
            name="ck_admin_access_grants_temporary_expiry",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from",
            name="ck_admin_access_grants_valid_window",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_grants_amo_user_status",
        "admin_access_grants",
        ["amo_id", "user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_admin_grants_status_valid_until",
        "admin_access_grants",
        ["status", "valid_until"],
        unique=False,
    )
    op.create_index(
        "ix_admin_grants_requested_by",
        "admin_access_grants",
        ["requested_by_user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "admin_access_grant_approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("grant_id", sa.String(length=36), nullable=False),
        sa.Column("approver_user_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('APPROVED', 'REJECTED')",
            name="ck_admin_grant_approvals_decision",
        ),
        sa.ForeignKeyConstraint(
            ["grant_id"],
            ["admin_access_grants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approver_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "grant_id",
            "approver_user_id",
            name="uq_admin_grant_approver",
        ),
    )
    op.create_index(
        "ix_admin_grant_approvals_grant_decision",
        "admin_access_grant_approvals",
        ["grant_id", "decision"],
        unique=False,
    )

    op.create_table(
        "admin_profile_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("auth_session_id", sa.String(length=64), nullable=False),
        sa.Column("grant_id", sa.String(length=36), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expires_at > activated_at",
            name="ck_admin_profile_sessions_expiry",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["grant_id"],
            ["admin_access_grants.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_profile_sessions_amo_user",
        "admin_profile_sessions",
        ["amo_id", "user_id", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_profile_sessions_auth_session",
        "admin_profile_sessions",
        ["amo_id", "user_id", "auth_session_id", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_profile_sessions_grant",
        "admin_profile_sessions",
        ["grant_id"],
        unique=False,
    )

    op.create_table(
        "admin_access_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("subject_user_id", sa.String(length=36), nullable=True),
        sa.Column("grant_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["grant_id"],
            ["admin_access_grants.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["admin_profile_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_access_events_amo_created",
        "admin_access_events",
        ["amo_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_access_events_subject_created",
        "admin_access_events",
        ["subject_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_access_events_grant",
        "admin_access_events",
        ["grant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_admin_access_events_grant", table_name="admin_access_events")
    op.drop_index(
        "ix_admin_access_events_subject_created",
        table_name="admin_access_events",
    )
    op.drop_index(
        "ix_admin_access_events_amo_created",
        table_name="admin_access_events",
    )
    op.drop_table("admin_access_events")

    op.drop_index(
        "ix_admin_profile_sessions_grant",
        table_name="admin_profile_sessions",
    )
    op.drop_index(
        "ix_admin_profile_sessions_auth_session",
        table_name="admin_profile_sessions",
    )
    op.drop_index(
        "ix_admin_profile_sessions_amo_user",
        table_name="admin_profile_sessions",
    )
    op.drop_table("admin_profile_sessions")

    op.drop_index(
        "ix_admin_grant_approvals_grant_decision",
        table_name="admin_access_grant_approvals",
    )
    op.drop_table("admin_access_grant_approvals")

    op.drop_index(
        "ix_admin_grants_requested_by",
        table_name="admin_access_grants",
    )
    op.drop_index(
        "ix_admin_grants_status_valid_until",
        table_name="admin_access_grants",
    )
    op.drop_index(
        "ix_admin_grants_amo_user_status",
        table_name="admin_access_grants",
    )
    op.drop_table("admin_access_grants")
