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
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from amodb.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class SupplierGovernancePolicy(Base):
    """Tenant-owned supplier evaluation and re-evaluation policy.

    The portal intentionally provides no regulatory or tenant-specific interval
    defaults here. A tenant must configure the risk intervals and surveillance
    triggers before a supplier can be approved through the governed workflow.
    """

    __tablename__ = "procurement_supplier_governance_policies"
    __table_args__ = (
        UniqueConstraint("amo_id", name="uq_supplier_governance_policy_amo"),
        CheckConstraint("revision_no >= 1", name="ck_supplier_governance_policy_revision"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_no = Column(Integer, nullable=False, default=1)
    risk_review_days = Column(JSON, nullable=False)
    re_evaluation_rules = Column(JSON, nullable=False)
    require_independent_review = Column(Boolean, nullable=False, default=True)
    conditional_approval_allowed = Column(Boolean, nullable=False, default=True)
    effective_from = Column(Date, nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class SupplierEvaluationTemplate(Base):
    __tablename__ = "procurement_supplier_evaluation_templates"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", "revision_no", name="uq_supplier_eval_template_revision"),
        Index("ix_supplier_eval_template_amo_status", "amo_id", "status"),
        CheckConstraint("revision_no >= 1", name="ck_supplier_eval_template_revision"),
        CheckConstraint("pass_threshold IS NULL OR (pass_threshold >= 0 AND pass_threshold <= 100)", name="ck_supplier_eval_template_threshold"),
        CheckConstraint("status IN ('DRAFT','ACTIVE','RETIRED')", name="ck_supplier_eval_template_status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    revision_no = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="DRAFT", index=True)
    pass_threshold = Column(Numeric(5, 2), nullable=True)
    manual_references = Column(JSON, nullable=False, default=list)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    activated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class SupplierEvaluationCriterion(Base):
    __tablename__ = "procurement_supplier_evaluation_criteria"
    __table_args__ = (
        UniqueConstraint("template_id", "criterion_key", name="uq_supplier_eval_criterion_key"),
        UniqueConstraint("template_id", "sequence_no", name="uq_supplier_eval_criterion_sequence"),
        Index("ix_supplier_eval_criteria_template", "template_id", "sequence_no"),
        CheckConstraint("sequence_no >= 1", name="ck_supplier_eval_criterion_sequence"),
        CheckConstraint("weight >= 0", name="ck_supplier_eval_criterion_weight"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(String(36), ForeignKey("procurement_supplier_evaluation_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    criterion_key = Column(String(64), nullable=False)
    sequence_no = Column(Integer, nullable=False)
    label = Column(String(255), nullable=False)
    guidance = Column(Text, nullable=True)
    response_type = Column(String(32), nullable=False, default="STRUCTURED")
    weight = Column(Numeric(8, 3), nullable=False, default=1)
    mandatory = Column(Boolean, nullable=False, default=True)
    evidence_required = Column(Boolean, nullable=False, default=False)
    failure_is_blocking = Column(Boolean, nullable=False, default=False)
    scoring_rule = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class SupplierEvaluation(Base):
    __tablename__ = "procurement_supplier_evaluations"
    __table_args__ = (
        Index("ix_supplier_evaluations_supplier_status", "supplier_id", "status"),
        Index("ix_supplier_evaluations_amo_valid", "amo_id", "valid_until"),
        CheckConstraint("version >= 1", name="ck_supplier_evaluation_version"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_supplier_evaluation_score"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','APPROVED','CONDITIONALLY_APPROVED','REJECTED','RETURNED','SUPERSEDED')",
            name="ck_supplier_evaluation_status",
        ),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("procurement_suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(String(36), ForeignKey("procurement_supplier_evaluation_templates.id", ondelete="RESTRICT"), nullable=False, index=True)
    template_revision_no = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="DRAFT", index=True)
    version = Column(Integer, nullable=False, default=1)
    intended_scope = Column(JSON, nullable=False)
    policy_snapshot = Column(JSON, nullable=False)
    score = Column(Numeric(5, 2), nullable=True)
    outcome = Column(String(32), nullable=True)
    valid_until = Column(Date, nullable=True, index=True)
    qms_finding_id = Column(String(36), nullable=True, index=True)
    qms_car_id = Column(String(36), nullable=True, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_comment = Column(Text, nullable=True)
    supersedes_evaluation_id = Column(String(36), ForeignKey("procurement_supplier_evaluations.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class SupplierEvaluationResponse(Base):
    __tablename__ = "procurement_supplier_evaluation_responses"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "criterion_id", name="uq_supplier_evaluation_response"),
        Index("ix_supplier_eval_response_evaluation", "evaluation_id"),
        CheckConstraint("score_percent IS NULL OR (score_percent >= 0 AND score_percent <= 100)", name="ck_supplier_eval_response_score"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    evaluation_id = Column(String(36), ForeignKey("procurement_supplier_evaluations.id", ondelete="CASCADE"), nullable=False, index=True)
    criterion_id = Column(String(36), ForeignKey("procurement_supplier_evaluation_criteria.id", ondelete="RESTRICT"), nullable=False, index=True)
    answer = Column(JSON, nullable=False)
    score_percent = Column(Numeric(5, 2), nullable=True)
    evidence_references = Column(JSON, nullable=False, default=list)
    comment = Column(Text, nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class SupplierGovernanceDecision(Base):
    """Append-only attributable supplier evaluation/approval decision record."""

    __tablename__ = "procurement_supplier_governance_decisions"
    __table_args__ = (
        Index("ix_supplier_governance_decision_supplier", "supplier_id", "created_at"),
        Index("ix_supplier_governance_decision_evaluation", "evaluation_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("procurement_suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    evaluation_id = Column(String(36), ForeignKey("procurement_supplier_evaluations.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    rationale = Column(Text, nullable=False)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=True)
    evidence_snapshot = Column(JSON, nullable=False, default=dict)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class SupplierReevaluationAction(Base):
    __tablename__ = "procurement_supplier_reevaluation_actions"
    __table_args__ = (
        UniqueConstraint("amo_id", "supplier_id", "trigger_key", name="uq_supplier_reevaluation_trigger"),
        Index("ix_supplier_reevaluation_amo_status", "amo_id", "status", "due_on"),
        CheckConstraint("status IN ('OPEN','ACKNOWLEDGED','CLOSED')", name="ck_supplier_reevaluation_status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("procurement_suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_key = Column(String(255), nullable=False)
    trigger_type = Column(String(64), nullable=False, index=True)
    trigger_snapshot = Column(JSON, nullable=False)
    source_reference = Column(String(255), nullable=True)
    status = Column(String(16), nullable=False, default="OPEN", index=True)
    due_on = Column(Date, nullable=True, index=True)
    assigned_to_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closure_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
