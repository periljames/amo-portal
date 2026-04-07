"""hard drop post-cutover legacy tables after retention approval

Revision ID: d9e2f3a4b5c6
Revises: c8d1e2f3a4b5
Create Date: 2026-04-07 00:05:00.000000
"""
from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa

revision = "d9e2f3a4b5c6"
down_revision = "c8d1e2f3a4b5"
branch_labels = None
depends_on = None


DROP_TABLES = (
    "technical_aircraft_utilisation_legacy",
    "qms_corrective_actions_legacy",
    "maintenance_statuses_legacy",
    "maintenance_program_items_legacy",
)


REQUIRED_ENV_FLAGS = (
    "AMO_ALLOW_HARD_DROP_LEGACY",
    "AMO_RETENTION_APPROVED",
    "AMO_CUTOVER_GATES_PASSED",
)


def _assert_hard_drop_gates() -> None:
    missing = [flag for flag in REQUIRED_ENV_FLAGS if os.getenv(flag) != "1"]
    if missing:
        missing_csv = ", ".join(missing)
        print(
            "Hard-drop migration skipped (no-op). Missing required env flags: "
            f"{missing_csv}. "
            "Expected preconditions: runtime verification passed, hidden-writer audit complete, "
            "dual-write completed, parity thresholds met for 2 cycles, rollback path retired, "
            "retention/compliance sign-off recorded."
        )
        return


def _drop_if_exists(table_name: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table(table_name):
        op.drop_table(table_name)


def upgrade() -> None:
    missing = [flag for flag in REQUIRED_ENV_FLAGS if os.getenv(flag) != "1"]
    if missing:
        _assert_hard_drop_gates()
        return
    for table_name in DROP_TABLES:
        _drop_if_exists(table_name)


def downgrade() -> None:
    raise RuntimeError(
        "Irreversible migration: hard-dropped legacy tables cannot be restored automatically. "
        "Restore from backups/export artifacts if rollback is required."
    )
