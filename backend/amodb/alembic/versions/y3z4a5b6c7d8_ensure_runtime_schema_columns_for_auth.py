"""ensure runtime schema columns for auth/realtime compatibility

Revision ID: y3z4a5b6c7d8
Revises: b1c2d3e4f5a6, d2c3e4f5a6b7, e41af43f2beb, w2x3y4z5a6b7, z9y8x7w6v5u4
Create Date: 2026-02-10 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "y3z4a5b6c7d8"
down_revision = ("b1c2d3e4f5a6", "d2c3e4f5a6b7", "e41af43f2beb", "w2x3y4z5a6b7", "z9y8x7w6v5u4")
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "users"):
        if not _has_column(inspector, "users", "is_auditor"):
            op.add_column(
                "users",
                sa.Column("is_auditor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if not _has_column(inspector, "users", "lockout_count"):
            op.add_column(
                "users",
                sa.Column("lockout_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            )
        if not _has_column(inspector, "users", "must_change_password"):
            op.add_column(
                "users",
                sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if not _has_column(inspector, "users", "token_revoked_at"):
            op.add_column("users", sa.Column("token_revoked_at", sa.DateTime(timezone=True), nullable=True))

    if _has_table(inspector, "audit_events"):
        if not _has_column(inspector, "audit_events", "before"):
            op.add_column("audit_events", sa.Column("before", sa.JSON(), nullable=True))
        if not _has_column(inspector, "audit_events", "after"):
            op.add_column("audit_events", sa.Column("after", sa.JSON(), nullable=True))
        if not _has_column(inspector, "audit_events", "metadata"):
            op.add_column("audit_events", sa.Column("metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "audit_events"):
        if _has_column(inspector, "audit_events", "metadata"):
            op.drop_column("audit_events", "metadata")
        if _has_column(inspector, "audit_events", "after"):
            op.drop_column("audit_events", "after")
        if _has_column(inspector, "audit_events", "before"):
            op.drop_column("audit_events", "before")

    if _has_table(inspector, "users"):
        if _has_column(inspector, "users", "token_revoked_at"):
            op.drop_column("users", "token_revoked_at")
        if _has_column(inspector, "users", "must_change_password"):
            op.drop_column("users", "must_change_password")
        if _has_column(inspector, "users", "lockout_count"):
            op.drop_column("users", "lockout_count")
        if _has_column(inspector, "users", "is_auditor"):
            op.drop_column("users", "is_auditor")
