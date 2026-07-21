"""tenant support sessions for platform read-only and approved admin access

Revision ID: plat_20260627_support
Revises: plat_p7_20260501
Create Date: 2026-06-27
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "plat_20260627_support"
down_revision: Union[str, Sequence[str], None] = "plat_p7_20260501"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_index(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    return name in {idx["name"] for idx in sa.inspect(op.get_bind()).get_indexes(table)}


def _json_type():
    bind = op.get_bind()
    return postgresql.JSONB(astext_type=sa.Text()) if bind.dialect.name == "postgresql" else sa.JSON()


def upgrade() -> None:
    if not _has_table("platform_tenant_support_sessions"):
        op.create_table(
            "platform_tenant_support_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("platform_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("access_level", sa.String(32), nullable=False, server_default="READ_ONLY"),
            sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("requested_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("denied_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("denied_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("metadata_json", _json_type(), nullable=True),
            sa.CheckConstraint("access_level IN ('READ_ONLY', 'ADMIN')", name="ck_platform_support_session_access_level"),
            sa.CheckConstraint("status IN ('PENDING', 'ACTIVE', 'DENIED', 'ENDED', 'EXPIRED')", name="ck_platform_support_session_status"),
        )

    for name, cols in {
        "ix_platform_support_session_tenant_status": ["tenant_id", "status", "expires_at"],
        "ix_platform_support_session_platform_user": ["platform_user_id", "status", "expires_at"],
        "ix_platform_support_session_approved_by": ["approved_by_user_id"],
    }.items():
        if not _has_index("platform_tenant_support_sessions", name):
            op.create_index(name, "platform_tenant_support_sessions", cols, unique=False)


def downgrade() -> None:
    if _has_table("platform_tenant_support_sessions"):
        op.drop_table("platform_tenant_support_sessions")
