from __future__ import annotations

import uuid
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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from amodb.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user_fk() -> ForeignKey:
    return ForeignKey("users.id", ondelete="SET NULL")


class QualityCARControlProfile(Base):
    __tablename__ = "quality_car_control_profiles"
    __table_args__ = (
        UniqueConstraint("car_id", name="uq_quality_car_control_profile_car"),
        Index("ix_quality_car_control_profile_due", "amo_id", "current_due_date"),
        Index("ix_quality_car_control_profile_owner", "amo_id", "accountable_owner_user_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    car_id = Column(UUID(as_uuid=True), ForeignKey("quality_cars.id", ondelete="CASCADE"), nullable=False, index=True)
    accountable_owner_user_id = Column(String(36), _user_fk(), nullable=True, index=True)
    original_due_date = Column(Date, nullable=False)
    current_due_date = Column(Date, nullable=False, index=True)
    effectiveness_required = Column(Boolean, nullable=False, default=True)
    initialized_from = Column(String(32), nullable=False, default="CAR")
    created_by_user_id = Column(String(36), _user_fk(), nullable=True)
    updated_by_user_id = Column(String(36), _user_fk(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    milestones = relationship(
        "QualityCARMilestone",
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="QualityCARMilestone.phase_order",
    )


class QualityCARMilestone(Base):
    __tablename__ = "quality_car_milestones"
    __table_args__ = (
        UniqueConstraint("profile_id", "milestone_key", name="uq_quality_car_milestone_key"),
        CheckConstraint(
            "milestone_key IN ('RCA_SUBMISSION','CAP_APPROVAL','IMPLEMENTATION_COMPLETE','EVIDENCE_COMPLETE','EFFECTIVENESS_REVIEW')",
            name="ck_quality_car_milestone_key",
        ),
        CheckConstraint(
            "status IN ('PLANNED','IN_PROGRESS','SUBMITTED','ACCEPTED','REJECTED','BLOCKED','COMPLETED','WAIVED')",
            name="ck_quality_car_milestone_status",
        ),
        Index("ix_quality_car_milestone_due", "amo_id", "current_due_date", "status"),
        Index("ix_quality_car_milestone_owner", "amo_id", "owner_user_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(UUID(as_uuid=True), ForeignKey("quality_car_control_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    car_id = Column(UUID(as_uuid=True), ForeignKey("quality_cars.id", ondelete="CASCADE"), nullable=False, index=True)
    milestone_key = Column(String(40), nullable=False)
    phase_order = Column(Integer, nullable=False)
    title = Column(String(160), nullable=False)
    owner_user_id = Column(String(36), _user_fk(), nullable=True, index=True)
    original_due_date = Column(Date, nullable=False)
    current_due_date = Column(Date, nullable=False, index=True)
    status = Column(String(24), nullable=False, default="PLANNED", index=True)
    notes = Column(Text, nullable=True)
    evidence_ref = Column(String(1024), nullable=True)
    completed_by_user_id = Column(String(36), _user_fk(), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id = Column(String(36), _user_fk(), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    profile = relationship("QualityCARControlProfile", back_populates="milestones", lazy="joined")


class QualityCARDependency(Base):
    __tablename__ = "quality_car_dependencies"
    __table_args__ = (
        CheckConstraint(
            "dependency_type IN ('INTERNAL','EXTERNAL','PROCUREMENT','FACILITY','RESOURCE','SUPPLIER','REGULATORY','OTHER')",
            name="ck_quality_car_dependency_type",
        ),
        CheckConstraint(
            "status IN ('OPEN','MITIGATING','MITIGATED','RESOLVED','ACCEPTED_RISK','CANCELLED')",
            name="ck_quality_car_dependency_status",
        ),
        CheckConstraint("risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_car_dependency_risk"),
        Index("ix_quality_car_dependency_state", "amo_id", "car_id", "status", "risk_level"),
        Index("ix_quality_car_dependency_due", "amo_id", "due_date", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    car_id = Column(UUID(as_uuid=True), ForeignKey("quality_cars.id", ondelete="CASCADE"), nullable=False, index=True)
    milestone_id = Column(UUID(as_uuid=True), ForeignKey("quality_car_milestones.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    dependency_type = Column(String(24), nullable=False, default="OTHER")
    owner_user_id = Column(String(36), _user_fk(), nullable=True, index=True)
    due_date = Column(Date, nullable=True, index=True)
    risk_level = Column(String(16), nullable=False, default="MEDIUM")
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    blocks_closure = Column(Boolean, nullable=False, default=False)
    mitigation_plan = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), _user_fk(), nullable=True)
    updated_by_user_id = Column(String(36), _user_fk(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class QualityCARDeadlineChange(Base):
    __tablename__ = "quality_car_deadline_changes"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED','CANCELLED')", name="ck_quality_car_deadline_change_status"),
        Index("ix_quality_car_deadline_change_state", "amo_id", "car_id", "status", "created_at"),
        Index("ix_quality_car_deadline_change_milestone", "amo_id", "milestone_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    car_id = Column(UUID(as_uuid=True), ForeignKey("quality_cars.id", ondelete="CASCADE"), nullable=False, index=True)
    milestone_id = Column(UUID(as_uuid=True), ForeignKey("quality_car_milestones.id", ondelete="CASCADE"), nullable=True, index=True)
    previous_due_date = Column(Date, nullable=False)
    requested_due_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=False)
    impact_statement = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="PENDING", index=True)
    requested_by_user_id = Column(String(36), _user_fk(), nullable=True)
    reviewed_by_user_id = Column(String(36), _user_fk(), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class QualityCARControlEvent(Base):
    __tablename__ = "quality_car_control_events"
    __table_args__ = (
        UniqueConstraint("car_id", "event_key", name="uq_quality_car_control_event_key"),
        CheckConstraint("severity IN ('INFO','ACTION_REQUIRED','WARNING','CRITICAL')", name="ck_quality_car_control_event_severity"),
        Index("ix_quality_car_control_event_timeline", "amo_id", "car_id", "created_at"),
        Index("ix_quality_car_control_event_type", "amo_id", "event_type", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    car_id = Column(UUID(as_uuid=True), ForeignKey("quality_cars.id", ondelete="CASCADE"), nullable=False, index=True)
    milestone_id = Column(UUID(as_uuid=True), ForeignKey("quality_car_milestones.id", ondelete="SET NULL"), nullable=True, index=True)
    event_key = Column(String(180), nullable=True)
    event_type = Column(String(48), nullable=False, index=True)
    severity = Column(String(24), nullable=False, default="INFO")
    reason = Column(Text, nullable=False)
    snapshot = Column(JSON, nullable=False, default=dict)
    actor_user_id = Column(String(36), _user_fk(), nullable=True)
    system_generated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
