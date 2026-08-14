"""Merge commercial control state with the current main migration line.

Revision ID: commercial_main_260814_merge
Revises: commercial_clean_20260808, roster_training_260814_merge
Create Date: 2026-08-14
"""
from __future__ import annotations

revision = "commercial_main_260814_merge"
down_revision = (
    "commercial_clean_20260808",
    "roster_training_260814_merge",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
