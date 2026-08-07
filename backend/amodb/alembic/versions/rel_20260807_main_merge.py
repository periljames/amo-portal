"""merge current main and Reliability workbook heads

Revision ID: rel_20260807_main_merge
Revises: rel_20260806_reference_integrity, merge_20260807_qms_planner_aircraft
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "rel_20260807_main_merge"
down_revision: Union[str, Sequence[str], None] = (
    "rel_20260806_reference_integrity",
    "merge_20260807_qms_planner_aircraft",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
