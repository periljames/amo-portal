"""ensure user group runtime columns exist

Revision ID: v0a1b2c3d4e5
Revises: u9v8w7x6y5z4
Create Date: 2026-04-09 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "v0a1b2c3d4e5"
down_revision = "u9v8w7x6y5z4"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "user_groups"):
        if not _has_column(inspector, "user_groups", "is_system_managed"):
            op.add_column(
                "user_groups",
                sa.Column("is_system_managed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if not _has_column(inspector, "user_groups", "is_active"):
            op.add_column(
                "user_groups",
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            )
        if not _has_column(inspector, "user_groups", "created_at"):
            op.add_column(
                "user_groups",
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                ),
            )
        if not _has_column(inspector, "user_groups", "updated_at"):
            op.add_column(
                "user_groups",
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                ),
            )
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_groups_amo_type ON user_groups (amo_id, group_type)"))
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_groups_amo_active ON user_groups (amo_id, is_active)"))

    inspector = sa.inspect(bind)
    if _has_table(inspector, "user_group_members"):
        if not _has_column(inspector, "user_group_members", "added_by_user_id"):
            op.add_column(
                "user_group_members",
                sa.Column("added_by_user_id", sa.String(length=36), nullable=True),
            )
        if not _has_column(inspector, "user_group_members", "member_role"):
            op.add_column(
                "user_group_members",
                sa.Column("member_role", sa.String(length=32), nullable=False, server_default="member"),
            )
        if not _has_column(inspector, "user_group_members", "added_at"):
            op.add_column(
                "user_group_members",
                sa.Column(
                    "added_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                ),
            )
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_group_members_user ON user_group_members (user_id)"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "user_group_members"):
        if _has_column(inspector, "user_group_members", "added_at"):
            op.drop_column("user_group_members", "added_at")
        if _has_column(inspector, "user_group_members", "member_role"):
            op.drop_column("user_group_members", "member_role")
        if _has_column(inspector, "user_group_members", "added_by_user_id"):
            op.drop_column("user_group_members", "added_by_user_id")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "user_groups"):
        if _has_column(inspector, "user_groups", "updated_at"):
            op.drop_column("user_groups", "updated_at")
        if _has_column(inspector, "user_groups", "created_at"):
            op.drop_column("user_groups", "created_at")
        if _has_column(inspector, "user_groups", "is_active"):
            op.drop_column("user_groups", "is_active")
        if _has_column(inspector, "user_groups", "is_system_managed"):
            op.drop_column("user_groups", "is_system_managed")
