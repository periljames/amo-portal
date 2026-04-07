"""Align training course status default with workbook domain.

Revision ID: a3c9e7f1b2d4
Revises: f2a6c1d9b8e7
Create Date: 2026-04-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3c9e7f1b2d4"
down_revision: Union[str, Sequence[str], None] = "f2a6c1d9b8e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "training_courses",
        "status",
        existing_type=sa.String(length=64),
        server_default=sa.text("'One_Off'"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "training_courses",
        "status",
        existing_type=sa.String(length=64),
        server_default=sa.text("'Active'"),
        existing_nullable=False,
    )
