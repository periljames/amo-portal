"""align aircraft usage HSI field with the Fleet model

Revision ID: aircraft_arch_20260806_usage_hsi
Revises: aircraft_arch_20260806_u6_guards
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aircraft_arch_20260806_usage_hsi"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260806_u6_guards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "aircraft_usage",
        sa.Column("ttshsi_after", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("aircraft_usage", "ttshsi_after")
