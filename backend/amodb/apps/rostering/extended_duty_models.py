from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import CheckConstraint, Column, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RosterDutyExtensionType(str, Enum):
    UNSCHEDULED_AIRCRAFT_UNSERVICEABILITY = "UNSCHEDULED_AIRCRAFT_UNSERVICEABILITY"


class RosterDutyExtensionStatus(str, Enum):
    AWAITING_PERSONNEL_ACKNOWLEDGEMENT = "AWAITING_PERSONNEL_ACKNOWLEDGEMENT"
    AWAITING_SUPERVISOR_APPROVAL = "AWAITING_SUPERVISOR_APPROVAL"
    COMPLIANCE_BLOCKED = "COMPLIANCE_BLOCKED"
    READY = "READY"
    CANCELLED = "CANCELLED"


class RosterDutyExtension(Base):
    __tablename__ = "roster_duty_extensions"
    __table_args__ = (
        Index("ix_roster_duty_extension_amo_status", "amo_id", "status"),
        Index("ix_roster_duty_extension_assignment", "assignment_id", "created_at"),
        CheckConstraint("proposed_extended_end > original_planned_end", name="ck_roster_duty_extension_end_after_original"),
        CheckConstraint("continuous_duty_minutes > 0", name="ck_roster_duty_extension_continuous_positive"),
        CheckConstraint("required_recovery_rest_minutes >= 0", name="ck_roster_duty_extension_recovery_nonneg"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    consent_id = Column(String(36), ForeignKey("roster_assignment_consents.id", ondelete="RESTRICT"), nullable=True, index=True)
    extension_type = Column(SAEnum(RosterDutyExtensionType, name="roster_duty_extension_type_enum", native_enum=False), nullable=False)
    aircraft_registration = Column(String(32), nullable=False)
    operational_reference = Column(String(255), nullable=False)
    work_order_reference = Column(String(255), nullable=True)
    reason = Column(Text, nullable=False)
    normal_duty_start = Column(DateTime(timezone=True), nullable=False)
    original_planned_end = Column(DateTime(timezone=True), nullable=False)
    proposed_extended_end = Column(DateTime(timezone=True), nullable=False)
    continuous_duty_minutes = Column(Integer, nullable=False)
    required_recovery_rest_minutes = Column(Integer, nullable=False, default=0)
    recovery_rest_basis = Column(String(255), nullable=True)
    compliance_snapshot_json = Column(JSON, nullable=False, default=dict)
    fatigue_risk_json = Column(JSON, nullable=False, default=dict)
    status = Column(SAEnum(RosterDutyExtensionStatus, name="roster_duty_extension_status_enum", native_enum=False), nullable=False, index=True)
    proposed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    assignment = relationship("RosterAssignment", lazy="joined")
    consent = relationship("RosterAssignmentConsent", lazy="joined")
