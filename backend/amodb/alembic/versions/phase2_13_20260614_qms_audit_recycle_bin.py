"""Add recycle bin support for QMS audit records and schedules.

Revision ID: phase2_13_20260614
Revises: phase2_12_20260607
Create Date: 2026-06-14
"""

from alembic import op


revision = "phase2_13_20260614"
down_revision = "phase2_12_20260607"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE qms_audits ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE qms_audits ADD COLUMN IF NOT EXISTS deleted_by_user_id VARCHAR(36)")
    op.execute("ALTER TABLE qms_audits ADD COLUMN IF NOT EXISTS delete_reason TEXT")
    op.execute("ALTER TABLE qms_audit_schedules ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE qms_audit_schedules ADD COLUMN IF NOT EXISTS deleted_by_user_id VARCHAR(36)")
    op.execute("ALTER TABLE qms_audit_schedules ADD COLUMN IF NOT EXISTS delete_reason TEXT")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_qms_audits_deleted_by_user_id'
            ) THEN
                ALTER TABLE qms_audits
                ADD CONSTRAINT fk_qms_audits_deleted_by_user_id
                FOREIGN KEY (deleted_by_user_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_qms_audit_schedules_deleted_by_user_id'
            ) THEN
                ALTER TABLE qms_audit_schedules
                ADD CONSTRAINT fk_qms_audit_schedules_deleted_by_user_id
                FOREIGN KEY (deleted_by_user_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_qms_audits_deleted_at ON qms_audits (deleted_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_deleted ON qms_audits (amo_id, deleted_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_qms_audit_schedules_deleted_at ON qms_audit_schedules (deleted_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_qms_audit_schedules_amo_deleted ON qms_audit_schedules (amo_id, deleted_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_qms_audit_schedules_amo_deleted")
    op.execute("DROP INDEX IF EXISTS ix_qms_audit_schedules_deleted_at")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_amo_deleted")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_deleted_at")
    op.execute("ALTER TABLE qms_audit_schedules DROP CONSTRAINT IF EXISTS fk_qms_audit_schedules_deleted_by_user_id")
    op.execute("ALTER TABLE qms_audits DROP CONSTRAINT IF EXISTS fk_qms_audits_deleted_by_user_id")
    op.execute("ALTER TABLE qms_audit_schedules DROP COLUMN IF EXISTS delete_reason")
    op.execute("ALTER TABLE qms_audit_schedules DROP COLUMN IF EXISTS deleted_by_user_id")
    op.execute("ALTER TABLE qms_audit_schedules DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE qms_audits DROP COLUMN IF EXISTS delete_reason")
    op.execute("ALTER TABLE qms_audits DROP COLUMN IF EXISTS deleted_by_user_id")
    op.execute("ALTER TABLE qms_audits DROP COLUMN IF EXISTS deleted_at")
