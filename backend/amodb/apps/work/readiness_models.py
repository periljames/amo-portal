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
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlanningForecastScenario(Base):
    __tablename__ = "planning_forecast_scenarios"
    __table_args__ = (
        UniqueConstraint("amo_id", "name", name="uq_forecast_scenario_amo_name"),
        Index("ix_forecast_scenarios_amo_status", "amo_id", "status"),
        CheckConstraint("horizon_days >= 1", name="ck_forecast_scenario_horizon"),
        CheckConstraint("default_daily_hours >= 0", name="ck_forecast_scenario_daily_hours"),
        CheckConstraint("default_daily_cycles >= 0", name="ck_forecast_scenario_daily_cycles"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    start_date = Column(Date, nullable=False)
    horizon_days = Column(Integer, nullable=False, default=180)
    default_daily_hours = Column(Numeric(10, 2), nullable=False, default=5)
    default_daily_cycles = Column(Numeric(10, 2), nullable=False, default=3)
    aircraft_assumptions_json = Column(JSON, nullable=False, default=dict)
    summary_json = Column(JSON, nullable=False, default=dict)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    items = relationship(
        "PlanningForecastScenarioItem",
        back_populates="scenario",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class PlanningForecastScenarioItem(Base):
    __tablename__ = "planning_forecast_scenario_items"
    __table_args__ = (
        UniqueConstraint("scenario_id", "aircraft_program_item_id", name="uq_forecast_scenario_item"),
        Index("ix_forecast_items_scenario_due", "scenario_id", "projected_due_date"),
        Index("ix_forecast_items_aircraft", "amo_id", "aircraft_serial_number"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    scenario_id = Column(String(36), ForeignKey("planning_forecast_scenarios.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(String(50), ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False, index=True)
    registration = Column(String(20), nullable=False)
    program_item_id = Column(Integer, ForeignKey("amp_program_items.id", ondelete="CASCADE"), nullable=False)
    aircraft_program_item_id = Column(Integer, ForeignKey("amp_aircraft_program_items.id", ondelete="CASCADE"), nullable=False)
    task_code = Column(String(64), nullable=True)
    task_title = Column(String(255), nullable=False)
    status = Column(String(24), nullable=False, index=True)
    projected_due_date = Column(Date, nullable=True, index=True)
    projected_trigger = Column(String(16), nullable=True)
    projected_days = Column(Numeric(12, 2), nullable=True)
    remaining_hours = Column(Numeric(14, 2), nullable=True)
    remaining_cycles = Column(Numeric(14, 2), nullable=True)
    remaining_days = Column(Numeric(14, 2), nullable=True)
    daily_hours = Column(Numeric(10, 2), nullable=False)
    daily_cycles = Column(Numeric(10, 2), nullable=False)
    source_snapshot_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    scenario = relationship("PlanningForecastScenario", back_populates="items", lazy="joined")


class WorkPackageReadinessRequirement(Base):
    __tablename__ = "work_package_readiness_requirements"
    __table_args__ = (
        Index("ix_package_requirements_package_status", "work_package_id", "status"),
        Index("ix_package_requirements_amo_category", "amo_id", "category"),
        CheckConstraint("quantity_required >= 0", name="ck_package_requirement_quantity_required"),
        CheckConstraint("quantity_confirmed >= 0", name="ck_package_requirement_quantity_confirmed"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    work_package_id = Column(Integer, ForeignKey("work_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(24), nullable=False, index=True)
    reference = Column(String(128), nullable=True)
    description = Column(String(255), nullable=False)
    quantity_required = Column(Numeric(12, 2), nullable=False, default=1)
    quantity_confirmed = Column(Numeric(12, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="REQUIRED", index=True)
    required_by = Column(DateTime(timezone=True), nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    evidence_json = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WorkPackageReadinessAssessment(Base):
    __tablename__ = "work_package_readiness_assessments"
    __table_args__ = (
        UniqueConstraint("work_package_id", "version", name="uq_package_assessment_version"),
        Index("ix_package_assessments_package", "work_package_id", "version"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    work_package_id = Column(Integer, ForeignKey("work_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)
    blockers_json = Column(JSON, nullable=False, default=list)
    warnings_json = Column(JSON, nullable=False, default=list)
    metrics_json = Column(JSON, nullable=False, default=dict)
    assessed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assessed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WorkPackageFreeze(Base):
    __tablename__ = "work_package_freezes"
    __table_args__ = (
        UniqueConstraint("work_package_id", "version", name="uq_package_freeze_version"),
        Index("ix_package_freezes_package_status", "work_package_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    work_package_id = Column(Integer, ForeignKey("work_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    manifest_hash = Column(String(64), nullable=False)
    manifest_json = Column(JSON, nullable=False, default=dict)
    reason = Column(Text, nullable=False)
    frozen_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    frozen_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
