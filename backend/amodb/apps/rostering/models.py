# backend/amodb/apps/rostering/models.py
"""Production duty-rostering persistence.

The module owns roster plans, immutable versions, assignments, configurable
validation rules, explicit exceptions, publication acknowledgements and
maintenance-task allocations. Identity, employment, leave, training, bases,
authorisations and work records remain owned by their canonical modules.
"""
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


class RosterAssignmentSource(str, Enum):
    MANUAL = "MANUAL"
    PATTERN = "PATTERN"
    IMPORT = "IMPORT"
    LEAVE = "LEAVE"
    TRAINING = "TRAINING"
    SYSTEM = "SYSTEM"


class RosterValidationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


class RosterValidationSource(str, Enum):
    ROSTER = "ROSTER"
    IDENTITY = "IDENTITY"
    CONTRACT = "CONTRACT"
    BASE = "BASE"
    AVAILABILITY = "AVAILABILITY"
    TRAINING = "TRAINING"
    AUTHORISATION = "AUTHORISATION"
    WORKLOAD = "WORKLOAD"
    ATTENDANCE = "ATTENDANCE"
    RULE = "RULE"


class RosterRuleType(str, Enum):
    MIN_REST_HOURS = "MIN_REST_HOURS"
    MAX_DUTY_HOURS_DAY = "MAX_DUTY_HOURS_DAY"
    MAX_DUTY_HOURS_ROLLING = "MAX_DUTY_HOURS_ROLLING"
    MAX_CONSECUTIVE_DAYS = "MAX_CONSECUTIVE_DAYS"
    REQUIRED_DAYS_OFF = "REQUIRED_DAYS_OFF"
    MIN_COVERAGE = "MIN_COVERAGE"
    REQUIRED_CERTIFYING_COVERAGE = "REQUIRED_CERTIFYING_COVERAGE"
    REQUIRED_AUTHORISATION = "REQUIRED_AUTHORISATION"
    TRAINING_VALIDITY = "TRAINING_VALIDITY"
    LICENCE_VALIDITY = "LICENCE_VALIDITY"
    CONTRACT_ELIGIBILITY = "CONTRACT_ELIGIBILITY"
    AVAILABILITY_CONFLICT = "AVAILABILITY_CONFLICT"
    OVERLAP = "OVERLAP"
    CUSTOM = "CUSTOM"


class RosterRuleScope(str, Enum):
    AMO = "AMO"
    DEPARTMENT = "DEPARTMENT"
    BASE = "BASE"
    SHIFT_TEMPLATE = "SHIFT_TEMPLATE"
    USER = "USER"


class RosterExceptionDecision(str, Enum):
    ACCEPT_WARNING = "ACCEPT_WARNING"
    OVERRIDE_BLOCKER = "OVERRIDE_BLOCKER"
    REVOKE = "REVOKE"


