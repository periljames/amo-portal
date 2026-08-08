from __future__ import annotations

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
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityPrivilegeRule(Base):
    """Tenant-owned definition of an internal Quality privilege.

    The rule stores only the Quality decision contract. Training, workforce and
    roster records remain in their authoritative modules and are evaluated by
    source reference at decision/use time.
    """

    __tablename__ = "quality_privilege_rules"
    __table_args__ = (
        UniqueConstraint("amo_id", "privilege_code", name="uq_quality_privilege_rule_code"),
        CheckConstraint(
            "privilege_type IN ('AUDITOR','LEAD_AUDITOR','QUALITY_INSPECTOR','AUTHORIZATION_REVIEWER','CUSTOM')",
            name="ck_quality_privilege_rule_type",
        ),
        CheckConstraint("max_concurrent_assignments IS NULL OR max_concurrent_assignments >= 1", name="ck_quality_privilege_rule_capacity"),
        Index("ix_quality_privilege_rules_active", "amo_id", "is_active", "privilege_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    privilege_code = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    privilege_type = Column(String(40), nullable=False)
    description = Column(Text, nullable=True)
    required_training_course_codes = Column(JSON, nullable=False, default=list)
    independence_required = Column(Boolean, nullable=False, default=True, server_default="true")
    max_concurrent_assignments = Column(Integer, nullable=True)
    scope_schema = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class QualityPrivilege(Base):
    """Current internal authorization granted by Quality to one person."""

    __tablename__ = "quality_privileges"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','SUSPENDED','REVOKED','EXPIRED')",
            name="ck_quality_privilege_status",
        ),
        CheckConstraint(
            "effective_from IS NULL OR expires_on IS NULL OR expires_on >= effective_from",
            name="ck_quality_privilege_dates",
        ),
        UniqueConstraint("amo_id", "user_id", "privilege_code", "scope_key", name="uq_quality_privilege_identity"),
        Index("ix_quality_privileges_person", "amo_id", "user_id", "status"),
        Index("ix_quality_privileges_code", "amo_id", "privilege_code", "status"),
        Index("ix_quality_privileges_expiry", "amo_id", "expires_on", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    rule_id = Column(String(36), ForeignKey("quality_privilege_rules.id", ondelete="RESTRICT"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    privilege_code = Column(String(64), nullable=False)
    scope_key = Column(String(255), nullable=False, default="GLOBAL", server_default="GLOBAL")
    scope = Column(JSON, nullable=False, default=dict)
    limitations = Column(JSON, nullable=False, default=list)
    status = Column(String(16), nullable=False, default="DRAFT", server_default="DRAFT")
    effective_from = Column(Date, nullable=True)
    expires_on = Column(Date, nullable=True)
    latest_decision_id = Column(String(36), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    rule = relationship("QualityPrivilegeRule", lazy="joined")
    decisions = relationship(
        "QualityPrivilegeDecision",
        back_populates="privilege",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QualityPrivilegeDecision.created_at",
        lazy="selectin",
        foreign_keys="QualityPrivilegeDecision.privilege_id",
    )


class QualityPrivilegeDecision(Base):
    """Append-only human decision changing privilege state."""

    __tablename__ = "quality_privilege_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision_type IN ('GRANT','RENEW','SUSPEND','REINSTATE','REVOKE','EXPIRE','REJECT')",
            name="ck_quality_privilege_decision_type",
        ),
        CheckConstraint(
            "resulting_status IN ('DRAFT','ACTIVE','SUSPENDED','REVOKED','EXPIRED')",
            name="ck_quality_privilege_decision_status",
        ),
        Index("ix_quality_privilege_decisions_history", "amo_id", "privilege_id", "created_at"),
        Index("ix_quality_privilege_decisions_actor", "amo_id", "decided_by_user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    privilege_id = Column(String(36), ForeignKey("quality_privileges.id", ondelete="CASCADE"), nullable=False)
    decision_type = Column(String(16), nullable=False)
    resulting_status = Column(String(16), nullable=False)
    rationale = Column(Text, nullable=False)
    eligibility_snapshot = Column(JSON, nullable=False, default=dict)
    source_references = Column(JSON, nullable=False, default=list)
    effective_from = Column(Date, nullable=True)
    expires_on = Column(Date, nullable=True)
    decided_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    privilege = relationship("QualityPrivilege", back_populates="decisions", lazy="joined", foreign_keys=[privilege_id])


class QualityIndependenceDeclaration(Base):
    """Attributable auditor independence declaration for one governed context."""

    __tablename__ = "quality_independence_declarations"
    __table_args__ = (
        CheckConstraint(
            "declaration IN ('INDEPENDENT','CONFLICT','REQUIRES_REVIEW')",
            name="ck_quality_independence_declaration",
        ),
        CheckConstraint(
            "context_type IN ('AUDIT','AUDIT_SCHEDULE','PROGRAMME_ITEM','ASSURANCE_CASE','MISSION','OTHER')",
            name="ck_quality_independence_context",
        ),
        UniqueConstraint("amo_id", "user_id", "context_type", "context_id", name="uq_quality_independence_context"),
        Index("ix_quality_independence_lookup", "amo_id", "context_type", "context_id", "declaration"),
        Index("ix_quality_independence_person", "amo_id", "user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    context_type = Column(String(24), nullable=False)
    context_id = Column(String(160), nullable=False)
    declaration = Column(String(24), nullable=False)
    relationship_to_subject = Column(Text, nullable=True)
    rationale = Column(Text, nullable=False)
    source_references = Column(JSON, nullable=False, default=list)
    declared_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    declared_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
