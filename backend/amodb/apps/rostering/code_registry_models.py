from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
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


class RosterShiftTemplatePolicy(Base):
    """Tenant-owned policy layered on a reusable ShiftTemplate.

    ShiftTemplate continues to answer *when* a person works. This policy stores
    roster-specific presentation/payroll metadata that should not be inferred
    from department, base, work-centre or aircraft codes.
    """

    __tablename__ = "roster_shift_template_policies"
    __table_args__ = (
        UniqueConstraint("shift_template_id", name="uq_roster_shift_policy_template"),
        Index("ix_roster_shift_policy_amo", "amo_id", "shift_template_id"),
        CheckConstraint("unpaid_break_minutes >= 0", name="ck_roster_shift_policy_break_nonneg"),
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
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    source_reference = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
