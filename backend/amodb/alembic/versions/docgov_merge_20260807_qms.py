"""Merge Document Control governance and QMS planner heads.

Revision ID: docgov_merge_20260807_qms
Revises: docgov_merge_20260807_heads, merge_20260807_qms_planner_aircraft
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "docgov_merge_20260807_qms"
down_revision: Union[str, Sequence[str], None] = (
    "docgov_merge_20260807_heads",
    "merge_20260807_qms_planner_aircraft",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
