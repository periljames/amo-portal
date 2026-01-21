"""add demo context

Revision ID: f7c8d9e0f1a2
Revises: f6b7c8d9e0f1
Create Date: 2025-01-12 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "f6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("amos", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(op.f("ix_amos_is_demo"), "amos", ["is_demo"], unique=False)
    op.alter_column("amos", "is_demo", server_default=None)

    op.create_table(
        "user_active_context",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("active_amo_id", sa.String(length=36), nullable=True),
        sa.Column(
            "data_mode",
            sa.Enum("DEMO", "REAL", name="user_data_mode_enum"),
            nullable=False,
        ),
        sa.Column("last_real_amo_id", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["active_amo_id"],
            ["amos.id"],
            name=op.f("fk_user_active_context_active_amo_id_amos"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_real_amo_id"],
            ["amos.id"],
            name=op.f("fk_user_active_context_last_real_amo_id_amos"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_active_context_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_active_context")),
        sa.UniqueConstraint("user_id", name="uq_user_active_context_user"),
    )
    op.create_index("ix_user_active_context_user", "user_active_context", ["user_id"], unique=False)
    op.create_index("ix_user_active_context_amo", "user_active_context", ["active_amo_id"], unique=False)
    op.create_index("ix_user_active_context_mode", "user_active_context", ["data_mode"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_active_context_mode", table_name="user_active_context")
    op.drop_index("ix_user_active_context_amo", table_name="user_active_context")
    op.drop_index("ix_user_active_context_user", table_name="user_active_context")
    op.drop_table("user_active_context")

    op.drop_index(op.f("ix_amos_is_demo"), table_name="amos")
    op.drop_column("amos", "is_demo")
