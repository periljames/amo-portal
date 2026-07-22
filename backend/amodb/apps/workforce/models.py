# backend/amodb/apps/workforce/models.py
"""Workforce and HR-owned records used by duty rostering.

Identity remains owned by ``accounts.users``.  This package owns employment
conditions, work patterns, leave/availability, attendance, timesheets,
overtime, public holidays and explicit workforce permission overrides.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

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


class ContractType(str, enum.Enum):
    PERMANENT = "PERMANENT"
    FIXED_TERM = "FIXED_TERM"
    TEMPORARY = "TEMPORARY"
    CONTRACTOR = "CONTRACTOR"
    INTERN = "INTERN"


class EmploymentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"
    ONBOARDING = "ONBOARDING"


class PatternDayStatus(str, enum.Enum):
    DUTY = "DUTY"
    STANDBY = "STANDBY"
    TRAINING = "TRAINING"
    OFF = "OFF"
    LEAVE = "LEAVE"
    TRAVEL = "TRAVEL"
    UNAVAILABLE = "UNAVAILABLE"
    OTHER = "OTHER"


class LeaveRequestStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    SUPERVISOR_APPROVED = "SUPERVISOR_APPROVED"
    HR_APPROVED = "HR_APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    RECALLED = "RECALLED"


class LeaveApprovalStage(str, enum.Enum):
    SUPERVISOR = "SUPERVISOR"
    HR = "HR"


class ApprovalDecision(str, enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AvailabilityType(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    ANNUAL_LEAVE = "ANNUAL_LEAVE"
    SICK_LEAVE = "SICK_LEAVE"
    COMPASSIONATE_LEAVE = "COMPASSIONATE_LEAVE"
    MATERNITY_LEAVE = "MATERNITY_LEAVE"
    PATERNITY_LEAVE = "PATERNITY_LEAVE"
    STUDY_LEAVE = "STUDY_LEAVE"
    UNPAID_LEAVE = "UNPAID_LEAVE"
    TRAINING = "TRAINING"
    TRAVEL = "TRAVEL"
    SUSPENDED = "SUSPENDED"
    OTHER = "OTHER"


class AttendanceEventType(str, enum.Enum):
    CLOCK_IN = "CLOCK_IN"
    CLOCK_OUT = "CLOCK_OUT"
    BREAK_START = "BREAK_START"
    BREAK_END = "BREAK_END"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"


class TimesheetCategory(str, enum.Enum):
    ORDINARY = "ORDINARY"
    OVERTIME = "OVERTIME"
    NIGHT = "NIGHT"
    WEEKEND = "WEEKEND"
    PUBLIC_HOLIDAY = "PUBLIC_HOLIDAY"
    STANDBY = "STANDBY"
    CALLOUT = "CALLOUT"
    TRAINING = "TRAINING"
    TRAVEL = "TRAVEL"
    LEAVE = "LEAVE"
    UNPAID_ABSENCE = "UNPAID_ABSENCE"


class TimesheetStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    SUPERVISOR_APPROVED = "SUPERVISOR_APPROVED"
    HR_APPROVED = "HR_APPROVED"
    EXPORTED = "EXPORTED"
    REJECTED = "REJECTED"


class OvertimeRequestStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    SUPERVISOR_APPROVED = "SUPERVISOR_APPROVED"
    HR_APPROVED = "HR_APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PermissionEffect(str, enum.Enum):
    GRANT = "GRANT"
    DENY = "DENY"


class EmploymentContract(Base):
    __tablename__ = "employment_contracts"
    __table_args__ = (
        Index("ix_employment_contracts_amo_user", "amo_id", "user_id"),
        Index("ix_employment_contracts_effective", "amo_id", "effective_from", "effective_to"),
        Index("ix_employment_contracts_status", "amo_id", "employment_status"),
        UniqueConstraint("amo_id", "user_id", "effective_from", name="uq_employment_contract_user_effective"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_employment_contract_dates"),
        CheckConstraint("standard_weekly_minutes >= 0", name="ck_employment_contract_weekly_minutes"),
        CheckConstraint("standard_daily_minutes >= 0", name="ck_employment_contract_daily_minutes"),
        CheckConstraint("fte_percentage > 0 AND fte_percentage <= 100", name="ck_employment_contract_fte"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_type = Column(SAEnum(ContractType, name="workforce_contract_type_enum", native_enum=False), nullable=False)
    employment_status = Column(SAEnum(EmploymentStatus, name="workforce_employment_status_enum", native_enum=False), nullable=False, default=EmploymentStatus.ACTIVE, index=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    standard_weekly_minutes = Column(Integer, nullable=False, default=2400)
    standard_daily_minutes = Column(Integer, nullable=False, default=480)
    fte_percentage = Column(Float, nullable=False, default=100.0)
    primary_base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="RESTRICT"), nullable=False, index=True)
    secondary_base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="RESTRICT"), nullable=True, index=True)
    supervisor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    cost_centre = Column(String(64), nullable=True, index=True)
    payroll_number = Column(String(64), nullable=True, index=True)
    overtime_eligible = Column(Boolean, nullable=False, default=True)
    night_shift_eligible = Column(Boolean, nullable=False, default=True)
    standby_eligible = Column(Boolean, nullable=False, default=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    supervisor = relationship("User", foreign_keys=[supervisor_user_id], lazy="joined")
    primary_base = relationship("BaseStation", foreign_keys=[primary_base_station_id], lazy="joined")
    secondary_base = relationship("BaseStation", foreign_keys=[secondary_base_station_id], lazy="joined")


class WorkPattern(Base):
    __tablename__ = "work_patterns"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_work_patterns_amo_code"),
        Index("ix_work_patterns_amo_active", "amo_id", "is_active"),
        CheckConstraint("cycle_length_days > 0 AND cycle_length_days <= 366", name="ck_work_pattern_cycle_length"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    cycle_length_days = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    timezone_name = Column(String(64), nullable=False, default="UTC")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    days = relationship("WorkPatternDay", back_populates="work_pattern", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")
    employee_assignments = relationship("EmployeeWorkPatternAssignment", back_populates="work_pattern", lazy="selectin")


class WorkPatternDay(Base):
    __tablename__ = "work_pattern_days"
    __table_args__ = (
        UniqueConstraint("work_pattern_id", "cycle_day_index", name="uq_work_pattern_day_index"),
        Index("ix_work_pattern_days_amo_pattern", "amo_id", "work_pattern_id"),
        CheckConstraint("cycle_day_index >= 0", name="ck_work_pattern_day_index"),
        CheckConstraint("planned_minutes >= 0", name="ck_work_pattern_day_minutes"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    work_pattern_id = Column(String(36), ForeignKey("work_patterns.id", ondelete="CASCADE"), nullable=False, index=True)
    cycle_day_index = Column(Integer, nullable=False)
    shift_template_id = Column(String(36), ForeignKey("shift_templates.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(SAEnum(PatternDayStatus, name="work_pattern_day_status_enum", native_enum=False), nullable=False, default=PatternDayStatus.DUTY)
    start_time_local = Column(String(5), nullable=True)
    end_time_local = Column(String(5), nullable=True)
    spans_next_day = Column(Boolean, nullable=False, default=False)
    planned_minutes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    work_pattern = relationship("WorkPattern", back_populates="days", lazy="joined")
    shift_template = relationship("ShiftTemplate", lazy="joined")


class EmployeeWorkPatternAssignment(Base):
    __tablename__ = "employee_work_pattern_assignments"
    __table_args__ = (
        Index("ix_employee_pattern_amo_user", "amo_id", "user_id"),
        Index("ix_employee_pattern_effective", "effective_from", "effective_to"),
        UniqueConstraint("amo_id", "user_id", "effective_from", name="uq_employee_pattern_user_effective"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_employee_pattern_dates"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    work_pattern_id = Column(String(36), ForeignKey("work_patterns.id", ondelete="CASCADE"), nullable=False, index=True)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    cycle_anchor_date = Column(Date, nullable=False)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    work_pattern = relationship("WorkPattern", back_populates="employee_assignments", lazy="joined")


class LeaveType(Base):
    __tablename__ = "leave_types"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_leave_types_amo_code"),
        Index("ix_leave_types_amo_active", "amo_id", "is_active"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    availability_type = Column(SAEnum(AvailabilityType, name="availability_type_enum", native_enum=False), nullable=False)
    description = Column(Text, nullable=True)
    paid = Column(Boolean, nullable=False, default=True)
    deducts_balance = Column(Boolean, nullable=False, default=True)
    requires_attachment = Column(Boolean, nullable=False, default=False)
    supervisor_approval_required = Column(Boolean, nullable=False, default=True)
    hr_approval_required = Column(Boolean, nullable=False, default=True)
    allow_negative_balance = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    display_order = Column(Integer, nullable=False, default=100)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class EmployeeLeaveBalance(Base):
    __tablename__ = "employee_leave_balances"
    __table_args__ = (
        UniqueConstraint("amo_id", "user_id", "leave_type_id", "leave_year", name="uq_leave_balance_user_type_year"),
        Index("ix_leave_balances_amo_user", "amo_id", "user_id"),
        CheckConstraint("allocated_minutes >= 0", name="ck_leave_balance_allocated"),
        CheckConstraint("used_minutes >= 0", name="ck_leave_balance_used"),
        CheckConstraint("pending_minutes >= 0", name="ck_leave_balance_pending"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id = Column(String(36), ForeignKey("leave_types.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_year = Column(Integer, nullable=False)
    allocated_minutes = Column(Integer, nullable=False, default=0)
    carried_minutes = Column(Integer, nullable=False, default=0)
    used_minutes = Column(Integer, nullable=False, default=0)
    pending_minutes = Column(Integer, nullable=False, default=0)
    adjustment_minutes = Column(Integer, nullable=False, default=0)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    leave_type = relationship("LeaveType", lazy="joined")
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    updated_by = relationship("User", foreign_keys=[updated_by_user_id], lazy="joined")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        Index("ix_leave_requests_amo_user_time", "amo_id", "user_id", "starts_at", "ends_at"),
        Index("ix_leave_requests_amo_status", "amo_id", "status"),
        CheckConstraint("ends_at > starts_at", name="ck_leave_request_time_order"),
        CheckConstraint("requested_minutes > 0", name="ck_leave_request_minutes_positive"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id = Column(String(36), ForeignKey("leave_types.id", ondelete="RESTRICT"), nullable=False, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=False, index=True)
    requested_minutes = Column(Integer, nullable=False)
    status = Column(SAEnum(LeaveRequestStatus, name="leave_request_status_enum", native_enum=False), nullable=False, default=LeaveRequestStatus.DRAFT, index=True)
    reason = Column(Text, nullable=True)
    attachment_reference = Column(String(255), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    supervisor_approved_at = Column(DateTime(timezone=True), nullable=True)
    hr_approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    leave_type = relationship("LeaveType", lazy="joined")
    approvals = relationship("LeaveRequestApproval", back_populates="leave_request", cascade="all, delete-orphan", lazy="selectin")


class LeaveRequestApproval(Base):
    __tablename__ = "leave_request_approvals"
    __table_args__ = (
        UniqueConstraint("leave_request_id", "stage", name="uq_leave_request_approval_stage"),
        Index("ix_leave_approvals_amo_actor", "amo_id", "actor_user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_request_id = Column(String(36), ForeignKey("leave_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(SAEnum(LeaveApprovalStage, name="leave_approval_stage_enum", native_enum=False), nullable=False)
    decision = Column(SAEnum(ApprovalDecision, name="workforce_approval_decision_enum", native_enum=False), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    leave_request = relationship("LeaveRequest", back_populates="approvals", lazy="joined")
    actor = relationship("User", foreign_keys=[actor_user_id], lazy="joined")


class EmployeeAvailabilityEvent(Base):
    __tablename__ = "employee_availability_events"
    __table_args__ = (
        Index("ix_employee_availability_amo_user_time", "amo_id", "user_id", "starts_at", "ends_at"),
        Index("ix_employee_availability_amo_type", "amo_id", "availability_type"),
        UniqueConstraint("amo_id", "source_type", "source_id", name="uq_employee_availability_source"),
        CheckConstraint("ends_at > starts_at", name="ck_employee_availability_time_order"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    availability_type = Column(SAEnum(AvailabilityType, name="employee_availability_type_enum", native_enum=False), nullable=False, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=False, index=True)
    blocking = Column(Boolean, nullable=False, default=True, index=True)
    provisional = Column(Boolean, nullable=False, default=False, index=True)
    source_type = Column(String(64), nullable=False, default="MANUAL", index=True)
    source_id = Column(String(64), nullable=False, index=True)
    reason = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_user_id], lazy="joined")
    updated_by = relationship("User", foreign_keys=[updated_by_user_id], lazy="joined")


class PublicHolidayCalendar(Base):
    __tablename__ = "public_holiday_calendars"
    __table_args__ = (UniqueConstraint("amo_id", "code", name="uq_public_holiday_calendar_code"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    country_code = Column(String(8), nullable=True)
    timezone_name = Column(String(64), nullable=False, default="UTC")
    is_active = Column(Boolean, nullable=False, default=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    holidays = relationship("PublicHoliday", back_populates="calendar", cascade="all, delete-orphan", lazy="selectin")


class PublicHoliday(Base):
    __tablename__ = "public_holidays"
    __table_args__ = (
        UniqueConstraint("calendar_id", "holiday_date", name="uq_public_holiday_date"),
        Index("ix_public_holidays_amo_date", "amo_id", "holiday_date"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    calendar_id = Column(String(36), ForeignKey("public_holiday_calendars.id", ondelete="CASCADE"), nullable=False, index=True)
    holiday_date = Column(Date, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    paid = Column(Boolean, nullable=False, default=True)
    metadata_json = Column(JSON, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    calendar = relationship("PublicHolidayCalendar", back_populates="holidays", lazy="joined")


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"
    __table_args__ = (
        Index("ix_attendance_events_amo_user_time", "amo_id", "user_id", "occurred_at"),
        UniqueConstraint("amo_id", "idempotency_key", name="uq_attendance_event_idempotency"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(SAEnum(AttendanceEventType, name="attendance_event_type_enum", native_enum=False), nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    source = Column(String(64), nullable=False, default="MANUAL")
    base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="SET NULL"), nullable=True, index=True)
    roster_assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="SET NULL"), nullable=True, index=True)
    idempotency_key = Column(String(128), nullable=False)
    note = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    recorded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    recorded_by = relationship("User", foreign_keys=[recorded_by_user_id], lazy="joined")


class Timesheet(Base):
    __tablename__ = "timesheets"
    __table_args__ = (
        UniqueConstraint("amo_id", "user_id", "period_start", "period_end", name="uq_timesheet_user_period"),
        Index("ix_timesheets_amo_status", "amo_id", "status"),
        Index("ix_timesheets_amo_user_period", "amo_id", "user_id", "period_start", "period_end"),
        CheckConstraint("period_end >= period_start", name="ck_timesheet_period"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    status = Column(SAEnum(TimesheetStatus, name="timesheet_status_enum", native_enum=False), nullable=False, default=TimesheetStatus.DRAFT, index=True)
    planned_minutes = Column(Integer, nullable=False, default=0)
    attendance_minutes = Column(Integer, nullable=False, default=0)
    productive_minutes = Column(Integer, nullable=False, default=0)
    overtime_minutes = Column(Integer, nullable=False, default=0)
    variance_minutes = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    supervisor_approved_at = Column(DateTime(timezone=True), nullable=True)
    hr_approved_at = Column(DateTime(timezone=True), nullable=True)
    exported_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_user_id], lazy="joined")
    updated_by = relationship("User", foreign_keys=[updated_by_user_id], lazy="joined")
    lines = relationship("TimesheetLine", back_populates="timesheet", cascade="all, delete-orphan", lazy="selectin")


class TimesheetLine(Base):
    __tablename__ = "timesheet_lines"
    __table_args__ = (
        Index("ix_timesheet_lines_sheet_date", "timesheet_id", "work_date"),
        CheckConstraint("minutes >= 0", name="ck_timesheet_line_minutes"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    timesheet_id = Column(String(36), ForeignKey("timesheets.id", ondelete="CASCADE"), nullable=False, index=True)
    work_date = Column(Date, nullable=False, index=True)
    category = Column(SAEnum(TimesheetCategory, name="timesheet_category_enum", native_enum=False), nullable=False, index=True)
    minutes = Column(Integer, nullable=False, default=0)
    roster_assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="SET NULL"), nullable=True, index=True)
    work_log_entry_id = Column(Integer, ForeignKey("work_log_entries.id", ondelete="SET NULL"), nullable=True, index=True)
    source = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    timesheet = relationship("Timesheet", back_populates="lines", lazy="joined")


class OvertimeRequest(Base):
    __tablename__ = "overtime_requests"
    __table_args__ = (
        Index("ix_overtime_requests_amo_user_time", "amo_id", "user_id", "starts_at", "ends_at"),
        CheckConstraint("ends_at > starts_at", name="ck_overtime_request_time_order"),
        CheckConstraint("requested_minutes > 0", name="ck_overtime_request_minutes"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    roster_assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="SET NULL"), nullable=True, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    requested_minutes = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(SAEnum(OvertimeRequestStatus, name="overtime_request_status_enum", native_enum=False), nullable=False, default=OvertimeRequestStatus.DRAFT, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_user_id], lazy="joined")
    approvals = relationship("OvertimeApproval", back_populates="overtime_request", cascade="all, delete-orphan", lazy="selectin")


class OvertimeApproval(Base):
    __tablename__ = "overtime_approvals"
    __table_args__ = (UniqueConstraint("overtime_request_id", "stage", name="uq_overtime_approval_stage"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    overtime_request_id = Column(String(36), ForeignKey("overtime_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(SAEnum(LeaveApprovalStage, name="overtime_approval_stage_enum", native_enum=False), nullable=False)
    decision = Column(SAEnum(ApprovalDecision, name="overtime_approval_decision_enum", native_enum=False), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    overtime_request = relationship("OvertimeRequest", back_populates="approvals", lazy="joined")
    actor = relationship("User", foreign_keys=[actor_user_id], lazy="joined")


class RosterActualVariance(Base):
    __tablename__ = "roster_actual_variances"
    __table_args__ = (
        UniqueConstraint("roster_assignment_id", name="uq_roster_actual_variance_assignment"),
        Index("ix_roster_actual_variances_amo_user", "amo_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    roster_assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    planned_minutes = Column(Integer, nullable=False, default=0)
    attendance_minutes = Column(Integer, nullable=False, default=0)
    productive_minutes = Column(Integer, nullable=False, default=0)
    variance_minutes = Column(Integer, nullable=False, default=0)
    classification = Column(String(64), nullable=False, default="MATCHED")
    metadata_json = Column(JSON, nullable=True)
    calculated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WorkforcePermissionGrant(Base):
    __tablename__ = "workforce_permission_grants"
    __table_args__ = (
        Index("ix_workforce_permission_user_code", "amo_id", "user_id", "permission_code"),
        Index("ix_workforce_permission_scope", "department_id", "base_station_id"),
        UniqueConstraint("amo_id", "user_id", "permission_code", "department_id", "base_station_id", name="uq_workforce_permission_scope"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_code = Column(String(128), nullable=False, index=True)
    effect = Column(SAEnum(PermissionEffect, name="workforce_permission_effect_enum", native_enum=False), nullable=False, default=PermissionEffect.GRANT)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True)
    base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="CASCADE"), nullable=True, index=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    reason = Column(Text, nullable=True)
    granted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingEventTimeWindow(Base):
    """Optional timezone-aware window for a date-based training event.

    The Training module remains the owner of the event.  This compatibility
    table supplies precise rostering times without duplicating course or
    participant data and preserves date-only fallback behaviour.
    """

    __tablename__ = "training_event_time_windows"
    __table_args__ = (
        UniqueConstraint("training_event_id", name="uq_training_event_time_window"),
        CheckConstraint("ends_at > starts_at", name="ck_training_event_window_order"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    training_event_id = Column(String(36), ForeignKey("training_events.id", ondelete="CASCADE"), nullable=False, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    timezone_name = Column(String(64), nullable=False, default="UTC")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class PlannerPreference(Base):
    __tablename__ = "roster_planner_preferences"
    __table_args__ = (UniqueConstraint("amo_id", "user_id", name="uq_roster_planner_preference_user"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    density = Column(String(32), nullable=False, default="compact")
    group_by = Column(String(32), nullable=False, default="department")
    zoom = Column(String(32), nullable=False, default="day")
    default_base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="SET NULL"), nullable=True)
    filters_json = Column(JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WorkforceNotificationPreference(Base):
    __tablename__ = "workforce_notification_preferences"
    __table_args__ = (UniqueConstraint("amo_id", "user_id", "event_code", name="uq_workforce_notification_preference"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_code = Column(String(128), nullable=False)
    in_app_enabled = Column(Boolean, nullable=False, default=True)
    email_enabled = Column(Boolean, nullable=False, default=True)
    reminder_hours = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
