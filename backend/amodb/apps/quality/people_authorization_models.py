from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAppointment(Base):
    """Quality function held by a person, separate from workforce role and authorization."""

    __tablename__ = "quality_appointments"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE','SUPERSEDED')", name="ck_quality_appointment_status"),
        Index("ix_quality_appointments_person", "amo_id", "user_id", "status"),
        Index("ix_quality_appointments_function", "amo_id", "function_code", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    function_code = Column(String(96), nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    effective_from = Column(Date, nullable=True)
    effective_until = Column(Date, nullable=True)
    source_references = Column(JSON, nullable=False, default=list)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class QualityAuthorizationCase(Base):
    """Pre-decision file for nomination, development, evidence, recommendation and approval."""

    __tablename__ = "quality_authorization_cases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('NOMINATED','UNDER_REVIEW','DEVELOPMENT','AWAITING_EVIDENCE','READY_FOR_DECISION','RETURNED','APPROVED','REJECTED','CANCELLED')",
            name="ck_quality_authorization_case_status",
        ),
        CheckConstraint(
            "case_type IN ('NEW_AUTHORIZATION','CHANGE_AUTHORIZATION','RENEWAL','REINSTATEMENT')",
            name="ck_quality_authorization_case_type",
        ),
        Index("ix_quality_authorization_cases_queue", "amo_id", "status", "updated_at"),
        Index("ix_quality_authorization_cases_person", "amo_id", "user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    appointment_id = Column(String(36), ForeignKey("quality_appointments.id", ondelete="SET NULL"), nullable=True)
    current_privilege_id = Column(String(36), ForeignKey("quality_privileges.id", ondelete="RESTRICT"), nullable=True)
    requested_rule_id = Column(String(36), ForeignKey("quality_privilege_rules.id", ondelete="RESTRICT"), nullable=False)
    case_type = Column(String(32), nullable=False, default="NEW_AUTHORIZATION", server_default="NEW_AUTHORIZATION")
    status = Column(String(32), nullable=False, default="NOMINATED", server_default="NOMINATED")
    requested_scope_key = Column(String(255), nullable=False, default="GLOBAL", server_default="GLOBAL")
    requested_scope = Column(JSON, nullable=False, default=dict)
    nomination_date = Column(Date, nullable=False)
    nominated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    person_snapshot = Column(JSON, nullable=False, default=dict)
    current_authorization_snapshot = Column(JSON, nullable=False, default=dict)
    requested_authorization_snapshot = Column(JSON, nullable=False, default=dict)
    recommendation = Column(Text, nullable=True)
    recommendation_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recommendation_at = Column(DateTime(timezone=True), nullable=True)
    decision = Column(String(32), nullable=True)
    decision_reason = Column(Text, nullable=True)
    decided_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    effective_from = Column(Date, nullable=True)
    expires_on = Column(Date, nullable=True)
    next_review_due = Column(Date, nullable=True)
    readiness_snapshot = Column(JSON, nullable=False, default=dict)
    source_references = Column(JSON, nullable=False, default=list)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    requested_rule = relationship("QualityPrivilegeRule", lazy="joined", foreign_keys=[requested_rule_id])
    current_privilege = relationship("QualityPrivilege", lazy="selectin", foreign_keys=[current_privilege_id])


class QualityAuthorizationCaseEvent(Base):
    """Append-only transition history for an authorization case."""

    __tablename__ = "quality_authorization_case_events"
    __table_args__ = (
        Index("ix_quality_authorization_case_events_history", "amo_id", "case_id", "occurred_at"),
        Index("ix_quality_authorization_case_events_actor", "amo_id", "actor_user_id", "occurred_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("quality_authorization_cases.id", ondelete="RESTRICT"), nullable=False)
    action = Column(String(64), nullable=False)
    previous_status = Column(String(32), nullable=True)
    new_status = Column(String(32), nullable=True)
    reason = Column(Text, nullable=False)
    before_snapshot = Column(JSON, nullable=False, default=dict)
    after_snapshot = Column(JSON, nullable=False, default=dict)
    source_references = Column(JSON, nullable=False, default=list)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuthorizationEvidence(Base):
    """Reference or optional external file considered in a Quality authorization case."""

    __tablename__ = "quality_authorization_evidence"
    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('TRAINING_RECORD','COMPETENCE_ASSESSMENT','PRIOR_AUTHORIZATION','AUDIT_EXPERIENCE','COMPETENCE_PACKAGE','ANNUAL_REVIEW','CONTROLLED_EXEMPTION','APPOINTMENT_LETTER','OTHER')",
            name="ck_quality_authorization_evidence_type",
        ),
        CheckConstraint("status IN ('ACTIVE','SUPERSEDED','VOID')", name="ck_quality_authorization_evidence_status"),
        CheckConstraint("case_id IS NOT NULL OR privilege_id IS NOT NULL", name="ck_quality_authorization_evidence_owner"),
        Index("ix_quality_authorization_evidence_case", "amo_id", "case_id", "created_at"),
        Index("ix_quality_authorization_evidence_privilege", "amo_id", "privilege_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("quality_authorization_cases.id", ondelete="RESTRICT"), nullable=True)
    privilege_id = Column(String(36), ForeignKey("quality_privileges.id", ondelete="RESTRICT"), nullable=True)
    evidence_type = Column(String(40), nullable=False)
    label = Column(String(255), nullable=False)
    source_module = Column(String(64), nullable=True)
    source_reference = Column(JSON, nullable=False, default=dict)
    original_filename = Column(String(255), nullable=True)
    storage_path = Column(Text, nullable=True)
    content_type = Column(String(255), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    sha256 = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityAuthorizationReview(Base):
    """Immutable periodic review record; authorization history is preserved."""

    __tablename__ = "quality_authorization_reviews"
    __table_args__ = (
        CheckConstraint(
            "review_outcome IN ('CONTINUE','CONTINUE_WITH_CONDITIONS','SUSPEND','REVOKE','REQUIRES_ACTION')",
            name="ck_quality_authorization_review_outcome",
        ),
        Index("ix_quality_authorization_reviews_due", "amo_id", "next_review_due"),
        Index("ix_quality_authorization_reviews_history", "amo_id", "privilege_id", "reviewed_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    privilege_id = Column(String(36), ForeignKey("quality_privileges.id", ondelete="RESTRICT"), nullable=False)
    last_reviewed = Column(Date, nullable=False)
    next_review_due = Column(Date, nullable=True)
    review_outcome = Column(String(32), nullable=False)
    review_reason = Column(Text, nullable=False)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    review_evidence = Column(JSON, nullable=False, default=list)
    review_notes = Column(Text, nullable=True)
    before_snapshot = Column(JSON, nullable=False, default=dict)
    after_snapshot = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityControlledExemption(Base):
    """Time-bounded conditional authorization approved only by governed decision authority."""

    __tablename__ = "quality_controlled_exemptions"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','EXPIRED','REVOKED','SUPERSEDED')", name="ck_quality_controlled_exemption_status"),
        CheckConstraint("expires_on >= effective_from", name="ck_quality_controlled_exemption_dates"),
        Index("ix_quality_controlled_exemptions_active", "amo_id", "status", "expires_on"),
        Index("ix_quality_controlled_exemptions_person", "amo_id", "person_user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("quality_authorization_cases.id", ondelete="RESTRICT"), nullable=True)
    privilege_id = Column(String(36), ForeignKey("quality_privileges.id", ondelete="RESTRICT"), nullable=True)
    person_user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    authorization_type = Column(String(255), nullable=False)
    criterion = Column(String(255), nullable=False)
    reason_normal_compliance_impossible = Column(Text, nullable=False)
    equivalent_evidence = Column(JSON, nullable=False, default=list)
    limitations = Column(JSON, nullable=False, default=list)
    supervision_required = Column(Boolean, nullable=False, default=False, server_default="false")
    supervisor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    conditions = Column(JSON, nullable=False, default=list)
    effective_from = Column(Date, nullable=False)
    expires_on = Column(Date, nullable=False)
    source_references = Column(JSON, nullable=False, default=list)
    status = Column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    revoked_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
