"""Add corporate structure and personnel governance domain.

Revision ID: accounts_20260805_corporate_structure
Revises: accounts_20260803_auth_session
Create Date: 2026-08-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "accounts_20260805_corporate_structure"
down_revision = "accounts_20260803_auth_session"
branch_labels = None
depends_on = None


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "organization_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("organization_units.id", ondelete="SET NULL"), nullable=True),
        sa.Column("department_id", sa.String(36), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("base_station_id", sa.String(36), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("unit_type", sa.String(32), nullable=False, server_default="DEPARTMENT"),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("cost_center", sa.String(64), nullable=True),
        sa.Column("accountable_manager_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("manager_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deputy_manager_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quality_owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("headcount_limit", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("amo_id", "code", name="uq_org_units_amo_code"),
        sa.CheckConstraint("headcount_limit IS NULL OR headcount_limit >= 0", name="ck_org_units_headcount_nonnegative"),
    )
    op.create_index("ix_org_units_amo_parent", "organization_units", ["amo_id", "parent_id"])
    op.create_index("ix_org_units_amo_type_active", "organization_units", ["amo_id", "unit_type", "is_active"])
    op.create_index("ix_organization_units_department_id", "organization_units", ["department_id"])
    op.create_index("ix_organization_units_base_station_id", "organization_units", ["base_station_id"])

    op.create_table(
        "organization_positions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_id", sa.String(36), sa.ForeignKey("organization_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reports_to_position_id", sa.String(36), sa.ForeignKey("organization_positions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("job_family", sa.String(128), nullable=True),
        sa.Column("grade", sa.String(64), nullable=True),
        sa.Column("employment_category", sa.String(32), nullable=False, server_default="EMPLOYEE"),
        sa.Column("headcount_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_supervisory", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_regulatory_post", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("regulatory_post_type", sa.String(64), nullable=True),
        sa.Column("authority_acceptance_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("minimum_competence_summary", sa.Text(), nullable=True),
        sa.Column("responsibilities", sa.Text(), nullable=True),
        sa.Column("approval_scope", sa.Text(), nullable=True),
        sa.Column("default_account_role", sa.String(64), nullable=True),
        sa.Column("succession_criticality", sa.String(32), nullable=False, server_default="STANDARD"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("amo_id", "code", name="uq_org_positions_amo_code"),
        sa.CheckConstraint("headcount_limit >= 1", name="ck_org_positions_headcount_positive"),
    )
    op.create_index("ix_org_positions_unit_active", "organization_positions", ["unit_id", "is_active"])
    op.create_index("ix_organization_positions_amo_id", "organization_positions", ["amo_id"])
    op.create_index("ix_organization_positions_reports_to", "organization_positions", ["reports_to_position_id"])
    op.create_index("ix_organization_positions_regulatory", "organization_positions", ["is_regulatory_post"])

    op.create_table(
        "position_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position_id", sa.String(36), sa.ForeignKey("organization_positions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reporting_manager_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assignment_type", sa.String(32), nullable=False, server_default="SUBSTANTIVE"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("matrix_reporting", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("matrix_reason", sa.Text(), nullable=True),
        sa.Column("fte_percent", sa.Numeric(5, 2), nullable=False, server_default="100"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("appointment_reference", sa.String(128), nullable=True),
        sa.Column("authority_acceptance_reference", sa.String(128), nullable=True),
        sa.Column("authority_accepted_on", sa.Date(), nullable=True),
        sa.Column("delegation_limitations", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("fte_percent > 0 AND fte_percent <= 100", name="ck_position_assignments_fte_range"),
    )
    op.create_index("ix_position_assignments_amo_user_status", "position_assignments", ["amo_id", "user_id", "status"])
    op.create_index("ix_position_assignments_position_dates", "position_assignments", ["position_id", "effective_from", "effective_to"])
    op.create_index("ix_position_assignments_manager", "position_assignments", ["reporting_manager_user_id"])
    op.create_index("ix_position_assignments_primary", "position_assignments", ["is_primary"])

    op.create_table(
        "workforce_engagements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_type", sa.String(32), nullable=False, server_default="EMPLOYEE"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("contract_reference", sa.String(128), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("probation_months", sa.Integer(), nullable=True),
        sa.Column("sponsor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_organisation", sa.String(255), nullable=True),
        sa.Column("institution_or_vendor", sa.String(255), nullable=True),
        sa.Column("programme_name", sa.String(255), nullable=True),
        sa.Column("learning_objectives", sa.Text(), nullable=True),
        sa.Column("work_permit_status", sa.String(32), nullable=True),
        sa.Column("work_permit_reference", sa.String(128), nullable=True),
        sa.Column("work_permit_expires_on", sa.Date(), nullable=True),
        sa.Column("background_check_status", sa.String(32), nullable=True),
        sa.Column("access_expiry_on", sa.Date(), nullable=True),
        sa.Column("offboarding_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("probation_months IS NULL OR probation_months >= 0", name="ck_workforce_engagements_probation_nonnegative"),
    )
    op.create_index("ix_workforce_engagements_amo_user_status", "workforce_engagements", ["amo_id", "user_id", "status"])
    op.create_index("ix_workforce_engagements_type", "workforce_engagements", ["engagement_type"])
    op.create_index("ix_workforce_engagements_sponsor", "workforce_engagements", ["sponsor_user_id"])

    op.create_table(
        "group_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_id", sa.String(36), sa.ForeignKey("organization_units.id", ondelete="SET NULL"), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("inheritance_mode", sa.String(32), nullable=False, server_default="UNIT_AND_DESCENDANTS"),
        sa.Column("membership_mode", sa.String(32), nullable=False, server_default="MANUAL"),
        sa.Column("default_account_role", sa.String(64), nullable=True),
        sa.Column("permission_template_json", sa.Text(), nullable=True),
        sa.Column("segregation_tags_json", sa.Text(), nullable=True),
        sa.Column("requires_manager_approval", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("requires_quality_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("maximum_assignment_days", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("amo_id", "code", name="uq_group_policies_amo_code"),
    )
    op.create_index("ix_group_policies_group_active", "group_policies", ["group_id", "is_active"])
    op.create_index("ix_group_policies_amo_id", "group_policies", ["amo_id"])
    op.create_index("ix_group_policies_unit_id", "group_policies", ["unit_id"])

    op.create_table(
        "personnel_compliance_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=True),
        sa.Column("preferred_name", sa.String(128), nullable=True),
        sa.Column("nationality", sa.String(64), nullable=True),
        sa.Column("residence_country", sa.String(64), nullable=True),
        sa.Column("identity_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("identity_reference", sa.String(128), nullable=True),
        sa.Column("identity_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("identity_verified_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("emergency_contact_name", sa.String(255), nullable=True),
        sa.Column("emergency_contact_relationship", sa.String(64), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(64), nullable=True),
        sa.Column("data_classification", sa.String(32), nullable=False, server_default="CONFIDENTIAL"),
        sa.Column("retention_class", sa.String(64), nullable=False, server_default="PERSONNEL_ACTIVE_PLUS_RETENTION"),
        sa.Column("confidentiality_ack_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code_of_conduct_ack_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conflict_declaration_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("competence_status", sa.String(32), nullable=False, server_default="NOT_ASSESSED"),
        sa.Column("training_status", sa.String(32), nullable=False, server_default="NOT_ASSESSED"),
        sa.Column("authorisation_status", sa.String(32), nullable=False, server_default="NOT_APPLICABLE"),
        sa.Column("medical_fitness_status", sa.String(32), nullable=False, server_default="NOT_APPLICABLE"),
        sa.Column("last_competence_assessment_on", sa.Date(), nullable=True),
        sa.Column("next_review_on", sa.Date(), nullable=True),
        sa.Column("compliance_owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("restrictions", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("amo_id", "user_id", name="uq_personnel_compliance_profiles_amo_user"),
    )
    op.create_index("ix_personnel_compliance_profiles_review", "personnel_compliance_profiles", ["amo_id", "next_review_on"])
    op.create_index("ix_personnel_compliance_profiles_competence", "personnel_compliance_profiles", ["competence_status"])
    op.create_index("ix_personnel_compliance_profiles_training", "personnel_compliance_profiles", ["training_status"])

    op.create_table(
        "personnel_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_type", sa.String(32), nullable=False),
        sa.Column("authority", sa.String(128), nullable=True),
        sa.Column("reference", sa.String(128), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("scope_json", sa.Text(), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="VALID"),
        sa.Column("evidence_document_id", sa.String(36), nullable=True),
        sa.Column("verified_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restrictions", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("amo_id", "user_id", "credential_type", "reference", name="uq_personnel_credentials_identity"),
    )
    op.create_index("ix_personnel_credentials_expiry", "personnel_credentials", ["amo_id", "expires_on", "status"])
    op.create_index("ix_personnel_credentials_user_id", "personnel_credentials", ["user_id"])
    op.create_index("ix_personnel_credentials_type", "personnel_credentials", ["credential_type"])


def downgrade() -> None:
    op.drop_table("personnel_credentials")
    op.drop_table("personnel_compliance_profiles")
    op.drop_table("group_policies")
    op.drop_table("workforce_engagements")
    op.drop_table("position_assignments")
    op.drop_table("organization_positions")
    op.drop_table("organization_units")
