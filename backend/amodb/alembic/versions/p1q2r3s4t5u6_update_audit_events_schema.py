"""update audit_events schema for qms audit logging

Revision ID: p1q2r3s4t5u6
Revises: n1b2c3d4e5f9
Create Date: 2026-03-05 00:00:00.000000
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "p1q2r3s4t5u6"
down_revision = "n1b2c3d4e5f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.alter_column(
            "id",
            existing_type=sa.Integer(),
            type_=sa.String(length=36),
            nullable=False,
        )
        batch_op.alter_column(
            "before_json",
            new_column_name="before",
            existing_type=sa.JSON(),
            nullable=True,
        )
        batch_op.alter_column(
            "after_json",
            new_column_name="after",
            existing_type=sa.JSON(),
            nullable=True,
        )
        batch_op.add_column(sa.Column("metadata", sa.JSON(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM audit_events")).fetchall()
    for (old_id,) in rows:
        bind.execute(
            sa.text("UPDATE audit_events SET id = :new_id WHERE id = :old_id"),
            {"new_id": str(uuid.uuid4()), "old_id": str(old_id)},
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_column("metadata")
        batch_op.alter_column(
            "before",
            new_column_name="before_json",
            existing_type=sa.JSON(),
            nullable=True,
        )
        batch_op.alter_column(
            "after",
            new_column_name="after_json",
            existing_type=sa.JSON(),
            nullable=True,
        )
        batch_op.alter_column(
            "id",
            existing_type=sa.String(length=36),
            type_=sa.Integer(),
            nullable=False,
        )
