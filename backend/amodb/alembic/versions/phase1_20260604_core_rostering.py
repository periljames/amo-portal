"""phase1 core duty rostering

Revision ID: phase1_20260604
Revises: phase0_20260604
Create Date: 2026-06-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "phase1_20260604"
down_revision = "phase0_20260604"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shift_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("default_start_time", sa.String(length=5), nullable=True),
        sa.Column("default_end_time", sa.String(length=5), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("counts_as_duty", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("duration_minutes IS NULL OR duration_minutes >= 0", name="ck_shift_template_duration_nonneg"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "code", name="uq_shift_templates_amo_code"),
    )
    op.create_index("ix_shift_templates_amo_active", "shift_templates", ["amo_id", "is_active"])
    op.create_index(op.f("ix_shift_templates_amo_id"), "shift_templates", ["amo_id"])
    op.create_index(op.f("ix_shift_templates_kind"), "shift_templates", ["kind"])
    op.create_index(op.f("ix_shift_templates_counts_as_duty"), "shift_templates", ["counts_as_duty"])
    op.create_index(op.f("ix_shift_templates_is_active"), "shift_templates", ["is_active"])
    op.create_index(op.f("ix_shift_templates_created_by_user_id"), "shift_templates", ["created_by_user_id"])
    op.create_index(op.f("ix_shift_templates_updated_by_user_id"), "shift_templates", ["updated_by_user_id"])

    op.create_table(
        "roster_periods",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("period_code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_roster_period_dates"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "period_code", name="uq_roster_periods_amo_code"),
    )
    op.create_index("ix_roster_periods_amo_dates", "roster_periods", ["amo_id", "starts_on", "ends_on"])
    op.create_index("ix_roster_periods_amo_status", "roster_periods", ["amo_id", "status"])
    op.create_index(op.f("ix_roster_periods_amo_id"), "roster_periods", ["amo_id"])
    op.create_index(op.f("ix_roster_periods_status"), "roster_periods", ["status"])
    op.create_index(op.f("ix_roster_periods_starts_on"), "roster_periods", ["starts_on"])
    op.create_index(op.f("ix_roster_periods_ends_on"), "roster_periods", ["ends_on"])
    op.create_index(op.f("ix_roster_periods_created_by_user_id"), "roster_periods", ["created_by_user_id"])

    op.create_table(
        "roster_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("period_id", sa.String(length=36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("submitted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("published_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version_no >= 1", name="ck_roster_version_no_positive"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["period_id"], ["roster_periods.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period_id", "version_no", name="uq_roster_versions_period_no"),
    )
    op.create_index("ix_roster_versions_amo_status", "roster_versions", ["amo_id", "status"])
    op.create_index("ix_roster_versions_period_status", "roster_versions", ["period_id", "status"])
    op.create_index(op.f("ix_roster_versions_amo_id"), "roster_versions", ["amo_id"])
    op.create_index(op.f("ix_roster_versions_period_id"), "roster_versions", ["period_id"])
    op.create_index(op.f("ix_roster_versions_status"), "roster_versions", ["status"])

    op.create_table(
        "roster_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("base_station_id", sa.String(length=36), nullable=True),
        sa.Column("shift_template_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planned_minutes", sa.Integer(), nullable=True),
        sa.Column("role_label", sa.String(length=128), nullable=True),
        sa.Column("task_note", sa.Text(), nullable=True),
        sa.Column("locked_after_publish", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_roster_assignment_time_order"),
        sa.CheckConstraint("planned_minutes IS NULL OR planned_minutes >= 0", name="ck_roster_assignment_minutes_nonneg"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["roster_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_station_id"], ["base_stations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["shift_template_id"], ["shift_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_roster_assignments_amo_user_time", "roster_assignments", ["amo_id", "user_id", "starts_at", "ends_at"])
    op.create_index("ix_roster_assignments_version_user", "roster_assignments", ["version_id", "user_id"])
    op.create_index("ix_roster_assignments_base_time", "roster_assignments", ["base_station_id", "starts_at", "ends_at"])
    op.create_index(op.f("ix_roster_assignments_amo_id"), "roster_assignments", ["amo_id"])
    op.create_index(op.f("ix_roster_assignments_user_id"), "roster_assignments", ["user_id"])
    op.create_index(op.f("ix_roster_assignments_version_id"), "roster_assignments", ["version_id"])
    op.create_index(op.f("ix_roster_assignments_shift_template_id"), "roster_assignments", ["shift_template_id"])
    op.create_index(op.f("ix_roster_assignments_status"), "roster_assignments", ["status"])
    op.create_index(op.f("ix_roster_assignments_starts_at"), "roster_assignments", ["starts_at"])
    op.create_index(op.f("ix_roster_assignments_ends_at"), "roster_assignments", ["ends_at"])
    op.create_index(op.f("ix_roster_assignments_locked_after_publish"), "roster_assignments", ["locked_after_publish"])

    op.create_table(
        "roster_validation_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["roster_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignment_id"], ["roster_assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_roster_validation_version_severity", "roster_validation_findings", ["version_id", "severity"])
    op.create_index("ix_roster_validation_amo_user", "roster_validation_findings", ["amo_id", "user_id"])
    op.create_index(op.f("ix_roster_validation_findings_amo_id"), "roster_validation_findings", ["amo_id"])
    op.create_index(op.f("ix_roster_validation_findings_version_id"), "roster_validation_findings", ["version_id"])
    op.create_index(op.f("ix_roster_validation_findings_assignment_id"), "roster_validation_findings", ["assignment_id"])
    op.create_index(op.f("ix_roster_validation_findings_source"), "roster_validation_findings", ["source"])
    op.create_index(op.f("ix_roster_validation_findings_severity"), "roster_validation_findings", ["severity"])
    op.create_index(op.f("ix_roster_validation_findings_code"), "roster_validation_findings", ["code"])
    op.create_index(op.f("ix_roster_validation_findings_resolved"), "roster_validation_findings", ["resolved"])

    op.create_table(
        "roster_publication_acknowledgements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledgement_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["roster_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "user_id", name="uq_roster_ack_version_user"),
    )
    op.create_index("ix_roster_ack_amo_user", "roster_publication_acknowledgements", ["amo_id", "user_id"])
    op.create_index(op.f("ix_roster_publication_acknowledgements_amo_id"), "roster_publication_acknowledgements", ["amo_id"])
    op.create_index(op.f("ix_roster_publication_acknowledgements_version_id"), "roster_publication_acknowledgements", ["version_id"])
    op.create_index(op.f("ix_roster_publication_acknowledgements_user_id"), "roster_publication_acknowledgements", ["user_id"])

    op.create_table(
        "roster_task_assignment_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("roster_assignment_id", sa.String(length=36), nullable=False),
        sa.Column("task_assignment_id", sa.Integer(), nullable=False),
        sa.Column("allocated_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("allocated_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("allocated_hours", sa.Float(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("allocated_end IS NULL OR allocated_start IS NULL OR allocated_end > allocated_start", name="ck_roster_task_link_time_order"),
        sa.CheckConstraint("allocated_hours IS NULL OR allocated_hours >= 0", name="ck_roster_task_link_hours_nonneg"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["roster_assignment_id"], ["roster_assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_assignment_id"], ["task_assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("roster_assignment_id", "task_assignment_id", name="uq_roster_task_assignment_link"),
    )
    op.create_index("ix_roster_task_links_amo_task", "roster_task_assignment_links", ["amo_id", "task_assignment_id"])
    op.create_index(op.f("ix_roster_task_assignment_links_amo_id"), "roster_task_assignment_links", ["amo_id"])
    op.create_index(op.f("ix_roster_task_assignment_links_roster_assignment_id"), "roster_task_assignment_links", ["roster_assignment_id"])
    op.create_index(op.f("ix_roster_task_assignment_links_task_assignment_id"), "roster_task_assignment_links", ["task_assignment_id"])
    op.create_index(op.f("ix_roster_task_assignment_links_created_by_user_id"), "roster_task_assignment_links", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_table("roster_task_assignment_links")
    op.drop_table("roster_publication_acknowledgements")
    op.drop_table("roster_validation_findings")
    op.drop_table("roster_assignments")
    op.drop_table("roster_versions")
    op.drop_table("roster_periods")
    op.drop_table("shift_templates")
