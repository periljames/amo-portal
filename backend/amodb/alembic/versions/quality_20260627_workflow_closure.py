"""close quality audit workflow gaps

Revision ID: qual_20260627_wf_close
Revises: plat_20260627_support
Create Date: 2026-06-27
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "qual_20260627_wf_close"
down_revision: Union[str, Sequence[str], None] = "plat_20260627_support"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _insp().has_table(name)


def _has_index(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    return name in {idx["name"] for idx in _insp().get_indexes(table)}


def _create_index(name: str, table: str, columns: list[str], unique: bool = False) -> None:
    if _has_table(table) and not _has_index(table, name):
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    if not _has_table("quality_tenant_workflow_settings"):
        op.create_table(
            "quality_tenant_workflow_settings",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("report_due_days", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("report_reminder_days_json", sa.Text(), nullable=False, server_default="[7,3,1]"),
            sa.Column("car_reminder_percentages_json", sa.Text(), nullable=False, server_default="[75,50,25]"),
            sa.Column("final_reminder_days_before_due", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("auto_escalation_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("auto_escalation_locked", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.CheckConstraint("report_due_days BETWEEN 1 AND 60", name="ck_quality_settings_report_due_days"),
            sa.CheckConstraint("final_reminder_days_before_due BETWEEN 0 AND 30", name="ck_quality_settings_final_reminder"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("amo_id", name="uq_quality_tenant_workflow_settings_amo"),
        )
    _create_index("ix_quality_tenant_workflow_settings_amo_id", "quality_tenant_workflow_settings", ["amo_id"])
    _create_index("ix_quality_settings_amo_escalation", "quality_tenant_workflow_settings", ["amo_id", "auto_escalation_enabled"])

    if not _has_table("quality_audit_document_requests"):
        op.create_table(
            "quality_audit_document_requests",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("audit_id", sa.UUID(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="REQUESTED"),
            sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("file_ref", sa.String(length=512), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.CheckConstraint("status IN ('REQUESTED','UPLOADED','ACCEPTED','REJECTED','WAIVED')", name="ck_quality_doc_request_status"),
            sa.PrimaryKeyConstraint("id"),
        )
    for name, cols in {
        "ix_quality_doc_requests_audit_status": ["audit_id", "status"],
        "ix_quality_audit_document_requests_amo_id": ["amo_id"],
        "ix_quality_audit_document_requests_due_date": ["due_date"],
    }.items():
        _create_index(name, "quality_audit_document_requests", cols)

    if not _has_table("quality_audit_checklist_items"):
        op.create_table(
            "quality_audit_checklist_items",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("audit_id", sa.UUID(), nullable=False),
            sa.Column("section", sa.String(length=128), nullable=True),
            sa.Column("checklist_ref", sa.String(length=128), nullable=True),
            sa.Column("requirement_ref", sa.String(length=255), nullable=True),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("response_status", sa.String(length=32), nullable=False, server_default="PENDING"),
            sa.Column("objective_evidence", sa.Text(), nullable=True),
            sa.Column("finding_id", sa.UUID(), nullable=True),
            sa.Column("assigned_to_user_id", sa.String(length=36), nullable=True),
            sa.Column("completed_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["finding_id"], ["qms_audit_findings.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.CheckConstraint("response_status IN ('PENDING','COMPLIANT','NON_CONFORMING','OBSERVATION','NOT_APPLICABLE')", name="ck_quality_checklist_response_status"),
            sa.PrimaryKeyConstraint("id"),
        )
    for name, cols in {
        "ix_quality_checklist_audit_order": ["audit_id", "section", "sort_order"],
        "ix_quality_audit_checklist_items_amo_id": ["amo_id"],
        "ix_quality_audit_checklist_items_response_status": ["response_status"],
    }.items():
        _create_index(name, "quality_audit_checklist_items", cols)

    if not _has_table("quality_audit_post_briefs"):
        op.create_table(
            "quality_audit_post_briefs",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("audit_id", sa.UUID(), nullable=False),
            sa.Column("briefing_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("attendees_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("report_due_date", sa.Date(), nullable=False),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("audit_id", name="uq_quality_audit_post_brief_audit"),
        )
    _create_index("ix_quality_audit_post_briefs_amo_id", "quality_audit_post_briefs", ["amo_id"])
    _create_index("ix_quality_audit_post_briefs_report_due_date", "quality_audit_post_briefs", ["report_due_date"])

    if not _has_table("quality_audit_report_trackers"):
        op.create_table(
            "quality_audit_report_trackers",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("audit_id", sa.UUID(), nullable=False),
            sa.Column("report_due_date", sa.Date(), nullable=False),
            sa.Column("report_submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("feedback_due_date", sa.Date(), nullable=True),
            sa.Column("feedback_submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="DUE"),
            sa.Column("next_reminder_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.CheckConstraint("status IN ('DUE','SUBMITTED','FEEDBACK_DUE','ACCEPTED','OVERDUE')", name="ck_quality_report_tracker_status"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("audit_id", name="uq_quality_audit_report_tracker_audit"),
        )
    for name, cols in {
        "ix_quality_report_tracker_status_due": ["amo_id", "status", "report_due_date"],
        "ix_quality_audit_report_trackers_next_reminder_at": ["next_reminder_at"],
    }.items():
        _create_index(name, "quality_audit_report_trackers", cols)

    if not _has_table("quality_car_extension_requests"):
        op.create_table(
            "quality_car_extension_requests",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("car_id", sa.UUID(), nullable=False),
            sa.Column("requested_due_date", sa.Date(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
            sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["car_id"], ["quality_cars.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_quality_car_extension_status"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index("ix_quality_car_ext_car_status", "quality_car_extension_requests", ["car_id", "status"])
    _create_index("ix_quality_car_extension_requests_amo_id", "quality_car_extension_requests", ["amo_id"])

    if not _has_table("quality_reminder_milestones"):
        op.create_table(
            "quality_reminder_milestones",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("entity_id", sa.String(length=64), nullable=False),
            sa.Column("milestone_key", sa.String(length=64), nullable=False),
            sa.Column("recipient_user_id", sa.String(length=36), nullable=True),
            sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("severity", sa.String(length=32), nullable=False, server_default="ACTION_REQUIRED"),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    for name, cols in {
        "ix_quality_reminder_entity_key": ["amo_id", "entity_type", "entity_id", "milestone_key"],
        "ix_quality_reminder_due_unsent": ["amo_id", "scheduled_for", "sent_at"],
        "ix_quality_reminder_milestones_recipient_user_id": ["recipient_user_id"],
    }.items():
        _create_index(name, "quality_reminder_milestones", cols)

    if not _has_table("quality_archive_packages"):
        op.create_table(
            "quality_archive_packages",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("audit_id", sa.UUID(), nullable=False),
            sa.Column("package_ref", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="READY"),
            sa.Column("file_ref", sa.String(length=512), nullable=True),
            sa.Column("metrics_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("generated_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.CheckConstraint("status IN ('READY','LOCKED','SUPERSEDED')", name="ck_quality_archive_status"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("amo_id", "audit_id", "package_ref", name="uq_quality_archive_package_ref"),
        )
    _create_index("ix_quality_archive_audit_generated", "quality_archive_packages", ["audit_id", "generated_at"])
    _create_index("ix_quality_archive_packages_amo_id", "quality_archive_packages", ["amo_id"])


def downgrade() -> None:
    for table in [
        "quality_archive_packages",
        "quality_reminder_milestones",
        "quality_car_extension_requests",
        "quality_audit_report_trackers",
        "quality_audit_post_briefs",
        "quality_audit_checklist_items",
        "quality_audit_document_requests",
        "quality_tenant_workflow_settings",
    ]:
        if _has_table(table):
            op.drop_table(table)
