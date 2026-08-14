"""Merge controlled rostering with the Document Control lifecycle migration line.

Revision ID: roster_docctl_260813_merge
Revises: docctl_20260812_retention_approver, rostering_control_260812
Create Date: 2026-08-13
"""
from __future__ import annotations

revision = "roster_docctl_260813_merge"
down_revision = (
    "docctl_20260812_retention_approver",
    "rostering_control_260812",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
