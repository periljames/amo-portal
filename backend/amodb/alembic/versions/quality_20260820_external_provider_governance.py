"""Add governed external-provider profiles, contracts and evidence.

Revision ID: quality_260820_provider_gov
Revises: quality_260820_wf_schema, training_260820_record_updated
Create Date: 2026-08-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260820_provider_gov"
down_revision = ("quality_260820_wf_schema", "training_260820_record_updated")
branch_labels = None
depends_on = None


_TABLES = (
    "quality_external_provider_profiles",
    "quality_external_provider_contracts",
    "quality_external_provider_evidence",
)


def _enable_rls(table_name: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    policy = f"{table_name}_tenant_isolation"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'DROP POLICY IF EXISTS "{policy}" ON "{table_name}"'))
    op.execute(sa.text(f'''CREATE POLICY "{policy}" ON "{table_name}"
        USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))'''))


def upgrade() -> None:
    op.create_table(
        "quality_external_provider_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("provider_kind", sa.String(length=32), nullable=False, server_default="SUPPLIER"),
        sa.Column("contract_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("oversight_owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("review_interval_days", sa.Integer(), nullable=False, server_default="365"),
        sa.Column("last_reviewed_on", sa.Date(), nullable=True),
        sa.Column("next_review_due_on", sa.Date(), nullable=True),
        sa.Column("scope_summary", sa.Text(), nullable=True),
        sa.Column("quality_requirements", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["procurement_suppliers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["oversight_owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("amo_id", "supplier_id", name="uq_quality_provider_profile_supplier"),
        sa.CheckConstraint(
            "provider_kind IN ('SUPPLIER','CONTRACTOR','SUBCONTRACTOR','SERVICE_PROVIDER','CONSULTANT','LABORATORY','CALIBRATION_PROVIDER','OTHER')",
            name="ck_quality_provider_kind",
        ),
        sa.CheckConstraint(
            "review_interval_days >= 30 AND review_interval_days <= 3650",
            name="ck_quality_provider_review_interval",
        ),
        sa.CheckConstraint("version >= 1", name="ck_quality_provider_profile_version"),
    )
    op.create_index(
        "ix_quality_provider_profiles_due",
        "quality_external_provider_profiles",
        ["amo_id", "next_review_due_on"],
    )

    op.create_table(
        "quality_external_provider_contracts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("contract_number", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"),
        sa.Column("scope_text", sa.Text(), nullable=False),
        sa.Column("effective_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("termination_notice_days", sa.Integer(), nullable=True),
        sa.Column("renewal_terms", sa.Text(), nullable=True),
        sa.Column("controlled_document_id", sa.String(length=64), nullable=True),
        sa.Column("controlled_document_revision", sa.String(length=64), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transition_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["procurement_suppliers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("amo_id", "contract_number", name="uq_quality_provider_contract_number"),
        sa.CheckConstraint(
            "status IN ('DRAFT','ACTIVE','SUSPENDED','EXPIRED','TERMINATED','SUPERSEDED')",
            name="ck_quality_provider_contract_status",
        ),
        sa.CheckConstraint(
            "expires_on IS NULL OR effective_on IS NULL OR expires_on >= effective_on",
            name="ck_quality_provider_contract_dates",
        ),
        sa.CheckConstraint(
            "termination_notice_days IS NULL OR termination_notice_days >= 0",
            name="ck_quality_provider_contract_notice",
        ),
        sa.CheckConstraint("version >= 1", name="ck_quality_provider_contract_version"),
    )
    op.create_index(
        "ix_quality_provider_contracts_supplier",
        "quality_external_provider_contracts",
        ["amo_id", "supplier_id", "status"],
    )
    op.create_index(
        "ix_quality_provider_contracts_expiry",
        "quality_external_provider_contracts",
        ["amo_id", "expires_on"],
    )

    op.create_table(
        "quality_external_provider_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False, server_default="DOCUMENT_CONTROL"),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PENDING"),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("verified_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["procurement_suppliers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_id"], ["quality_external_provider_contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "amo_id", "supplier_id", "source_system", "source_id",
            name="uq_quality_provider_evidence_source",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','VERIFIED','EXPIRED','REJECTED','SUPERSEDED')",
            name="ck_quality_provider_evidence_status",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from",
            name="ck_quality_provider_evidence_dates",
        ),
    )
    op.create_index(
        "ix_quality_provider_evidence_supplier",
        "quality_external_provider_evidence",
        ["amo_id", "supplier_id", "status"],
    )
    op.create_index(
        "ix_quality_provider_evidence_validity",
        "quality_external_provider_evidence",
        ["amo_id", "valid_until"],
    )

    for table_name in _TABLES:
        _enable_rls(table_name)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name in reversed(_TABLES):
            policy = f"{table_name}_tenant_isolation"
            op.execute(sa.text(f'DROP POLICY IF EXISTS "{policy}" ON "{table_name}"'))
            op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))

    op.drop_index("ix_quality_provider_evidence_validity", table_name="quality_external_provider_evidence")
    op.drop_index("ix_quality_provider_evidence_supplier", table_name="quality_external_provider_evidence")
    op.drop_table("quality_external_provider_evidence")
    op.drop_index("ix_quality_provider_contracts_expiry", table_name="quality_external_provider_contracts")
    op.drop_index("ix_quality_provider_contracts_supplier", table_name="quality_external_provider_contracts")
    op.drop_table("quality_external_provider_contracts")
    op.drop_index("ix_quality_provider_profiles_due", table_name="quality_external_provider_profiles")
    op.drop_table("quality_external_provider_profiles")
