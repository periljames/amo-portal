"""Support active audit pages and tenant annual finding events.

Revision ID: quality_260913_assurance_idx
Revises: accounts_260907_access_profiles
"""
from alembic import op
import sqlalchemy as sa

revision = "quality_260913_assurance_idx"
down_revision = "accounts_260907_access_profiles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_qms_audits_active_page", "qms_audits",
                    ["amo_id", "domain", "planned_start", "id"],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("ix_qms_findings_amo_created", "qms_audit_findings", ["amo_id", "created_at"])


def downgrade():
    op.drop_index("ix_qms_findings_amo_created", table_name="qms_audit_findings")
    op.drop_index("ix_qms_audits_active_page", table_name="qms_audits")
