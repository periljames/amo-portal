"""Repair missing CAR responses table for public invite submissions.

Revision ID: qual_20260704_carresp
Revises: qual_20260704_schedfix
Create Date: 2026-07-04
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "qual_20260704_carresp"
down_revision: Union[str, Sequence[str], None] = "qual_20260704_schedfix"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _columns(bind, table_name: str) -> set[str]:
    if not _table_exists(bind, table_name):
        return set()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "quality_car_responses"):
        op.execute(
            sa.text(
                """
                CREATE TABLE IF NOT EXISTS quality_car_responses (
                    id UUID NOT NULL,
                    car_id UUID NOT NULL,
                    containment_action TEXT,
                    root_cause TEXT,
                    corrective_action TEXT,
                    preventive_action TEXT,
                    evidence_ref VARCHAR(512),
                    submitted_by_name VARCHAR(255),
                    submitted_by_email VARCHAR(255),
                    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(32) NOT NULL DEFAULT 'SUBMITTED'
                )
                """
            )
        )

    existing = _columns(bind, "quality_car_responses")
    column_ddls = {
        "id": "UUID",
        "car_id": "UUID",
        "containment_action": "TEXT",
        "root_cause": "TEXT",
        "corrective_action": "TEXT",
        "preventive_action": "TEXT",
        "evidence_ref": "VARCHAR(512)",
        "submitted_by_name": "VARCHAR(255)",
        "submitted_by_email": "VARCHAR(255)",
        "submitted_at": "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
        "status": "VARCHAR(32) DEFAULT 'SUBMITTED'",
    }
    for column_name, ddl in column_ddls.items():
        if column_name not in existing:
            op.execute(sa.text(f"ALTER TABLE quality_car_responses ADD COLUMN IF NOT EXISTS {column_name} {ddl}"))

    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_id_runtime ON quality_car_responses (id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_car_runtime ON quality_car_responses (car_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_submitted_runtime ON quality_car_responses (submitted_at)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_status_runtime ON quality_car_responses (status)"))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_quality_car_responses_status_runtime"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_quality_car_responses_submitted_runtime"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_quality_car_responses_car_runtime"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_quality_car_responses_id_runtime"))
    # Do not drop quality_car_responses in downgrade: it may contain live CAR submissions.
