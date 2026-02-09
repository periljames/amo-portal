"""Ensure assistant auditor user id exists on qms_audits.

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2026-03-12 09:00:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "w2x3y4z5a6b7"
down_revision = "v1w2x3y4z5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE qms_audits
        ADD COLUMN IF NOT EXISTS assistant_auditor_user_id VARCHAR(36);
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                WHERE tc.constraint_name = 'fk_qms_audits_assistant_auditor_user_id_users'
            ) THEN
                ALTER TABLE qms_audits
                ADD CONSTRAINT fk_qms_audits_assistant_auditor_user_id_users
                FOREIGN KEY (assistant_auditor_user_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_qms_audits_assistant_auditor_user_id
        ON qms_audits (assistant_auditor_user_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_qms_audits_assistant_auditor_user_id;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                WHERE tc.constraint_name = 'fk_qms_audits_assistant_auditor_user_id_users'
            ) THEN
                ALTER TABLE qms_audits
                DROP CONSTRAINT fk_qms_audits_assistant_auditor_user_id_users;
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        ALTER TABLE qms_audits
        DROP COLUMN IF EXISTS assistant_auditor_user_id;
        """
    )
