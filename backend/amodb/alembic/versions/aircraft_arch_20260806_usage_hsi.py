"""align aircraft usage fields with the Fleet model

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


USAGE_COLUMNS = (
    ("ttshsi_after", sa.Float()),
    ("tcsoh_after", sa.Float()),
    ("pttsn_after", sa.Float()),
    ("pttso_after", sa.Float()),
    ("tscoa_after", sa.Float()),
    ("hours_to_mx", sa.Float()),
    ("days_to_mx", sa.Integer()),
)


def upgrade() -> None:
    for column_name, column_type in USAGE_COLUMNS:
        op.add_column(
            "aircraft_usage",
            sa.Column(column_name, column_type, nullable=True),
        )


def downgrade() -> None:
    for column_name, _column_type in reversed(USAGE_COLUMNS):
        op.drop_column("aircraft_usage", column_name)
