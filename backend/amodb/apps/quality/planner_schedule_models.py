from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from amodb.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


class QMSPlannerScheduleMetadata(Base):
    """Planner-only timing, attendance and lifecycle metadata.

    The linked audit schedule, audit, CAR/CAPA, training event or management
    review remains authoritative for its business lifecycle. This table adds the
    information those records do not natively own: clock time, location,
    attendees, notification policy, suspension history and an optimistic-lock
    version. It must be created and changed only through Alembic migrations.
    """

    __tablename__ = "qms_planner_schedule_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)

    schedule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audit_schedules.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    audit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audits.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_type = Column(String(32), nullable=True, index=True)
    source_id = Column(String(64), nullable=True, index=True)

    source_schedule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audit_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    occurrence_date = Column(Date, nullable=True, index=True)

    start_time = Column(Time(timezone=False), nullable=True)
    end_time = Column(Time(timezone=False), nullable=True)
    timezone_name = Column(String(64), nullable=False, default="Africa/Nairobi")
    location = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    attendee_user_ids_json = Column(Text, nullable=False, default="[]")
    external_attendees_json = Column(Text, nullable=False, default="[]")
    notify_attendees = Column(Boolean, nullable=False, default=True)

    lifecycle_status = Column(String(16), nullable=False, default="ACTIVE", index=True)
    suspension_reason = Column(Text, nullable=True)
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspended_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    version = Column(Integer, nullable=False, default=1)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    @property
    def attendee_user_ids(self) -> list[str]:
        return [str(item) for item in _json_list(self.attendee_user_ids_json) if item]

    @property
    def external_attendees(self) -> list[dict[str, Any]]:
        return [dict(item) for item in _json_list(self.external_attendees_json) if isinstance(item, dict)]

    __table_args__ = (
        UniqueConstraint("amo_id", "schedule_id", name="uq_qms_planner_metadata_schedule"),
        UniqueConstraint("amo_id", "audit_id", name="uq_qms_planner_metadata_audit"),
        UniqueConstraint("amo_id", "source_type", "source_id", name="uq_qms_planner_metadata_source"),
        UniqueConstraint(
            "amo_id",
            "source_schedule_id",
            "occurrence_date",
            name="uq_qms_planner_metadata_occurrence",
        ),
        CheckConstraint(
            "(source_type IS NULL AND source_id IS NULL) OR "
            "(source_type IS NOT NULL AND source_id IS NOT NULL)",
            name="ck_qms_planner_metadata_source_pair",
        ),
        CheckConstraint(
            "(CASE WHEN schedule_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN audit_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN source_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_qms_planner_metadata_single_subject",
        ),
        CheckConstraint(
            "source_type IS NULL OR source_type IN "
            "('CAR','CAPA','TRAINING_EVENT','MANAGEMENT_REVIEW','OTHER_QMS_COMMITMENT')",
            name="ck_qms_planner_metadata_source_type",
        ),
        CheckConstraint(
            "lifecycle_status IN ('ACTIVE','SUSPENDED','CANCELLED','COMPLETED')",
            name="ck_qms_planner_metadata_lifecycle",
        ),
        CheckConstraint("version >= 1", name="ck_qms_planner_metadata_version"),
        Index("ix_qms_planner_metadata_amo_occurrence", "amo_id", "occurrence_date"),
        Index("ix_qms_planner_metadata_amo_lifecycle", "amo_id", "lifecycle_status"),
        Index("ix_qms_planner_metadata_amo_source", "amo_id", "source_type", "source_id"),
    )
