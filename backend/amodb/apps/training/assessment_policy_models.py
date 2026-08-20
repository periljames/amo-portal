from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrainingAssessmentAttemptPolicy(Base):
    """Explicit approved tenant policy for one canonical assessment-template revision.

    A policy row must be ACTIVE before a learner can start an attempt. Nullable
    time limit means the tenant explicitly chose no countdown; absence of the row
    never means a portal default.
    """

    __tablename__ = "training_assessment_attempt_policies"
    __table_args__ = (
        UniqueConstraint("amo_id", "template_id", name="uq_training_assessment_attempt_policy_template"),
        Index("ix_training_assessment_attempt_policy_amo", "amo_id", "template_id"),
        Index("ix_training_assessment_attempt_policy_status", "amo_id", "status"),
        CheckConstraint("attempt_limit > 0 AND attempt_limit <= 20", name="ck_training_assessment_policy_attempt_limit"),
        CheckConstraint("time_limit_minutes IS NULL OR (time_limit_minutes > 0 AND time_limit_minutes <= 1440)", name="ck_training_assessment_policy_time_limit"),
        CheckConstraint("cooldown_hours >= 0 AND cooldown_hours <= 720", name="ck_training_assessment_policy_cooldown"),
        CheckConstraint("question_count IS NULL OR (question_count > 0 AND question_count <= 500)", name="ck_training_assessment_policy_question_count"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(String(36), ForeignKey("training_assessment_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="DRAFT", index=True)
    attempt_limit = Column(Integer, nullable=False)
    time_limit_minutes = Column(Integer, nullable=True)
    cooldown_hours = Column(Integer, nullable=False)
    randomize_questions = Column(Boolean, nullable=False)
    question_count = Column(Integer, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


__all__ = ["TrainingAssessmentAttemptPolicy"]
