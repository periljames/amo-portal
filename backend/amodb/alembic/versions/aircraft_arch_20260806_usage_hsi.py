"""align aircraft usage component total fields with the Fleet model

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


USAGE_TOTAL_COLUMNS = (
    "ttshsi_after",
    "tcsoh_after",
    "pttsn_after",
    "pttso_after",
    "tscoa_after",
)


def upgrade() -> None:
    for column_name in USAGE_TOTAL_COLUMNS:
        op.add_column(
            "aircraft_usage",
            sa.Column(column_name, sa.Float(), nullable=True),
        )


def downgrade() -> None:
    for column_name in reversed(USAGE_TOTAL_COLUMNS):
        op.drop_column("aircraft_usage", column_name)
