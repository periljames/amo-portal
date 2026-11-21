"""add attributable, tenant-isolated process performance review evidence

Revision ID: quality_process_review_261111
Revises: docctl_261009_favorites
Create Date: 2026-11-11

Process definition and objectives retain their canonical QMS table ownership.
The new table stores only periodic measurements and human verification; it does
not replace qms_processes, qms_quality_objectives, change-control or QMS tasks.
"""
from __future__ import annotations

from alembic import op

revision = "quality_process_review_261111"
down_revision = "docctl_261009_favorites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS qms_process_performance_reviews (
            id varchar(36) PRIMARY KEY,
            amo_id varchar(36) NOT NULL REFERENCES amos(id) ON DELETE CASCADE,
            process_id varchar(36) NOT NULL REFERENCES qms_processes(id) ON DELETE CASCADE,
            owner_user_id varchar(36) NOT NULL REFERENCES users(id),
            period_start date NOT NULL,
            period_end date NOT NULL,
            status varchar(32) NOT NULL DEFAULT 'PENDING_VERIFICATION'
                CHECK (status IN ('PENDING_VERIFICATION','VERIFIED','REWORK')),
            measurements jsonb NOT NULL,
            evidence_ids jsonb NOT NULL,
            owner_reason text NOT NULL,
            verification_evidence_ids jsonb,
            reviewed_by varchar(36) REFERENCES users(id),
            review_reason text,
            reviewed_at timestamptz,
            created_by varchar(36) NOT NULL REFERENCES users(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT qms_process_performance_review_dates
                CHECK (period_end >= period_start)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_qms_process_reviews_tenant_process_period
        ON qms_process_performance_reviews (amo_id, process_id, period_start DESC, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_qms_process_reviews_pending
        ON qms_process_performance_reviews (amo_id, status, created_at DESC)
    """)
    op.execute("ALTER TABLE qms_process_performance_reviews ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS qms_process_performance_reviews_tenant ON qms_process_performance_reviews")
    op.execute("""
        CREATE POLICY qms_process_performance_reviews_tenant
        ON qms_process_performance_reviews
        USING (amo_id = current_setting('app.tenant_id', true))
        WITH CHECK (amo_id = current_setting('app.tenant_id', true))
    """)


def downgrade() -> None:
    # Prevent silently deleting retained management-system review evidence.
    op.execute("""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM qms_process_performance_reviews LIMIT 1) THEN
            RAISE EXCEPTION 'Archive and formally authorise disposition of QMS process review evidence before downgrade';
          END IF;
        END $$;
    """)
    op.execute("DROP TABLE IF EXISTS qms_process_performance_reviews")
