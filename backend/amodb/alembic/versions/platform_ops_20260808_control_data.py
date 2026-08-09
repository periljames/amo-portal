"""Add Platform Operations product analytics, saved views, incidents and change markers.

Revision ID: platform_ops_20260808_control_data
Revises: docgov_rel_20260807_merge
Create Date: 2026-08-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "platform_ops_20260808_control_data"
down_revision = "docgov_rel_20260807_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_product_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("session_class", sa.String(length=32), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_product_events_occurred", "platform_product_events", ["occurred_at"], unique=False)
    op.create_index("ix_platform_product_events_tenant_occurred", "platform_product_events", ["tenant_id", "occurred_at"], unique=False)
    op.create_index("ix_platform_product_events_module_event", "platform_product_events", ["module", "event_type", "occurred_at"], unique=False)

    op.create_table(
        "platform_product_rollups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_kind", sa.String(length=16), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), server_default="UNKNOWN", nullable=False),
        sa.Column("event_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_total_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_max_ms", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bucket_start", "bucket_kind", "tenant_id", "module", "event_type", "outcome", name="uq_platform_product_rollup_bucket"),
    )
    op.create_index("ix_platform_product_rollups_bucket", "platform_product_rollups", ["bucket_kind", "bucket_start"], unique=False)
    op.create_index("ix_platform_product_rollups_tenant", "platform_product_rollups", ["tenant_id", "bucket_start"], unique=False)
    op.create_index("ix_platform_product_rollups_module", "platform_product_rollups", ["module", "event_type", "bucket_start"], unique=False)

    op.create_table(
        "platform_saved_views",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("platform_user_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=64), server_default="tenant_fleet", nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("filters_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["platform_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_user_id", "scope", "name", name="uq_platform_saved_view_user_scope_name"),
    )
    op.create_index("ix_platform_saved_views_user_scope", "platform_saved_views", ["platform_user_id", "scope", "updated_at"], unique=False)

    op.create_table(
        "platform_incidents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=16), server_default="HIGH", nullable=False),
        sa.Column("state", sa.String(length=32), server_default="DETECTED", nullable=False),
        sa.Column("source", sa.String(length=64), server_default="manual", nullable=False),
        sa.Column("components_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("affected_nodes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("affected_tenants_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("alert_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("change_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("runbook", sa.String(length=255), nullable=True),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=36), nullable=True),
        sa.Column("mitigated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mitigated_by", sa.String(length=36), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mitigated_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_incidents_state_severity", "platform_incidents", ["state", "severity", "started_at"], unique=False)
    op.create_index("ix_platform_incidents_started", "platform_incidents", ["started_at"], unique=False)

    op.create_table(
        "platform_incident_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["platform_incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_incident_events_incident", "platform_incident_events", ["incident_id", "created_at"], unique=False)

    op.create_table(
        "platform_change_markers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_change_markers_occurred", "platform_change_markers", ["occurred_at"], unique=False)
    op.create_index("ix_platform_change_markers_kind", "platform_change_markers", ["kind", "occurred_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_platform_change_markers_kind", table_name="platform_change_markers")
    op.drop_index("ix_platform_change_markers_occurred", table_name="platform_change_markers")
    op.drop_table("platform_change_markers")
    op.drop_index("ix_platform_incident_events_incident", table_name="platform_incident_events")
    op.drop_table("platform_incident_events")
    op.drop_index("ix_platform_incidents_started", table_name="platform_incidents")
    op.drop_index("ix_platform_incidents_state_severity", table_name="platform_incidents")
    op.drop_table("platform_incidents")
    op.drop_index("ix_platform_saved_views_user_scope", table_name="platform_saved_views")
    op.drop_table("platform_saved_views")
    op.drop_index("ix_platform_product_rollups_module", table_name="platform_product_rollups")
    op.drop_index("ix_platform_product_rollups_tenant", table_name="platform_product_rollups")
    op.drop_index("ix_platform_product_rollups_bucket", table_name="platform_product_rollups")
    op.drop_table("platform_product_rollups")
    op.drop_index("ix_platform_product_events_module_event", table_name="platform_product_events")
    op.drop_index("ix_platform_product_events_tenant_occurred", table_name="platform_product_events")
    op.drop_index("ix_platform_product_events_occurred", table_name="platform_product_events")
    op.drop_table("platform_product_events")
