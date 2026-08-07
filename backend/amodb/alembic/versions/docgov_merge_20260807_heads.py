"""Merge governed reader with the current aircraft architecture migration line.

Revision ID: docgov_merge_20260807_heads
Revises: docgov_20260807_reader_governance, aircraft_arch_20260806_usage_hsi
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "docgov_merge_20260807_heads"
down_revision: Union[str, Sequence[str], None] = (
    "docgov_20260807_reader_governance",
    "aircraft_arch_20260806_usage_hsi",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
