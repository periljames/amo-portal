"""Merge QMS patch migration heads.

Revision ID: phase2_11_20260605
Revises: phase2_3_20260605, phase2_10_20260605
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op

revision = "phase2_11_20260605"
down_revision = ("phase2_3_20260605", "phase2_10_20260605")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SELECT 1")


def downgrade() -> None:
    op.execute("SELECT 1")
