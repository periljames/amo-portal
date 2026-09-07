from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)

from amodb.database import Base
from amodb.user_id import generate_user_id


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TenantAISettings(Base):
    __tablename__ = "tenant_ai_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_ai_settings_tenant"),
        Index("ix_tenant_ai_settings_enabled_plan", "enabled", "plan_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=False)
    provider = Column(String(32), nullable=False, default="openai")
    default_model = Column(String(96), nullable=False)
    lightweight_model = Column(String(96), nullable=False)
    embedding_model = Column(String(96), nullable=False)
    plan_type = Column(String(32), nullable=False, default="DEVELOPMENT")
    monthly_token_allowance = Column(BigInteger, nullable=False, default=0)
    monthly_request_allowance = Column(Integer, nullable=False, default=0)
    max_input_tokens_per_request = Column(Integer, nullable=False, default=0)
    max_output_tokens_per_request = Column(Integer, nullable=False, default=0)
    usage_limits_json = Column(JSON, nullable=False, default=dict)
    enabled_features_json = Column(JSON, nullable=False, default=list)
    allow_external_document_context = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class AIUsageRecord(Base):
    __tablename__ = "ai_usage_records"
    __table_args__ = (
        Index("ix_ai_usage_tenant_period", "tenant_id", "created_at"),
        Index("ix_ai_usage_tenant_feature", "tenant_id", "feature", "created_at"),
        Index("ix_ai_usage_request", "tenant_id", "request_id"),
        Index("ix_ai_usage_user", "tenant_id", "user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(32), nullable=False)
    model = Column(String(96), nullable=False)
    feature = Column(String(96), nullable=False, index=True)
    operation_type = Column(String(24), nullable=False, default="COMPLETION")
    request_id = Column(String(96), nullable=False)
    provider_response_id = Column(String(255), nullable=True)
    status = Column(String(24), nullable=False, default="SUCCEEDED", index=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost_usd = Column(Numeric(18, 8), nullable=False, default=0)
    latency_ms = Column(Integer, nullable=True)
    failure_code = Column(String(96), nullable=True)
    document_id = Column(String(96), nullable=True)
    document_revision_id = Column(String(96), nullable=True)
    workflow_type = Column(String(96), nullable=True)
    workflow_id = Column(String(96), nullable=True)
    context_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
