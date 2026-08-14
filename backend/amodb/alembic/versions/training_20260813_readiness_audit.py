"""Frontend-readiness control plane for tenant training operations.

Revision ID: training_20260813_readiness_audit
Revises: training_20260813_frontend_operability
Create Date: 2026-08-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "training_20260813_readiness_audit"
down_revision = "training_20260813_frontend_operability"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
    ]


def upgrade() -> None:
    tables = _tables()
    if "training_setup_versions" not in tables:
        op.create_table(
            "training_setup_versions", *_base_columns(),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("source_mode", sa.String(length=24), nullable=False, server_default="BLANK"),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("change_summary", sa.Text()), sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("validation_result", sa.JSON(), nullable=False), sa.Column("effective_from", sa.DateTime(timezone=True)),
            sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("reviewed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("activated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("supersedes_version_id", sa.String(length=36), sa.ForeignKey("training_setup_versions.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "version_no", name="uq_training_setup_version"),
        )
        op.create_index("ix_training_setup_version_status", "training_setup_versions", ["amo_id", "status", "effective_from"])

    if "training_change_requests" not in tables:
        op.create_table(
            "training_change_requests", *_base_columns(),
            sa.Column("object_type", sa.String(length=48), nullable=False), sa.Column("object_id", sa.String(length=36)),
            sa.Column("operation", sa.String(length=48), nullable=False), sa.Column("status", sa.String(length=24), nullable=False, server_default="PREVIEW"),
            sa.Column("requested_payload", sa.JSON(), nullable=False), sa.Column("impact_summary", sa.JSON(), nullable=False),
            sa.Column("validation_result", sa.JSON(), nullable=False), sa.Column("source_cutoff_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("decided_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("decision_reason", sa.Text()), sa.Column("applied_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_training_change_request_queue", "training_change_requests", ["amo_id", "object_type", "status", "created_at"])

    if "training_workflow_instances" not in tables:
        op.create_table(
            "training_workflow_instances", *_base_columns(),
            sa.Column("workflow_type", sa.String(length=48), nullable=False),
            sa.Column("form_template_id", sa.String(length=36), sa.ForeignKey("training_controlled_form_templates.id", ondelete="SET NULL")),
            sa.Column("form_revision_no", sa.Integer()), sa.Column("subject_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("reviewer_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("event_id", sa.String(length=36), sa.ForeignKey("training_events.id", ondelete="SET NULL")),
            sa.Column("course_id", sa.String(length=36), sa.ForeignKey("training_courses.id", ondelete="SET NULL")),
            sa.Column("authorization_case_id", sa.String(length=36), sa.ForeignKey("training_authorization_cases.id", ondelete="SET NULL")),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"), sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("due_at", sa.DateTime(timezone=True)), sa.Column("data_json", sa.JSON(), nullable=False),
            sa.Column("validation_result", sa.JSON(), nullable=False), sa.Column("provenance", sa.JSON(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False), sa.Column("revision_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("submitted_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "workflow_type", "idempotency_key", name="uq_training_workflow_idempotency"),
        )
        op.create_index("ix_training_workflow_task_queue", "training_workflow_instances", ["amo_id", "status", "owner_user_id", "due_at"])
        op.create_index("ix_training_workflow_subject", "training_workflow_instances", ["amo_id", "subject_user_id", "workflow_type"])

    if "training_workflow_steps" not in tables:
        op.create_table(
            "training_workflow_steps", *_base_columns(),
            sa.Column("workflow_instance_id", sa.String(length=36), sa.ForeignKey("training_workflow_instances.id", ondelete="CASCADE"), nullable=False),
            sa.Column("step_key", sa.String(length=64), nullable=False), sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="1"), sa.Column("status", sa.String(length=24), nullable=False, server_default="PENDING"),
            sa.Column("assigned_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("response_json", sa.JSON(), nullable=False), sa.Column("signature_json", sa.JSON(), nullable=False),
            sa.Column("completed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("workflow_instance_id", "step_key", name="uq_training_workflow_step"),
        )
        op.create_index("ix_training_workflow_step_status", "training_workflow_steps", ["amo_id", "status", "assigned_user_id"])

    if "training_session_invitations" not in tables:
        op.create_table(
            "training_session_invitations", *_base_columns(),
            sa.Column("event_id", sa.String(length=36), sa.ForeignKey("training_events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("channel", sa.String(length=24), nullable=False, server_default="IN_APP"),
            sa.Column("delivery_status", sa.String(length=24), nullable=False, server_default="QUEUED"),
            sa.Column("email_log_id", sa.String(length=36), sa.ForeignKey("email_logs.id", ondelete="SET NULL")),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("last_error", sa.Text()),
            sa.Column("rsvp_status", sa.String(length=24), nullable=False, server_default="PENDING"),
            sa.Column("responded_at", sa.DateTime(timezone=True)), sa.Column("sent_at", sa.DateTime(timezone=True)),
            sa.Column("delivered_at", sa.DateTime(timezone=True)), sa.Column("read_at", sa.DateTime(timezone=True)),
            sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "event_id", "user_id", "channel", name="uq_training_session_invitation"),
        )
        op.create_index("ix_training_invitation_delivery", "training_session_invitations", ["amo_id", "event_id", "delivery_status"])

    if "training_report_definitions" not in tables:
        op.create_table(
            "training_report_definitions", *_base_columns(), sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False), sa.Column("description", sa.Text()),
            sa.Column("dataset", sa.String(length=64), nullable=False), sa.Column("allowed_formats", sa.JSON(), nullable=False),
            sa.Column("default_filters", sa.JSON(), nullable=False), sa.Column("schedule_json", sa.JSON(), nullable=False),
            sa.Column("retention_days", sa.Integer(), nullable=False, server_default="365"), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "code", name="uq_training_report_definition_code"),
        )

    if "training_report_jobs" not in tables:
        op.create_table(
            "training_report_jobs", *_base_columns(),
            sa.Column("report_definition_id", sa.String(length=36), sa.ForeignKey("training_report_definitions.id", ondelete="SET NULL")),
            sa.Column("report_code", sa.String(length=64), nullable=False), sa.Column("output_format", sa.String(length=12), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="QUEUED"), sa.Column("filters_json", sa.JSON(), nullable=False),
            sa.Column("scope_manifest", sa.JSON(), nullable=False), sa.Column("artifact_path", sa.Text()),
            sa.Column("artifact_checksum", sa.String(length=64)), sa.Column("error_text", sa.Text()),
            sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_training_report_job_queue", "training_report_jobs", ["amo_id", "status", "created_at"])

    if "training_saved_views" not in tables:
        op.create_table(
            "training_saved_views", *_base_columns(), sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("workspace", sa.String(length=48), nullable=False), sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("filter_json", sa.JSON(), nullable=False), sa.Column("column_json", sa.JSON(), nullable=False),
            sa.Column("density", sa.String(length=16), nullable=False, server_default="COMPACT"), sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "user_id", "workspace", "name", name="uq_training_saved_view"),
        )


def downgrade() -> None:
    for table in (
        "training_saved_views", "training_report_jobs", "training_report_definitions", "training_session_invitations",
        "training_workflow_steps", "training_workflow_instances", "training_change_requests", "training_setup_versions",
    ):
        if table in _tables():
            op.drop_table(table)
