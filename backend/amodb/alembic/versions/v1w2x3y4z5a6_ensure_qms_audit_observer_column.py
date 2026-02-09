"""Ensure observer auditor user id exists on qms_audits.

Revision ID: v1w2x3y4z5a6
Revises: u1v2w3x4y5z6
Create Date: 2025-02-01 12:00:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "v1w2x3y4z5a6"
down_revision = "u1v2w3x4y5z6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE qms_audits
        ADD COLUMN IF NOT EXISTS observer_auditor_user_id VARCHAR(36);
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                WHERE tc.constraint_name = 'fk_qms_audits_observer_auditor_user_id_users'
            ) THEN
                ALTER TABLE qms_audits
                ADD CONSTRAINT fk_qms_audits_observer_auditor_user_id_users
                FOREIGN KEY (observer_auditor_user_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                WHERE tc.constraint_name = 'fk_qms_audits_observer_auditor_user_id_users'
            ) THEN
                ALTER TABLE qms_audits
                DROP CONSTRAINT fk_qms_audits_observer_auditor_user_id_users;
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        ALTER TABLE qms_audits
        DROP COLUMN IF EXISTS observer_auditor_user_id;
        """
    )
