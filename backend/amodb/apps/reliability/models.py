# backend/amodb/apps/reliability/models.py

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ...database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReliabilityProgramTemplate(Base):
    """
    Default programme templates seeded when the Reliability module is enabled.

    Kept simple on purpose – operators can clone and tailor these for their
    aircraft / AMP context. Tied to an AMO for multi-tenant isolation.
    """

    __tablename__ = "reliability_program_templates"

    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_reliability_template_amo_code"),
        Index("ix_reliability_template_amo_default", "amo_id", "is_default"),
    )

    id = Column(Integer, primary_key=True, index=True)

    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)

    code = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    focus_areas = Column(Text, nullable=True)

    is_default = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<ReliabilityProgramTemplate id={self.id} code={self.code} default={self.is_default}>"


class ReliabilityDefectTrend(Base):
    """
    Snapshot of defect trend metrics for a date window and (optionally) an aircraft.

    - defects_count       : total defect task-cards raised in the window.
    - repeat_defects      : defects tied to the same AMP item repeating in the window.
    - finding_events      : QMS findings logged in the window (trend correlation).
    - utilisation_hours   : total flight hours in the window (from fleet utilisation).
    - defect_rate_per_100_fh : normalised defect rate per 100FH.
    """

    __tablename__ = "reliability_defect_trends"

    __table_args__ = (
        Index("ix_reliability_trends_amo_aircraft", "amo_id", "aircraft_serial_number"),
        Index("ix_reliability_trends_window", "window_start", "window_end"),
        CheckConstraint("defects_count >= 0", name="ck_reliability_trend_defects_nonneg"),
        CheckConstraint("repeat_defects >= 0", name="ck_reliability_trend_repeat_nonneg"),
        CheckConstraint("finding_events >= 0", name="ck_reliability_trend_findings_nonneg"),
        CheckConstraint("utilisation_hours >= 0", name="ck_reliability_trend_hours_nonneg"),
        CheckConstraint("utilisation_cycles >= 0", name="ck_reliability_trend_cycles_nonneg"),
    )

    id = Column(Integer, primary_key=True, index=True)

    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ata_chapter = Column(String(20), nullable=True, index=True)

    window_start = Column(Date, nullable=False, index=True)
    window_end = Column(Date, nullable=False, index=True)

    defects_count = Column(Integer, nullable=False, default=0)
    repeat_defects = Column(Integer, nullable=False, default=0)
    finding_events = Column(Integer, nullable=False, default=0)

    utilisation_hours = Column(Float, nullable=False, default=0.0)
    utilisation_cycles = Column(Float, nullable=False, default=0.0)
    defect_rate_per_100_fh = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    recommendations = relationship(
        "ReliabilityRecommendation",
        back_populates="trend",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"<ReliabilityDefectTrend id={self.id} aircraft={self.aircraft_serial_number} "
            f"window={self.window_start}:{self.window_end} rate={self.defect_rate_per_100_fh}>"
        )


class ReliabilityRecurringFinding(Base):
    """
    Tracks recurring findings tied to AMP items or ATA chapters.

    Allows linking to non-routine task-cards (DEFECT category) and QMS audit
    findings for deeper corrective-action follow up.
    """

    __tablename__ = "reliability_recurring_findings"

    __table_args__ = (
        UniqueConstraint(
            "amo_id",
            "aircraft_serial_number",
            "program_item_id",
            "ata_chapter",
            name="uq_reliability_recurring_unique_key",
        ),
        Index("ix_reliability_recurring_amo_aircraft", "amo_id", "aircraft_serial_number"),
        Index("ix_reliability_recurring_program_item", "program_item_id"),
        CheckConstraint("occurrence_count >= 1", name="ck_reliability_recurring_count_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)

    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ata_chapter = Column(String(20), nullable=True, index=True)
    program_item_id = Column(Integer, ForeignKey("amp_program_items.id", ondelete="SET NULL"), nullable=True, index=True)
    task_card_id = Column(Integer, ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True, index=True)
    quality_finding_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audit_findings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    occurrence_count = Column(Integer, nullable=False, default=1)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    recommendation = Column(Text, nullable=True)

    recommendation_links = relationship(
        "ReliabilityRecommendation",
        back_populates="recurring_finding",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"<ReliabilityRecurringFinding id={self.id} aircraft={self.aircraft_serial_number} "
            f"program_item={self.program_item_id} count={self.occurrence_count}>"
        )


class RecommendationPriorityEnum(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RecommendationStatusEnum(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class ReliabilityRecommendation(Base):
    """
    Reliability recommendations derived from trend analysis or recurring findings.
    """

    __tablename__ = "reliability_recommendations"

    __table_args__ = (
        Index("ix_reliability_recommendations_amo_status", "amo_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)

    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)

    priority = Column(
        SAEnum(RecommendationPriorityEnum, name="reliability_rec_priority_enum", native_enum=False),
        nullable=False,
        default=RecommendationPriorityEnum.MEDIUM,
        index=True,
    )
    status = Column(
        SAEnum(RecommendationStatusEnum, name="reliability_rec_status_enum", native_enum=False),
        nullable=False,
        default=RecommendationStatusEnum.OPEN,
        index=True,
    )

    trend_id = Column(
        Integer,
        ForeignKey("reliability_defect_trends.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recurring_finding_id = Column(
        Integer,
        ForeignKey("reliability_recurring_findings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    trend = relationship("ReliabilityDefectTrend", back_populates="recommendations", lazy="joined")
    recurring_finding = relationship(
        "ReliabilityRecurringFinding",
        back_populates="recommendation_links",
        lazy="joined",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<ReliabilityRecommendation id={self.id} title={self.title!r} priority={self.priority}>"
