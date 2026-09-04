"""Add the Quality Officer role and Authority submission attestations.

Revision ID: quality_260903_officer_ae
Revises: quality_260902_qms13_gate
Create Date: 2026-09-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260903_officer_ae"
down_revision = "quality_260902_qms13_gate"
branch_labels = None
depends_on = None


TABLE = "quality_authority_submission_attestations"
TENANT_POLICY = "quality_authority_submission_attestations_tenant_isolation"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'QUALITY_OFFICER'")

    constraints: list[sa.SchemaItem] = [
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["report_revision_id"],
            ["quality_audit_report_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["attested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    ]
    if bind.dialect.name != "postgresql":
        constraints.append(
            sa.UniqueConstraint(
                "amo_id",
                "audit_id",
                "report_revision_id",
                name="uq_quality_authority_attestation_current",
            )
        )

    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("report_revision_id", sa.String(length=36), nullable=False),
        sa.Column("report_sha256", sa.String(length=64), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("attested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pack_filename", sa.String(length=255), nullable=True),
        sa.Column("pack_content_type", sa.String(length=128), nullable=True),
        sa.Column("pack_size_bytes", sa.Integer(), nullable=True),
        sa.Column("pack_sha256", sa.String(length=64), nullable=True),
        sa.Column("pack_storage_ref", sa.String(length=1024), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        *constraints,
    )
    op.create_index(
        "ix_quality_authority_attestation_audit",
        TABLE,
        ["amo_id", "audit_id"],
    )
    if bind.dialect.name == "postgresql":
        op.create_index(
            "uq_quality_authority_attestation_current",
            TABLE,
            ["amo_id", "audit_id", "report_revision_id"],
            unique=True,
            postgresql_where=sa.text("superseded_at IS NULL"),
        )
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'''
            CREATE POLICY "{TENANT_POLICY}" ON "{TABLE}"
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        '''))


def downgrade() -> None:
    op.drop_table(TABLE)
