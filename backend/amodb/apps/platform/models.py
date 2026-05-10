from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base
from amodb.user_id import generate_user_id


def utcnow() -> datetime:
    return datetime.utcnow()


class PlatformCommandJob(Base):
    __tablename__ = "platform_command_jobs"
    __table_args__ = (
        Index("ix_platform_command_jobs_status", "status"),
        Index("ix_platform_command_jobs_tenant", "tenant_id"),
        Index("ix_platform_command_jobs_actor", "actor_user_id"),
        Index("ix_platform_command_jobs_created", "created_at"),
        Index("ix_platform_command_jobs_command", "command_name"),
        UniqueConstraint("idempotency_key", name="uq_platform_command_jobs_idempotency_key"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    command_name = Column(String(96), nullable=False, index=True)
    risk_level = Column(String(16), nullable=False, default="LOW")
    status = Column(String(32), nullable=False, default="PENDING", index=True)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = Column(Text, nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    input_json = Column(JSONB, nullable=True)
    output_json = Column(JSONB, nullable=True)
    error_code = Column(String(96), nullable=True)
    error_detail = Column(Text, nullable=True)
    dry_run = Column(Boolean, nullable=False, default=False)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=0)
    timeout_seconds = Column(Integer, nullable=False, default=10)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class PlatformCommandJobEvent(Base):
    __tablename__ = "platform_command_job_events"
    __table_args__ = (Index("ix_platform_command_job_events_job", "job_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    job_id = Column(String(36), ForeignKey("platform_command_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), nullable=False)
    message = Column(Text, nullable=True)
    data_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PlatformAuditLog(Base):
    __tablename__ = "platform_audit_log"
    __table_args__ = (
        Index("ix_platform_audit_log_actor", "actor_user_id", "created_at"),
        Index("ix_platform_audit_log_tenant", "tenant_id", "created_at"),
        Index("ix_platform_audit_log_action", "action", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(128), nullable=False, index=True)
    module = Column(String(64), nullable=False, default="platform")
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(String(96), nullable=True)
    reason = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    details_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PlatformHealthSnapshot(Base):
    __tablename__ = "platform_health_snapshots"
    __table_args__ = (Index("ix_platform_health_snapshots_created", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    status = Column(String(32), nullable=False, default="UNKNOWN", index=True)
    db_ok = Column(Boolean, nullable=True)
    storage_ok = Column(Boolean, nullable=True)
    internet_ok = Column(Boolean, nullable=True)
    smtp_ok = Column(Boolean, nullable=True)
    worker_ok = Column(Boolean, nullable=True)
    route_metrics_fresh = Column(Boolean, nullable=True)
    p95_latency_ms = Column(Float, nullable=True)
    p99_latency_ms = Column(Float, nullable=True)
    requests_per_minute = Column(Float, nullable=True)
    error_rate = Column(Float, nullable=True)
    details_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PlatformRouteMetric1m(Base):
    __tablename__ = "platform_route_metrics_1m"
    __table_args__ = (
        UniqueConstraint("bucket_start", "method", "route", "tenant_id", "is_platform_route", name="uq_platform_route_metric_bucket"),
        Index("ix_platform_route_metrics_bucket", "bucket_start"),
        Index("ix_platform_route_metrics_route", "route"),
        Index("ix_platform_route_metrics_tenant", "tenant_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    bucket_start = Column(DateTime(timezone=True), nullable=False, index=True)
    method = Column(String(16), nullable=False)
    route = Column(String(255), nullable=False)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="SET NULL"), nullable=True, index=True)
    is_platform_route = Column(Boolean, nullable=False, default=False)
    request_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    client_error_count = Column(Integer, nullable=False, default=0)
    server_error_count = Column(Integer, nullable=False, default=0)
    timeout_count = Column(Integer, nullable=False, default=0)
    total_duration_ms = Column(Float, nullable=False, default=0)
    min_duration_ms = Column(Float, nullable=True)
    max_duration_ms = Column(Float, nullable=True)
    p50_latency_ms = Column(Float, nullable=True)
    p95_latency_ms = Column(Float, nullable=True)
    p99_latency_ms = Column(Float, nullable=True)
    avg_latency_ms = Column(Float, nullable=True)
    requests_per_minute = Column(Float, nullable=True)
    errors_per_minute = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PlatformDiagnosticRun(Base):
    __tablename__ = "platform_diagnostic_runs"
    __table_args__ = (Index("ix_platform_diagnostic_runs_created", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="PENDING", index=True)
    probe_type = Column(String(64), nullable=False, default="health")
    duration_ms = Column(Float, nullable=True)
    result_json = Column(JSONB, nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class PlatformSupportSession(Base):
    __tablename__ = "platform_support_sessions"
    __table_args__ = (
        Index("ix_platform_support_sessions_actor", "actor_user_id", "status"),
        Index("ix_platform_support_sessions_tenant", "tenant_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reason = Column(Text, nullable=False)
    mode = Column(String(32), nullable=False, default="READ_ONLY")
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class PlatformSecurityAlert(Base):
    __tablename__ = "platform_security_alerts"
    __table_args__ = (
        Index("ix_platform_security_alerts_status", "status", "created_at"),
        Index("ix_platform_security_alerts_tenant", "tenant_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    severity = Column(String(16), nullable=False, default="INFO", index=True)
    status = Column(String(32), nullable=False, default="OPEN", index=True)
    category = Column(String(64), nullable=False, default="GENERAL")
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_ip = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    evidence_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class PlatformAPIKey(Base):
    __tablename__ = "platform_api_keys"
    __table_args__ = (UniqueConstraint("key_prefix", name="uq_platform_api_keys_prefix"), Index("ix_platform_api_keys_status", "status"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    name = Column(String(255), nullable=False)
    key_prefix = Column(String(32), nullable=False)
    key_hash = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    scopes_json = Column(JSONB, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class PlatformWebhookConfig(Base):
    __tablename__ = "platform_webhook_configs"
    __table_args__ = (Index("ix_platform_webhook_configs_status", "status"), Index("ix_platform_webhook_configs_tenant", "tenant_id"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    name = Column(String(255), nullable=False)
    event_type = Column(String(128), nullable=False, index=True)
    target_url = Column(Text, nullable=False)
    secret_hash = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="SET NULL"), nullable=True, index=True)
    is_global = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    last_delivery_at = Column(DateTime(timezone=True), nullable=True)
    failure_count = Column(Integer, nullable=False, default=0)


class PlatformWebhookDeliveryLog(Base):
    __tablename__ = "platform_webhook_delivery_logs"
    __table_args__ = (Index("ix_platform_webhook_deliveries_webhook", "webhook_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    webhook_id = Column(String(36), ForeignKey("platform_webhook_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(128), nullable=False)
    status_code = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, default=False)
    duration_ms = Column(Float, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=1)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class PlatformIntegrationProvider(Base):
    __tablename__ = "platform_integration_providers"
    __table_args__ = (UniqueConstraint("provider", name="uq_platform_integration_provider"), Index("ix_platform_integration_providers_status", "status"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    provider = Column(String(64), nullable=False)
    display_name = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="NOT_CONFIGURED", index=True)
    uptime_percent = Column(Float, nullable=True)
    last_latency_ms = Column(Float, nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    config_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class PlatformFeatureFlag(Base):
    __tablename__ = "platform_feature_flags"
    __table_args__ = (UniqueConstraint("key", "scope", "tenant_id", "plan_code", name="uq_platform_feature_flag_scope"), Index("ix_platform_feature_flags_scope", "scope"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    key = Column(String(128), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=False)
    scope = Column(String(32), nullable=False, default="GLOBAL")
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=True, index=True)
    plan_code = Column(String(64), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class PlatformMaintenanceWindow(Base):
    __tablename__ = "platform_maintenance_windows"
    __table_args__ = (Index("ix_platform_maintenance_windows_status", "status", "starts_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="SCHEDULED", index=True)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    impact_level = Column(String(32), nullable=False, default="LOW")
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class PlatformInfrastructureSnapshot(Base):
    __tablename__ = "platform_infrastructure_snapshots"
    __table_args__ = (Index("ix_platform_infrastructure_snapshots_captured", "captured_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    captured_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    cpu_percent = Column(Float, nullable=True)
    memory_percent = Column(Float, nullable=True)
    db_connections_active = Column(Integer, nullable=True)
    db_connections_max = Column(Integer, nullable=True)
    queue_depth = Column(Integer, nullable=True)
    worker_count = Column(Integer, nullable=True)
    storage_used_bytes = Column(Integer, nullable=True)
    storage_quota_bytes = Column(Integer, nullable=True)
    api_error_rate = Column(Float, nullable=True)
    api_p95_latency_ms = Column(Float, nullable=True)
    api_requests_per_minute = Column(Float, nullable=True)
    status = Column(String(32), nullable=False, default="UNKNOWN")
    details_json = Column(JSONB, nullable=True)


class PlatformWorkerHeartbeat(Base):
    __tablename__ = "platform_worker_heartbeats"
    __table_args__ = (UniqueConstraint("worker_name", name="uq_platform_worker_name"), Index("ix_platform_worker_heartbeats_status", "status", "last_seen_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    worker_name = Column(String(128), nullable=False)
    worker_type = Column(String(64), nullable=False, default="generic")
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    status = Column(String(32), nullable=False, default="ONLINE")
    metadata_json = Column(JSONB, nullable=True)


class PlatformSupportTicket(Base):
    __tablename__ = "platform_support_tickets"
    __table_args__ = (Index("ix_platform_support_tickets_status", "status", "created_at"), Index("ix_platform_support_tickets_tenant", "tenant_id"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    external_id = Column(String(128), nullable=True)
    provider = Column(String(64), nullable=False, default="INTERNAL")
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="OPEN", index=True)
    priority = Column(String(32), nullable=False, default="NORMAL")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSONB, nullable=True)


class PlatformTenantResourceSnapshot(Base):
    __tablename__ = "platform_tenant_resource_snapshots"
    __table_args__ = (Index("ix_platform_tenant_resource_snapshots_tenant", "tenant_id", "captured_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    storage_used_bytes = Column(Integer, nullable=True)
    storage_quota_bytes = Column(Integer, nullable=True)
    database_estimated_bytes = Column(Integer, nullable=True)
    database_record_count = Column(Integer, nullable=True)
    api_requests_1h = Column(Integer, nullable=False, default=0)
    api_requests_24h = Column(Integer, nullable=False, default=0)
    bandwidth_bytes = Column(Integer, nullable=True)
    file_count = Column(Integer, nullable=True)
    active_users_24h = Column(Integer, nullable=True)
    quota_percent = Column(Float, nullable=True)
    details_json = Column(JSONB, nullable=True)


class PlatformNotification(Base):
    __tablename__ = "platform_notifications"
    __table_args__ = (Index("ix_platform_notifications_read", "read_at", "created_at"), Index("ix_platform_notifications_severity", "severity", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    severity = Column(String(16), nullable=False, default="INFO")
    source = Column(String(64), nullable=False, default="platform")
    route = Column(String(255), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
