from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from amodb.database import Base
from amodb.user_id import generate_user_id


def utcnow() -> datetime:
    return datetime.utcnow()


class CommercialModule(Base):
    __tablename__ = "platform_commercial_modules"
    __table_args__ = (
        UniqueConstraint("code", name="uq_platform_commercial_module_code"),
        Index("ix_platform_commercial_module_status", "status", "category"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    code = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(64), nullable=False, default="GENERAL", index=True)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    sellable = Column(Boolean, nullable=False, default=True)
    trial_eligible = Column(Boolean, nullable=False, default=True)
    route_prefix = Column(String(255), nullable=True)
    dependencies_json = Column(JSON, nullable=False, default=list)
    features_json = Column(JSON, nullable=False, default=list)
    default_limits_json = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class ProductPlan(Base):
    __tablename__ = "platform_product_plans"
    __table_args__ = (
        UniqueConstraint("code", name="uq_platform_product_plan_code"),
        Index("ix_platform_product_plan_status", "status", "is_public"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    code = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    is_public = Column(Boolean, nullable=False, default=False)
    trial_days = Column(Integer, nullable=False, default=0)
    default_billing_term = Column(String(32), nullable=False, default="MONTHLY")
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class ProductPlanModule(Base):
    __tablename__ = "platform_product_plan_modules"
    __table_args__ = (
        UniqueConstraint("plan_id", "module_id", name="uq_platform_plan_module"),
        Index("ix_platform_plan_module_plan", "plan_id", "sort_order"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    plan_id = Column(String(36), ForeignKey("platform_product_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(String(36), ForeignKey("platform_commercial_modules.id", ondelete="CASCADE"), nullable=False, index=True)
    included = Column(Boolean, nullable=False, default=True)
    limits_json = Column(JSON, nullable=False, default=dict)
    feature_overrides_json = Column(JSON, nullable=False, default=dict)
    sort_order = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class PriceBook(Base):
    __tablename__ = "platform_price_books"
    __table_args__ = (
        UniqueConstraint("code", name="uq_platform_price_book_code"),
        Index("ix_platform_price_book_scope", "status", "currency", "data_mode"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    code = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    currency = Column(String(8), nullable=False, default="USD")
    market = Column(String(64), nullable=True)
    data_mode = Column(String(16), nullable=False, default="REAL", index=True)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    tax_inclusive = Column(Boolean, nullable=False, default=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class PriceBookEntry(Base):
    __tablename__ = "platform_price_book_entries"
    __table_args__ = (
        UniqueConstraint(
            "price_book_id", "plan_id", "module_id", "billing_term", "effective_from",
            name="uq_platform_price_book_entry_version",
        ),
        Index("ix_platform_price_entry_active", "status", "effective_from", "effective_to"),
        Index("ix_platform_price_entry_lookup", "price_book_id", "plan_id", "module_id", "billing_term"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    price_book_id = Column(String(36), ForeignKey("platform_price_books.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(String(36), ForeignKey("platform_product_plans.id", ondelete="CASCADE"), nullable=True, index=True)
    module_id = Column(String(36), ForeignKey("platform_commercial_modules.id", ondelete="CASCADE"), nullable=True, index=True)
    billing_term = Column(String(32), nullable=False, default="MONTHLY")
    unit_amount_cents = Column(Integer, nullable=False)
    included_quantity = Column(Integer, nullable=False, default=1)
    overage_amount_cents = Column(Integer, nullable=True)
    trial_days = Column(Integer, nullable=False, default=0)
    tax_rate_bps = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    effective_from = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    effective_to = Column(DateTime(timezone=True), nullable=True)
    external_product_ref = Column(String(255), nullable=True)
    external_price_ref = Column(String(255), nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class TenantSubscription(Base):
    __tablename__ = "platform_tenant_subscriptions"
    __table_args__ = (
        Index("ix_platform_tenant_subscription_tenant", "tenant_id", "status", "created_at"),
        Index("ix_platform_tenant_subscription_period", "status", "current_period_end"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(String(36), ForeignKey("platform_product_plans.id", ondelete="RESTRICT"), nullable=False, index=True)
    price_book_id = Column(String(36), ForeignKey("platform_price_books.id", ondelete="RESTRICT"), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="DRAFT", index=True)
    billing_term = Column(String(32), nullable=False, default="MONTHLY")
    quantity = Column(Integer, nullable=False, default=1)
    currency = Column(String(8), nullable=False, default="USD")
    provider = Column(String(64), nullable=True)
    external_customer_ref = Column(String(255), nullable=True)
    external_subscription_ref = Column(String(255), nullable=True, index=True)
    auto_collection = Column(Boolean, nullable=False, default=False)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SubscriptionItem(Base):
    __tablename__ = "platform_subscription_items"
    __table_args__ = (
        UniqueConstraint("subscription_id", "module_id", name="uq_platform_subscription_item_module"),
        Index("ix_platform_subscription_item_subscription", "subscription_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    subscription_id = Column(String(36), ForeignKey("platform_tenant_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(String(36), ForeignKey("platform_commercial_modules.id", ondelete="RESTRICT"), nullable=False, index=True)
    price_entry_id = Column(String(36), ForeignKey("platform_price_book_entries.id", ondelete="RESTRICT"), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    quantity = Column(Integer, nullable=False, default=1)
    unit_amount_cents = Column(Integer, nullable=False, default=0)
    limits_json = Column(JSON, nullable=False, default=dict)
    effective_from = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    effective_to = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class EntitlementOverride(Base):
    __tablename__ = "platform_entitlement_overrides"
    __table_args__ = (
        Index("ix_platform_entitlement_override_tenant", "tenant_id", "status", "expires_at"),
        Index("ix_platform_entitlement_override_module", "module_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(String(36), ForeignKey("platform_commercial_modules.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    access_state = Column(String(32), nullable=False, default="ENABLED")
    limits_json = Column(JSON, nullable=False, default=dict)
    reason = Column(Text, nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    approved_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SubscriptionEvent(Base):
    __tablename__ = "platform_subscription_events"
    __table_args__ = (Index("ix_platform_subscription_event_subscription", "subscription_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    subscription_id = Column(String(36), ForeignKey("platform_tenant_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(96), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = Column(Text, nullable=True)
    before_json = Column(JSON, nullable=False, default=dict)
    after_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PaymentTransaction(Base):
    __tablename__ = "platform_payment_transactions"
    __table_args__ = (
        UniqueConstraint("provider", "external_reference", name="uq_platform_payment_provider_reference"),
        Index("ix_platform_payment_transaction_tenant", "tenant_id", "status", "recorded_at"),
        Index("ix_platform_payment_transaction_invoice", "invoice_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id = Column(String(36), ForeignKey("billing_invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(64), nullable=False, default="MANUAL")
    external_reference = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="SUCCEEDED", index=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(8), nullable=False, default="USD")
    payment_method = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    recorded_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class InvoiceLineItem(Base):
    __tablename__ = "platform_invoice_line_items"
    __table_args__ = (Index("ix_platform_invoice_line_item_invoice", "invoice_id", "sort_order"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    invoice_id = Column(String(36), ForeignKey("billing_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(String(36), ForeignKey("platform_commercial_modules.id", ondelete="SET NULL"), nullable=True, index=True)
    subscription_item_id = Column(String(36), ForeignKey("platform_subscription_items.id", ondelete="SET NULL"), nullable=True)
    description = Column(Text, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_amount_cents = Column(Integer, nullable=False)
    subtotal_cents = Column(Integer, nullable=False)
    tax_rate_bps = Column(Integer, nullable=False, default=0)
    tax_amount_cents = Column(Integer, nullable=False, default=0)
    total_cents = Column(Integer, nullable=False)
    sort_order = Column(Integer, nullable=False, default=100)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
