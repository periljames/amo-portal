"""merge QMS planner and aircraft architecture heads

Revision ID: merge_20260807_qms_planner_aircraft
Revises: quality_20260806_planner_metadata, aircraft_arch_20260806_usage_hsi
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "merge_20260807_qms_planner_aircraft"
down_revision: Union[str, Sequence[str], None] = (
    "quality_20260806_planner_metadata",
    "aircraft_arch_20260806_usage_hsi",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
