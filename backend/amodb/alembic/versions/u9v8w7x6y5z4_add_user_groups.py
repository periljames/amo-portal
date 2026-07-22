"""Add user groups.

Revision ID: u9v8w7x6y5z4
Revises: multiple module heads
Create Date: 2026-04-08

PostgreSQL enum creation is separated from table creation. The table column
uses ``create_type=False`` so a pre-existing or explicitly-created enum is not
created a second time by SQLAlchemy's table DDL event.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "u9v8w7x6y5z4"
down_revision = (
    "2c4d7e9f0a1b",
    "9c6a7d2e8f10",
    "a1b2c3d4e5f6",
    "a5c1d2e3f4b6",
    "b1c2d3e4f5a6",
    "b2c3d4e5f6g7",
    "c1d2e3f4a5b7",
    "c3d4e5f6a7b8",
    "d0c1b2a3e4f5",
    "d7e6f5a4b3c2",
    "d9e2f3a4b5c6",
    "e4b7d1a2c3f4",
    "g1b2c3d4e5f6",
    "l1b2c3d4e5f7",
    "p0a4_training_gate_fields",
    "s9t8u7v6w5x4",
    "w2x3y4z5a6b7",
)
branch_labels = None
depends_on = None

ENUM_NAME = "user_group_type_enum"
ENUM_VALUES = ("POST_HOLDERS", "DEPARTMENT", "CUSTOM", "PERSONAL")


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _group_type(bind) -> sa.types.TypeEngine:
    if bind.dialect.name == "postgresql":
        values = ", ".join(f"'{value}'" for value in ENUM_VALUES)
        bind.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    CREATE TYPE {ENUM_NAME} AS ENUM ({values});
                EXCEPTION
                    WHEN duplicate_object THEN NULL;
                END $$
                """
            )
        )
        return postgresql.ENUM(
            *ENUM_VALUES,
            name=ENUM_NAME,
            create_type=False,
        )
    return sa.Enum(
        *ENUM_VALUES,
        name=ENUM_NAME,
        native_enum=False,
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    group_type = _group_type(bind)

    if not inspector.has_table("user_groups"):
        op.create_table(
            "user_groups",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("owner_user_id", sa.String(length=36), nullable=True),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("group_type", group_type, nullable=False),
            sa.Column("is_system_managed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("amo_id", "code", name="uq_user_groups_amo_code"),
        )
    else:
        existing = _column_names(inspector, "user_groups")
        if "owner_user_id" not in existing:
            op.add_column("user_groups", sa.Column("owner_user_id", sa.String(length=36), nullable=True))
        if "description" not in existing:
            op.add_column("user_groups", sa.Column("description", sa.Text(), nullable=True))
        if "group_type" not in existing:
            op.add_column(
                "user_groups",
                sa.Column(
                    "group_type",
                    group_type,
                    nullable=False,
                    server_default="CUSTOM",
                ),
            )
        if "is_system_managed" not in existing:
            op.add_column("user_groups", sa.Column("is_system_managed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        if "is_active" not in existing:
            op.add_column("user_groups", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
        if "created_at" not in existing:
            op.add_column("user_groups", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        if "updated_at" not in existing:
            op.add_column("user_groups", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    for index_sql in (
        "CREATE INDEX IF NOT EXISTS ix_user_groups_amo_id ON user_groups (amo_id)",
        "CREATE INDEX IF NOT EXISTS ix_user_groups_owner_user_id ON user_groups (owner_user_id)",
        "CREATE INDEX IF NOT EXISTS ix_user_groups_amo_type ON user_groups (amo_id, group_type)",
        "CREATE INDEX IF NOT EXISTS ix_user_groups_amo_active ON user_groups (amo_id, is_active)",
    ):
        op.execute(sa.text(index_sql))

    inspector = sa.inspect(bind)
    if not inspector.has_table("user_group_members"):
        op.create_table(
            "user_group_members",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("group_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("added_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("member_role", sa.String(length=32), nullable=False, server_default="member"),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["added_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["group_id"], ["user_groups.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("group_id", "user_id", name="uq_user_group_members_group_user"),
        )
    for index_sql in (
        "CREATE INDEX IF NOT EXISTS ix_user_group_members_group_id ON user_group_members (group_id)",
        "CREATE INDEX IF NOT EXISTS ix_user_group_members_user_id ON user_group_members (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_user_group_members_user ON user_group_members (user_id)",
    ):
        op.execute(sa.text(index_sql))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("user_group_members"):
        op.drop_table("user_group_members")
    if inspector.has_table("user_groups"):
        op.drop_table("user_groups")
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f"DROP TYPE IF EXISTS {ENUM_NAME}"))
