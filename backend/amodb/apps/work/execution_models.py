from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProductionExecutionSession(Base):
    __tablename__ = "production_execution_sessions"
    __table_args__ = (
        Index("ix_execution_sessions_amo_status", "amo_id", "status"),
        Index("ix_execution_sessions_package", "work_package_id", "started_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    work_package_id = Column(Integer, ForeignKey("work_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=True, index=True)
    package_freeze_id = Column(String(36), ForeignKey("work_package_freezes.id", ondelete="RESTRICT"), nullable=False, index=True)
    shift_reference = Column(String(64), nullable=True)
    station = Column(String(16), nullable=True)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    started_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    closed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closure_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    events = relationship(
        "ProductionExecutionEvent",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    issues = relationship(
        "ProductionTaskIssue",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class ProductionExecutionEvent(Base):
    __tablename__ = "production_execution_events"
    __table_args__ = (
        Index("ix_execution_events_session_time", "session_id", "occurred_at"),
        Index("ix_execution_events_task", "task_card_id", "occurred_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("production_execution_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    task_card_id = Column(Integer, ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    from_status = Column(String(24), nullable=True)
    to_status = Column(String(24), nullable=True)
    payload_json = Column(JSON, nullable=False, default=dict)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    session = relationship("ProductionExecutionSession", back_populates="events", lazy="joined")


class ProductionTaskIssue(Base):
    __tablename__ = "production_task_issues"
    __table_args__ = (
        Index("ix_task_issues_session_status", "session_id", "status"),
        Index("ix_task_issues_amo_severity", "amo_id", "severity", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("production_execution_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    task_card_id = Column(Integer, ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True, index=True)
    category = Column(String(32), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default="MEDIUM", index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    disposition = Column(String(32), nullable=True)
    linked_non_routine_task_id = Column(Integer, ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True)
    evidence_json = Column(JSON, nullable=False, default=list)
    raised_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    raised_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    resolved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    session = relationship("ProductionExecutionSession", back_populates="issues", lazy="joined")


class RecordsHandbackPackage(Base):
    __tablename__ = "records_handback_packages"
    __table_args__ = (
        UniqueConstraint("work_package_id", "version", name="uq_handback_package_version"),
        Index("ix_handback_packages_amo_status", "amo_id", "status"),
        Index("ix_handback_packages_package", "work_package_id", "version"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    work_package_id = Column(Integer, ForeignKey("work_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    package_freeze_id = Column(String(36), ForeignKey("work_package_freezes.id", ondelete="RESTRICT"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", index=True)
    manifest_hash = Column(String(64), nullable=False)
    manifest_json = Column(JSON, nullable=False, default=dict)
    readiness_json = Column(JSON, nullable=False, default=dict)
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    findings = relationship(
        "RecordsHandbackFinding",
        back_populates="handback",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    events = relationship(
        "RecordsHandbackEvent",
        back_populates="handback",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class RecordsHandbackFinding(Base):
    __tablename__ = "records_handback_findings"
    __table_args__ = (Index("ix_handback_findings_handback_status", "handback_id", "status"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    handback_id = Column(String(36), ForeignKey("records_handback_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(32), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default="ERROR", index=True)
    description = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    response_notes = Column(Text, nullable=True)
    raised_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    raised_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    resolved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    handback = relationship("RecordsHandbackPackage", back_populates="findings", lazy="joined")


class RecordsHandbackEvent(Base):
    __tablename__ = "records_handback_events"
    __table_args__ = (Index("ix_handback_events_handback_time", "handback_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    handback_id = Column(String(36), ForeignKey("records_handback_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(32), nullable=False)
    from_status = Column(String(24), nullable=True)
    to_status = Column(String(24), nullable=False)
    notes = Column(Text, nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    handback = relationship("RecordsHandbackPackage", back_populates="events", lazy="joined")
