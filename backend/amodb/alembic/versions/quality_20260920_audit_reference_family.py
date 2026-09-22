"""Add tenant-configurable audit reference family prefix.

Upgrade: adds quality_tenant_workflow_settings.audit_reference_family (default QAR).
Rollback: drop the column. Existing audits keep their stored reference_family values.
"""
from alembic import op
import sqlalchemy as sa

revision = "quality_260920_audit_ref_family"
down_revision = "quality_260918_people_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("quality_tenant_workflow_settings")}
    if "audit_reference_family" not in columns:
        op.add_column(
            "quality_tenant_workflow_settings",
            sa.Column(
                "audit_reference_family",
                sa.String(length=16),
                nullable=False,
                server_default="QAR",
            ),
        )
        # Keep server_default for backfill only; application model supplies the default.
        if bind.dialect.name == "postgresql":
            op.alter_column(
                "quality_tenant_workflow_settings",
                "audit_reference_family",
                server_default=None,
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("quality_tenant_workflow_settings")}
    if "audit_reference_family" in columns:
        op.drop_column("quality_tenant_workflow_settings", "audit_reference_family")
