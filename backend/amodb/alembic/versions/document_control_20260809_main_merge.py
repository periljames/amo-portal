"""merge current main QMS head with DMS regulatory mapping

Revision ID: docctl_20260809_main_merge
Revises: docctl_20260808_regmap, quality_260809_checklist_exec
Create Date: 2026-08-09
"""

from __future__ import annotations


revision = "docctl_20260809_main_merge"
down_revision = ("docctl_20260808_regmap", "quality_260809_checklist_exec")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
