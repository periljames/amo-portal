from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RosterCalendarMode(str, Enum):
    TIMED = "TIMED"
    ALL_DAY = "ALL_DAY"
    HIDDEN = "HIDDEN"


class RosterDutySemantic(str, Enum):
    DUTY = "DUTY"
    STANDBY = "STANDBY"
    TRAINING = "TRAINING"
    REST = "REST"
    OFF = "OFF"
    LEAVE = "LEAVE"
    SICK = "SICK"
    OTHER = "OTHER"


class RosterCodeVerificationStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNRESOLVED = "UNRESOLVED"


class RosterShiftTemplatePolicy(Base):
    """Tenant-owned governance layered on a reusable ShiftTemplate.

    ShiftTemplate answers *when* a person works. This policy records roster
    semantics and workflow policy without assigning statutory meaning to the
    tenant's display code. Consent is therefore configured explicitly rather
    than inferred from names such as X, OT, RD or SA.

    ``counts_as_rest`` is descriptive scheduling metadata only. A rest/off code
    can never satisfy protected-rest law by itself; the compliance engine proves
    release from all duty using the effective timestamp timeline. Conversely,
    on-site availability must not be configured as non-duty because personnel
    remain available for work rather than relieved from all duties.
    """

    __tablename__ = "roster_shift_template_policies"
    __table_args__ = (
        UniqueConstraint("shift_template_id", name="uq_roster_shift_policy_template"),
        Index("ix_roster_shift_policy_amo", "amo_id", "shift_template_id"),
        Index("ix_roster_shift_policy_verification", "amo_id", "verification_status"),
        CheckConstraint("unpaid_break_minutes >= 0", name="ck_roster_shift_policy_break_nonneg"),
        CheckConstraint("fatigue_weight >= 0", name="ck_roster_shift_policy_fatigue_nonneg"),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_roster_shift_policy_effective_dates",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    shift_template_id = Column(
        String(36),
        ForeignKey("shift_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    unpaid_break_minutes = Column(Integer, nullable=False, default=0)
    calendar_mode = Column(
        SAEnum(RosterCalendarMode, name="roster_calendar_mode_enum", native_enum=False),
        nullable=False,
        default=RosterCalendarMode.TIMED,
    )
    duty_semantic = Column(
        SAEnum(RosterDutySemantic, name="roster_duty_semantic_enum", native_enum=False),
        nullable=False,
        default=RosterDutySemantic.DUTY,
    )
    verification_status = Column(
        SAEnum(RosterCodeVerificationStatus, name="roster_code_verification_status_enum", native_enum=False),
        nullable=False,
        default=RosterCodeVerificationStatus.UNRESOLVED,
    )
    counts_as_rest = Column(Boolean, nullable=False, default=False)
    on_site_availability = Column(Boolean, nullable=False, default=False)
    scheduling_eligible = Column(Boolean, nullable=False, default=True)
    requires_personnel_acknowledgement = Column(Boolean, nullable=False, default=False)
    requires_supervisor_approval = Column(Boolean, nullable=False, default=False)
    fatigue_weight = Column(Float, nullable=False, default=1.0)
    pay_classification = Column(String(64), nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    source_reference = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
