"""add billing audit logs table

Revision ID: m1b2c3d4e5f8
Revises: l1b2c3d4e5f7
Create Date: 2026-02-03 12:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "m1b2c3d4e5f8"
down_revision: Union[str, Sequence[str], None] = "l1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billing_audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["amo_id"],
            ["amos.id"],
            name=op.f("fk_billing_audit_logs_amo_id_amos"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_billing_audit_logs")),
    )
    op.create_index(
        op.f("ix_billing_audit_logs_amo_id"),
        "billing_audit_logs",
        ["amo_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_billing_audit_logs_amo_id"), table_name="billing_audit_logs")
    op.drop_table("billing_audit_logs")
