"""add auditee_email to qms_audits

Revision ID: u1v2w3x4y5z6
Revises: t1u2v3w4x5y6
Create Date: 2025-02-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "u1v2w3x4y5z6"
down_revision = "t1u2v3w4x5y6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("qms_audits", sa.Column("auditee_email", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("qms_audits", "auditee_email")
