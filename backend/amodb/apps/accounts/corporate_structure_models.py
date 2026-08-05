"""Tenant-scoped corporate structure and workforce-governance models.

These records intentionally separate portal access roles from corporate positions,
reporting lines, engagement terms and aviation competence evidence.  A user's
login role must never be treated as proof that the person is appointed, competent
or authorised for an aviation function.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from amodb.database import Base
from amodb.user_id import generate_user_id


class OrganizationUnit(Base):
    __tablename__ = "organization_units"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_org_units_amo_code"),
        Index("ix_org_units_amo_parent", "amo_id", "parent_id"),
        Index("ix_org_units_amo_type_active", "amo_id", "unit_type", "is_active"),
        CheckConstraint("headcount_limit IS NULL OR headcount_limit >= 0", name="ck_org_units_headcount_nonnegative"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String(36), ForeignKey("organization_units.id", ondelete="SET NULL"), nullable=True, index=True)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    base_station_id = Column(
        String(36),
        ForeignKey("base_stations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    unit_type = Column(String(32), nullable=False, default="DEPARTMENT", index=True)
    purpose = Column(Text, nullable=True)
    cost_center = Column(String(64), nullable=True)
    accountable_manager_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    manager_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    deputy_manager_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    quality_owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    headcount_limit = Column(Integer, nullable=True)
    sort_order = Column(Integer, nullable=False, default=100)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class OrganizationPosition(Base):
    __tablename__ = "organization_positions"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_org_positions_amo_code"),
        Index("ix_org_positions_unit_active", "unit_id", "is_active"),
        CheckConstraint("headcount_limit >= 1", name="ck_org_positions_headcount_positive"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_id = Column(String(36), ForeignKey("organization_units.id", ondelete="CASCADE"), nullable=False, index=True)
    reports_to_position_id = Column(String(36), ForeignKey("organization_positions.id", ondelete="SET NULL"), nullable=True, index=True)
    code = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    job_family = Column(String(128), nullable=True)
    grade = Column(String(64), nullable=True)
    employment_category = Column(String(32), nullable=False, default="EMPLOYEE")
    headcount_limit = Column(Integer, nullable=False, default=1)
    is_supervisory = Column(Boolean, nullable=False, default=False)
    is_regulatory_post = Column(Boolean, nullable=False, default=False, index=True)
    regulatory_post_type = Column(String(64), nullable=True)
    authority_acceptance_required = Column(Boolean, nullable=False, default=False)
    minimum_competence_summary = Column(Text, nullable=True)
    responsibilities = Column(Text, nullable=True)
    approval_scope = Column(Text, nullable=True)
    default_account_role = Column(String(64), nullable=True)
    succession_criticality = Column(String(32), nullable=False, default="STANDARD")
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PositionAssignment(Base):
    __tablename__ = "position_assignments"
    __table_args__ = (
        Index("ix_position_assignments_amo_user_status", "amo_id", "user_id", "status"),
        Index("ix_position_assignments_position_dates", "position_id", "effective_from", "effective_to"),
        CheckConstraint("fte_percent > 0 AND fte_percent <= 100", name="ck_position_assignments_fte_range"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_position_assignments_effective_period",
        ),
        CheckConstraint(
            "matrix_reporting = false OR length(trim(coalesce(matrix_reason, ''))) > 0",
            name="ck_position_assignments_matrix_reason",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    position_id = Column(String(36), ForeignKey("organization_positions.id", ondelete="CASCADE"), nullable=False, index=True)
    reporting_manager_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    assignment_type = Column(String(32), nullable=False, default="SUBSTANTIVE")
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    is_primary = Column(Boolean, nullable=False, default=True, index=True)
    matrix_reporting = Column(Boolean, nullable=False, default=False)
    matrix_reason = Column(Text, nullable=True)
    fte_percent = Column(Numeric(5, 2), nullable=False, default=100)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    appointment_reference = Column(String(128), nullable=True)
    authority_acceptance_reference = Column(String(128), nullable=True)
    authority_accepted_on = Column(Date, nullable=True)
    delegation_limitations = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkforceEngagement(Base):
    __tablename__ = "workforce_engagements"
    __table_args__ = (
        Index("ix_workforce_engagements_amo_user_status", "amo_id", "user_id", "status"),
        CheckConstraint("probation_months IS NULL OR probation_months >= 0", name="ck_workforce_engagements_probation_nonnegative"),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_workforce_engagements_effective_period",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    engagement_type = Column(String(32), nullable=False, default="EMPLOYEE", index=True)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    contract_reference = Column(String(128), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    probation_months = Column(Integer, nullable=True)
    sponsor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    external_organisation = Column(String(255), nullable=True)
    institution_or_vendor = Column(String(255), nullable=True)
    programme_name = Column(String(255), nullable=True)
    learning_objectives = Column(Text, nullable=True)
    work_permit_status = Column(String(32), nullable=True)
    work_permit_reference = Column(String(128), nullable=True)
    work_permit_expires_on = Column(Date, nullable=True)
    background_check_status = Column(String(32), nullable=True)
    access_expiry_on = Column(Date, nullable=True)
    offboarding_required = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class GroupPolicy(Base):
    __tablename__ = "group_policies"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_group_policies_amo_code"),
        Index("ix_group_policies_group_active", "group_id", "is_active"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(String(36), ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_id = Column(String(36), ForeignKey("organization_units.id", ondelete="SET NULL"), nullable=True, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    inheritance_mode = Column(String(32), nullable=False, default="UNIT_AND_DESCENDANTS")
    membership_mode = Column(String(32), nullable=False, default="MANUAL")
    default_account_role = Column(String(64), nullable=True)
    permission_template_json = Column(Text, nullable=True)
    segregation_tags_json = Column(Text, nullable=True)
    requires_manager_approval = Column(Boolean, nullable=False, default=True)
    requires_quality_approval = Column(Boolean, nullable=False, default=False)
    maximum_assignment_days = Column(Integer, nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PersonnelComplianceProfile(Base):
    __tablename__ = "personnel_compliance_profiles"
    __table_args__ = (
        UniqueConstraint("amo_id", "user_id", name="uq_personnel_compliance_profiles_amo_user"),
        Index("ix_personnel_compliance_profiles_review", "amo_id", "next_review_on"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    legal_name = Column(String(255), nullable=True)
    preferred_name = Column(String(128), nullable=True)
    nationality = Column(String(64), nullable=True)
    residence_country = Column(String(64), nullable=True)
    identity_verified = Column(Boolean, nullable=False, default=False)
    identity_reference = Column(String(128), nullable=True)
    identity_verified_at = Column(DateTime(timezone=True), nullable=True)
    identity_verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    emergency_contact_name = Column(String(255), nullable=True)
    emergency_contact_relationship = Column(String(64), nullable=True)
    emergency_contact_phone = Column(String(64), nullable=True)
    data_classification = Column(String(32), nullable=False, default="CONFIDENTIAL")
    retention_class = Column(String(64), nullable=False, default="PERSONNEL_ACTIVE_PLUS_RETENTION")
    confidentiality_ack_at = Column(DateTime(timezone=True), nullable=True)
    code_of_conduct_ack_at = Column(DateTime(timezone=True), nullable=True)
    conflict_declaration_at = Column(DateTime(timezone=True), nullable=True)
    competence_status = Column(String(32), nullable=False, default="NOT_ASSESSED", index=True)
    training_status = Column(String(32), nullable=False, default="NOT_ASSESSED", index=True)
    authorisation_status = Column(String(32), nullable=False, default="NOT_APPLICABLE", index=True)
    medical_fitness_status = Column(String(32), nullable=False, default="NOT_APPLICABLE", index=True)
    last_competence_assessment_on = Column(Date, nullable=True)
    next_review_on = Column(Date, nullable=True)
    compliance_owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    restrictions = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PersonnelCredential(Base):
    __tablename__ = "personnel_credentials"
    __table_args__ = (
        UniqueConstraint("amo_id", "user_id", "credential_type", "reference", name="uq_personnel_credentials_identity"),
        Index("ix_personnel_credentials_expiry", "amo_id", "expires_on", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_type = Column(String(32), nullable=False, index=True)
    authority = Column(String(128), nullable=True)
    reference = Column(String(128), nullable=False)
    title = Column(String(255), nullable=True)
    scope_json = Column(Text, nullable=True)
    issued_on = Column(Date, nullable=True)
    expires_on = Column(Date, nullable=True, index=True)
    status = Column(String(32), nullable=False, default="VALID", index=True)
    evidence_document_id = Column(String(36), nullable=True)
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    restrictions = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
