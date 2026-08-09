from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualitySignalRule(Base):
    """Explainable deterministic Quality surveillance rule."""

    __tablename__ = "quality_signal_rules"
    __table_args__ = (
        UniqueConstraint("amo_id", "rule_code", name="uq_quality_signal_rule_code"),
        CheckConstraint(
            "metric IN ('PROGRAMME_COMPLETION_RATE','PROGRAMME_DEFERRAL_RATE','OPEN_FINDING_COUNT','FINDING_RECURRENCE_COUNT','OVERDUE_CAR_COUNT','CAR_AGE_DAYS','INEFFECTIVE_ACTION_RATE','AUDITOR_CAPACITY_EXCEPTIONS','OPEN_ASSURANCE_CASES')",
            name="ck_quality_signal_rule_metric",
        ),
        CheckConstraint(
            "operator IN ('GT','GTE','LT','LTE','EQ')",
            name="ck_quality_signal_rule_operator",
        ),
        CheckConstraint("severity IN ('INFO','WATCH','WARNING','CRITICAL')", name="ck_quality_signal_rule_severity"),
        Index("ix_quality_signal_rules_active", "amo_id", "is_active", "metric"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    rule_code = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    metric = Column(String(48), nullable=False)
    operator = Column(String(8), nullable=False)
    threshold = Column(Numeric(18, 6), nullable=False)
    severity = Column(String(16), nullable=False, default="WATCH", server_default="WATCH")
    explanation = Column(Text, nullable=False)
    source_contract = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class QualitySignalObservation(Base):
    """Immutable evaluated signal with source lineage and as-of timestamp."""

    __tablename__ = "quality_signal_observations"
    __table_args__ = (
        CheckConstraint("severity IN ('INFO','WATCH','WARNING','CRITICAL')", name="ck_quality_signal_observation_severity"),
        CheckConstraint("state IN ('OPEN','ACKNOWLEDGED','CONVERTED_TO_CASE','CLOSED')", name="ck_quality_signal_observation_state"),
        Index("ix_quality_signal_observations_open", "amo_id", "state", "severity", "observed_at"),
        Index("ix_quality_signal_observations_rule", "amo_id", "rule_id", "observed_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    rule_id = Column(String(36), ForeignKey("quality_signal_rules.id", ondelete="CASCADE"), nullable=False)
    metric = Column(String(48), nullable=False)
    observed_value = Column(Numeric(18, 6), nullable=False)
    threshold = Column(Numeric(18, 6), nullable=False)
    operator = Column(String(8), nullable=False)
    triggered = Column(Boolean, nullable=False)
    severity = Column(String(16), nullable=False)
    explanation = Column(Text, nullable=False)
    source_snapshot = Column(JSON, nullable=False, default=dict)
    source_references = Column(JSON, nullable=False, default=list)
    as_of = Column(DateTime(timezone=True), nullable=False)
    state = Column(String(24), nullable=False, default="OPEN", server_default="OPEN")
    assurance_case_id = Column(String(36), ForeignKey("quality_assurance_cases.id", ondelete="SET NULL"), nullable=True)
    observed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class QualityRequirementNode(Base):
    """Reference node in the AMO approval/requirement impact graph."""

    __tablename__ = "quality_requirement_nodes"
    __table_args__ = (
        CheckConstraint(
            "node_type IN ('REQUIREMENT','APPROVAL','MANUAL','PROCEDURE','FORM','TRAINING','ROLE','CHECKLIST','EVIDENCE','MISSION','FINDING','ACTION','CAPABILITY')",
            name="ck_quality_requirement_node_type",
        ),
        CheckConstraint(
            "support_state IN ('SUPPORTED','UNSUPPORTED','STALE','UNRESOLVED','BLOCKED')",
            name="ck_quality_requirement_node_state",
        ),
        UniqueConstraint("amo_id", "node_type", "source_owner_module", "source_type", "source_id", name="uq_quality_requirement_node_source"),
        Index("ix_quality_requirement_nodes_state", "amo_id", "node_type", "support_state"),
        Index("ix_quality_requirement_nodes_owner", "amo_id", "source_owner_module", "source_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    node_type = Column(String(24), nullable=False)
    title = Column(String(255), nullable=False)
    source_owner_module = Column(String(80), nullable=False)
    source_type = Column(String(80), nullable=False)
    source_id = Column(String(160), nullable=False)
    source_route = Column(String(500), nullable=True)
    support_state = Column(String(16), nullable=False, default="UNRESOLVED", server_default="UNRESOLVED")
    state_reason = Column(Text, nullable=False)
    source_snapshot = Column(JSON, nullable=True)
    evidence_as_of = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class QualityRequirementLink(Base):
    """Directed source-attributed relationship between impact graph nodes."""

    __tablename__ = "quality_requirement_links"
    __table_args__ = (
        CheckConstraint(
            "relationship IN ('REQUIRES','IMPLEMENTS','EVIDENCES','AUTHORIZES','DEPENDS_ON','AFFECTS','VERIFIES','BLOCKS','SUPERSEDES')",
            name="ck_quality_requirement_link_relationship",
        ),
        UniqueConstraint("amo_id", "from_node_id", "to_node_id", "relationship", name="uq_quality_requirement_link"),
        Index("ix_quality_requirement_links_from", "amo_id", "from_node_id", "relationship"),
        Index("ix_quality_requirement_links_to", "amo_id", "to_node_id", "relationship"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    from_node_id = Column(String(36), ForeignKey("quality_requirement_nodes.id", ondelete="CASCADE"), nullable=False)
    to_node_id = Column(String(36), ForeignKey("quality_requirement_nodes.id", ondelete="CASCADE"), nullable=False)
    relationship = Column(String(24), nullable=False)
    rationale = Column(Text, nullable=False)
    evidence_references = Column(JSON, nullable=False, default=list)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
