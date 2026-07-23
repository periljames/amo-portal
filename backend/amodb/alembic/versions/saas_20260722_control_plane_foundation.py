"""add durable SaaS control plane, billing providers, queue and support desk

Revision ID: saas_20260722_control_plane
Revises: quality_20260722_schema_integrity
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "saas_20260722_control_plane"
down_revision = "quality_20260722_schema_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saas_provider_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="GENERAL"),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="NOT_CONFIGURED"),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("encrypted_secret", sa.Text(), nullable=True),
        sa.Column("secret_fingerprint", sa.String(length=32), nullable=True),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_health_detail", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_saas_provider_credentials"),
        sa.UniqueConstraint("provider", "tenant_id", name="uq_saas_provider_scope"),
    )
    op.create_index("ix_saas_provider_status", "saas_provider_credentials", ["provider", "status"])
    op.create_index("ix_saas_provider_tenant", "saas_provider_credentials", ["tenant_id", "provider"])
    # UniqueConstraint permits multiple NULL tenant_id rows in PostgreSQL. This
    # expression index enforces one global configuration per provider.
    op.execute(
        "CREATE UNIQUE INDEX uq_saas_provider_global_scope "
        "ON saas_provider_credentials (provider) WHERE tenant_id IS NULL"
    )

    op.create_table(
        "saas_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("queue_name", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("job_type", sa.String(length=96), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("tenant_scope", sa.String(length=36), nullable=False, server_default="__platform__"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("correlation_id", sa.String(length=96), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_saas_jobs"),
        sa.UniqueConstraint("job_type", "tenant_scope", "idempotency_key", name="uq_saas_job_idempotency"),
        sa.CheckConstraint("priority >= 0 AND priority <= 1000", name="ck_saas_jobs_priority"),
        sa.CheckConstraint("attempt_count >= 0 AND max_attempts >= 1", name="ck_saas_jobs_attempts"),
    )
    op.create_index("ix_saas_jobs_claim", "saas_jobs", ["queue_name", "status", "available_at", "priority"])
    op.create_index("ix_saas_jobs_lease", "saas_jobs", ["status", "lease_expires_at"])
    op.create_index("ix_saas_jobs_tenant", "saas_jobs", ["tenant_id", "status", "created_at"])
    op.create_index("ix_saas_jobs_correlation", "saas_jobs", ["correlation_id"])

    op.create_table(
        "saas_job_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("data_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["saas_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_saas_job_events"),
    )
    op.create_index("ix_saas_job_events_job", "saas_job_events", ["job_id", "created_at"])

    op.create_table(
        "saas_module_prices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("module_code", sa.String(length=64), nullable=False),
        sa.Column("plan_code", sa.String(length=64), nullable=False, server_default="STANDARD"),
        sa.Column("billing_term", sa.String(length=32), nullable=False, server_default="MONTHLY"),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tax_rate_bps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("external_price_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_saas_module_prices"),
        sa.UniqueConstraint("module_code", "plan_code", "billing_term", "currency", name="uq_saas_module_price"),
        sa.CheckConstraint("amount_cents >= 0", name="ck_saas_module_price_amount"),
        sa.CheckConstraint("trial_days >= 0 AND trial_days <= 365", name="ck_saas_module_price_trial"),
        sa.CheckConstraint("tax_rate_bps >= 0 AND tax_rate_bps <= 10000", name="ck_saas_module_price_tax"),
    )
    op.create_index("ix_saas_module_prices_active", "saas_module_prices", ["is_active", "module_code", "billing_term"])

    op.create_table(
        "saas_billing_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="NOT_CONFIGURED"),
        sa.Column("external_customer_ref", sa.String(length=255), nullable=True),
        sa.Column("external_subscription_ref", sa.String(length=255), nullable=True),
        sa.Column("auto_collection", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_saas_billing_accounts"),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_saas_billing_account_provider"),
    )
    op.create_index("ix_saas_billing_account_status", "saas_billing_accounts", ["provider", "status"])
    op.create_index("ix_saas_billing_customer", "saas_billing_accounts", ["external_customer_ref"])
    op.create_index("ix_saas_billing_subscription", "saas_billing_accounts", ["external_subscription_ref"])

    op.create_table(
        "saas_invoice_fiscalizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("invoice_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="ETIMS_OSCU"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("fiscal_document_number", sa.String(length=255), nullable=True),
        sa.Column("control_unit_serial", sa.String(length=255), nullable=True),
        sa.Column("receipt_signature", sa.Text(), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fiscalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_saas_invoice_fiscalizations"),
        sa.UniqueConstraint("invoice_id", name="uq_saas_invoice_fiscalization_invoice"),
    )
    op.create_index("ix_saas_fiscalization_status", "saas_invoice_fiscalizations", ["status", "created_at"])

    op.create_table(
        "saas_support_ticket_details",
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("requester_user_id", sa.String(length=36), nullable=True),
        sa.Column("requester_email", sa.String(length=255), nullable=True),
        sa.Column("assignee_user_id", sa.String(length=36), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="GENERAL"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["ticket_id"], ["platform_support_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("ticket_id", name="pk_saas_support_ticket_details"),
    )
    op.create_index("ix_saas_support_detail_requester", "saas_support_ticket_details", ["requester_user_id"])
    op.create_index("ix_saas_support_detail_assignee", "saas_support_ticket_details", ["assignee_user_id"])
    op.create_index("ix_saas_support_detail_sla", "saas_support_ticket_details", ["sla_due_at"])

    op.create_table(
        "saas_support_ticket_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), nullable=True),
        sa.Column("author_type", sa.String(length=32), nullable=False, server_default="USER"),
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default="PUBLIC"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["ticket_id"], ["platform_support_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_saas_support_ticket_messages"),
    )
    op.create_index("ix_saas_support_message_ticket", "saas_support_ticket_messages", ["ticket_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_saas_support_message_ticket", table_name="saas_support_ticket_messages")
    op.drop_table("saas_support_ticket_messages")
    op.drop_index("ix_saas_support_detail_sla", table_name="saas_support_ticket_details")
    op.drop_index("ix_saas_support_detail_assignee", table_name="saas_support_ticket_details")
    op.drop_index("ix_saas_support_detail_requester", table_name="saas_support_ticket_details")
    op.drop_table("saas_support_ticket_details")
    op.drop_index("ix_saas_fiscalization_status", table_name="saas_invoice_fiscalizations")
    op.drop_table("saas_invoice_fiscalizations")
    op.drop_index("ix_saas_billing_subscription", table_name="saas_billing_accounts")
    op.drop_index("ix_saas_billing_customer", table_name="saas_billing_accounts")
    op.drop_index("ix_saas_billing_account_status", table_name="saas_billing_accounts")
    op.drop_table("saas_billing_accounts")
    op.drop_index("ix_saas_module_prices_active", table_name="saas_module_prices")
    op.drop_table("saas_module_prices")
    op.drop_index("ix_saas_job_events_job", table_name="saas_job_events")
    op.drop_table("saas_job_events")
    op.drop_index("ix_saas_jobs_correlation", table_name="saas_jobs")
    op.drop_index("ix_saas_jobs_tenant", table_name="saas_jobs")
    op.drop_index("ix_saas_jobs_lease", table_name="saas_jobs")
    op.drop_index("ix_saas_jobs_claim", table_name="saas_jobs")
    op.drop_table("saas_jobs")
    op.execute("DROP INDEX IF EXISTS uq_saas_provider_global_scope")
    op.drop_index("ix_saas_provider_tenant", table_name="saas_provider_credentials")
    op.drop_index("ix_saas_provider_status", table_name="saas_provider_credentials")
    op.drop_table("saas_provider_credentials")
