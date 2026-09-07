"""Add tenant AI plans and immutable usage accounting.

Revision ID: ai_260904_foundation
Revises: quality_260904_dms_memory
Create Date: 2026-09-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "ai_260904_foundation"
down_revision = "quality_260904_dms_memory"
branch_labels = None
depends_on = None


SETTINGS_TABLE = "tenant_ai_settings"
USAGE_TABLE = "ai_usage_records"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_settings_rls() -> None:
    op.execute(sa.text(f'ALTER TABLE "{SETTINGS_TABLE}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{SETTINGS_TABLE}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"""
        CREATE POLICY {SETTINGS_TABLE}_tenant_access ON "{SETTINGS_TABLE}"
        USING (tenant_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (tenant_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
    """))


def _enable_usage_rls() -> None:
    op.execute(sa.text(f'ALTER TABLE "{USAGE_TABLE}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{USAGE_TABLE}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"""
        CREATE POLICY {USAGE_TABLE}_tenant_select ON "{USAGE_TABLE}"
        FOR SELECT
        USING (tenant_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
    """))
    op.execute(sa.text(f"""
        CREATE POLICY {USAGE_TABLE}_tenant_insert ON "{USAGE_TABLE}"
        FOR INSERT
        WITH CHECK (tenant_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
    """))


def upgrade() -> None:
    op.create_table(
        SETTINGS_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("provider", sa.String(length=32), server_default="openai", nullable=False),
        sa.Column("default_model", sa.String(length=96), server_default="gpt-5-mini", nullable=False),
        sa.Column("lightweight_model", sa.String(length=96), server_default="gpt-5-nano", nullable=False),
        sa.Column("embedding_model", sa.String(length=96), server_default="text-embedding-3-small", nullable=False),
        sa.Column("plan_type", sa.String(length=32), server_default="DEVELOPMENT", nullable=False),
        sa.Column("monthly_token_allowance", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("monthly_request_allowance", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_input_tokens_per_request", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_output_tokens_per_request", sa.Integer(), server_default="0", nullable=False),
        sa.Column("usage_limits_json", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("enabled_features_json", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("allow_external_document_context", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("monthly_token_allowance >= 0", name="ck_tenant_ai_monthly_tokens_nonnegative"),
        sa.CheckConstraint("monthly_request_allowance >= 0", name="ck_tenant_ai_monthly_requests_nonnegative"),
        sa.CheckConstraint("max_input_tokens_per_request >= 0", name="ck_tenant_ai_input_limit_nonnegative"),
        sa.CheckConstraint("max_output_tokens_per_request >= 0", name="ck_tenant_ai_output_limit_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_ai_settings_tenant"),
    )
    op.create_index("ix_tenant_ai_settings_tenant_id", SETTINGS_TABLE, ["tenant_id"])
    op.create_index("ix_tenant_ai_settings_enabled_plan", SETTINGS_TABLE, ["enabled", "plan_type"])

    op.create_table(
        USAGE_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=96), nullable=False),
        sa.Column("feature", sa.String(length=96), nullable=False),
        sa.Column("operation_type", sa.String(length=24), server_default="COMPLETION", nullable=False),
        sa.Column("request_id", sa.String(length=96), nullable=False),
        sa.Column("provider_response_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="SUCCEEDED", nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=18, scale=8), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=96), nullable=True),
        sa.Column("document_id", sa.String(length=96), nullable=True),
        sa.Column("document_revision_id", sa.String(length=96), nullable=True),
        sa.Column("workflow_type", sa.String(length=96), nullable=True),
        sa.Column("workflow_id", sa.String(length=96), nullable=True),
        sa.Column("context_json", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("input_tokens >= 0", name="ck_ai_usage_input_tokens_nonnegative"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_ai_usage_output_tokens_nonnegative"),
        sa.CheckConstraint("total_tokens >= 0", name="ck_ai_usage_total_tokens_nonnegative"),
        sa.CheckConstraint("estimated_cost_usd >= 0", name="ck_ai_usage_cost_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_records_tenant_id", USAGE_TABLE, ["tenant_id"])
    op.create_index("ix_ai_usage_records_user_id", USAGE_TABLE, ["user_id"])
    op.create_index("ix_ai_usage_records_feature", USAGE_TABLE, ["feature"])
    op.create_index("ix_ai_usage_records_status", USAGE_TABLE, ["status"])
    op.create_index("ix_ai_usage_records_created_at", USAGE_TABLE, ["created_at"])
    op.create_index("ix_ai_usage_tenant_period", USAGE_TABLE, ["tenant_id", "created_at"])
    op.create_index("ix_ai_usage_tenant_feature", USAGE_TABLE, ["tenant_id", "feature", "created_at"])
    op.create_index("ix_ai_usage_request", USAGE_TABLE, ["tenant_id", "request_id"])
    op.create_index("ix_ai_usage_user", USAGE_TABLE, ["tenant_id", "user_id", "created_at"])

    if _is_postgresql():
        _enable_settings_rls()
        _enable_usage_rls()


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(f"DROP POLICY IF EXISTS {USAGE_TABLE}_tenant_insert ON \"{USAGE_TABLE}\""))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {USAGE_TABLE}_tenant_select ON \"{USAGE_TABLE}\""))
        op.execute(sa.text(f'ALTER TABLE "{USAGE_TABLE}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{USAGE_TABLE}" DISABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {SETTINGS_TABLE}_tenant_access ON \"{SETTINGS_TABLE}\""))
        op.execute(sa.text(f'ALTER TABLE "{SETTINGS_TABLE}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{SETTINGS_TABLE}" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_ai_usage_user", table_name=USAGE_TABLE)
    op.drop_index("ix_ai_usage_request", table_name=USAGE_TABLE)
    op.drop_index("ix_ai_usage_tenant_feature", table_name=USAGE_TABLE)
    op.drop_index("ix_ai_usage_tenant_period", table_name=USAGE_TABLE)
    op.drop_index("ix_ai_usage_records_created_at", table_name=USAGE_TABLE)
    op.drop_index("ix_ai_usage_records_status", table_name=USAGE_TABLE)
    op.drop_index("ix_ai_usage_records_feature", table_name=USAGE_TABLE)
    op.drop_index("ix_ai_usage_records_user_id", table_name=USAGE_TABLE)
    op.drop_index("ix_ai_usage_records_tenant_id", table_name=USAGE_TABLE)
    op.drop_table(USAGE_TABLE)
    op.drop_index("ix_tenant_ai_settings_enabled_plan", table_name=SETTINGS_TABLE)
    op.drop_index("ix_tenant_ai_settings_tenant_id", table_name=SETTINGS_TABLE)
    op.drop_table(SETTINGS_TABLE)
