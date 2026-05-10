"""platform control plane tables and SaaS superadmin expansion

Revision ID: plat_p7_20260501
Revises: 
Create Date: 2026-05-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "plat_p7_20260501"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _json():
    return postgresql.JSONB(astext_type=sa.Text())


def _create(name: str, *cols, **kw) -> None:
    if not _has_table(name):
        op.create_table(name, *cols, **kw)


def _idx(name: str, table: str, cols: list[str], unique: bool = False) -> None:
    bind = op.get_bind()
    existing = {idx["name"] for idx in sa.inspect(bind).get_indexes(table)} if _has_table(table) else set()
    if name not in existing:
        op.create_index(name, table, cols, unique=unique)


def upgrade() -> None:
    _create("platform_command_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("command_name", sa.String(96), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="LOW"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("input_json", _json(), nullable=True),
        sa.Column("output_json", _json(), nullable=True),
        sa.Column("error_code", sa.String(96), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("idempotency_key", name="uq_platform_command_jobs_idempotency_key"),
    )
    for name, cols in [
        ("ix_platform_command_jobs_status", ["status"]), ("ix_platform_command_jobs_tenant", ["tenant_id"]),
        ("ix_platform_command_jobs_actor", ["actor_user_id"]), ("ix_platform_command_jobs_created", ["created_at"]),
        ("ix_platform_command_jobs_command", ["command_name"]),
    ]: _idx(name, "platform_command_jobs", cols)

    _create("platform_command_job_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("platform_command_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("data_json", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ); _idx("ix_platform_command_job_events_job", "platform_command_job_events", ["job_id", "created_at"])

    _create("platform_audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("module", sa.String(64), nullable=False, server_default="platform"),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.String(96), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("details_json", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    _idx("ix_platform_audit_log_actor", "platform_audit_log", ["actor_user_id", "created_at"]); _idx("ix_platform_audit_log_tenant", "platform_audit_log", ["tenant_id", "created_at"]); _idx("ix_platform_audit_log_action", "platform_audit_log", ["action", "created_at"])

    _create("platform_health_snapshots",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("status", sa.String(32), nullable=False, server_default="UNKNOWN"),
        sa.Column("db_ok", sa.Boolean()), sa.Column("storage_ok", sa.Boolean()), sa.Column("internet_ok", sa.Boolean()), sa.Column("smtp_ok", sa.Boolean()), sa.Column("worker_ok", sa.Boolean()), sa.Column("route_metrics_fresh", sa.Boolean()),
        sa.Column("p95_latency_ms", sa.Float()), sa.Column("p99_latency_ms", sa.Float()), sa.Column("requests_per_minute", sa.Float()), sa.Column("error_rate", sa.Float()),
        sa.Column("details_json", _json()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ); _idx("ix_platform_health_snapshots_created", "platform_health_snapshots", ["created_at"])

    _create("platform_route_metrics_1m",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(16), nullable=False), sa.Column("route", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="SET NULL"), nullable=True), sa.Column("is_platform_route", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("client_error_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("server_error_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("timeout_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_ms", sa.Float(), nullable=False, server_default="0"), sa.Column("min_duration_ms", sa.Float()), sa.Column("max_duration_ms", sa.Float()), sa.Column("p50_latency_ms", sa.Float()), sa.Column("p95_latency_ms", sa.Float()), sa.Column("p99_latency_ms", sa.Float()), sa.Column("avg_latency_ms", sa.Float()), sa.Column("requests_per_minute", sa.Float()), sa.Column("errors_per_minute", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("bucket_start", "method", "route", "tenant_id", "is_platform_route", name="uq_platform_route_metric_bucket"),
    )
    _idx("ix_platform_route_metrics_bucket", "platform_route_metrics_1m", ["bucket_start"]); _idx("ix_platform_route_metrics_route", "platform_route_metrics_1m", ["route"]); _idx("ix_platform_route_metrics_tenant", "platform_route_metrics_1m", ["tenant_id"])

    for table_name, cols in {
        "platform_diagnostic_runs": [sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"), sa.Column("probe_type", sa.String(64), nullable=False, server_default="health"), sa.Column("duration_ms", sa.Float()), sa.Column("result_json", _json()), sa.Column("error_detail", sa.Text()), sa.Column("finished_at", sa.DateTime(timezone=True))],
        "platform_support_sessions": [sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False), sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("reason", sa.Text(), nullable=False), sa.Column("mode", sa.String(32), nullable=False, server_default="READ_ONLY"), sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("ended_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())],
        "platform_security_alerts": [sa.Column("severity", sa.String(16), nullable=False, server_default="INFO"), sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"), sa.Column("category", sa.String(64), nullable=False, server_default="GENERAL"), sa.Column("title", sa.String(255), nullable=False), sa.Column("description", sa.Text()), sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="SET NULL")), sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("source_ip", sa.String(64)), sa.Column("user_agent", sa.Text()), sa.Column("evidence_json", _json()), sa.Column("acknowledged_at", sa.DateTime(timezone=True)), sa.Column("acknowledged_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("resolved_at", sa.DateTime(timezone=True)), sa.Column("resolved_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"))],
        "platform_api_keys": [sa.Column("name", sa.String(255), nullable=False), sa.Column("key_prefix", sa.String(32), nullable=False), sa.Column("key_hash", sa.String(128), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"), sa.Column("scopes_json", _json()), sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("last_used_at", sa.DateTime(timezone=True)), sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("revoked_at", sa.DateTime(timezone=True)), sa.Column("revoked_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.UniqueConstraint("key_prefix", name="uq_platform_api_keys_prefix")],
        "platform_webhook_configs": [sa.Column("name", sa.String(255), nullable=False), sa.Column("event_type", sa.String(128), nullable=False), sa.Column("target_url", sa.Text(), nullable=False), sa.Column("secret_hash", sa.String(128)), sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"), sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="SET NULL")), sa.Column("is_global", sa.Boolean(), nullable=False, server_default=sa.text("true")), sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("last_delivery_at", sa.DateTime(timezone=True)), sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0")],
        "platform_webhook_delivery_logs": [sa.Column("webhook_id", sa.String(36), sa.ForeignKey("platform_webhook_configs.id", ondelete="CASCADE"), nullable=False), sa.Column("event_type", sa.String(128), nullable=False), sa.Column("status_code", sa.Integer()), sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")), sa.Column("duration_ms", sa.Float()), sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"), sa.Column("error_detail", sa.Text())],
        "platform_integration_providers": [sa.Column("provider", sa.String(64), nullable=False), sa.Column("display_name", sa.String(255), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="NOT_CONFIGURED"), sa.Column("uptime_percent", sa.Float()), sa.Column("last_latency_ms", sa.Float()), sa.Column("last_checked_at", sa.DateTime(timezone=True)), sa.Column("config_json", _json()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("provider", name="uq_platform_integration_provider")],
        "platform_feature_flags": [sa.Column("key", sa.String(128), nullable=False), sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text()), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")), sa.Column("scope", sa.String(32), nullable=False, server_default="GLOBAL"), sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE")), sa.Column("plan_code", sa.String(64)), sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("key", "scope", "tenant_id", "plan_code", name="uq_platform_feature_flag_scope")],
        "platform_maintenance_windows": [sa.Column("title", sa.String(255), nullable=False), sa.Column("description", sa.Text()), sa.Column("status", sa.String(32), nullable=False, server_default="SCHEDULED"), sa.Column("starts_at", sa.DateTime(timezone=True)), sa.Column("ends_at", sa.DateTime(timezone=True)), sa.Column("impact_level", sa.String(32), nullable=False, server_default="LOW"), sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())],
        "platform_infrastructure_snapshots": [sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("cpu_percent", sa.Float()), sa.Column("memory_percent", sa.Float()), sa.Column("db_connections_active", sa.Integer()), sa.Column("db_connections_max", sa.Integer()), sa.Column("queue_depth", sa.Integer()), sa.Column("worker_count", sa.Integer()), sa.Column("storage_used_bytes", sa.Integer()), sa.Column("storage_quota_bytes", sa.Integer()), sa.Column("api_error_rate", sa.Float()), sa.Column("api_p95_latency_ms", sa.Float()), sa.Column("api_requests_per_minute", sa.Float()), sa.Column("status", sa.String(32), nullable=False, server_default="UNKNOWN"), sa.Column("details_json", _json())],
        "platform_worker_heartbeats": [sa.Column("worker_name", sa.String(128), nullable=False), sa.Column("worker_type", sa.String(64), nullable=False, server_default="generic"), sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("status", sa.String(32), nullable=False, server_default="ONLINE"), sa.Column("metadata_json", _json()), sa.UniqueConstraint("worker_name", name="uq_platform_worker_name")],
        "platform_support_tickets": [sa.Column("external_id", sa.String(128)), sa.Column("provider", sa.String(64), nullable=False, server_default="INTERNAL"), sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="SET NULL")), sa.Column("title", sa.String(255), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"), sa.Column("priority", sa.String(32), nullable=False, server_default="NORMAL"), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("last_synced_at", sa.DateTime(timezone=True)), sa.Column("metadata_json", _json())],
        "platform_tenant_resource_snapshots": [sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False), sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("storage_used_bytes", sa.Integer()), sa.Column("storage_quota_bytes", sa.Integer()), sa.Column("database_estimated_bytes", sa.Integer()), sa.Column("database_record_count", sa.Integer()), sa.Column("api_requests_1h", sa.Integer(), nullable=False, server_default="0"), sa.Column("api_requests_24h", sa.Integer(), nullable=False, server_default="0"), sa.Column("bandwidth_bytes", sa.Integer()), sa.Column("file_count", sa.Integer()), sa.Column("active_users_24h", sa.Integer()), sa.Column("quota_percent", sa.Float()), sa.Column("details_json", _json())],
        "platform_notifications": [sa.Column("title", sa.String(255), nullable=False), sa.Column("message", sa.Text()), sa.Column("severity", sa.String(16), nullable=False, server_default="INFO"), sa.Column("source", sa.String(64), nullable=False, server_default="platform"), sa.Column("route", sa.String(255)), sa.Column("read_at", sa.DateTime(timezone=True))],
    }.items():
        _create(table_name, sa.Column("id", sa.String(36), primary_key=True), *cols, sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    # Common indexes for large list/read paths.
    index_specs = [
        ("ix_platform_diagnostic_runs_created", "platform_diagnostic_runs", ["created_at"]),
        ("ix_platform_support_sessions_tenant", "platform_support_sessions", ["tenant_id", "status"]),
        ("ix_platform_security_alerts_status", "platform_security_alerts", ["status", "created_at"]),
        ("ix_platform_api_keys_status", "platform_api_keys", ["status"]),
        ("ix_platform_webhook_configs_status", "platform_webhook_configs", ["status"]),
        ("ix_platform_feature_flags_scope", "platform_feature_flags", ["scope"]),
        ("ix_platform_maintenance_windows_status", "platform_maintenance_windows", ["status", "starts_at"]),
        ("ix_platform_infrastructure_snapshots_captured", "platform_infrastructure_snapshots", ["captured_at"]),
        ("ix_platform_worker_heartbeats_status", "platform_worker_heartbeats", ["status", "last_seen_at"]),
        ("ix_platform_support_tickets_status", "platform_support_tickets", ["status", "created_at"]),
        ("ix_platform_tenant_resource_snapshots_tenant", "platform_tenant_resource_snapshots", ["tenant_id", "captured_at"]),
        ("ix_platform_notifications_read", "platform_notifications", ["read_at", "created_at"]),
    ]
    for name, table, cols in index_specs:
        _idx(name, table, cols)


def downgrade() -> None:
    # Non-destructive by design. Drop only on explicit manual rollback if needed.
    pass
