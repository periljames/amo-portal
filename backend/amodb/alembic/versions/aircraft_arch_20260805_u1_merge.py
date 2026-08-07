"""merge aircraft catalogue and training workbook heads

Revision ID: aircraft_arch_20260805_u1_merge
Revises: aircraft_arch_20260805_u1_catalogue, training_260804_workbook
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "aircraft_arch_20260805_u1_merge"
down_revision: Union[str, Sequence[str], None] = (
    "aircraft_arch_20260805_u1_catalogue",
    "training_260804_workbook",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
