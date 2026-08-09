from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
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
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityMission(Base):
    """Governed cross-department Quality project/change.

    A Mission coordinates evidence and decisions owned across the AMO. It does
    not replace the source records in Fleet, Tooling, Training, DMS, Stores or
    other operational domains.
    """

    __tablename__ = "quality_missions"
    __table_args__ = (
        UniqueConstraint("amo_id", "mission_ref", name="uq_quality_mission_ref"),
        CheckConstraint(
            "mission_type IN ("
            "'CAPABILITY_ADDITION','CAPABILITY_CHANGE','LINE_STATION','SUPPLIER_APPROVAL',"
            "'SUBCONTRACTOR_APPROVAL','REGULATORY_TRANSITION','AMO_RENEWAL',"
            "'AUTHORIZATION_CAMPAIGN','PROCEDURE_CHANGE','IMPROVEMENT')",
            name="ck_quality_mission_type",
        ),
        CheckConstraint(
            "status IN ("
            "'DRAFT','PLANNING','IN_PROGRESS','GATE_REVIEW','READY_FOR_APPROVAL',"
            "'APPROVED','SUBMITTED_TO_AUTHORITY','COMPLETE','CANCELLED')",
            name="ck_quality_mission_status",
        ),
        CheckConstraint(
            "risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_quality_mission_risk",
        ),
        Index("ix_quality_missions_status", "amo_id", "status", "target_date"),
        Index("ix_quality_missions_owner", "amo_id", "owner_user_id", "status"),
        Index("ix_quality_missions_type", "amo_id", "mission_type", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    mission_ref = Column(String(64), nullable=False)
    mission_type = Column(String(40), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    scope = Column(JSON, nullable=False, default=dict)
    regulatory_basis = Column(JSON, nullable=False, default=list)
    risk_level = Column(String(16), nullable=False, default="MEDIUM", server_default="MEDIUM")
    status = Column(String(32), nullable=False, default="DRAFT", server_default="DRAFT")

    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sponsor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    requested_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    target_date = Column(Date, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    gates = relationship(
        "QualityMissionGate",
        back_populates="mission",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="QualityMissionGate.sort_order, QualityMissionGate.gate_code",
    )
    decisions = relationship(
        "QualityMissionDecision",
        back_populates="mission",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="QualityMissionDecision.created_at",
    )


class QualityMissionGate(Base):
    """Readiness dependency backed by authoritative source evidence."""

    __tablename__ = "quality_mission_gates"
    __table_args__ = (
        UniqueConstraint("mission_id", "gate_code", name="uq_quality_mission_gate_code"),
        CheckConstraint("gate_type IN ('HARD','SOFT')", name="ck_quality_mission_gate_type"),
        CheckConstraint(
            "status IN ('PENDING','IN_PROGRESS','PASS','FAIL','BLOCKED')",
            name="ck_quality_mission_gate_status",
        ),
        CheckConstraint(
            "evidence_status IN ('UNLINKED','LINKED','VERIFIED','REJECTED','EXPIRED')",
            name="ck_quality_mission_gate_evidence_status",
        ),
        Index("ix_quality_mission_gates_state", "amo_id", "mission_id", "gate_type", "status"),
        Index("ix_quality_mission_gates_source", "amo_id", "source_type", "source_id"),
        Index("ix_quality_mission_gates_due", "amo_id", "due_date", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    mission_id = Column(
        String(36),
        ForeignKey("quality_missions.id", ondelete="CASCADE"),
        nullable=False,
    )
    gate_code = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    category = Column(String(80), nullable=False)
    description = Column(Text, nullable=True)
    gate_type = Column(String(12), nullable=False, default="HARD", server_default="HARD")
    status = Column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    requirement_ref = Column(String(255), nullable=True)

    source_owner_module = Column(String(80), nullable=True)
    source_type = Column(String(48), nullable=True)
    source_id = Column(String(160), nullable=True)
    source_route = Column(String(500), nullable=True)
    source_snapshot = Column(JSON, nullable=True)
    evidence_status = Column(String(16), nullable=False, default="UNLINKED", server_default="UNLINKED")

    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(Date, nullable=True)
    blocking_reason = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=100, server_default="100")

    passed_at = Column(DateTime(timezone=True), nullable=True)
    passed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    mission = relationship("QualityMission", back_populates="gates", lazy="joined")


class QualityMissionDecision(Base):
    """Immutable human decision in a Mission approval chain."""

    __tablename__ = "quality_mission_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision_type IN ("
            "'QUALITY_SELF_EVALUATION','ACCOUNTABLE_EXECUTIVE','AUTHORITY_SUBMISSION',"
            "'AUTHORITY_ACCEPTANCE','CUSTOM')",
            name="ck_quality_mission_decision_type",
        ),
        CheckConstraint(
            "status IN ('APPROVED','REJECTED','RETURNED')",
            name="ck_quality_mission_decision_status",
        ),
        Index("ix_quality_mission_decisions", "amo_id", "mission_id", "decision_type", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    mission_id = Column(
        String(36),
        ForeignKey("quality_missions.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision_type = Column(String(40), nullable=False)
    status = Column(String(16), nullable=False)
    rationale = Column(Text, nullable=False)
    evidence_snapshot = Column(JSON, nullable=False, default=dict)
    decided_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    mission = relationship("QualityMission", back_populates="decisions", lazy="joined")
