"""esign phase 2.1 policy trust

Revision ID: p2h1t0r5t9
Revises: g2p2r0v1d3r
Create Date: 2026-03-05 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "p2h1t0r5t9"
down_revision = "g2p2r0v1d3r"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "esign_signature_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("policy_code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("minimum_level", sa.String(length=48), nullable=False, server_default="APPEARANCE_ONLY_ALLOWED"),
        sa.Column("allow_fallback_to_appearance", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("require_provider_health_before_send", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("require_provider_health_before_finalization", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("require_timestamp", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("require_revalidation_on_verify", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("revalidation_ttl_minutes", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_esign_signature_policies_tenant_id", "esign_signature_policies", ["tenant_id"], unique=False)
    op.create_index("uq_esign_signature_policies_tenant_code", "esign_signature_policies", ["tenant_id", "policy_code"], unique=True)

    op.add_column("esign_signature_requests", sa.Column("policy_id", sa.String(length=36), nullable=True))
    op.add_column("esign_signature_requests", sa.Column("achieved_level", sa.String(length=48), nullable=True))
    op.add_column("esign_signature_requests", sa.Column("downgrade_reason_code", sa.String(length=128), nullable=True))
    op.add_column("esign_signature_requests", sa.Column("finalized_with_fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_foreign_key("fk_esign_signature_requests_policy", "esign_signature_requests", "esign_signature_policies", ["policy_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_esign_signature_requests_policy_id", "esign_signature_requests", ["policy_id"], unique=False)

    op.add_column("esign_signed_artifacts", sa.Column("validation_last_result_source", sa.String(length=8), nullable=False, server_default="LIVE"))
    op.add_column("esign_signed_artifacts", sa.Column("validation_error_count", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "esign_policy_overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("override_type", sa.String(length=48), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["esign_signature_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_esign_policy_overrides_tenant_id", "esign_policy_overrides", ["tenant_id"], unique=False)
    op.create_index("ix_esign_policy_overrides_request_id", "esign_policy_overrides", ["request_id"], unique=False)

    op.create_table(
        "esign_evidence_bundles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("bundle_sha256", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("format", sa.String(length=8), nullable=False, server_default="ZIP"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["esign_signature_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["esign_signed_artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_esign_evidence_bundles_tenant_id", "esign_evidence_bundles", ["tenant_id"], unique=False)
    op.create_index("ix_esign_evidence_bundles_request_id", "esign_evidence_bundles", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_esign_evidence_bundles_request_id", table_name="esign_evidence_bundles")
    op.drop_index("ix_esign_evidence_bundles_tenant_id", table_name="esign_evidence_bundles")
    op.drop_table("esign_evidence_bundles")
    op.drop_index("ix_esign_policy_overrides_request_id", table_name="esign_policy_overrides")
    op.drop_index("ix_esign_policy_overrides_tenant_id", table_name="esign_policy_overrides")
    op.drop_table("esign_policy_overrides")
    op.drop_column("esign_signed_artifacts", "validation_error_count")
    op.drop_column("esign_signed_artifacts", "validation_last_result_source")
    op.drop_index("ix_esign_signature_requests_policy_id", table_name="esign_signature_requests")
    op.drop_constraint("fk_esign_signature_requests_policy", "esign_signature_requests", type_="foreignkey")
    op.drop_column("esign_signature_requests", "finalized_with_fallback")
    op.drop_column("esign_signature_requests", "downgrade_reason_code")
    op.drop_column("esign_signature_requests", "achieved_level")
    op.drop_column("esign_signature_requests", "policy_id")
    op.drop_index("uq_esign_signature_policies_tenant_code", table_name="esign_signature_policies")
    op.drop_index("ix_esign_signature_policies_tenant_id", table_name="esign_signature_policies")
    op.drop_table("esign_signature_policies")
