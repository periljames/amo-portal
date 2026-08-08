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


class QualityAssuranceCase(Base):
    """Evidence-centred Quality case linking signals, findings and decisions."""

    __tablename__ = "quality_assurance_cases"
    __table_args__ = (
        UniqueConstraint("amo_id", "case_ref", name="uq_quality_assurance_case_ref"),
        CheckConstraint(
            "case_type IN ('SIGNAL','INVESTIGATION','RECURRING_FINDING','EFFECTIVENESS','SUPPLIER','REGULATORY','OTHER')",
            name="ck_quality_assurance_case_type",
        ),
        CheckConstraint(
            "status IN ('OPEN','INVESTIGATING','ACTION_PENDING','EFFECTIVENESS_REVIEW','CLOSED','CANCELLED')",
            name="ck_quality_assurance_case_status",
        ),
        CheckConstraint("severity IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_assurance_case_severity"),
        Index("ix_quality_assurance_cases_status", "amo_id", "status", "due_date"),
        Index("ix_quality_assurance_cases_owner", "amo_id", "owner_user_id", "status"),
        Index("ix_quality_assurance_cases_type", "amo_id", "case_type", "severity"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    case_ref = Column(String(64), nullable=False)
    case_type = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(16), nullable=False, default="MEDIUM", server_default="MEDIUM")
    status = Column(String(32), nullable=False, default="OPEN", server_default="OPEN")
    source_references = Column(JSON, nullable=False, default=list)
    regulatory_basis = Column(JSON, nullable=False, default=list)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(Date, nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closure_rationale = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    investigation_entries = relationship(
        "QualityInvestigationEntry",
        back_populates="case",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityInvestigationEntry.sequence_no, QualityInvestigationEntry.created_at",
        lazy="selectin",
    )
    effectiveness_plans = relationship(
        "QualityEffectivenessPlan",
        back_populates="case",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityEffectivenessPlan.created_at",
        lazy="selectin",
    )
    events = relationship(
        "QualityAssuranceCaseEvent",
        back_populates="case",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityAssuranceCaseEvent.created_at",
        lazy="selectin",
    )


class QualityInvestigationEntry(Base):
    """Append-only investigation statement with explicit epistemic class."""

    __tablename__ = "quality_investigation_entries"
    __table_args__ = (
        CheckConstraint(
            "method IN ('FIVE_WHYS','ISHIKAWA','CAUSAL_FACTOR','BARRIER_ANALYSIS','CHANGE_ANALYSIS','HUMAN_ORGANIZATIONAL')",
            name="ck_quality_investigation_method",
        ),
        CheckConstraint(
            "entry_type IN ('FACT','HYPOTHESIS','CAUSAL_CONCLUSION')",
            name="ck_quality_investigation_entry_type",
        ),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 100)", name="ck_quality_investigation_confidence"),
        Index("ix_quality_investigation_case", "amo_id", "case_id", "method", "sequence_no"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("quality_assurance_cases.id", ondelete="CASCADE"), nullable=False)
    method = Column(String(32), nullable=False)
    entry_type = Column(String(24), nullable=False)
    sequence_no = Column(Integer, nullable=False, default=1, server_default="1")
    category = Column(String(80), nullable=True)
    prompt = Column(Text, nullable=True)
    statement = Column(Text, nullable=False)
    confidence = Column(Integer, nullable=True)
    evidence_references = Column(JSON, nullable=False, default=list)
    parent_entry_id = Column(String(36), ForeignKey("quality_investigation_entries.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    case = relationship("QualityAssuranceCase", back_populates="investigation_entries", lazy="joined")


class QualityEffectivenessPlan(Base):
    """Governed effectiveness test for corrective action or assurance treatment."""

    __tablename__ = "quality_effectiveness_plans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PLANNED','OBSERVING','READY_FOR_REVIEW','CONCLUDED','REOPENED','CANCELLED')",
            name="ck_quality_effectiveness_status",
        ),
        CheckConstraint(
            "conclusion IS NULL OR conclusion IN ('EFFECTIVE','PARTIALLY_EFFECTIVE','INEFFECTIVE','INCONCLUSIVE')",
            name="ck_quality_effectiveness_conclusion",
        ),
        Index("ix_quality_effectiveness_due", "amo_id", "planned_review_date", "status"),
        Index("ix_quality_effectiveness_case", "amo_id", "case_id", "status"),
        Index("ix_quality_effectiveness_source", "amo_id", "source_type", "source_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("quality_assurance_cases.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(String(48), nullable=True)
    source_id = Column(String(160), nullable=True)
    source_route = Column(String(500), nullable=True)
    expected_outcome = Column(Text, nullable=False)
    effectiveness_measure = Column(Text, nullable=False)
    verification_method = Column(Text, nullable=False)
    observation_window = Column(String(255), nullable=True)
    source_indicators = Column(JSON, nullable=False, default=list)
    responsible_reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    planned_review_date = Column(Date, nullable=False)
    status = Column(String(24), nullable=False, default="PLANNED", server_default="PLANNED")
    conclusion = Column(String(24), nullable=True)
    conclusion_rationale = Column(Text, nullable=True)
    conclusion_evidence = Column(JSON, nullable=False, default=list)
    concluded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    concluded_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    case = relationship("QualityAssuranceCase", back_populates="effectiveness_plans", lazy="joined")


class QualityAssuranceCaseEvent(Base):
    """Immutable human-attributed case/effectiveness lifecycle history."""

    __tablename__ = "quality_assurance_case_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('CREATED','STATUS_CHANGED','INVESTIGATION_ADDED','EFFECTIVENESS_PLANNED','EFFECTIVENESS_CONCLUDED','REOPENED','ESCALATED','CLOSED','CANCELLED')",
            name="ck_quality_assurance_case_event_type",
        ),
        Index("ix_quality_assurance_case_events", "amo_id", "case_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("quality_assurance_cases.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(32), nullable=False)
    reason = Column(Text, nullable=False)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    case = relationship("QualityAssuranceCase", back_populates="events", lazy="joined")
