from __future__ import annotations

from datetime import datetime

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

from amodb.database import Base
from amodb.user_id import generate_user_id


class QualityAssuranceControl(Base):
    """Tenant control that joins regulations, process ownership and evidence.

    A control is intentionally more durable than an audit checklist question. It
    represents the continuing obligation that must remain effective between audit
    events, regardless of which framework or authority tests it next.
    """

    __tablename__ = "quality_assurance_controls"
    __table_args__ = (
        UniqueConstraint("amo_id", "control_code", name="uq_quality_assurance_control_code"),
        CheckConstraint(
            "criticality IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_quality_assurance_control_criticality",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'RETIRED')",
            name="ck_quality_assurance_control_status",
        ),
        CheckConstraint("test_frequency_days > 0", name="ck_quality_assurance_control_frequency"),
        Index("ix_quality_assurance_controls_due", "amo_id", "status", "next_test_due"),
        Index("ix_quality_assurance_controls_framework", "amo_id", "framework", "process_area"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    control_code = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    framework = Column(String(120), nullable=False, default="INTERNAL_QMS", server_default="INTERNAL_QMS")
    clause_reference = Column(String(255), nullable=True)
    process_area = Column(String(160), nullable=False)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    criticality = Column(String(16), nullable=False, default="MEDIUM", server_default="MEDIUM")
    status = Column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    test_frequency_days = Column(Integer, nullable=False, default=365, server_default="365")
    evidence_expectation = Column(Text, nullable=True)
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    next_test_due = Column(Date, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class QualityAssuranceEvidenceLink(Base):
    """Typed edge from an assurance control to authoritative portal evidence."""

    __tablename__ = "quality_assurance_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "control_id",
            "source_type",
            "source_id",
            "relationship",
            name="uq_quality_assurance_evidence_edge",
        ),
        CheckConstraint(
            "evidence_status IN ('LINKED', 'VERIFIED', 'EXPIRED', 'REJECTED')",
            name="ck_quality_assurance_evidence_status",
        ),
        Index("ix_quality_assurance_evidence_control", "amo_id", "control_id", "evidence_status"),
        Index("ix_quality_assurance_evidence_source", "amo_id", "source_type", "source_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    control_id = Column(
        String(36),
        ForeignKey("quality_assurance_controls.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type = Column(String(48), nullable=False)
    source_id = Column(String(160), nullable=False)
    relationship = Column(String(48), nullable=False, default="EVIDENCES", server_default="EVIDENCES")
    label = Column(String(255), nullable=True)
    evidence_status = Column(String(16), nullable=False, default="LINKED", server_default="LINKED")
    valid_until = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class QualityIntelligenceReview(Base):
    """Human-governed quality insight or machine-generated recommendation.

    Nothing in this table changes a regulated record. A user must explicitly
    accept, dismiss or implement the recommendation, preserving accountable QMS
    decision-making and a reviewable audit trail.
    """

    __tablename__ = "quality_intelligence_reviews"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PROPOSED', 'ACCEPTED', 'DISMISSED', 'IMPLEMENTED')",
            name="ck_quality_intelligence_review_status",
        ),
        CheckConstraint(
            "risk_level IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_quality_intelligence_review_risk",
        ),
        UniqueConstraint("amo_id", "source_fingerprint", name="uq_quality_intelligence_fingerprint"),
        Index("ix_quality_intelligence_queue", "amo_id", "status", "risk_level", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    insight_type = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    rationale = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    source_fingerprint = Column(String(160), nullable=False)
    risk_level = Column(String(16), nullable=False, default="MEDIUM", server_default="MEDIUM")
    status = Column(String(16), nullable=False, default="PROPOSED", server_default="PROPOSED")
    created_by = Column(String(32), nullable=False, default="RULE_ENGINE", server_default="RULE_ENGINE")
    human_decision_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    human_decision_note = Column(Text, nullable=True)
    decision_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
