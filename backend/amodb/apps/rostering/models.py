# backend/amodb/apps/rostering/models.py
"""Duty rostering ORM models.

Phase 1 scope:
- Shift templates.
- Roster periods and immutable versions.
- Roster assignments keyed by accounts.users.id.
- Validation findings, publication acknowledgements, and roster-to-task links.

The module deliberately references shared source-of-truth records instead of
copying them: users, base_stations, training, work orders, and task assignments
remain owned by their respective modules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ShiftTemplateKind(str, Enum):
    DAY = "DAY"
    NIGHT = "NIGHT"
    STANDBY = "STANDBY"
    TRAINING = "TRAINING"
    OFF = "OFF"
    LEAVE = "LEAVE"
    OTHER = "OTHER"


class RosterPeriodStatus(str, Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    LOCKED = "LOCKED"
    ARCHIVED = "ARCHIVED"


class RosterVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class RosterAssignmentStatus(str, Enum):
    DUTY = "DUTY"
    STANDBY = "STANDBY"
    TRAINING = "TRAINING"
    OFF = "OFF"
    LEAVE = "LEAVE"
    TRAVEL = "TRAVEL"
    UNAVAILABLE = "UNAVAILABLE"
    OTHER = "OTHER"


class RosterValidationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


class RosterValidationSource(str, Enum):
    ROSTER = "ROSTER"
    IDENTITY = "IDENTITY"
    BASE = "BASE"
    AVAILABILITY = "AVAILABILITY"
    TRAINING = "TRAINING"
    AUTHORISATION = "AUTHORISATION"
    WORKLOAD = "WORKLOAD"
    RULE = "RULE"


class ShiftTemplate(Base):
    __tablename__ = "shift_templates"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_shift_templates_amo_code"),
        Index("ix_shift_templates_amo_active", "amo_id", "is_active"),
        CheckConstraint("duration_minutes IS NULL OR duration_minutes >= 0", name="ck_shift_template_duration_nonneg"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(32), nullable=False)
    label = Column(String(128), nullable=False)
    kind = Column(SAEnum(ShiftTemplateKind, name="shift_template_kind_enum", native_enum=False), nullable=False, default=ShiftTemplateKind.DAY, index=True)
    default_start_time = Column(String(5), nullable=True, doc="HH:MM local time for UI defaults.")
    default_end_time = Column(String(5), nullable=True, doc="HH:MM local time for UI defaults.")
    duration_minutes = Column(Integer, nullable=True)
    counts_as_duty = Column(Boolean, nullable=False, default=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    display_order = Column(Integer, nullable=False, default=100)
    description = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    assignments = relationship("RosterAssignment", back_populates="shift_template", lazy="selectin")


class RosterPeriod(Base):
    __tablename__ = "roster_periods"
    __table_args__ = (
        UniqueConstraint("amo_id", "period_code", name="uq_roster_periods_amo_code"),
        Index("ix_roster_periods_amo_dates", "amo_id", "starts_on", "ends_on"),
        Index("ix_roster_periods_amo_status", "amo_id", "status"),
        CheckConstraint("ends_on >= starts_on", name="ck_roster_period_dates"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    period_code = Column(String(32), nullable=False, doc="e.g. 2026-07")
    name = Column(String(255), nullable=False)
    starts_on = Column(Date, nullable=False, index=True)
    ends_on = Column(Date, nullable=False, index=True)
    status = Column(SAEnum(RosterPeriodStatus, name="roster_period_status_enum", native_enum=False), nullable=False, default=RosterPeriodStatus.DRAFT, index=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    versions = relationship("RosterVersion", back_populates="period", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")


class RosterVersion(Base):
    __tablename__ = "roster_versions"
    __table_args__ = (
        UniqueConstraint("period_id", "version_no", name="uq_roster_versions_period_no"),
        Index("ix_roster_versions_amo_status", "amo_id", "status"),
        Index("ix_roster_versions_period_status", "period_id", "status"),
        CheckConstraint("version_no >= 1", name="ck_roster_version_no_positive"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    period_id = Column(String(36), ForeignKey("roster_periods.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no = Column(Integer, nullable=False, default=1)
    status = Column(SAEnum(RosterVersionStatus, name="roster_version_status_enum", native_enum=False), nullable=False, default=RosterVersionStatus.DRAFT, index=True)
    title = Column(String(255), nullable=True)
    change_summary = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    published_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    period = relationship("RosterPeriod", back_populates="versions", lazy="joined")
    assignments = relationship("RosterAssignment", back_populates="version", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")
    validation_findings = relationship("RosterValidationFinding", back_populates="version", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")


class RosterAssignment(Base):
    __tablename__ = "roster_assignments"
    __table_args__ = (
        Index("ix_roster_assignments_amo_user_time", "amo_id", "user_id", "starts_at", "ends_at"),
        Index("ix_roster_assignments_version_user", "version_id", "user_id"),
        Index("ix_roster_assignments_base_time", "base_station_id", "starts_at", "ends_at"),
        CheckConstraint("ends_at > starts_at", name="ck_roster_assignment_time_order"),
        CheckConstraint("planned_minutes IS NULL OR planned_minutes >= 0", name="ck_roster_assignment_minutes_nonneg"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="RESTRICT"), nullable=True, index=True)
    shift_template_id = Column(String(36), ForeignKey("shift_templates.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(SAEnum(RosterAssignmentStatus, name="roster_assignment_status_enum", native_enum=False), nullable=False, default=RosterAssignmentStatus.DUTY, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=False, index=True)
    planned_minutes = Column(Integer, nullable=True)
    role_label = Column(String(128), nullable=True)
    task_note = Column(Text, nullable=True)
    locked_after_publish = Column(Boolean, nullable=False, default=False, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    version = relationship("RosterVersion", back_populates="assignments", lazy="joined")
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    base_station = relationship("BaseStation", lazy="joined")
    shift_template = relationship("ShiftTemplate", back_populates="assignments", lazy="joined")
    task_links = relationship("RosterTaskAssignmentLink", back_populates="roster_assignment", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")


class RosterValidationFinding(Base):
    __tablename__ = "roster_validation_findings"
    __table_args__ = (
        Index("ix_roster_validation_version_severity", "version_id", "severity"),
        Index("ix_roster_validation_amo_user", "amo_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source = Column(SAEnum(RosterValidationSource, name="roster_validation_source_enum", native_enum=False), nullable=False, default=RosterValidationSource.ROSTER, index=True)
    severity = Column(SAEnum(RosterValidationSeverity, name="roster_validation_severity_enum", native_enum=False), nullable=False, index=True)
    code = Column(String(64), nullable=False, index=True)
    message = Column(Text, nullable=False)
    resolved = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    version = relationship("RosterVersion", back_populates="validation_findings", lazy="joined")


class RosterPublicationAcknowledgement(Base):
    __tablename__ = "roster_publication_acknowledgements"
    __table_args__ = (
        UniqueConstraint("version_id", "user_id", name="uq_roster_ack_version_user"),
        Index("ix_roster_ack_amo_user", "amo_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    acknowledgement_note = Column(Text, nullable=True)


class RosterTaskAssignmentLink(Base):
    __tablename__ = "roster_task_assignment_links"
    __table_args__ = (
        UniqueConstraint("roster_assignment_id", "task_assignment_id", name="uq_roster_task_assignment_link"),
        Index("ix_roster_task_links_amo_task", "amo_id", "task_assignment_id"),
        CheckConstraint("allocated_end IS NULL OR allocated_start IS NULL OR allocated_end > allocated_start", name="ck_roster_task_link_time_order"),
        CheckConstraint("allocated_hours IS NULL OR allocated_hours >= 0", name="ck_roster_task_link_hours_nonneg"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    roster_assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    task_assignment_id = Column(Integer, ForeignKey("task_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    allocated_start = Column(DateTime(timezone=True), nullable=True)
    allocated_end = Column(DateTime(timezone=True), nullable=True)
    allocated_hours = Column(Float, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    roster_assignment = relationship("RosterAssignment", back_populates="task_links", lazy="joined")
    task_assignment = relationship("TaskAssignment", lazy="joined")
