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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from ...database import Base
from ..accounts.models import AccountRole


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


class ReliabilityEventTypeEnum(str, Enum):
    DEFECT = "DEFECT"
    REMOVAL = "REMOVAL"
    INSTALLATION = "INSTALLATION"
    OCTM = "OCTM"
    ECTM = "ECTM"
    FRACAS = "FRACAS"
    OTHER = "OTHER"


class ReliabilitySeverityEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReliabilityAlertStatusEnum(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CLOSED = "CLOSED"


class KPIBaseScopeEnum(str, Enum):
    FLEET = "FLEET"
    AIRCRAFT = "AIRCRAFT"
    ENGINE = "ENGINE"
    COMPONENT = "COMPONENT"
    ATA = "ATA"


class FRACASStatusEnum(str, Enum):
    OPEN = "OPEN"
    IN_ANALYSIS = "IN_ANALYSIS"
    ACTIONS = "ACTIONS"
    MONITORING = "MONITORING"
    CLOSED = "CLOSED"


class FRACASActionTypeEnum(str, Enum):
    CORRECTIVE = "CORRECTIVE"
    PREVENTIVE = "PREVENTIVE"


class FRACASActionStatusEnum(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    VERIFIED = "VERIFIED"
    CANCELLED = "CANCELLED"


class PartMovementTypeEnum(str, Enum):
    INSTALL = "INSTALL"
    REMOVE = "REMOVE"
    SWAP = "SWAP"
    INSPECT = "INSPECT"


class AlertComparatorEnum(str, Enum):
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"


class ControlChartMethodEnum(str, Enum):
    EWMA = "EWMA"
    CUSUM = "CUSUM"
    SLOPE = "SLOPE"


class EngineTrendStatusEnum(str, Enum):
    NORMAL = "Trend Normal"
    SHIFT = "Trend Shift"


class ReliabilityEvent(Base):
    """
    Canonical reliability event log with references to source objects.
    """

    __tablename__ = "reliability_events"

    __table_args__ = (
        Index("ix_reliability_events_amo_type", "amo_id", "event_type"),
        Index("ix_reliability_events_aircraft_date", "aircraft_serial_number", "occurred_at"),
    )

    id = Column(Integer, primary_key=True, index=True)

    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    engine_position = Column(String(32), nullable=True, index=True)
    component_id = Column(
        Integer,
        ForeignKey("aircraft_components.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    work_order_id = Column(
        Integer,
        ForeignKey("work_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_card_id = Column(
        Integer,
        ForeignKey("task_cards.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    event_type = Column(
        SAEnum(ReliabilityEventTypeEnum, name="reliability_event_type_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    severity = Column(
        SAEnum(ReliabilitySeverityEnum, name="reliability_event_severity_enum", native_enum=False),
        nullable=True,
        index=True,
    )
    ata_chapter = Column(String(20), nullable=True, index=True)
    reference_code = Column(String(64), nullable=True, index=True)
    source_system = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)


class ReliabilityKPI(Base):
    """
    Materialized KPI snapshots with traceability to underlying data windows.
    """

    __tablename__ = "reliability_kpis"

    __table_args__ = (
        Index("ix_reliability_kpis_scope_window", "amo_id", "kpi_code", "window_start", "window_end"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)

    kpi_code = Column(String(64), nullable=False, index=True)
    scope_type = Column(
        SAEnum(KPIBaseScopeEnum, name="reliability_kpi_scope_enum", native_enum=False),
        nullable=False,
        default=KPIBaseScopeEnum.FLEET,
        index=True,
    )

    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    engine_position = Column(String(32), nullable=True, index=True)
    component_id = Column(Integer, ForeignKey("aircraft_components.id", ondelete="SET NULL"), nullable=True, index=True)
    ata_chapter = Column(String(20), nullable=True, index=True)

    window_start = Column(Date, nullable=False, index=True)
    window_end = Column(Date, nullable=False, index=True)

    value = Column(Float, nullable=False)
    numerator = Column(Float, nullable=True)
    denominator = Column(Float, nullable=True)
    unit = Column(String(32), nullable=True)
    calculation_version = Column(String(32), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ReliabilityAlert(Base):
    """
    Alert emitted from KPI thresholds or control chart rules.
    """

    __tablename__ = "reliability_alerts"

    __table_args__ = (
        Index("ix_reliability_alerts_status", "amo_id", "status"),
        Index("ix_reliability_alerts_triggered", "triggered_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)

    kpi_id = Column(Integer, ForeignKey("reliability_kpis.id", ondelete="SET NULL"), nullable=True, index=True)
    threshold_set_id = Column(
        Integer,
        ForeignKey("reliability_threshold_sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    alert_code = Column(String(64), nullable=False, index=True)
    status = Column(
        SAEnum(ReliabilityAlertStatusEnum, name="reliability_alert_status_enum", native_enum=False),
        nullable=False,
        default=ReliabilityAlertStatusEnum.OPEN,
        index=True,
    )
    severity = Column(
        SAEnum(ReliabilitySeverityEnum, name="reliability_alert_severity_enum", native_enum=False),
        nullable=False,
        default=ReliabilitySeverityEnum.MEDIUM,
        index=True,
    )

    message = Column(Text, nullable=True)
    triggered_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    resolved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    acknowledged_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)


class ReliabilityNotification(Base):
    """
    In-app notification for reliability alerts, scoped to an AMO.
    """

    __tablename__ = "reliability_notifications"

    __table_args__ = (
        UniqueConstraint("amo_id", "user_id", "dedupe_key", name="uq_reliability_notifications_dedupe"),
        Index("ix_reliability_notifications_amo_user", "amo_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    alert_id = Column(Integer, ForeignKey("reliability_alerts.id", ondelete="CASCADE"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    severity = Column(
        SAEnum(ReliabilitySeverityEnum, name="reliability_notification_severity_enum", native_enum=False),
        nullable=False,
        default=ReliabilitySeverityEnum.MEDIUM,
        index=True,
    )
    dedupe_key = Column(String(128), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)


class ReliabilityNotificationRule(Base):
    """
    Routing rule to map alerts to users/departments for an AMO.
    """

    __tablename__ = "reliability_notification_rules"

    __table_args__ = (
        Index("ix_reliability_notification_rules_amo", "amo_id", "severity"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    role = Column(
        SAEnum(AccountRole, name="reliability_notification_role_enum", native_enum=False),
        nullable=True,
        index=True,
    )
    severity = Column(
        SAEnum(ReliabilitySeverityEnum, name="reliability_notification_rule_severity_enum", native_enum=False),
        nullable=False,
        default=ReliabilitySeverityEnum.MEDIUM,
    )
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)


class FRACASCase(Base):
    """
    FRACAS case tracking lifecycle.
    """

    __tablename__ = "fracas_cases"

    __table_args__ = (
        Index("ix_fracas_cases_amo_status", "amo_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(
        SAEnum(FRACASStatusEnum, name="fracas_status_enum", native_enum=False),
        nullable=False,
        default=FRACASStatusEnum.OPEN,
        index=True,
    )
    severity = Column(
        SAEnum(ReliabilitySeverityEnum, name="fracas_severity_enum", native_enum=False),
        nullable=True,
        index=True,
    )
    classification = Column(String(64), nullable=True, index=True)

    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    engine_position = Column(String(32), nullable=True, index=True)
    component_id = Column(Integer, ForeignKey("aircraft_components.id", ondelete="SET NULL"), nullable=True, index=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    task_card_id = Column(Integer, ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True, index=True)
    reliability_event_id = Column(
        Integer,
        ForeignKey("reliability_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    opened_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    root_cause = Column(Text, nullable=True)
    corrective_action_summary = Column(Text, nullable=True)
    verification_notes = Column(Text, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    actions = relationship("FRACASAction", back_populates="case", lazy="selectin")


class FRACASAction(Base):
    """
    Action items tied to a FRACAS case.
    """

    __tablename__ = "fracas_actions"

    __table_args__ = (
        Index("ix_fracas_actions_case_status", "fracas_case_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    fracas_case_id = Column(Integer, ForeignKey("fracas_cases.id", ondelete="CASCADE"), nullable=False, index=True)

    action_type = Column(
        SAEnum(FRACASActionTypeEnum, name="fracas_action_type_enum", native_enum=False),
        nullable=False,
        default=FRACASActionTypeEnum.CORRECTIVE,
        index=True,
    )
    status = Column(
        SAEnum(FRACASActionStatusEnum, name="fracas_action_status_enum", native_enum=False),
        nullable=False,
        default=FRACASActionStatusEnum.OPEN,
        index=True,
    )

    description = Column(Text, nullable=False)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    due_date = Column(Date, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    effectiveness_notes = Column(Text, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    case = relationship("FRACASCase", back_populates="actions", lazy="joined")


class EngineFlightSnapshot(Base):
    """
    Normalized per-flight per-engine snapshot (ECTM/EHM).
    """

    __tablename__ = "engine_flight_snapshots"

    __table_args__ = (
        UniqueConstraint(
            "aircraft_serial_number",
            "engine_position",
            "flight_date",
            "flight_leg",
            name="uq_engine_snapshot_flight",
        ),
        Index("ix_engine_snapshots_aircraft_date", "aircraft_serial_number", "flight_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    engine_position = Column(String(32), nullable=False, index=True)
    engine_serial_number = Column(String(64), nullable=True, index=True)

    flight_date = Column(Date, nullable=False, index=True)
    flight_leg = Column(String(32), nullable=True)
    flight_hours = Column(Float, nullable=True)
    cycles = Column(Float, nullable=True)

    phase = Column(String(32), nullable=True)
    power_reference_type = Column(String(32), nullable=True)
    power_reference_value = Column(Float, nullable=True)
    pressure_altitude_ft = Column(Float, nullable=True)
    oat_c = Column(Float, nullable=True)
    isa_dev_c = Column(Float, nullable=True)

    metrics = Column(JSONB, nullable=True)
    data_source = Column(String(64), nullable=True)
    source_record_id = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class EngineTrendStatus(Base):
    """
    Latest trend status rollup for CAMP-style fleet summaries.
    """

    __tablename__ = "engine_trend_statuses"

    __table_args__ = (
        UniqueConstraint(
            "amo_id",
            "aircraft_serial_number",
            "engine_position",
            "engine_serial_number",
            name="uq_engine_trend_status_engine",
        ),
        Index("ix_engine_trend_status_aircraft", "aircraft_serial_number"),
        Index("ix_engine_trend_status_engine", "engine_serial_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    engine_position = Column(String(32), nullable=False, index=True)
    engine_serial_number = Column(String(64), nullable=True, index=True)

    last_upload_date = Column(Date, nullable=True)
    last_trend_date = Column(Date, nullable=True)
    last_review_date = Column(Date, nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    previous_status = Column(
        SAEnum(EngineTrendStatusEnum, name="engine_trend_status_enum", native_enum=False),
        nullable=True,
    )
    current_status = Column(
        SAEnum(EngineTrendStatusEnum, name="engine_trend_status_enum", native_enum=False),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class OilUplift(Base):
    """
    Oil uplift/servicing record for OCTM.
    """

    __tablename__ = "oil_uplifts"

    __table_args__ = (
        Index("ix_oil_uplifts_aircraft_date", "aircraft_serial_number", "uplift_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    engine_position = Column(String(32), nullable=True, index=True)
    uplift_date = Column(Date, nullable=False, index=True)
    quantity_quarts = Column(Float, nullable=False)
    source = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class OilConsumptionRate(Base):
    """
    Derived oil consumption rate per engine and window.
    """

    __tablename__ = "oil_consumption_rates"

    __table_args__ = (
        Index("ix_oil_rates_aircraft_window", "aircraft_serial_number", "window_start", "window_end"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    engine_position = Column(String(32), nullable=True, index=True)
    window_start = Column(Date, nullable=False, index=True)
    window_end = Column(Date, nullable=False, index=True)
    oil_used_quarts = Column(Float, nullable=False)
    flight_hours = Column(Float, nullable=True)
    rate_qt_per_hour = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ComponentInstance(Base):
    """
    Master record for serialized components for reliability tracking.
    """

    __tablename__ = "component_instances"

    __table_args__ = (
        UniqueConstraint("amo_id", "part_number", "serial_number", name="uq_component_instance_amo_pn_sn"),
        Index("ix_component_instances_ata", "ata"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=True, index=True)
    part_number = Column(String(50), nullable=False, index=True)
    serial_number = Column(String(50), nullable=False, index=True)
    description = Column(String(255), nullable=True)
    component_class = Column(String(64), nullable=True, index=True)
    ata = Column(String(20), nullable=True, index=True)
    manufacturer_code = Column(String(32), nullable=True, index=True)
    operator_code = Column(String(32), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class PartMovementLedger(Base):
    """
    Movement events for components tied to work orders and aircraft.
    """

    __tablename__ = "part_movement_ledger"

    __table_args__ = (
        Index("ix_part_movement_aircraft_date", "aircraft_serial_number", "event_date"),
        Index("ix_part_movement_component", "component_id", "event_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    component_id = Column(Integer, ForeignKey("aircraft_components.id", ondelete="SET NULL"), nullable=True, index=True)
    component_instance_id = Column(
        Integer,
        ForeignKey("component_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    work_order_id = Column(Integer, ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    task_card_id = Column(Integer, ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True, index=True)

    event_type = Column(
        SAEnum(PartMovementTypeEnum, name="part_movement_type_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    event_date = Column(Date, nullable=False, index=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class RemovalEvent(Base):
    """
    Removal events with usage at removal for MTBUR/MTBF analytics.
    """

    __tablename__ = "removal_events"

    __table_args__ = (
        Index("ix_removal_events_component_date", "component_id", "removed_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    component_id = Column(Integer, ForeignKey("aircraft_components.id", ondelete="SET NULL"), nullable=True, index=True)
    component_instance_id = Column(
        Integer,
        ForeignKey("component_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    part_movement_id = Column(
        Integer,
        ForeignKey("part_movement_ledger.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    removal_reason = Column(String(128), nullable=True, index=True)
    hours_at_removal = Column(Float, nullable=True)
    cycles_at_removal = Column(Float, nullable=True)
    removed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class AircraftUtilizationDaily(Base):
    """
    Daily aircraft utilization denominators for reliability KPIs.
    """

    __tablename__ = "aircraft_utilization_daily"

    __table_args__ = (
        UniqueConstraint("aircraft_serial_number", "date", name="uq_aircraft_utilization_date"),
        Index("ix_aircraft_utilization_amo_date", "amo_id", "date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date = Column(Date, nullable=False, index=True)
    flight_hours = Column(Float, nullable=False, default=0.0)
    cycles = Column(Float, nullable=False, default=0.0)
    source = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class EngineUtilizationDaily(Base):
    """
    Daily engine utilization denominators for reliability KPIs.
    """

    __tablename__ = "engine_utilization_daily"

    __table_args__ = (
        UniqueConstraint(
            "aircraft_serial_number",
            "engine_position",
            "date",
            name="uq_engine_utilization_date",
        ),
        Index("ix_engine_utilization_amo_date", "amo_id", "date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    engine_position = Column(String(32), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    flight_hours = Column(Float, nullable=False, default=0.0)
    cycles = Column(Float, nullable=False, default=0.0)
    source = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ThresholdSet(Base):
    """
    Threshold configuration for KPI alerts.
    """

    __tablename__ = "reliability_threshold_sets"

    __table_args__ = (
        Index("ix_reliability_threshold_sets_scope", "amo_id", "scope_type", "scope_value"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(128), nullable=False)
    scope_type = Column(
        SAEnum(KPIBaseScopeEnum, name="reliability_threshold_scope_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    scope_value = Column(String(128), nullable=True, index=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class AlertRule(Base):
    """
    Rules that drive alert generation from KPI values.
    """

    __tablename__ = "reliability_alert_rules"

    __table_args__ = (
        Index("ix_reliability_alert_rules_threshold", "threshold_set_id", "kpi_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    threshold_set_id = Column(
        Integer,
        ForeignKey("reliability_threshold_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kpi_code = Column(String(64), nullable=False, index=True)
    comparator = Column(
        SAEnum(AlertComparatorEnum, name="reliability_alert_comparator_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    threshold_value = Column(Float, nullable=False)
    severity = Column(
        SAEnum(ReliabilitySeverityEnum, name="reliability_alert_rule_severity_enum", native_enum=False),
        nullable=False,
        default=ReliabilitySeverityEnum.MEDIUM,
        index=True,
    )
    enabled = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ControlChartConfig(Base):
    """
    Control chart configuration per KPI code.
    """

    __tablename__ = "reliability_control_chart_configs"

    __table_args__ = (
        Index("ix_reliability_control_chart_kpi", "amo_id", "kpi_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    kpi_code = Column(String(64), nullable=False, index=True)
    method = Column(
        SAEnum(ControlChartMethodEnum, name="reliability_control_chart_method_enum", native_enum=False),
        nullable=False,
    )
    parameters = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ReliabilityReportStatusEnum(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


class ReliabilityReport(Base):
    """
    Generated reliability report artifact.
    """

    __tablename__ = "reliability_reports"

    __table_args__ = (
        Index("ix_reliability_reports_amo_window", "amo_id", "window_start", "window_end"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    window_start = Column(Date, nullable=False, index=True)
    window_end = Column(Date, nullable=False, index=True)
    status = Column(
        SAEnum(ReliabilityReportStatusEnum, name="reliability_report_status_enum", native_enum=False),
        nullable=False,
        default=ReliabilityReportStatusEnum.PENDING,
        index=True,
    )
    file_ref = Column(String(512), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