class RosterAmendmentType(str, Enum):
    CORRECTION = "CORRECTION"
    LEAVE = "LEAVE"
    SICKNESS = "SICKNESS"
    TRAINING = "TRAINING"
    OPERATIONAL = "OPERATIONAL"
    COVERAGE = "COVERAGE"
    OTHER = "OTHER"


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
    color_token = Column(String(64), nullable=True, doc="Semantic UI token, never a hard-coded theme colour.")
    icon_name = Column(String(64), nullable=True, doc="Lucide icon name used by the planner.")
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
    timezone_name = Column(String(64), nullable=False, default="UTC")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    versions = relationship("RosterVersion", back_populates="period", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")


class RosterVersion(Base):
    __tablename__ = "roster_versions"
    __table_args__ = (
        UniqueConstraint("period_id", "version_no", name="uq_roster_versions_period_no"),
        UniqueConstraint("amo_id", "idempotency_key", name="uq_roster_version_idempotency"),
        Index("ix_roster_versions_amo_status", "amo_id", "status"),
        Index("ix_roster_versions_period_status", "period_id", "status"),
        CheckConstraint("version_no >= 1", name="ck_roster_version_no_positive"),
        CheckConstraint("state_revision >= 1", name="ck_roster_version_state_revision"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    period_id = Column(String(36), ForeignKey("roster_periods.id", ondelete="CASCADE"), nullable=False, index=True)
    source_version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    version_no = Column(Integer, nullable=False, default=1)
    status = Column(SAEnum(RosterVersionStatus, name="roster_version_status_enum", native_enum=False), nullable=False, default=RosterVersionStatus.DRAFT, index=True)
    title = Column(String(255), nullable=True)
    change_summary = Column(Text, nullable=True)
    amendment_type = Column(SAEnum(RosterAmendmentType, name="roster_amendment_type_enum", native_enum=False), nullable=True, index=True)
    amendment_reason = Column(Text, nullable=True)
    effective_from = Column(DateTime(timezone=True), nullable=True)
    idempotency_key = Column(String(128), nullable=True, index=True)
    state_revision = Column(Integer, nullable=False, default=1)
    last_validated_at = Column(DateTime(timezone=True), nullable=True)
    validation_fingerprint = Column(String(128), nullable=True)
    publication_correlation_key = Column(String(128), nullable=True, index=True)
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
    source_version = relationship("RosterVersion", remote_side=[id], foreign_keys=[source_version_id], lazy="joined")
    assignments = relationship("RosterAssignment", back_populates="version", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")
    validation_findings = relationship("RosterValidationFinding", back_populates="version", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")
    exceptions = relationship("RosterRuleException", back_populates="version", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")


class RosterAssignment(Base):
    __tablename__ = "roster_assignments"
    __table_args__ = (
        Index("ix_roster_assignments_amo_user_time", "amo_id", "user_id", "starts_at", "ends_at"),
        Index("ix_roster_assignments_version_user", "version_id", "user_id"),
        Index("ix_roster_assignments_base_time", "base_station_id", "starts_at", "ends_at"),
        Index("ix_roster_assignments_department_time", "department_id", "starts_at", "ends_at"),
        Index("ix_roster_assignments_source_reference", "version_id", "source", "source_reference_id"),
        UniqueConstraint("version_id", "source", "source_reference_id", name="uq_roster_assignment_source_reference"),
        CheckConstraint("ends_at > starts_at", name="ck_roster_assignment_time_order"),
        CheckConstraint("planned_minutes IS NULL OR planned_minutes >= 0", name="ck_roster_assignment_minutes_nonneg"),
        CheckConstraint("state_revision >= 1", name="ck_roster_assignment_state_revision"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="RESTRICT"), nullable=True, index=True)
    shift_template_id = Column(String(36), ForeignKey("shift_templates.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(SAEnum(RosterAssignmentStatus, name="roster_assignment_status_enum", native_enum=False), nullable=False, default=RosterAssignmentStatus.DUTY, index=True)
    source = Column(SAEnum(RosterAssignmentSource, name="roster_assignment_source_enum", native_enum=False), nullable=False, default=RosterAssignmentSource.MANUAL, index=True)
    source_reference_id = Column(String(128), nullable=True, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=False, index=True)
    planned_minutes = Column(Integer, nullable=True)
    role_label = Column(String(128), nullable=True)
    team_code = Column(String(64), nullable=True, index=True)
    location_label = Column(String(128), nullable=True)
    task_note = Column(Text, nullable=True)
    change_reason = Column(Text, nullable=True)
    locked_after_publish = Column(Boolean, nullable=False, default=False, index=True)
    state_revision = Column(Integer, nullable=False, default=1)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    version = relationship("RosterVersion", back_populates="assignments", lazy="joined")
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    department = relationship("Department", lazy="joined")
    base_station = relationship("BaseStation", lazy="joined")
    shift_template = relationship("ShiftTemplate", back_populates="assignments", lazy="joined")
    task_links = relationship("RosterTaskAssignmentLink", back_populates="roster_assignment", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")


class RosterRule(Base):
    __tablename__ = "roster_rules"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_roster_rules_amo_code"),
        Index("ix_roster_rules_amo_active", "amo_id", "is_active"),
        Index("ix_wr_roster_rules_scope", "amo_id", "scope", "department_id", "base_station_id"),
        CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from", name="ck_roster_rule_effective_dates"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    rule_type = Column(SAEnum(RosterRuleType, name="roster_rule_type_enum", native_enum=False), nullable=False, index=True)
    scope = Column(SAEnum(RosterRuleScope, name="roster_rule_scope_enum", native_enum=False), nullable=False, default=RosterRuleScope.AMO, index=True)
    severity = Column(SAEnum(RosterValidationSeverity, name="roster_rule_severity_enum", native_enum=False), nullable=False, default=RosterValidationSeverity.BLOCKER, index=True)
    parameters_json = Column(JSON, nullable=False, default=dict)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True)
    base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="CASCADE"), nullable=True, index=True)
    shift_template_id = Column(String(36), ForeignKey("shift_templates.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    allow_override = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    display_order = Column(Integer, nullable=False, default=100)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class RosterValidationFinding(Base):
    __tablename__ = "roster_validation_findings"
    __table_args__ = (
        Index("ix_roster_validation_version_severity", "version_id", "severity"),
        Index("ix_roster_validation_amo_user", "amo_id", "user_id"),
        Index("ix_roster_validation_rule", "rule_id", "resolved"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    rule_id = Column(String(36), ForeignKey("roster_rules.id", ondelete="SET NULL"), nullable=True, index=True)
    source = Column(SAEnum(RosterValidationSource, name="roster_validation_source_enum", native_enum=False), nullable=False, default=RosterValidationSource.ROSTER, index=True)
    severity = Column(SAEnum(RosterValidationSeverity, name="roster_validation_severity_enum", native_enum=False), nullable=False, index=True)
    code = Column(String(64), nullable=False, index=True)
    message = Column(Text, nullable=False)
    details_json = Column(JSON, nullable=True)
    overridable = Column(Boolean, nullable=False, default=False)
    resolved = Column(Boolean, nullable=False, default=False, index=True)
    overridden_at = Column(DateTime(timezone=True), nullable=True)
    overridden_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    override_reason = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    version = relationship("RosterVersion", back_populates="validation_findings", lazy="joined")
    rule = relationship("RosterRule", lazy="joined")


class RosterRuleException(Base):
    __tablename__ = "roster_rule_exceptions"
    __table_args__ = (
        Index("ix_roster_rule_exceptions_version", "version_id", "decision"),
        Index("ix_roster_rule_exceptions_rule", "rule_id", "user_id"),
        CheckConstraint("expires_at IS NULL OR expires_at >= created_at", name="ck_roster_rule_exception_expiry"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    finding_id = Column(String(36), ForeignKey("roster_validation_findings.id", ondelete="SET NULL"), nullable=True, index=True)
    rule_id = Column(String(36), ForeignKey("roster_rules.id", ondelete="SET NULL"), nullable=True, index=True)
    assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    decision = Column(SAEnum(RosterExceptionDecision, name="roster_exception_decision_enum", native_enum=False), nullable=False)
    reason = Column(Text, nullable=False)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    version = relationship("RosterVersion", back_populates="exceptions", lazy="joined")
    finding = relationship("RosterValidationFinding", lazy="joined")
    rule = relationship("RosterRule", lazy="joined")


class RosterDemandRequirement(Base):
    __tablename__ = "roster_demand_requirements"
    __table_args__ = (
        Index("ix_roster_demand_amo_time", "amo_id", "starts_at", "ends_at"),
        Index("ix_roster_demand_scope", "base_station_id", "department_id"),
        CheckConstraint("ends_at > starts_at", name="ck_roster_demand_time_order"),
        CheckConstraint("required_headcount >= 0", name="ck_roster_demand_headcount"),
        CheckConstraint("required_minutes >= 0", name="ck_roster_demand_minutes"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    base_station_id = Column(String(36), ForeignKey("base_stations.id", ondelete="CASCADE"), nullable=True, index=True)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=False, index=True)
    requirement_code = Column(String(64), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    required_headcount = Column(Integer, nullable=False, default=0)
    required_minutes = Column(Integer, nullable=False, default=0)
    role_label = Column(String(128), nullable=True)
    authorisation_type_id = Column(String(36), ForeignKey("authorisation_types.id", ondelete="SET NULL"), nullable=True, index=True)
    source_type = Column(String(64), nullable=False, default="MANUAL")
    source_id = Column(String(128), nullable=True, index=True)
    metadata_json = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class RosterPublicationAcknowledgement(Base):
    __tablename__ = "roster_publication_acknowledgements"
    __table_args__ = (
        UniqueConstraint("version_id", "user_id", name="uq_roster_ack_version_user"),
        UniqueConstraint("amo_id", "idempotency_key", name="uq_roster_ack_idempotency"),
        Index("ix_roster_ack_amo_user", "amo_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=True, index=True)
    delivery_status = Column(String(32), nullable=False, default="PENDING")
    viewed_at = Column(DateTime(timezone=True), nullable=True)
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


class RosterCommandReceipt(Base):
    __tablename__ = "roster_command_receipts"
    __table_args__ = (
        UniqueConstraint("amo_id", "idempotency_key", name="uq_roster_command_receipt_key"),
        Index("ix_roster_command_receipts_operation", "amo_id", "operation"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=False, index=True)
    operation = Column(String(64), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    request_hash = Column(String(128), nullable=False)
    response_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
