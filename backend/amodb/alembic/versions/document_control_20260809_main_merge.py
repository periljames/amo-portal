"""merge current main QMS/Reliability head with DMS regulatory mapping

Revision ID: docctl_20260809_main_merge
Revises: docctl_20260808_regmap, merge_260809_qms_reliability
Create Date: 2026-08-09
"""

from __future__ import annotations


revision = "docctl_20260809_main_merge"
down_revision = ("docctl_20260808_regmap", "merge_260809_qms_reliability")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
