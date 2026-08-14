"""Merge controlled Rostering with the current Training migration line.

Revision ID: roster_training_260814_merge
Revises: roster_docctl_260813_merge, training_20260814_plan_controls
Create Date: 2026-08-14
"""
from __future__ import annotations

revision = "roster_training_260814_merge"
down_revision = (
    "roster_docctl_260813_merge",
    "training_20260814_plan_controls",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
