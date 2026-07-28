"""Tenant-scoped roster automation policy and immutable execution evidence."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
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


class RosterAutomationFrequency(str, enum.Enum):
    MONTHLY = "MONTHLY"
    FORTNIGHTLY = "FORTNIGHTLY"
    WEEKLY = "WEEKLY"
    MANUAL = "MANUAL"


class RosterAutomationRunStatus(str, enum.Enum):
    PREVIEWED = "PREVIEWED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_CONFLICTS = "COMPLETED_WITH_CONFLICTS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RosterAutomationTrigger(str, enum.Enum):
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"
    PERIOD_CREATED = "PERIOD_CREATED"


class RosterGenerationPolicy(Base):
    __tablename__ = "roster_generation_policies"
    __table_args__ = (
        UniqueConstraint("amo_id", name="uq_roster_generation_policy_amo"),
        Index("ix_roster_generation_policy_enabled", "enabled", "next_run_at"),
        CheckConstraint("lead_periods >= 1 AND lead_periods <= 12", name="ck_roster_generation_policy_lead"),
        CheckConstraint("run_day >= 1 AND run_day <= 28", name="ck_roster_generation_policy_run_day"),
        CheckConstraint("run_hour_local >= 0 AND run_hour_local <= 23", name="ck_roster_generation_policy_run_hour"),
        CheckConstraint("state_revision >= 1", name="ck_roster_generation_policy_revision"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=False, index=True)
    frequency = Column(
        SAEnum(RosterAutomationFrequency, name="roster_automation_frequency_enum", native_enum=False),
        nullable=False,
        default=RosterAutomationFrequency.MONTHLY,
    )
    lead_periods = Column(Integer, nullable=False, default=1)
    run_day = Column(Integer, nullable=False, default=15)
    run_hour_local = Column(Integer, nullable=False, default=6)
    timezone_name = Column(String(64), nullable=False, default="UTC")
    period_code_pattern = Column(String(128), nullable=False, default="{YYYY}-{MM}")
    period_name_pattern = Column(String(255), nullable=False, default="{MMMM} {YYYY} duty roster")
    create_initial_draft = Column(Boolean, nullable=False, default=True)
    generate_from_patterns = Column(Boolean, nullable=False, default=True)
    preserve_source_commitments = Column(Boolean, nullable=False, default=True)
    validate_after_generation = Column(Boolean, nullable=False, default=True)
    notify_planners = Column(Boolean, nullable=False, default=True)
    require_preview_confirmation = Column(Boolean, nullable=False, default=True)
    state_revision = Column(Integer, nullable=False, default=1)
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    updated_reason = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    runs = relationship(
        "RosterGenerationRun",
        back_populates="policy",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class RosterGenerationRun(Base):
    __tablename__ = "roster_generation_runs"
    __table_args__ = (
        UniqueConstraint("amo_id", "idempotency_key", name="uq_roster_generation_run_idempotency"),
        Index("ix_roster_generation_runs_amo_created", "amo_id", "created_at"),
        Index("ix_roster_generation_runs_status", "amo_id", "status"),
        CheckConstraint("generated_count >= 0", name="ck_roster_generation_run_generated"),
        CheckConstraint("skipped_count >= 0", name="ck_roster_generation_run_skipped"),
        CheckConstraint("conflict_count >= 0", name="ck_roster_generation_run_conflicts"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_id = Column(String(36), ForeignKey("roster_generation_policies.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger = Column(
        SAEnum(RosterAutomationTrigger, name="roster_automation_trigger_enum", native_enum=False),
        nullable=False,
        default=RosterAutomationTrigger.MANUAL,
    )
    status = Column(
        SAEnum(RosterAutomationRunStatus, name="roster_automation_run_status_enum", native_enum=False),
        nullable=False,
        default=RosterAutomationRunStatus.RUNNING,
        index=True,
    )
    idempotency_key = Column(String(128), nullable=False)
    dry_run = Column(Boolean, nullable=False, default=False)
    period_id = Column(String(36), ForeignKey("roster_periods.id", ondelete="SET NULL"), nullable=True, index=True)
    version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    target_from = Column(String(10), nullable=False)
    target_to = Column(String(10), nullable=False)
    generated_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    conflict_count = Column(Integer, nullable=False, default=0)
    validation_blocker_count = Column(Integer, nullable=False, default=0)
    validation_warning_count = Column(Integer, nullable=False, default=0)
    summary_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    policy = relationship("RosterGenerationPolicy", back_populates="runs", lazy="joined")
    period = relationship("RosterPeriod", lazy="joined")
    version = relationship("RosterVersion", lazy="joined")
