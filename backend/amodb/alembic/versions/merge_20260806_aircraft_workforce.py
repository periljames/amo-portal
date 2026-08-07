"""merge aircraft architecture and Workforce governance heads

Revision ID: merge_20260806_aircraft_workforce
Revises: aircraft_arch_20260806_u5_u6, workforce_20260806_governance
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "merge_20260806_aircraft_workforce"
down_revision: Union[str, Sequence[str], None] = (
    "aircraft_arch_20260806_u5_u6",
    "workforce_20260806_governance",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
