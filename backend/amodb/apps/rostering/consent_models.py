from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RosterConsentStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    INVALIDATED = "INVALIDATED"


class RosterSupervisorDecision(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RosterAssignmentConsent(Base):
    """Immutable-revision consent request for one exact roster assignment.

    A new assignment revision creates a new request. Older accepted requests are
    invalidated rather than overwritten so an employee can never be treated as
    accepting duty they did not see.
    """

    __tablename__ = "roster_assignment_consents"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "assignment_revision",
            name="uq_roster_assignment_consent_revision",
        ),
        Index("ix_roster_consent_amo_personnel_status", "amo_id", "personnel_id", "personnel_response"),
        Index("ix_roster_consent_version_status", "version_id", "personnel_response", "supervisor_decision"),
        CheckConstraint("assignment_revision >= 1", name="ck_roster_consent_revision_positive"),
        CheckConstraint("planned_end > planned_start", name="ck_roster_consent_time_order"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_revision = Column(Integer, nullable=False)
    assignment_fingerprint = Column(String(64), nullable=False, index=True)
    personnel_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    proposed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reason = Column(Text, nullable=False)
    duty_type = Column(String(64), nullable=False)
    planned_start = Column(DateTime(timezone=True), nullable=False)
    planned_end = Column(DateTime(timezone=True), nullable=False)
    original_schedule_json = Column(JSON, nullable=True)
    personnel_response = Column(
        SAEnum(RosterConsentStatus, name="roster_consent_status_enum", native_enum=False),
        nullable=False,
        default=RosterConsentStatus.PENDING,
        index=True,
    )
    personnel_response_at = Column(DateTime(timezone=True), nullable=True)
    personnel_comment = Column(Text, nullable=True)
    supervisor_required = Column(Boolean, nullable=False, default=False)
    supervisor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    supervisor_decision = Column(
        SAEnum(RosterSupervisorDecision, name="roster_supervisor_decision_enum", native_enum=False),
        nullable=False,
        default=RosterSupervisorDecision.NOT_REQUIRED,
        index=True,
    )
    supervisor_decision_at = Column(DateTime(timezone=True), nullable=True)
    supervisor_decided_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    supervisor_comment = Column(Text, nullable=True)
    overtime_rest_day_classification = Column(String(64), nullable=True)
    replacement_rest_json = Column(JSON, nullable=True)
    statutory_compliance_json = Column(JSON, nullable=True)
    fatigue_risk_json = Column(JSON, nullable=True)
    invalidated_at = Column(DateTime(timezone=True), nullable=True)
    invalidation_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    assignment = relationship("RosterAssignment", lazy="joined")
    personnel = relationship("User", foreign_keys=[personnel_id], lazy="joined")
    supervisor = relationship("User", foreign_keys=[supervisor_user_id], lazy="joined")


class RosterRegulatoryExemption(Base):
    """Authority-issued exemption; never an internal manager override."""

    __tablename__ = "roster_regulatory_exemptions"
    __table_args__ = (
        UniqueConstraint("amo_id", "authority", "exemption_reference", name="uq_roster_exemption_reference"),
        Index("ix_roster_exemption_amo_validity", "amo_id", "effective_date", "expiry_date"),
        Index("ix_roster_exemption_amo_user", "amo_id", "personnel_id"),
        CheckConstraint("expiry_date >= effective_date", name="ck_roster_exemption_validity"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    authority = Column(String(255), nullable=False)
    exemption_reference = Column(String(128), nullable=False)
    regulation_provision = Column(String(255), nullable=False, index=True)
    scope = Column(Text, nullable=False)
    personnel_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    role_applicability = Column(String(128), nullable=True)
    conditions_json = Column(JSON, nullable=False, default=dict)
    effective_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
    supporting_document_id = Column(String(36), ForeignKey("doc_control_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    is_revoked = Column(Boolean, nullable=False, default=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revocation_reason = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
