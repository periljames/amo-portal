"""Add training course catalog import columns and defaults.

Revision ID: f2a6c1d9b8e7
Revises: e1f2a3b4c5d6
Create Date: 2026-04-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a6c1d9b8e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("training_courses", sa.Column("category_raw", sa.String(length=255), nullable=True))
    op.add_column(
        "training_courses",
        sa.Column("status", sa.String(length=64), nullable=False, server_default=sa.text("'Active'")),
    )
    op.add_column("training_courses", sa.Column("scope", sa.String(length=255), nullable=True))
    op.alter_column(
        "training_courses",
        "is_mandatory",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "training_courses",
        "is_mandatory",
        existing_type=sa.Boolean(),
        server_default=None,
        existing_nullable=False,
    )
    op.drop_column("training_courses", "scope")
    op.drop_column("training_courses", "status")
    op.drop_column("training_courses", "category_raw")
