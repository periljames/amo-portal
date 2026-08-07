"""Merge Document Control governance with the aircraft/workforce migration line.

Revision ID: docgov_merge_20260807
Revises: docgov_20260806_governance, merge_20260806_aircraft_workforce
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "docgov_merge_20260807"
down_revision: Union[str, Sequence[str], None] = (
    "docgov_20260806_governance",
    "merge_20260806_aircraft_workforce",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
