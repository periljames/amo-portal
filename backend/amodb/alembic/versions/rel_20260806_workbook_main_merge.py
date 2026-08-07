"""Merge Reliability workbook parity with current Workforce governance head.

Revision ID: rel_20260806_workbook_main_merge
Revises: rel_20260806_workbook_parity, workforce_20260806_governance
Create Date: 2026-08-06

This is a graph-only merge. Both parent revisions remain fully applied and no
schema object is created or altered by this revision.
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "rel_20260806_workbook_main_merge"
down_revision: Union[str, Sequence[str], None] = (
    "rel_20260806_workbook_parity",
    "workforce_20260806_governance",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
