"""Converge the current Quality and Reliability migration heads.

Revision ID: rel_quality_20260804_merge
Revises: quality_260804_trigger_fix, rel_20260803_complete_scope
Create Date: 2026-08-04
"""
from typing import Sequence, Union


revision: str = "rel_quality_20260804_merge"
down_revision: Union[str, Sequence[str], None] = (
    "quality_260804_trigger_fix",
    "rel_20260803_complete_scope",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge both schema branches without changing database objects."""
    pass


def downgrade() -> None:
    """Split back to the Quality and Reliability heads without schema changes."""
    pass
