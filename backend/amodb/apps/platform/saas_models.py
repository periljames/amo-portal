from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from amodb.database import Base
from amodb.user_id import generate_user_id


def utcnow() -> datetime:
    return datetime.utcnow()


class SaaSProviderCredential(Base):
    """Encrypted, scoped provider configuration.

    Secret values are encrypted by :mod:`saas_secrets` before persistence. API
    responses must expose only ``secret_fingerprint`` and ``has_secret``.
    """

    __tablename__ = "saas_provider_credentials"
    __table_args__ = (
        UniqueConstraint("provider", "tenant_id", name="uq_saas_provider_scope"),
        Index("ix_saas_provider_status", "provider", "status"),
        Index("ix_saas_provider_tenant", "tenant_id", "provider"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    provider = Column(String(64), nullable=False, index=True)
    category = Column(String(32), nullable=False, default="GENERAL", index=True)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=True, index=True)
    display_name = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="NOT_CONFIGURED", index=True)
    config_json = Column(JSON, nullable=False, default=dict)
    encrypted_secret = Column(Text, nullable=True)
    secret_fingerprint = Column(String(32), nullable=True)
    configured_at = Column(DateTime(timezone=True), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_latency_ms = Column(Integer, nullable=True)
    last_health_detail = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SaaSJob(Base):
    """Database-backed queue item claimed with PostgreSQL ``SKIP LOCKED``."""

    __tablename__ = "saas_jobs"
    __table_args__ = (
        UniqueConstraint("job_type", "tenant_scope", "idempotency_key", name="uq_saas_job_idempotency"),
        Index("ix_saas_jobs_claim", "queue_name", "status", "available_at", "priority"),
        Index("ix_saas_jobs_lease", "status", "lease_expires_at"),
        Index("ix_saas_jobs_tenant", "tenant_id", "status", "created_at"),
        Index("ix_saas_jobs_correlation", "correlation_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    queue_name = Column(String(64), nullable=False, default="default", index=True)
    job_type = Column(String(96), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=True, index=True)
    # PostgreSQL treats NULLs as distinct in unique constraints. This stable
    # scope value preserves global-job idempotency as well as tenant idempotency.
    tenant_scope = Column(String(36), nullable=False, default="__platform__")
    status = Column(String(32), nullable=False, default="PENDING", index=True)
    priority = Column(Integer, nullable=False, default=100)
    payload_json = Column(JSON, nullable=False, default=dict)
    result_json = Column(JSON, nullable=True)
    idempotency_key = Column(String(160), nullable=False)
    correlation_id = Column(String(96), nullable=True, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    available_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_by = Column(String(128), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class SaaSJobEvent(Base):
    __tablename__ = "saas_job_events"
    __table_args__ = (Index("ix_saas_job_events_job", "job_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    job_id = Column(String(36), ForeignKey("saas_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), nullable=False)
    message = Column(Text, nullable=True)
    data_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class SaaSModulePrice(Base):
    __tablename__ = "saas_module_prices"
    __table_args__ = (
        UniqueConstraint("module_code", "plan_code", "billing_term", "currency", name="uq_saas_module_price"),
        Index("ix_saas_module_prices_active", "is_active", "module_code", "billing_term"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    module_code = Column(String(64), nullable=False, index=True)
    plan_code = Column(String(64), nullable=False, default="STANDARD", index=True)
    billing_term = Column(String(32), nullable=False, default="MONTHLY", index=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(8), nullable=False, default="USD")
    trial_days = Column(Integer, nullable=False, default=0)
    tax_rate_bps = Column(Integer, nullable=False, default=0)
    external_price_ref = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SaaSBillingAccount(Base):
    __tablename__ = "saas_billing_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_saas_billing_account_provider"),
        Index("ix_saas_billing_account_status", "provider", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="NOT_CONFIGURED", index=True)
    external_customer_ref = Column(String(255), nullable=True, index=True)
    external_subscription_ref = Column(String(255), nullable=True, index=True)
    auto_collection = Column(Boolean, nullable=False, default=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SaaSInvoiceFiscalization(Base):
    __tablename__ = "saas_invoice_fiscalizations"
    __table_args__ = (
        UniqueConstraint("invoice_id", name="uq_saas_invoice_fiscalization_invoice"),
        Index("ix_saas_fiscalization_status", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    invoice_id = Column(String(36), ForeignKey("billing_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(64), nullable=False, default="ETIMS_OSCU", index=True)
    status = Column(String(32), nullable=False, default="PENDING", index=True)
    fiscal_document_number = Column(String(255), nullable=True)
    control_unit_serial = Column(String(255), nullable=True)
    receipt_signature = Column(Text, nullable=True)
    request_json = Column(JSON, nullable=False, default=dict)
    response_json = Column(JSON, nullable=True)
    last_error = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    fiscalized_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SaaSSupportTicketDetail(Base):
    __tablename__ = "saas_support_ticket_details"

    ticket_id = Column(String(36), ForeignKey("platform_support_tickets.id", ondelete="CASCADE"), primary_key=True)
    requester_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    requester_email = Column(String(255), nullable=True)
    assignee_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    category = Column(String(64), nullable=False, default="GENERAL", index=True)
    description = Column(Text, nullable=False)
    sla_due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SaaSSupportTicketMessage(Base):
    __tablename__ = "saas_support_ticket_messages"
    __table_args__ = (Index("ix_saas_support_message_ticket", "ticket_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    ticket_id = Column(String(36), ForeignKey("platform_support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    author_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    author_type = Column(String(32), nullable=False, default="USER")
    visibility = Column(String(32), nullable=False, default="PUBLIC")
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
