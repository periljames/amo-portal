"""repair schedule frequency width and training report settings

Revision ID: qual_20260704_schedfix
Revises: qual_20260628_lvl4
Create Date: 2026-07-04
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "qual_20260704_schedfix"
down_revision: Union[str, Sequence[str], None] = "qual_20260628_lvl4"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if _has_table("qms_audit_schedules"):
        op.execute("ALTER TABLE qms_audit_schedules ALTER COLUMN frequency TYPE VARCHAR(32)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_qms_audit_schedules_frequency ON qms_audit_schedules (frequency)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS training_report_settings (
            id VARCHAR(36) PRIMARY KEY,
            amo_id VARCHAR(36) NOT NULL REFERENCES amos(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL DEFAULT 'Personnel Training Record',
            subtitle TEXT,
            form_no VARCHAR(64) NOT NULL DEFAULT 'QAM/49A',
            issue_date VARCHAR(64) NOT NULL DEFAULT '1 Sept 25',
            revision VARCHAR(32) NOT NULL DEFAULT '00',
            show_compliance_summary BOOLEAN NOT NULL DEFAULT TRUE,
            show_training_history BOOLEAN NOT NULL DEFAULT TRUE,
            show_scheduled_events BOOLEAN NOT NULL DEFAULT TRUE,
            show_deferrals BOOLEAN NOT NULL DEFAULT TRUE,
            footer_note TEXT,
            updated_by_user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_training_report_settings_amo UNIQUE (amo_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_report_settings_amo ON training_report_settings (amo_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_training_report_settings_updated_by_user_id ON training_report_settings (updated_by_user_id)")


def downgrade() -> None:
    # Do not drop tenant report settings or shrink schedule frequency; both are safe forward-only repairs.
    pass
