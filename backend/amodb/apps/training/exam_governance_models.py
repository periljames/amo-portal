"""Examination quality extensions for the governed Training OS.

Kept separate from the core governance models so the examination intelligence layer
can evolve without coupling learner delivery to analytics.  Approved questions are
never altered by analysis jobs; analysis produces review evidence only.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, text

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrainingExamForm(Base):
    __tablename__ = "training_exam_forms"
    __table_args__ = (
        UniqueConstraint("amo_id", "form_code", "revision_no", name="uq_training_exam_form_revision"),
        Index("ix_training_exam_form_status", "amo_id", "blueprint_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id = Column(String(36), ForeignKey("training_exam_blueprints.id", ondelete="CASCADE"), nullable=False, index=True)
    form_code = Column(String(64), nullable=False)
    revision_no = Column(Integer, nullable=False, default=1, server_default="1")
    question_revision_ids = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingExamItemAnalysis(Base):
    __tablename__ = "training_exam_item_analysis"
    __table_args__ = (
        UniqueConstraint("amo_id", "question_revision_id", "analysis_window", name="uq_training_exam_item_analysis_window"),
        Index("ix_training_exam_item_analysis_queue", "amo_id", "review_status", "computed_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    question_revision_id = Column(String(36), ForeignKey("training_question_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_window = Column(String(64), nullable=False)
    sample_size = Column(Integer, nullable=False, default=0, server_default="0")
    response_distribution = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    percent_correct = Column(Numeric(8, 4), nullable=True)
    difficulty_index = Column(Numeric(8, 4), nullable=True)
    discrimination_index = Column(Numeric(8, 4), nullable=True)
    distractor_performance = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    abnormal_patterns = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    complaint_count = Column(Integer, nullable=False, default=0, server_default="0")
    source_superseded = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    review_status = Column(String(24), nullable=False, default="CLEAR", server_default="CLEAR")
    review_reasons = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    computed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)


class TrainingExamModeration(Base):
    __tablename__ = "training_exam_moderations"
    __table_args__ = (Index("ix_training_exam_moderation_queue", "amo_id", "status", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    question_revision_id = Column(String(36), ForeignKey("training_question_revisions.id", ondelete="SET NULL"), nullable=True, index=True)
    generation_id = Column(String(36), ForeignKey("training_exam_generations.id", ondelete="SET NULL"), nullable=True, index=True)
    reason = Column(Text, nullable=False)
    evidence_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    recommendation = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="OPEN", server_default="OPEN")
    opened_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision = Column(String(32), nullable=True)
    decision_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    decided_at = Column(DateTime(timezone=True), nullable=True)


class TrainingExamAppeal(Base):
    __tablename__ = "training_exam_appeals"
    __table_args__ = (
        UniqueConstraint("amo_id", "attempt_id", "appellant_user_id", name="uq_training_exam_appeal_attempt_user"),
        Index("ix_training_exam_appeal_queue", "amo_id", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_id = Column(String(36), ForeignKey("training_exam_attempts_governed.id", ondelete="CASCADE"), nullable=False, index=True)
    appellant_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    grounds = Column(Text, nullable=False)
    evidence_json = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    status = Column(String(24), nullable=False, default="SUBMITTED", server_default="SUBMITTED")
    reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision = Column(String(24), nullable=True)
    decision_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    decided_at = Column(DateTime(timezone=True), nullable=True)
