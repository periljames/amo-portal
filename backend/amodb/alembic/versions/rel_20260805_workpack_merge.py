"""Converge current Foundation and Training migration heads.

Revision ID: rel_20260805_workpack_merge
Revises: foundation_20260805_timestamp_defaults, training_260804_workbook
Create Date: 2026-08-05

This is a graph-only merge. Both parent revisions remain fully applied and no
schema object is created or altered by this revision.
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "rel_20260805_workpack_merge"
down_revision: Union[str, Sequence[str], None] = (
    "foundation_20260805_timestamp_defaults",
    "training_260804_workbook",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
