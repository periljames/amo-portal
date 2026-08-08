from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base
from amodb.user_id import generate_user_id


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlatformProductEvent(Base):
    __tablename__ = "platform_product_events"
    __table_args__ = (
        Index("ix_platform_product_events_occurred", "occurred_at"),
        Index("ix_platform_product_events_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_platform_product_events_module_event", "module", "event_type", "occurred_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    module = Column(String(64), nullable=False, index=True)
    outcome = Column(String(32), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    session_class = Column(String(32), nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PlatformProductRollup(Base):
    __tablename__ = "platform_product_rollups"
    __table_args__ = (
        UniqueConstraint("bucket_start", "bucket_kind", "tenant_id", "module", "event_type", "outcome", name="uq_platform_product_rollup_bucket"),
        Index("ix_platform_product_rollups_bucket", "bucket_kind", "bucket_start"),
        Index("ix_platform_product_rollups_tenant", "tenant_id", "bucket_start"),
        Index("ix_platform_product_rollups_module", "module", "event_type", "bucket_start"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    bucket_start = Column(DateTime(timezone=True), nullable=False, index=True)
    bucket_kind = Column(String(16), nullable=False)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    module = Column(String(64), nullable=False)
    event_type = Column(String(64), nullable=False)
    outcome = Column(String(32), nullable=False, default="UNKNOWN")
    event_count = Column(Integer, nullable=False, default=0)
    duration_total_ms = Column(Integer, nullable=False, default=0)
    duration_count = Column(Integer, nullable=False, default=0)
    duration_max_ms = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class PlatformSavedView(Base):
    __tablename__ = "platform_saved_views"
    __table_args__ = (
        UniqueConstraint("platform_user_id", "scope", "name", name="uq_platform_saved_view_user_scope_name"),
        Index("ix_platform_saved_views_user_scope", "platform_user_id", "scope", "updated_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    platform_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scope = Column(String(64), nullable=False, default="tenant_fleet")
    name = Column(String(128), nullable=False)
    filters_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class PlatformIncident(Base):
    __tablename__ = "platform_incidents"
    __table_args__ = (
        Index("ix_platform_incidents_state_severity", "state", "severity", "started_at"),
        Index("ix_platform_incidents_started", "started_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    severity = Column(String(16), nullable=False, default="HIGH", index=True)
    state = Column(String(32), nullable=False, default="DETECTED", index=True)
    source = Column(String(64), nullable=False, default="manual")
    components_json = Column(JSONB, nullable=True)
    affected_nodes_json = Column(JSONB, nullable=True)
    affected_tenants_json = Column(JSONB, nullable=True)
    alert_refs_json = Column(JSONB, nullable=True)
    change_refs_json = Column(JSONB, nullable=True)
    runbook = Column(String(255), nullable=True)
    external_ref = Column(String(255), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    mitigated_at = Column(DateTime(timezone=True), nullable=True)
    mitigated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class PlatformIncidentEvent(Base):
    __tablename__ = "platform_incident_events"
    __table_args__ = (Index("ix_platform_incident_events_incident", "incident_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    incident_id = Column(String(36), ForeignKey("platform_incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    message = Column(Text, nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    data_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PlatformChangeMarker(Base):
    __tablename__ = "platform_change_markers"
    __table_args__ = (
        Index("ix_platform_change_markers_occurred", "occurred_at"),
        Index("ix_platform_change_markers_kind", "kind", "occurred_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    kind = Column(String(32), nullable=False, index=True)
    reference = Column(String(255), nullable=True)
    title = Column(String(255), nullable=False)
    details_json = Column(JSONB, nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
