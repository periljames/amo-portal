"""Add governed multi-sheet training workbook imports, licences and matrices.

Revision ID: training_260804_workbook
Revises: quality_260804_trigger_fix
Create Date: 2026-08-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "training_260804_workbook"
down_revision = "quality_260804_trigger_fix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_workbook_import_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("committed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("duplicate_of_job_id", sa.String(36), sa.ForeignKey("training_workbook_import_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column("stage", sa.String(32), nullable=False, server_default="UPLOAD"),
        sa.Column("current_sheet", sa.String(128), nullable=True),
        sa.Column("current_record_label", sa.String(255), nullable=True),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preview_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_training_wb_jobs_amo_idempotency"),
    )
    op.create_index("ix_training_wb_jobs_amo_created", "training_workbook_import_jobs", ["amo_id", "created_at"])
    op.create_index("ix_training_wb_jobs_amo_status", "training_workbook_import_jobs", ["amo_id", "status"])
    op.create_index("ix_training_wb_jobs_hash", "training_workbook_import_jobs", ["amo_id", "file_sha256"])

    op.create_table(
        "training_workbook_import_sheets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("training_workbook_import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sheet_name", sa.String(128), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="VISIBLE"),
        sa.Column("classification", sa.String(32), nullable=False),
        sa.Column("portal_destination", sa.String(255), nullable=False),
        sa.Column("is_operational", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("job_id", "sheet_name", name="uq_training_wb_sheets_job_name"),
    )
    op.create_index("ix_training_wb_sheets_job_order", "training_workbook_import_sheets", ["job_id", "display_order"])

    op.create_table(
        "training_workbook_import_rows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("training_workbook_import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sheet_name", sa.String(128), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("source_key", sa.String(255), nullable=True),
        sa.Column("display_label", sa.String(255), nullable=True),
        sa.Column("proposed_action", sa.String(32), nullable=False, server_default="UNCHANGED"),
        sa.Column("status", sa.String(32), nullable=False, server_default="READY"),
        sa.Column("decision_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("decision", sa.String(48), nullable=True),
        sa.Column("decision_options", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("changes_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("issue_code", sa.String(64), nullable=True),
        sa.Column("issue_message", sa.Text(), nullable=True),
        sa.Column("committed_entity_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("job_id", "sheet_name", "source_row", "entity_type", name="uq_training_wb_rows_identity"),
    )
    op.create_index("ix_training_wb_rows_job_status", "training_workbook_import_rows", ["job_id", "status"])
    op.create_index("ix_training_wb_rows_job_review", "training_workbook_import_rows", ["job_id", "decision_required"])
    op.create_index("ix_training_wb_rows_job_sheet", "training_workbook_import_rows", ["job_id", "sheet_name", "source_row"])

    op.create_table(
        "personnel_licences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("personnel_profile_id", sa.String(36), sa.ForeignKey("personnel_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("authority", sa.String(64), nullable=False),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("licence_number", sa.String(128), nullable=False),
        sa.Column("category_code", sa.String(255), nullable=True),
        sa.Column("category_source", sa.String(64), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("internal_stamp_no", sa.String(255), nullable=True),
        sa.Column("initial_authorization_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_job_id", sa.String(36), sa.ForeignKey("training_workbook_import_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "personnel_profile_id", "authority", "licence_number", name="uq_personnel_licences_identity"),
    )
    op.create_index("ix_personnel_licences_amo_profile", "personnel_licences", ["amo_id", "personnel_profile_id"])
    op.create_index("ix_personnel_licences_amo_user", "personnel_licences", ["amo_id", "user_id"])
    op.create_index("ix_personnel_licences_expiry", "personnel_licences", ["amo_id", "expires_on"])

    op.create_table(
        "training_role_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_job_id", sa.String(36), sa.ForeignKey("training_workbook_import_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "code", name="uq_training_role_groups_amo_code"),
    )
    op.create_index("ix_training_role_groups_amo_active", "training_role_groups", ["amo_id", "is_active"])

    op.create_table(
        "training_person_roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.String(64), nullable=False),
        sa.Column("personnel_profile_id", sa.String(36), sa.ForeignKey("personnel_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role_group_id", sa.String(36), sa.ForeignKey("training_role_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("position", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_job_id", sa.String(36), sa.ForeignKey("training_workbook_import_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "person_id", "role_group_id", name="uq_training_person_roles_identity"),
    )
    op.create_index("ix_training_person_roles_person", "training_person_roles", ["amo_id", "person_id", "is_active"])
    op.create_index("ix_training_person_roles_user", "training_person_roles", ["amo_id", "user_id", "is_active"])

    op.create_table(
        "training_course_role_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("training_courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_group_id", sa.String(36), sa.ForeignKey("training_role_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("requirement_type", sa.String(64), nullable=False, server_default="GENERAL"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_job_id", sa.String(36), sa.ForeignKey("training_workbook_import_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "course_id", "role_group_id", "requirement_type", name="uq_training_course_role_rules_identity"),
    )
    op.create_index("ix_training_course_role_rules_course", "training_course_role_rules", ["amo_id", "course_id", "is_active"])
    op.create_index("ix_training_course_role_rules_group", "training_course_role_rules", ["amo_id", "role_group_id", "is_active"])


def downgrade() -> None:
    op.drop_table("training_course_role_rules")
    op.drop_table("training_person_roles")
    op.drop_table("training_role_groups")
    op.drop_table("personnel_licences")
    op.drop_table("training_workbook_import_rows")
    op.drop_table("training_workbook_import_sheets")
    op.drop_table("training_workbook_import_jobs")
