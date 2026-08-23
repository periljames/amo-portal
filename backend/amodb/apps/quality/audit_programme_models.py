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
    Uuid,
)
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QualityAuditProgramme(Base):
    """Versioned annual/periodic audit programme owned by Quality.

    Every programme uses one continuous hybrid assurance model: compliance is
    the permanent baseline while risk and performance intelligence can increase
    surveillance priority or recommend additional coverage. The programme owns
    governed coverage and target windows; the Planner owns exact delivery.

    Approved revisions are not edited in place. Amendments create a new DRAFT
    revision linked through ``supersedes_programme_id`` while immutable events
    retain the human-attributed decision history.
    """

    __tablename__ = "quality_audit_programmes"
    __table_args__ = (
        UniqueConstraint("amo_id", "programme_ref", name="uq_quality_audit_programme_ref"),
        UniqueConstraint("amo_id", "programme_series", "revision_no", name="uq_quality_audit_programme_revision"),
        CheckConstraint(
            "status IN ('DRAFT','UNDER_REVIEW','APPROVED','ACTIVE','SUPERSEDED','CLOSED')",
            name="ck_quality_audit_programme_status",
        ),
        CheckConstraint("programme_year >= 2000 AND programme_year <= 2200", name="ck_quality_audit_programme_year"),
        CheckConstraint("revision_no >= 1", name="ck_quality_audit_programme_revision"),
        CheckConstraint("period_end >= period_start", name="ck_quality_audit_programme_period"),
        Index("ix_quality_audit_programmes_year", "amo_id", "programme_year", "status"),
        Index("ix_quality_audit_programmes_owner", "amo_id", "owner_user_id", "status"),
        Index("ix_quality_audit_programmes_series", "amo_id", "programme_series", "revision_no"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    programme_ref = Column(String(72), nullable=False)
    programme_series = Column(String(64), nullable=False)
    programme_year = Column(Integer, nullable=False)
    revision_no = Column(Integer, nullable=False, default=1, server_default="1")
    title = Column(String(255), nullable=False)
    continuous_monitoring_enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    optimizer_version = Column(String(64), nullable=False, default="HYBRID_ASSURANCE_V1", server_default="HYBRID_ASSURANCE_V1")
    objectives = Column(JSON, nullable=False, default=list)
    regulatory_basis = Column(JSON, nullable=False, default=list)
    status = Column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    supersedes_programme_id = Column(String(36), ForeignKey("quality_audit_programmes.id", ondelete="SET NULL"), nullable=True)

    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    items = relationship(
        "QualityAuditProgrammeItem",
        back_populates="programme",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="QualityAuditProgrammeItem.target_start, QualityAuditProgrammeItem.title",
    )
    events = relationship(
        "QualityAuditProgrammeEvent",
        back_populates="programme",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="QualityAuditProgrammeEvent.created_at",
    )


class QualityAuditUniverseItem(Base):
    """Governed catalogue entry pointing to the authoritative auditable entity."""

    __tablename__ = "quality_audit_universe_items"
    __table_args__ = (
        UniqueConstraint(
            "amo_id", "source_owner_module", "source_type", "source_id",
            name="uq_quality_audit_universe_source",
        ),
        CheckConstraint(
            "entity_type IN ('DEPARTMENT','FACILITY','STATION','SUPPLIER','CONTRACTOR','PROCESS',"
            "'CAPABILITY','APPROVAL_RATING','AIRCRAFT_TYPE','PERSONNEL_GROUP','OTHER')",
            name="ck_quality_audit_universe_entity_type",
        ),
        CheckConstraint("risk_classification IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_audit_universe_risk"),
        CheckConstraint("regulatory_criticality IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_audit_universe_regulatory"),
        CheckConstraint("surveillance_interval_days IS NULL OR surveillance_interval_days > 0", name="ck_quality_audit_universe_interval"),
        Index("ix_quality_audit_universe_type", "amo_id", "entity_type", "active"),
        Index("ix_quality_audit_universe_risk", "amo_id", "risk_classification", "regulatory_criticality"),
        Index("ix_quality_audit_universe_source", "amo_id", "source_owner_module", "source_type", "source_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(32), nullable=False)
    display_label = Column(String(255), nullable=False)
    source_owner_module = Column(String(80), nullable=False)
    source_type = Column(String(64), nullable=False)
    source_id = Column(String(160), nullable=False)
    source_route = Column(String(500), nullable=True)
    risk_classification = Column(String(16), nullable=False, default="MEDIUM", server_default="MEDIUM")
    regulatory_criticality = Column(String(16), nullable=False, default="MEDIUM", server_default="MEDIUM")
    surveillance_interval_days = Column(Integer, nullable=True)
    mandatory_surveillance = Column(Boolean, nullable=False, default=False, server_default="false")
    active = Column(Boolean, nullable=False, default=True, server_default="true")
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    programme_items = relationship("QualityAuditProgrammeItem", back_populates="universe_item", lazy="selectin")


class QualityAuditProgrammeItem(Base):
    """One governed surveillance requirement inside a programme revision.

    ``schedule_id`` is assigned only when the authoritative Quality planner
    creates the schedule. A unique schedule link prevents one schedule from
    silently satisfying multiple governed programme requirements.
    """

    __tablename__ = "quality_audit_programme_items"
    __table_args__ = (
        UniqueConstraint("schedule_id", name="uq_quality_audit_programme_item_schedule"),
        CheckConstraint(
            "audit_type IN ('INTERNAL','DEPARTMENTAL','TECHNICAL','WORK_PACK','SUPPLIER','CONTRACTED_FUNCTION',"
            "'FACILITY','PERSONNEL','PRODUCT','PROCESS','REGULATORY','SPECIAL','REACTIVE','FOLLOW_UP')",
            name="ck_quality_audit_programme_item_type",
        ),
        CheckConstraint(
            "state IN ('PLANNED','SCHEDULED','COMPLETED','DEFERRED','CANCELLED','FOLLOW_UP_REQUIRED')",
            name="ck_quality_audit_programme_item_state",
        ),
        CheckConstraint(
            "recurrence IN ('ONE_TIME','MONTHLY','QUARTERLY','SEMI_ANNUAL','ANNUAL','CUSTOM','RISK_TRIGGERED')",
            name="ck_quality_audit_programme_item_recurrence",
        ),
        CheckConstraint("target_end IS NULL OR target_start IS NULL OR target_end >= target_start", name="ck_quality_audit_programme_item_dates"),
        Index("ix_quality_audit_programme_items_period", "amo_id", "programme_id", "target_start", "state"),
        Index("ix_quality_audit_programme_items_universe", "amo_id", "universe_item_id", "state"),
        Index("ix_quality_audit_programme_items_type", "amo_id", "audit_type", "state"),
        Index("ix_quality_audit_programme_items_schedule", "amo_id", "schedule_id", "state"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    programme_id = Column(String(36), ForeignKey("quality_audit_programmes.id", ondelete="CASCADE"), nullable=False)
    universe_item_id = Column(String(36), ForeignKey("quality_audit_universe_items.id", ondelete="RESTRICT"), nullable=False)
    schedule_id = Column(Uuid(as_uuid=True), ForeignKey("qms_audit_schedules.id", ondelete="SET NULL"), nullable=True)
    audit_type = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    purpose = Column(Text, nullable=True)
    scope = Column(Text, nullable=False)
    criteria = Column(JSON, nullable=False, default=list)
    mandatory_surveillance = Column(Boolean, nullable=False, default=False, server_default="false")
    recurrence = Column(String(20), nullable=False, default="ONE_TIME", server_default="ONE_TIME")
    custom_interval_days = Column(Integer, nullable=True)
    target_start = Column(Date, nullable=True)
    target_end = Column(Date, nullable=True)
    state = Column(String(24), nullable=False, default="PLANNED", server_default="PLANNED")
    prioritization_basis = Column(JSON, nullable=False, default=list)
    deferral_reason = Column(Text, nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    scheduled_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    programme = relationship("QualityAuditProgramme", back_populates="items", lazy="joined")
    universe_item = relationship("QualityAuditUniverseItem", back_populates="programme_items", lazy="joined")


class QualityAuditProgrammeEvent(Base):
    """Immutable attributable programme lifecycle/amendment event."""

    __tablename__ = "quality_audit_programme_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('CREATED','UPDATED','SUBMITTED_FOR_REVIEW','RETURNED_TO_DRAFT','APPROVED','ACTIVATED',"
            "'AMENDMENT_CREATED','SUPERSEDED','CLOSED','ITEM_ADDED','ITEM_UPDATED','ITEM_SCHEDULED')",
            name="ck_quality_audit_programme_event_type",
        ),
        Index("ix_quality_audit_programme_events", "amo_id", "programme_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    programme_id = Column(String(36), ForeignKey("quality_audit_programmes.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(32), nullable=False)
    reason = Column(Text, nullable=False)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    programme = relationship("QualityAuditProgramme", back_populates="events", lazy="joined")
