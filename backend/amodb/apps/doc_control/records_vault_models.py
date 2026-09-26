from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class TenantRecordSeries(Base):
    """Tenant-wide record classification independent of a particular manual template."""

    __tablename__ = "document_record_series"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_document_record_series_tenant_code"),
        Index("ix_document_record_series_tenant_owner", "tenant_id", "owner_department", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(128), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    owner_department = Column(String(128), nullable=False)
    retention_years = Column(Integer, nullable=False, default=7)
    disposition_method = Column(String(40), nullable=False, default="REVIEW_AT_EXPIRY")
    restricted_flag = Column(Boolean, nullable=False, default=True)
    controllers_can_read = Column(Boolean, nullable=False, default=True)
    access_scope_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="ACTIVE")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TenantRecordAsset(Base):
    """Immutable tenant record with source provenance, retention and legal-hold state."""

    __tablename__ = "document_record_assets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "record_number", name="uq_document_record_asset_tenant_number"),
        Index("ix_document_record_asset_series_capture", "series_id", "captured_at"),
        Index("ix_document_record_asset_tenant_retention", "tenant_id", "retention_due_at", "status"),
        Index("ix_document_record_asset_tenant_source", "tenant_id", "source_module", "source_entity_type", "source_entity_id"),
        Index("ix_document_record_asset_tenant_sha", "tenant_id", "sha256"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    series_id = Column(String(36), ForeignKey("document_record_series.id", ondelete="RESTRICT"), nullable=False)
    record_number = Column(String(160), nullable=False)
    title = Column(String(500), nullable=False)
    source_module = Column(String(64), nullable=False, default="DOCUMENT_CONTROL")
    source_entity_type = Column(String(80), nullable=True)
    source_entity_id = Column(String(160), nullable=True)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_path = Column(Text, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    retention_due_at = Column(DateTime(timezone=True), nullable=True)
    legal_hold = Column(Boolean, nullable=False, default=False)
    legal_hold_reason = Column(Text, nullable=True)
    legal_hold_set_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    legal_hold_set_at = Column(DateTime(timezone=True), nullable=True)
    disposition_status = Column(String(40), nullable=False, default="ACTIVE")
    disposed_at = Column(DateTime(timezone=True), nullable=True)
    disposed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    disposition_reason = Column(Text, nullable=True)
    search_text = Column(Text, nullable=False, default="")
    access_scope_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TenantRecordEvent(Base):
    """Append-only chain of custody and governance history for a retained record."""

    __tablename__ = "document_record_events"
    __table_args__ = (
        Index("ix_document_record_event_asset_created", "record_asset_id", "created_at"),
        Index("ix_document_record_event_tenant_action", "tenant_id", "event_type", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    record_asset_id = Column(String(36), ForeignKey("document_record_assets.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(48), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
