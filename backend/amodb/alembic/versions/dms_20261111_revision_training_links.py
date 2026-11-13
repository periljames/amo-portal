"""link published DMS revisions to canonical training requirements

Revision ID: dms_training_link_261111
Revises: quality_process_review_261111
Create Date: 2026-11-11

The link stores exact immutable revision identity and references the existing
Training requirement; it does not duplicate course, enrollment or completion.
"""
from __future__ import annotations

from alembic import op

revision = "dms_training_link_261111"
down_revision = "quality_process_review_261111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS manual_revision_training_links (
            id varchar(36) PRIMARY KEY,
            amo_id varchar(36) NOT NULL REFERENCES amos(id) ON DELETE CASCADE,
            manual_id varchar(36) NOT NULL REFERENCES manuals(id),
            revision_id varchar(36) NOT NULL REFERENCES manual_revisions(id),
            training_requirement_id varchar(36) NOT NULL REFERENCES training_requirements(id),
            immutable_source_sha256 varchar(64) NOT NULL,
            rationale text NOT NULL,
            linked_by_user_id varchar(36) NOT NULL REFERENCES users(id),
            linked_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (amo_id, revision_id, training_requirement_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_manual_revision_training_links_tenant_revision
        ON manual_revision_training_links (amo_id, revision_id, linked_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_manual_revision_training_links_requirement
        ON manual_revision_training_links (amo_id, training_requirement_id)
    """)
    op.execute("ALTER TABLE manual_revision_training_links ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS manual_revision_training_links_tenant ON manual_revision_training_links")
    op.execute("""
        CREATE POLICY manual_revision_training_links_tenant
        ON manual_revision_training_links
        USING (amo_id = current_setting('app.tenant_id', true))
        WITH CHECK (amo_id = current_setting('app.tenant_id', true))
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM manual_revision_training_links LIMIT 1) THEN
            RAISE EXCEPTION 'Retained manual-to-training provenance must be dispositioned before schema downgrade';
          END IF;
        END $$;
    """)
    op.execute("DROP TABLE IF EXISTS manual_revision_training_links")
