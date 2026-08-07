"""complete aircraft import lifecycle controls

Revision ID: aircraft_arch_20260805_u4_import_lifecycle
Revises: aircraft_arch_20260805_u4_programmes
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aircraft_arch_20260805_u4_import_lifecycle"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260805_u4_programmes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("aircraft_import_batches", sa.Column("approved_by_user_id", sa.String(36), nullable=True))
    op.add_column("aircraft_import_batches", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_aircraft_import_batch_approver",
        "aircraft_import_batches",
        "users",
        ["approved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_aircraft_import_global_profile",
        "aircraft_import_mapping_profiles",
        ["code"],
        unique=True,
        postgresql_where=sa.text("scope = 'GLOBAL'"),
    )


def downgrade() -> None:
    op.drop_index("uq_aircraft_import_global_profile", table_name="aircraft_import_mapping_profiles")
    op.drop_constraint("fk_aircraft_import_batch_approver", "aircraft_import_batches", type_="foreignkey")
    op.drop_column("aircraft_import_batches", "approved_at")
    op.drop_column("aircraft_import_batches", "approved_by_user_id")
