"""Governed aviation Training Operating System models.

This module is additive by design.  Existing Training records, events, certificates,
competence/experience evidence and Accounts authorisations remain canonical.  These
objects add the approval, source-rule, curriculum, facility/provider, examination and
session-governance envelopes required to decide whether an action is permitted.

No authority/manual numeric value belongs in this module as a magic constant.  Rules
are tenant scoped, source attributed, revision aware and effective dated.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrainingAuthority(Base):
    __tablename__ = "training_authorities"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_training_authority_code"),
        Index("ix_training_authority_status", "amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    jurisdiction = Column(String(128), nullable=True)
    authority_type = Column(String(64), nullable=True)
    status = Column(String(24), nullable=False, default="ACTIVE", server_default="ACTIVE")
    metadata_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingGovernanceRule(Base):
    """Effective-dated, source-attributed rule interpreted by governed services."""

    __tablename__ = "training_governance_rules"
    __table_args__ = (
        UniqueConstraint("amo_id", "rule_code", "source_revision_id", "effective_from", name="uq_training_rule_source_effective"),
        Index("ix_training_rule_effective", "amo_id", "rule_code", "status", "effective_from", "effective_to"),
        Index("ix_training_rule_source", "amo_id", "source_document_id", "source_revision_id"),
        CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from", name="ck_training_rule_dates"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_code = Column(String(128), nullable=False)
    authority_id = Column(String(36), ForeignKey("training_authorities.id", ondelete="SET NULL"), nullable=True, index=True)
    source_type = Column(String(32), nullable=False, default="MANUAL", server_default="MANUAL")
    source_document_id = Column(String(64), nullable=True, index=True)
    source_revision_id = Column(String(64), nullable=True, index=True)
    source_title = Column(String(255), nullable=True)
    source_section = Column(String(128), nullable=True)
    source_paragraph = Column(String(128), nullable=True)
    applicability = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    value_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    condition_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    severity = Column(String(32), nullable=False, default="BLOCK", server_default="BLOCK")
    exception_permitted = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    exception_approver_capability = Column(String(128), nullable=True)
    evidence_required = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    status = Column(String(24), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingGovernanceConflict(Base):
    __tablename__ = "training_governance_conflicts"
    __table_args__ = (
        Index("ix_training_governance_conflict_queue", "amo_id", "status", "rule_code", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_code = Column(String(128), nullable=False)
    rule_ids = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    conflict_summary = Column(Text, nullable=False)
    affected_context = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    status = Column(String(24), nullable=False, default="OPEN", server_default="OPEN")
    resolution = Column(Text, nullable=True)
    resolved_rule_id = Column(String(36), ForeignKey("training_governance_rules.id", ondelete="SET NULL"), nullable=True)
    resolved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingApproval(Base):
    __tablename__ = "training_approvals"
    __table_args__ = (
        UniqueConstraint("amo_id", "approval_number", name="uq_training_approval_number"),
        Index("ix_training_approval_status", "amo_id", "approval_type", "status", "expiry_date"),
        CheckConstraint("expiry_date IS NULL OR effective_date IS NULL OR expiry_date >= effective_date", name="ck_training_approval_dates"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    authority_id = Column(String(36), ForeignKey("training_authorities.id", ondelete="RESTRICT"), nullable=False, index=True)
    approval_number = Column(String(128), nullable=False)
    approval_type = Column(String(64), nullable=False)
    title = Column(String(255), nullable=True)
    effective_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    limitations = Column(Text, nullable=True)
    supporting_dms_document_id = Column(String(64), nullable=True)
    supporting_dms_revision_id = Column(String(64), nullable=True)
    authority_correspondence_id = Column(String(64), nullable=True)
    recognition_json = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingApprovalScope(Base):
    __tablename__ = "training_approval_scopes"
    __table_args__ = (
        Index("ix_training_approval_scope_lookup", "amo_id", "approval_id", "scope_type", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    approval_id = Column(String(36), ForeignKey("training_approvals.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_type = Column(String(32), nullable=False)
    course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="SET NULL"), nullable=True, index=True)
    facility_id = Column(String(36), nullable=True, index=True)
    provider_id = Column(String(36), nullable=True, index=True)
    aircraft = Column(String(128), nullable=True)
    engine = Column(String(128), nullable=True)
    component_system = Column(String(255), nullable=True)
    training_level = Column(String(64), nullable=True)
    theory_privilege = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    practical_privilege = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    limitations = Column(Text, nullable=True)
    applicability = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    status = Column(String(24), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingTechnicalAuthorisation(Base):
    """Instructor/examiner/assessor/OJT authorisation; never inferred from RBAC."""

    __tablename__ = "training_technical_authorisations"
    __table_args__ = (
        Index("ix_training_technical_auth_person", "amo_id", "user_id", "privilege_type", "status", "expiry_date"),
        CheckConstraint("expiry_date IS NULL OR issue_date IS NULL OR expiry_date >= issue_date", name="ck_training_technical_auth_dates"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    privilege_type = Column(String(24), nullable=False)  # INSTRUCTOR / EXAMINER / ASSESSOR / OJT
    authority_id = Column(String(36), ForeignKey("training_authorities.id", ondelete="SET NULL"), nullable=True, index=True)
    approval_id = Column(String(36), ForeignKey("training_approvals.id", ondelete="SET NULL"), nullable=True, index=True)
    aircraft = Column(String(128), nullable=True)
    engine = Column(String(128), nullable=True)
    system_scope = Column(String(255), nullable=True)
    course_ids = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    theoretical_privilege = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    practical_privilege = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    ojt_privilege = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    limitations = Column(Text, nullable=True)
    licence_dependency = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    training_dependencies = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    observation_requirements = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    recurrent_requirements = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    appointment_authority = Column(String(255), nullable=True)
    issue_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    evidence_json = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    issued_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    suspended_reason = Column(Text, nullable=True)
    revoked_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingCourseRevision(Base):
    __tablename__ = "training_course_revisions"
    __table_args__ = (
        UniqueConstraint("amo_id", "course_id", "revision_no", name="uq_training_course_revision"),
        Index("ix_training_course_revision_active", "amo_id", "course_id", "status", "effective_from"),
        CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from", name="ck_training_course_revision_dates"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_no = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    authority_id = Column(String(36), ForeignKey("training_authorities.id", ondelete="SET NULL"), nullable=True)
    course_approval_id = Column(String(36), ForeignKey("training_approvals.id", ondelete="SET NULL"), nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    theory_hours = Column(Numeric(8, 2), nullable=False, default=0, server_default="0")
    practical_hours = Column(Numeric(8, 2), nullable=False, default=0, server_default="0")
    total_hours = Column(Numeric(8, 2), nullable=False, default=0, server_default="0")
    delivery_methods = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    completion_rules = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    assessment_blueprint = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    instructor_requirements = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    facility_requirements = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    certificate_rules = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    source_document_id = Column(String(64), nullable=True)
    source_revision_id = Column(String(64), nullable=True)
    source_section = Column(String(128), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingCourseModule(Base):
    __tablename__ = "training_course_modules"
    __table_args__ = (
        UniqueConstraint("course_revision_id", "sequence_no", name="uq_training_course_module_sequence"),
        Index("ix_training_course_module_course", "amo_id", "course_revision_id", "sequence_no"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    course_revision_id = Column(String(36), ForeignKey("training_course_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_no = Column(Integer, nullable=False)
    code = Column(String(64), nullable=True)
    subject = Column(String(255), nullable=False)
    theory_hours = Column(Numeric(8, 2), nullable=False, default=0, server_default="0")
    practical_hours = Column(Numeric(8, 2), nullable=False, default=0, server_default="0")
    delivery_method = Column(String(64), nullable=True)
    required_materials = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    manual_references = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    assessment_requirements = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    instructor_requirements = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    required = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingLearningObjective(Base):
    __tablename__ = "training_learning_objectives"
    __table_args__ = (
        UniqueConstraint("module_id", "code", name="uq_training_learning_objective_code"),
        Index("ix_training_learning_objective_module", "amo_id", "module_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(String(36), ForeignKey("training_course_modules.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    statement = Column(Text, nullable=False)
    knowledge_level = Column(String(32), nullable=True)
    competency_reference = Column(String(128), nullable=True)
    assessment_required = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingPracticalTask(Base):
    __tablename__ = "training_practical_tasks"
    __table_args__ = (
        UniqueConstraint("course_revision_id", "code", name="uq_training_practical_task_code"),
        Index("ix_training_practical_task_course", "amo_id", "course_revision_id", "required"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    course_revision_id = Column(String(36), ForeignKey("training_course_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(String(36), ForeignKey("training_course_modules.id", ondelete="SET NULL"), nullable=True, index=True)
    code = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    competency_reference = Column(String(128), nullable=True)
    evidence_requirements = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    assessor_requirements = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    required = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingCoursePrerequisite(Base):
    __tablename__ = "training_course_prerequisites"
    __table_args__ = (
        Index("ix_training_course_prerequisite_course", "amo_id", "course_revision_id", "group_key"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    course_revision_id = Column(String(36), ForeignKey("training_course_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    group_key = Column(String(64), nullable=False, default="ROOT", server_default="ROOT")
    group_operator = Column(String(8), nullable=False, default="AND", server_default="AND")
    requirement_type = Column(String(32), nullable=False)
    requirement_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    required = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingCourseReference(Base):
    __tablename__ = "training_course_references"
    __table_args__ = (
        Index("ix_training_course_reference_source", "amo_id", "source_document_id", "source_revision_id"),
        Index("ix_training_course_reference_course", "amo_id", "course_revision_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    course_revision_id = Column(String(36), ForeignKey("training_course_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(String(36), ForeignKey("training_course_modules.id", ondelete="SET NULL"), nullable=True)
    source_document_id = Column(String(64), nullable=False)
    source_revision_id = Column(String(64), nullable=False)
    section = Column(String(128), nullable=True)
    paragraph = Column(String(128), nullable=True)
    reference_type = Column(String(32), nullable=False, default="REQUIRED", server_default="REQUIRED")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingMaterialRevision(Base):
    __tablename__ = "training_material_revisions"
    __table_args__ = (
        UniqueConstraint("amo_id", "material_code", "revision_no", name="uq_training_material_revision"),
        Index("ix_training_material_active", "amo_id", "course_revision_id", "status", "effective_from"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    course_revision_id = Column(String(36), ForeignKey("training_course_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    material_code = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    revision_no = Column(Integer, nullable=False)
    material_type = Column(String(32), nullable=False)
    dms_document_id = Column(String(64), nullable=True)
    dms_revision_id = Column(String(64), nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    required = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingFacility(Base):
    __tablename__ = "training_facilities"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_training_facility_code"),
        Index("ix_training_facility_status", "amo_id", "facility_type", "status", "expiry_date"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    facility_type = Column(String(32), nullable=False, default="PERMANENT", server_default="PERMANENT")
    address = Column(Text, nullable=True)
    approval_id = Column(String(36), ForeignKey("training_approvals.id", ondelete="SET NULL"), nullable=True, index=True)
    authority_id = Column(String(36), ForeignKey("training_authorities.id", ondelete="SET NULL"), nullable=True)
    approved_scope = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    classroom_capacity = Column(Integer, nullable=True)
    practical_capacity = Column(Integer, nullable=True)
    equipment = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    training_aids = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    technical_library_access = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    product_access = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    contracts = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    restrictions = Column(Text, nullable=True)
    evidence_json = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    expiry_date = Column(Date, nullable=True)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingProvider(Base):
    __tablename__ = "training_providers_governed"
    __table_args__ = (
        UniqueConstraint("amo_id", "legal_name", name="uq_training_provider_legal_name"),
        Index("ix_training_provider_status", "amo_id", "status", "expiry_date"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    legal_name = Column(String(255), nullable=False)
    authority_id = Column(String(36), ForeignKey("training_authorities.id", ondelete="SET NULL"), nullable=True)
    approval_id = Column(String(36), ForeignKey("training_approvals.id", ondelete="SET NULL"), nullable=True)
    approval_number = Column(String(128), nullable=True)
    approved_scope = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    recognition_status = Column(String(32), nullable=False, default="UNVERIFIED", server_default="UNVERIFIED")
    locations = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    audits = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    contracts = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    findings = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    evidence_json = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    approved_course_ids = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    approved_instructor_ids = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    effective_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingSessionGovernance(Base):
    __tablename__ = "training_session_governance"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_training_session_governance_event"),
        Index("ix_training_session_governance_status", "amo_id", "status", "readiness_status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="CASCADE"), nullable=False, index=True)
    course_revision_id = Column(String(36), ForeignKey("training_course_revisions.id", ondelete="RESTRICT"), nullable=False, index=True)
    facility_id = Column(String(36), ForeignKey("training_facilities.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_id = Column(String(36), ForeignKey("training_providers_governed.id", ondelete="SET NULL"), nullable=True, index=True)
    instructor_authorisation_ids = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    examiner_authorisation_ids = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    assessor_authorisation_ids = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    readiness_status = Column(String(24), nullable=False, default="NOT_EVALUATED", server_default="NOT_EVALUATED")
    readiness_snapshot = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    readiness_evaluated_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(24), nullable=False, default="PLANNED", server_default="PLANNED")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingModuleAttendance(Base):
    __tablename__ = "training_module_attendance"
    __table_args__ = (
        UniqueConstraint("amo_id", "event_id", "module_id", "user_id", name="uq_training_module_attendance"),
        Index("ix_training_module_attendance_user", "amo_id", "event_id", "user_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(String(36), ForeignKey("training_course_modules.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="ATTENDED", server_default="ATTENDED")
    attended_minutes = Column(Integer, nullable=True)
    evidence_json = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    validated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    correction_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingPracticalAssessment(Base):
    __tablename__ = "training_practical_assessments"
    __table_args__ = (
        UniqueConstraint("amo_id", "event_id", "practical_task_id", "user_id", name="uq_training_practical_assessment"),
        Index("ix_training_practical_assessment_user", "amo_id", "event_id", "user_id", "result"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="CASCADE"), nullable=False, index=True)
    practical_task_id = Column(String(36), ForeignKey("training_practical_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assessor_authorisation_id = Column(String(36), ForeignKey("training_technical_authorisations.id", ondelete="RESTRICT"), nullable=False)
    result = Column(String(32), nullable=False)
    evidence_json = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    comments = Column(Text, nullable=True)
    assessed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingQuestionBankItem(Base):
    __tablename__ = "training_question_bank_items"
    __table_args__ = (
        UniqueConstraint("amo_id", "question_code", name="uq_training_question_code"),
        Index("ix_training_question_status", "amo_id", "status", "course_revision_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    question_code = Column(String(64), nullable=False)
    course_revision_id = Column(String(36), ForeignKey("training_course_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(String(36), ForeignKey("training_course_modules.id", ondelete="SET NULL"), nullable=True)
    learning_objective_id = Column(String(36), ForeignKey("training_learning_objectives.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    exposure_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingQuestionRevision(Base):
    __tablename__ = "training_question_revisions"
    __table_args__ = (
        UniqueConstraint("question_id", "revision_no", name="uq_training_question_revision"),
        Index("ix_training_question_revision_active", "amo_id", "question_id", "status", "effective_from"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(36), ForeignKey("training_question_bank_items.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_no = Column(Integer, nullable=False)
    prompt = Column(Text, nullable=False)
    options_json = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    answer_key_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    explanation = Column(Text, nullable=True)
    ata_chapter = Column(String(32), nullable=True)
    knowledge_level = Column(String(32), nullable=True)
    difficulty = Column(Numeric(6, 3), nullable=True)
    marks = Column(Numeric(8, 2), nullable=False, default=1, server_default="1")
    source_document_id = Column(String(64), nullable=True)
    source_revision_id = Column(String(64), nullable=True)
    source_section = Column(String(128), nullable=True)
    author_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingExamBlueprint(Base):
    __tablename__ = "training_exam_blueprints"
    __table_args__ = (
        UniqueConstraint("amo_id", "course_revision_id", "revision_no", name="uq_training_exam_blueprint_revision"),
        Index("ix_training_exam_blueprint_active", "amo_id", "course_revision_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    course_revision_id = Column(String(36), ForeignKey("training_course_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_no = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    selection_rules = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    result_rules = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    security_rules = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingExamGeneration(Base):
    __tablename__ = "training_exam_generations"
    __table_args__ = (
        UniqueConstraint("amo_id", "generation_code", name="uq_training_exam_generation_code"),
        Index("ix_training_exam_generation_event", "amo_id", "event_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    generation_code = Column(String(64), nullable=False)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id = Column(String(36), ForeignKey("training_exam_blueprints.id", ondelete="RESTRICT"), nullable=False)
    question_revision_ids = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    generated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    status = Column(String(24), nullable=False, default="ACTIVE", server_default="ACTIVE")
    security_metadata = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))


class TrainingExamAttempt(Base):
    __tablename__ = "training_exam_attempts_governed"
    __table_args__ = (
        Index("ix_training_exam_attempt_user", "amo_id", "user_id", "event_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    generation_id = Column(String(36), ForeignKey("training_exam_generations.id", ondelete="RESTRICT"), nullable=False)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_no = Column(Integer, nullable=False, default=1, server_default="1")
    status = Column(String(24), nullable=False, default="NOT_STARTED", server_default="NOT_STARTED")
    score = Column(Numeric(8, 3), nullable=True)
    result = Column(String(24), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    proctor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingExamAttemptItem(Base):
    __tablename__ = "training_exam_attempt_items"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_revision_id", name="uq_training_exam_attempt_question"),
        Index("ix_training_exam_attempt_item_attempt", "amo_id", "attempt_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_id = Column(String(36), ForeignKey("training_exam_attempts_governed.id", ondelete="CASCADE"), nullable=False, index=True)
    question_revision_id = Column(String(36), ForeignKey("training_question_revisions.id", ondelete="RESTRICT"), nullable=False)
    response_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    awarded_marks = Column(Numeric(8, 2), nullable=True)
    correct = Column(Boolean, nullable=True)
    manual_mark_required = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    marked_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    marked_at = Column(DateTime(timezone=True), nullable=True)


class TrainingExamSecurityEvent(Base):
    __tablename__ = "training_exam_security_events"
    __table_args__ = (Index("ix_training_exam_security_attempt", "amo_id", "attempt_id", "severity", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_id = Column(String(36), ForeignKey("training_exam_attempts_governed.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    severity = Column(String(24), nullable=False, default="INFO", server_default="INFO")
    details_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    recorded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingImpactAssessment(Base):
    __tablename__ = "training_impact_assessments"
    __table_args__ = (Index("ix_training_impact_queue", "amo_id", "status", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id = Column(String(64), nullable=False, index=True)
    previous_revision_id = Column(String(64), nullable=True)
    new_revision_id = Column(String(64), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="PREVIEW", server_default="PREVIEW")
    summary_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    blockers_json = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    approved_at = Column(DateTime(timezone=True), nullable=True)


class TrainingImpactItem(Base):
    __tablename__ = "training_impact_items"
    __table_args__ = (Index("ix_training_impact_item", "amo_id", "impact_assessment_id", "entity_type", "action_status"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    impact_assessment_id = Column(String(36), ForeignKey("training_impact_assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(32), nullable=False)
    entity_id = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    required_action = Column(Text, nullable=True)
    blocking = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    action_status = Column(String(24), nullable=False, default="OPEN", server_default="OPEN")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingSessionCloseout(Base):
    __tablename__ = "training_session_closeouts"
    __table_args__ = (UniqueConstraint("event_id", name="uq_training_session_closeout_event"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    summary_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingLearnerCloseout(Base):
    __tablename__ = "training_learner_closeouts"
    __table_args__ = (
        UniqueConstraint("session_closeout_id", "user_id", name="uq_training_learner_closeout"),
        Index("ix_training_learner_closeout_status", "amo_id", "status", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    session_closeout_id = Column(String(36), ForeignKey("training_session_closeouts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), nullable=False)
    blockers_json = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    certificate_eligible = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    certificate_issue_id = Column(String(36), ForeignKey("training_certificate_issues.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingAuthoritySubmission(Base):
    __tablename__ = "training_authority_submissions"
    __table_args__ = (Index("ix_training_authority_submission_queue", "amo_id", "authority_id", "status", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    authority_id = Column(String(36), ForeignKey("training_authorities.id", ondelete="RESTRICT"), nullable=False, index=True)
    submission_type = Column(String(64), nullable=False)
    subject_type = Column(String(64), nullable=False)
    subject_id = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    application_reference = Column(String(128), nullable=True)
    evidence_json = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    authority_comments = Column(Text, nullable=True)
    approval_number = Column(String(128), nullable=True)
    effective_date = Column(Date, nullable=True)
    externally_received = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    independently_verified = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingQualityLink(Base):
    """Link Training quality events to canonical QMS findings/CARs; never duplicate them."""

    __tablename__ = "training_quality_links"
    __table_args__ = (
        UniqueConstraint("amo_id", "training_entity_type", "training_entity_id", "qms_entity_type", "qms_entity_id", name="uq_training_quality_link"),
        Index("ix_training_quality_link_training", "amo_id", "training_entity_type", "training_entity_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    training_entity_type = Column(String(64), nullable=False)
    training_entity_id = Column(String(64), nullable=False)
    qms_entity_type = Column(String(32), nullable=False)
    qms_entity_id = Column(String(64), nullable=False)
    relationship_type = Column(String(32), nullable=False, default="RELATED", server_default="RELATED")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
