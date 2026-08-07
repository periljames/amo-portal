"""add atomic induction, immutable lineage and source-backed content packs

Revision ID: aircraft_arch_20260806_u5_u6
Revises: aircraft_arch_20260805_daily_utilisation, rel_20260805_ops_exact_counts
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

from amodb.alembic_helpers.aircraft_u5 import downgrade_u5, upgrade_u5
from amodb.alembic_helpers.aircraft_u6 import downgrade_u6, upgrade_u6
from amodb.alembic_helpers.aircraft_utilisation_guards import (
    downgrade_guards,
    upgrade_guards,
)

revision: str = "aircraft_arch_20260806_u5_u6"
down_revision: Union[str, Sequence[str], None] = (
    "aircraft_arch_20260805_daily_utilisation",
    "rel_20260805_ops_exact_counts",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    upgrade_u5()
    upgrade_u6()
    upgrade_guards()


def downgrade() -> None:
    downgrade_guards()
    downgrade_u6()
    downgrade_u5()
