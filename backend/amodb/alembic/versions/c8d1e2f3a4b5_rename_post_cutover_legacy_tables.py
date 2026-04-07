"""rename post-cutover legacy tables to *_legacy

Revision ID: c8d1e2f3a4b5
Revises: aa11bb22cc33, b2c3d4e5f6g7, c1d2e3f4a5b7, d7e6f5a4b3c2, p0a4_training_gate_fields
Create Date: 2026-04-07 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c8d1e2f3a4b5"
down_revision = (
    "aa11bb22cc33",
    "b2c3d4e5f6g7",
    "c1d2e3f4a5b7",
    "d7e6f5a4b3c2",
    "p0a4_training_gate_fields",
)
branch_labels = None
depends_on = None


LEGACY_TABLES = (
    "technical_aircraft_utilisation",
    "qms_corrective_actions",
    "maintenance_program_items",
    "maintenance_statuses",
)


def _rename_if_exists(old_name: str, new_name: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    old_exists = insp.has_table(old_name)
    new_exists = insp.has_table(new_name)

    if old_exists and not new_exists:
        op.rename_table(old_name, new_name)


def _rename_back_if_exists(old_name: str, new_name: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    old_exists = insp.has_table(old_name)
    new_exists = insp.has_table(new_name)

    if old_exists and not new_exists:
        op.rename_table(old_name, new_name)


def upgrade() -> None:
    # Non-destructive first step in post-cutover cleanup.
    # Hard drop is intentionally handled in a separate migration.
    for table_name in LEGACY_TABLES:
        _rename_if_exists(table_name, f"{table_name}_legacy")


def downgrade() -> None:
    # Reversible rollback path: rename *_legacy back to original table names.
    for table_name in LEGACY_TABLES:
        _rename_back_if_exists(f"{table_name}_legacy", table_name)
