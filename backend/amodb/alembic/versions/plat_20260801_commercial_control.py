"""canonical commercial control plane

Revision ID: plat_20260801_commercial_v2
Revises: saas_20260731_route_latency_hist
Create Date: 2026-08-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "plat_20260801_commercial_v2"
down_revision: Union[str, Sequence[str], None] = "saas_20260731_route_latency_hist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _id():
    return sa.Column("id", sa.String(36), primary_key=True)


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    ]


def upgrade() -> None:
    if not _has("platform_commercial_modules"):
        op.create_table(
            "platform_commercial_modules", _id(),
            sa.Column("code", sa.String(64), nullable=False), sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text()), sa.Column("category", sa.String(64), nullable=False, server_default="GENERAL"),
            sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
            sa.Column("sellable", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("trial_eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("route_prefix", sa.String(255)),
            sa.Column("dependencies_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("features_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("default_limits_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            *_timestamps(), sa.UniqueConstraint("code", name="uq_platform_commercial_module_code"),
        )
        op.create_index("ix_platform_commercial_module_status", "platform_commercial_modules", ["status", "category"])

    if not _has("platform_product_plans"):
        op.create_table(
            "platform_product_plans", _id(), sa.Column("code", sa.String(64), nullable=False),
            sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text()),
            sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("default_billing_term", sa.String(32), nullable=False, server_default="MONTHLY"),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            *_timestamps(), sa.UniqueConstraint("code", name="uq_platform_product_plan_code"),
        )
        op.create_index("ix_platform_product_plan_status", "platform_product_plans", ["status", "is_public"])

    if not _has("platform_product_plan_modules"):
        op.create_table(
            "platform_product_plan_modules", _id(),
            sa.Column("plan_id", sa.String(36), sa.ForeignKey("platform_product_plans.id", ondelete="CASCADE"), nullable=False),
            sa.Column("module_id", sa.String(36), sa.ForeignKey("platform_commercial_modules.id", ondelete="CASCADE"), nullable=False),
            sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("limits_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("feature_overrides_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"), *_timestamps(),
            sa.UniqueConstraint("plan_id", "module_id", name="uq_platform_plan_module"),
        )
        op.create_index("ix_platform_plan_module_plan", "platform_product_plan_modules", ["plan_id", "sort_order"])

    if not _has("platform_price_books"):
        op.create_table(
            "platform_price_books", _id(), sa.Column("code", sa.String(64), nullable=False),
            sa.Column("name", sa.String(255), nullable=False), sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
            sa.Column("market", sa.String(64)), sa.Column("data_mode", sa.String(16), nullable=False, server_default="REAL"),
            sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
            sa.Column("tax_inclusive", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), *_timestamps(),
            sa.UniqueConstraint("code", name="uq_platform_price_book_code"),
            sa.CheckConstraint("data_mode IN ('REAL','DEMO')", name="ck_platform_price_book_data_mode"),
        )
        op.create_index("ix_platform_price_book_scope", "platform_price_books", ["status", "currency", "data_mode"])

    if not _has("platform_price_book_entries"):
        op.create_table(
            "platform_price_book_entries", _id(),
            sa.Column("price_book_id", sa.String(36), sa.ForeignKey("platform_price_books.id", ondelete="CASCADE"), nullable=False),
            sa.Column("plan_id", sa.String(36), sa.ForeignKey("platform_product_plans.id", ondelete="CASCADE")),
            sa.Column("module_id", sa.String(36), sa.ForeignKey("platform_commercial_modules.id", ondelete="CASCADE")),
            sa.Column("billing_term", sa.String(32), nullable=False, server_default="MONTHLY"),
            sa.Column("unit_amount_cents", sa.Integer(), nullable=False), sa.Column("included_quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("overage_amount_cents", sa.Integer()), sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tax_rate_bps", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
            sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("effective_to", sa.DateTime(timezone=True)), sa.Column("external_product_ref", sa.String(255)),
            sa.Column("external_price_ref", sa.String(255)), sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), *_timestamps(),
            sa.UniqueConstraint("price_book_id", "plan_id", "module_id", "billing_term", "effective_from", name="uq_platform_price_book_entry_version"),
            sa.CheckConstraint("plan_id IS NOT NULL OR module_id IS NOT NULL", name="ck_platform_price_target"),
        )
        op.create_index("ix_platform_price_entry_active", "platform_price_book_entries", ["status", "effective_from", "effective_to"])
        op.create_index("ix_platform_price_entry_lookup", "platform_price_book_entries", ["price_book_id", "plan_id", "module_id", "billing_term"])

    if not _has("platform_tenant_subscriptions"):
        op.create_table(
            "platform_tenant_subscriptions", _id(),
            sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("plan_id", sa.String(36), sa.ForeignKey("platform_product_plans.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("price_book_id", sa.String(36), sa.ForeignKey("platform_price_books.id", ondelete="RESTRICT")),
            sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
            sa.Column("billing_term", sa.String(32), nullable=False, server_default="MONTHLY"),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"), sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
            sa.Column("provider", sa.String(64)), sa.Column("external_customer_ref", sa.String(255)), sa.Column("external_subscription_ref", sa.String(255)),
            sa.Column("auto_collection", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("current_period_start", sa.DateTime(timezone=True)), sa.Column("current_period_end", sa.DateTime(timezone=True)),
            sa.Column("trial_ends_at", sa.DateTime(timezone=True)), sa.Column("cancelled_at", sa.DateTime(timezone=True)),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), *_timestamps(),
        )
        op.create_index("ix_platform_tenant_subscription_tenant", "platform_tenant_subscriptions", ["tenant_id", "status", "created_at"])
        op.create_index("ix_platform_tenant_subscription_period", "platform_tenant_subscriptions", ["status", "current_period_end"])

    if not _has("platform_subscription_items"):
        op.create_table(
            "platform_subscription_items", _id(),
            sa.Column("subscription_id", sa.String(36), sa.ForeignKey("platform_tenant_subscriptions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("module_id", sa.String(36), sa.ForeignKey("platform_commercial_modules.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("price_entry_id", sa.String(36), sa.ForeignKey("platform_price_book_entries.id", ondelete="RESTRICT")),
            sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"), sa.Column("unit_amount_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("limits_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("effective_to", sa.DateTime(timezone=True)), *_timestamps(),
            sa.UniqueConstraint("subscription_id", "module_id", name="uq_platform_subscription_item_module"),
        )
        op.create_index("ix_platform_subscription_item_subscription", "platform_subscription_items", ["subscription_id", "status"])

    if not _has("platform_entitlement_overrides"):
        op.create_table(
            "platform_entitlement_overrides", _id(),
            sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("module_id", sa.String(36), sa.ForeignKey("platform_commercial_modules.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
            sa.Column("access_state", sa.String(32), nullable=False, server_default="ENABLED"),
            sa.Column("limits_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), *_timestamps(),
        )
        op.create_index("ix_platform_entitlement_override_tenant", "platform_entitlement_overrides", ["tenant_id", "status", "expires_at"])
        op.create_index("ix_platform_entitlement_override_module", "platform_entitlement_overrides", ["module_id", "status"])

    if not _has("platform_subscription_events"):
        op.create_table(
            "platform_subscription_events", _id(),
            sa.Column("subscription_id", sa.String(36), sa.ForeignKey("platform_tenant_subscriptions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_type", sa.String(96), nullable=False),
            sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("reason", sa.Text()), sa.Column("before_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("after_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_platform_subscription_event_subscription", "platform_subscription_events", ["subscription_id", "created_at"])

    if not _has("platform_payment_transactions"):
        op.create_table(
            "platform_payment_transactions", _id(),
            sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("invoice_id", sa.String(36), sa.ForeignKey("billing_invoices.id", ondelete="SET NULL")),
            sa.Column("provider", sa.String(64), nullable=False, server_default="MANUAL"), sa.Column("external_reference", sa.String(255)),
            sa.Column("status", sa.String(32), nullable=False, server_default="SUCCEEDED"), sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(8), nullable=False, server_default="USD"), sa.Column("payment_method", sa.String(64)),
            sa.Column("notes", sa.Text()), sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("provider", "external_reference", name="uq_platform_payment_provider_reference"),
        )
        op.create_index("ix_platform_payment_transaction_tenant", "platform_payment_transactions", ["tenant_id", "status", "recorded_at"])
        op.create_index("ix_platform_payment_transaction_invoice", "platform_payment_transactions", ["invoice_id", "status"])

    if not _has("platform_invoice_line_items"):
        op.create_table(
            "platform_invoice_line_items", _id(),
            sa.Column("invoice_id", sa.String(36), sa.ForeignKey("billing_invoices.id", ondelete="CASCADE"), nullable=False),
            sa.Column("module_id", sa.String(36), sa.ForeignKey("platform_commercial_modules.id", ondelete="SET NULL")),
            sa.Column("subscription_item_id", sa.String(36), sa.ForeignKey("platform_subscription_items.id", ondelete="SET NULL")),
            sa.Column("description", sa.Text(), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("unit_amount_cents", sa.Integer(), nullable=False), sa.Column("subtotal_cents", sa.Integer(), nullable=False),
            sa.Column("tax_rate_bps", sa.Integer(), nullable=False, server_default="0"), sa.Column("tax_amount_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_cents", sa.Integer(), nullable=False), sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_platform_invoice_line_item_invoice", "platform_invoice_line_items", ["invoice_id", "sort_order"])


def downgrade() -> None:
    for table in [
        "platform_invoice_line_items", "platform_payment_transactions", "platform_subscription_events",
        "platform_entitlement_overrides", "platform_subscription_items", "platform_tenant_subscriptions",
        "platform_price_book_entries", "platform_price_books", "platform_product_plan_modules",
        "platform_product_plans", "platform_commercial_modules",
    ]:
        if _has(table):
            op.drop_table(table)
