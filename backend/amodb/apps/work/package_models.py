from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

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
from sqlalchemy.orm import relationship

from ...database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkPackageStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    READY = "READY"
    RELEASED = "RELEASED"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class WorkPackage(Base):
    __tablename__ = "work_packages"
    __table_args__ = (
        UniqueConstraint("amo_id", "package_ref", name="uq_work_packages_amo_ref"),
        Index("ix_work_packages_amo_status", "amo_id", "status"),
        Index("ix_work_packages_amo_aircraft", "amo_id", "aircraft_serial_number"),
        CheckConstraint(
            "planned_start IS NULL OR planned_end IS NULL OR planned_end >= planned_start",
            name="ck_work_packages_date_order",
        ),
        CheckConstraint("source_horizon_days >= 1", name="ck_work_packages_horizon_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    package_ref = Column(String(64), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    check_type = Column(String(32), nullable=True)
    status = Column(String(24), nullable=False, default=WorkPackageStatus.DRAFT.value, index=True)
    due_date = Column(Date, nullable=True)
    planned_start = Column(DateTime(timezone=True), nullable=True)
    planned_end = Column(DateTime(timezone=True), nullable=True)
    source_horizon_days = Column(Integer, nullable=False, default=90)
    baseline_generated_at = Column(DateTime(timezone=True), nullable=True)
    readiness_status = Column(String(24), nullable=False, default="NOT_CHECKED")
    readiness_json = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    order_links = relationship(
        "WorkPackageOrder",
        back_populates="work_package",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class WorkPackageOrder(Base):
    __tablename__ = "work_package_orders"
    __table_args__ = (
        UniqueConstraint("work_package_id", "work_order_id", name="uq_work_package_order"),
        Index("ix_work_package_orders_package", "work_package_id", "sequence_no"),
        Index("ix_work_package_orders_order", "work_order_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    work_package_id = Column(
        Integer,
        ForeignKey("work_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_order_id = Column(
        Integer,
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_no = Column(Integer, nullable=False, default=1)
    source_type = Column(String(32), nullable=False, default="MANUAL")
    source_ref = Column(String(128), nullable=True)
    added_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    added_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    work_package = relationship("WorkPackage", back_populates="order_links", lazy="joined")
    work_order = relationship("WorkOrder", lazy="joined")
