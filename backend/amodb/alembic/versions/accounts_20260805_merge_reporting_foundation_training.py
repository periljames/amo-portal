"""Converge reporting, foundation and training migration branches.

Revision ID: accounts_20260805_merge_reporting_foundation_training
Revises: accounts_20260805_reporting_integrity, foundation_20260805_timestamp_defaults, training_260804_workbook
Create Date: 2026-08-05

This merge revision performs no schema operations. It records that all three
independent, legitimate migration branches must be present before subsequent
revisions can proceed, restoring one authoritative Alembic head.
"""
from __future__ import annotations

revision = "accounts_20260805_merge_reporting_foundation_training"
down_revision = (
    "accounts_20260805_reporting_integrity",
    "foundation_20260805_timestamp_defaults",
    "training_260804_workbook",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
