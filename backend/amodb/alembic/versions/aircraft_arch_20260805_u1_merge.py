"""stabilize aircraft architecture catalogue lineage

Revision ID: aircraft_arch_20260805_u1_merge
Revises: aircraft_arch_20260805_u1_catalogue
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "aircraft_arch_20260805_u1_merge"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260805_u1_catalogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
