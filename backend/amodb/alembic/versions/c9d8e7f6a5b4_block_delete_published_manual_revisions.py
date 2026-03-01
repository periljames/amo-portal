"""block deletion of published manual revisions

Revision ID: c9d8e7f6a5b4
Revises: b1a2e3r4o5d6
Create Date: 2026-03-01
"""

from __future__ import annotations

from alembic import op

revision = "c9d8e7f6a5b4"
down_revision = "b1a2e3r4o5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_published_manual_revision_delete()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.status_enum = 'PUBLISHED' THEN
                RAISE EXCEPTION 'Deleting published manual revisions is not allowed';
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_prevent_published_manual_revision_delete ON manual_revisions;
        CREATE TRIGGER trg_prevent_published_manual_revision_delete
        BEFORE DELETE ON manual_revisions
        FOR EACH ROW
        EXECUTE FUNCTION prevent_published_manual_revision_delete();
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP TRIGGER IF EXISTS trg_prevent_published_manual_revision_delete ON manual_revisions;")
    op.execute("DROP FUNCTION IF EXISTS prevent_published_manual_revision_delete();")
