"""add user availability table for qms manpower

Revision ID: a1b2c3d4e5f6
Revises: r9t8m7q6p5n4
Create Date: 2026-02-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "r9t8m7q6p5n4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_availability",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.Enum("ON_DUTY", "AWAY", "ON_LEAVE", name="user_availability_status_enum", native_enum=False), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_availability_amo_status", "user_availability", ["amo_id", "status"], unique=False)
    op.create_index("ix_user_availability_amo_user", "user_availability", ["amo_id", "user_id"], unique=False)
    op.create_index("ix_user_availability_amo_updated", "user_availability", ["amo_id", "updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_availability_amo_updated", table_name="user_availability")
    op.drop_index("ix_user_availability_amo_user", table_name="user_availability")
    op.drop_index("ix_user_availability_amo_status", table_name="user_availability")
    op.drop_table("user_availability")
